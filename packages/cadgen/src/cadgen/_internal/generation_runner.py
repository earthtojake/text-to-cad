from __future__ import annotations

from collections.abc import Callable
import copy
import contextlib
from dataclasses import dataclass
import importlib.abc
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import threading
from typing import Iterator
from typing import Sequence

from cadgen._internal.source_hash import PythonSourceClosure
from cadgen._internal.source_hash import PythonSourceHash
from cadgen._internal.source_hash import evict_first_party_modules
from cadgen._internal.source_hash import is_first_party_source_file
from cadgen._internal.source_hash import python_source_hash
from cadgen._internal.step_scene import LoadedStepScene
from cadgen.catalog import build_scope
from cadgen.cli_logging import CliLogger
from cadgen.cli_progress import cli_progress_line
from cadgen.coordination import DRAWING_PACKAGE
from cadgen.coordination import PHASE_GENERATE
from cadgen.coordination import ProgressEvent
from cadgen.coordination import STEP_PACKAGE
from cadgen.coordination import generator_busy
from cadgen.coordination import reporting_as
from cadgen.coordination import resolve as resolve_progress
from cadgen.render import relative_to_file
from cadgen.step_export import build_build123d_step_scene

from cadgen._internal.generation_spec import EntrySpec, _display_path
from cadgen._internal import filetrace
from cadgen._internal.import_roots import import_roots


GIT_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"

def package_context(script_path: Path) -> tuple[str | None, Path | None]:
    """``(package, root)`` when ``script_path`` lives inside a package: every
    ancestor up to ``root``'s child carries an ``__init__.py``, so the module's
    dotted name is ``pkg.sub.script`` and relative imports (``from .parts import
    washer``) resolve exactly as under ``python -m pkg.sub.script``. ``(None,
    None)`` for a plain script."""
    resolved = Path(script_path).resolve()
    parts: list[str] = []
    folder = resolved.parent
    while (folder / "__init__.py").is_file():
        parts.append(folder.name)
        if folder.parent == folder:
            break
        folder = folder.parent
    if not parts:
        return None, None
    return ".".join(reversed(parts)), folder


_MODULE_LOAD_LOCK = threading.RLock()


def _seat_import_roots(search_paths: Sequence[str]) -> None:
    """Put a script's import roots at the front of sys.path, in order, even when an
    earlier load already put them on it.

    A warm process (the daemon reading declarations, the viewer) loads scripts from
    many projects, and every project names its helpers `lib`. Evicting another
    project's `lib` makes Python look `lib` up again, along sys.path: a root that an
    earlier load left AHEAD of this script's own resolves it to that project's folder.
    Nothing is taken away: a script loaded inside a build (cadgen.sources) must not
    pull its caller's folder out from under the caller's own later imports."""
    for candidate in reversed(search_paths):
        with contextlib.suppress(ValueError):
            sys.path.remove(candidate)
        sys.path.insert(0, candidate)


def _load_generator_module(script_path: Path) -> object:
    resolved_script_path = script_path.resolve()
    package, package_root = package_context(resolved_script_path)
    if package is not None:
        # Inside a package the module keeps its real dotted name and package, and
        # the package's root joins sys.path -- what `python -m pkg.script` gives.
        module_name = f"{package}.{resolved_script_path.stem}"
    else:
        module_name = (
            "_cad_tool_"
            + _display_path(resolved_script_path).replace("/", "_").replace("\\", "_").replace("-", "_").replace(".", "_")
        )
    module_spec = importlib.util.spec_from_file_location(module_name, resolved_script_path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Failed to load generator module from {_display_path(resolved_script_path)}")

    # Compile from the CURRENT source bytes, never the __pycache__ .pyc:
    # bytecode is validated by (mtime-second, size), so a same-size edit
    # rebuilt within the same second — exactly the warm-edit loop — silently
    # executes STALE code. Model scripts are small; recompiling each load
    # costs ~ms and makes what runs always be what is on disk.
    try:
        source_bytes = resolved_script_path.read_bytes()
        source_code = compile(
            source_bytes,
            str(resolved_script_path),
            "exec",
            dont_inherit=True,
        )
    except (OSError, SyntaxError) as error:
        raise RuntimeError(
            f"Failed to load generator module from {_display_path(resolved_script_path)}: {error}"
        ) from error

    # Capture the exact compiled buffer before executing any module code. The
    # file can change during module initialization, or even between compile and
    # exec; hashing its path later would associate new source with old geometry.
    from cadgen.store.closure import note_compiled_source

    note_compiled_source(resolved_script_path, source_bytes)

    module = importlib.util.module_from_spec(module_spec)
    # sys.path is exactly what `python script.py` gives: the script's own folder first,
    # then the caller's PYTHONPATH (already on the path in a transient process; applied
    # per job by the daemon worker). Seeded for the WHOLE build, so an import inside the
    # model function or a helper it calls resolves like one at module top. cadgen adds no
    # root of its own and infers none from directory names (see import_roots.py).
    search_paths = import_roots(resolved_script_path)
    if package_root is not None:
        search_paths = [*search_paths, str(package_root)]

    from cadgen._internal.source_hash import evict_foreign_first_party_modules
    from cadgen._internal.source_hash import record_first_party_execution
    from cadgen.authoring import record_import_closure

    # One load at a time per process: the daemon's relay threads read several
    # scripts' declarations at once, and sys.path and sys.modules are shared.
    with _MODULE_LOAD_LOCK:
        _seat_import_roots(search_paths)
        # Another project's modules must not be importable-by-cache here: every
        # cad-project shares the same top-level names (`lib`, sibling models), so a
        # warm process that built project A would hand project B a stale `lib`
        # bound to A's directory. Path-aware eviction at the ONE load choke point
        # makes "which project's lib" unambiguous for every caller.
        evict_foreign_first_party_modules(search_paths)
        if package is not None:
            # The parent packages must exist for a relative import to resolve.
            importlib.import_module(package)
            module.__package__ = package
        sys.modules[module_name] = module
        # What the module top executes is what its declarations were evaluated from;
        # the metadata reader reuses this load only while every one of those files
        # still holds the bytes it had now (cadgen.authoring.import_closure_current).
        with record_first_party_execution() as executed_files:
            exec(source_code, module.__dict__)
        record_import_closure(resolved_script_path, executed_files)

    return module


class _SourceOnlyLoader(importlib.machinery.SourceFileLoader):
    """Compiles the bytes on disk, never a ``__pycache__`` ``.pyc``, and hands
    those exact bytes to the build's execution hashes."""

    def get_code(self, fullname: str):  # noqa: ANN201 - importlib protocol
        path = self.get_filename(fullname)
        data = self.get_data(path)
        from cadgen.store.closure import note_compiled_source

        note_compiled_source(path, data)
        return compile(data, path, "exec", dont_inherit=True)


class _FirstPartyFromSource(importlib.abc.MetaPathFinder):
    """Loads every first-party module through :class:`_SourceOnlyLoader`.

    It asks the path finder itself, never the rest of ``sys.meta_path``: two
    finders that each delegate to the other would hand one lookup back and
    forth forever. Anything that is not first-party source is not answered
    here, so every other finder sees it as if this one were absent."""

    def find_spec(self, fullname, path, target=None):  # noqa: ANN001, ANN201 - importlib protocol
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if (spec is None or type(spec.loader) is not importlib.machinery.SourceFileLoader or not spec.origin
                or not is_first_party_source_file(Path(spec.origin).resolve())):
            return None
        spec.loader = _SourceOnlyLoader(spec.loader.name, spec.loader.path)
        return spec


@contextlib.contextmanager
def _first_party_from_source():
    """Run model code from the source bytes on disk: no ``.pyc`` read for a
    first-party module, and none written for anything imported here.

    CPython accepts a ``.pyc`` by (whole-second mtime, size), so two same-length
    edits inside one second -- an agent's edit loop -- run STALE bytecode left
    by any tool, while the closure hashes the new source: silently wrong output
    recorded as current. Model code never reads bytecode here, so nothing can
    go stale; model libraries are small, and recompiling them costs the
    milliseconds the entry script already pays (it is compiled from bytes for
    the same reason)."""
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    finder = _FirstPartyFromSource()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous
        with contextlib.suppress(ValueError):
            sys.meta_path.remove(finder)


@dataclass(frozen=True)
class _DeclaredKinematics:
    """What the decorator declared for the build: kinematics, named materials,
    and the animation clips (baked at publication). None of these declarations
    moves geometry or changes STEP bytes."""

    block: dict | None
    materials: dict | None = None
    animation: dict | None = None


def _resolve_declared_kinematics(defn: object) -> _DeclaredKinematics:
    """The model's kinematics block.

    The block comes validated from the decoration-time normalizer; axis refs
    resolve against real geometry later in the tree build."""
    kinematics_def = getattr(defn, "kinematics", None)
    block = dict(kinematics_def.block) if kinematics_def is not None else None
    materials = copy.deepcopy(getattr(defn, "materials", None))
    clips = getattr(defn, "animation", None)
    return _DeclaredKinematics(block=block, materials=materials, animation=dict(clips) if clips else None)


def _normalize_step_payload(
    result: object,
    *,
    script_path: Path,
) -> dict[str, object]:
    """A @step returns a build123d shape and nothing else.

    The dict envelope (``{"shape": ..., "stl": ..., "mesh_tolerance": ...}``) is
    gone: exports are declared with ``@stl``/``@threemf``/``@glb`` stacked on the
    model and tolerances with ``@step(mesh_tolerance=...)``. A dict here is a hard
    error that names those decorators; the static parser refuses the same shape
    before a build starts.
    """
    from build123d import Shape as Build123dShape

    if isinstance(result, Build123dShape):
        return {"shape": result}
    if isinstance(result, dict):
        raise TypeError(
            f"{_display_path(script_path)} @step returned a dict; a model returns a "
            "build123d shape and nothing else. Declare mesh exports with "
            "@stl/@threemf/@glb stacked on the model and tolerances with "
            "@step(mesh_tolerance=..., mesh_angular_tolerance=...)."
        )
    raise TypeError(
        f"{_display_path(script_path)} @step must return a build123d Shape, got "
        f"{type(result).__name__}"
    )


def _mark_scene_step_payload(
    scene: LoadedStepScene,
    *,
    payload_kind: str,
) -> LoadedStepScene:
    if isinstance(scene, LoadedStepScene):
        scene.step_payload_kind = payload_kind
    return scene


def _write_shape_step_payload(
    payload: dict[str, object],
    *,
    output_path: Path,
    script_path: Path,
    logger: CliLogger,
    defer_reference_scene: bool = False,
) -> LoadedStepScene:
    shape = payload.get("shape")
    from build123d import Shape as Build123dShape

    if not isinstance(shape, Build123dShape):
        raise TypeError(
            f"{_display_path(script_path)} @step must return a build123d Shape, "
            f"got {type(shape).__name__}"
        )
    # A @step run builds the render scene in memory and does NOT write a text STEP — STEP is
    # written on demand from scene.source_compound (a model-script run, or the
    # Viewer's Save-dialog export). The scene is built straight from the XCAF doc, never
    # via a STEP round-trip.
    source_identity = python_source_hash(script_path)
    scene = None
    if defer_reference_scene:
        from cadgen.store._references import source_scene

        scene = source_scene(shape, output_path)
    if scene is None:
        scene = build_build123d_step_scene(
            shape,
            output_path,
            source_kind="python",
            source_hash=source_identity.source_hash,
        )
    _mark_scene_python_backed(scene, source_identity=source_identity, source_path=script_path)
    _mark_scene_step_payload(scene, payload_kind="shape")
    # Stash the compound: the tree build introspects its located
    # children (occurrence transforms + dedup), and the STEP export serializes it.
    scene.source_compound = shape
    logger.debug(f"built render scene (no STEP written): {_display_path(output_path)}")
    return scene


def _mark_scene_python_backed(
    scene: LoadedStepScene,
    *,
    source_identity: PythonSourceHash,
    source_path: Path,
) -> LoadedStepScene:
    if not isinstance(scene, LoadedStepScene):
        return scene
    scene.source_kind = "python"
    scene.source_hash = source_identity.source_hash
    scene.source_path = relative_to_file(source_path, scene.step_path)
    return scene


def _write_drawing_record(
    spec: EntrySpec, output_path: Path, *, source_closure, child_trees
) -> None:
    """The drawing's model record: ``tree: null``, its ``.dxf`` as the one output,
    children pinned from the body's calls. Published under the same rule as a
    @step record (never replace a current record with a stale one)."""
    import hashlib

    from cadgen.store.publish import decide
    from cadgen.store.records import note_output, write_record

    from cadgen.store.index import model_ref

    model_path = model_ref(spec.script_path, getattr(spec.generator_metadata, "entry_function", None))
    written = Path(output_path).resolve()
    closure_files = list(source_closure.files)
    closure_hash = str(source_closure.closure_hash)
    record = {
        "entryKind": "drawing",
        "sourceKind": "python",
        "tree": None,
        "closure": {
            "hash": closure_hash,
            "files": closure_files,
            "shas": dict(getattr(source_closure, "file_hashes", None) or {}),
            "names": {rel: list(names) for rel, names in (getattr(source_closure, "names", None) or {}).items()},
            "wholes": dict(getattr(source_closure, "wholes", None) or {}),
            "own": {rel: list(names) for rel, names in (getattr(source_closure, "own", None) or {}).items()},
            "static": False,
        },
        "constants": dict(getattr(source_closure, "constants", None) or {}),
        "children": [{"model": str(child), "tree": tree} for child, tree in child_trees],
        "outputs": {str(written): {"sha256": hashlib.sha256(written.read_bytes()).hexdigest()}},
        "stepHash": "",
    }
    from cadgen._internal.build_timing import record_fields

    record.update(record_fields())
    decision = decide(model_path, ran_closure_hash=closure_hash, ran_files=closure_files,
                      ran_names=record["closure"]["names"], ran_shas=record["closure"]["shas"],
                      ran_wholes=record["closure"]["wholes"], ran_own=record["closure"]["own"])
    if not decision.publish_outputs:
        return
    write_record(model_path, record)
    note_output(written, model_path)


def _write_dxf_payload(
    result: object,
    *,
    output_path: Path,
    script_path: Path,
    logger: CliLogger,
) -> None:
    """Serialize a ``@dxf`` return value and write it.

    The drawing's bytes are engineered to be a pure function of its geometry
    (:mod:`cadgen._internal.dxf_emit`), so nothing about this process — heap
    layout, hash seed, wall clock — reaches the file. Validation runs against the
    document those exact bytes came from, before anything is written.
    """
    from cadgen._internal.dxf_emit import emit_dxf, write_dxf
    from cadgen.drawing_checks import raise_on_error_findings, validate_drawing_document

    label = _display_path(script_path)
    payload, document = emit_dxf(result, label=label)
    if document is not None:
        findings = validate_drawing_document(document)
        for finding in findings:
            if finding.severity != "error":
                logger.info(f"{label} {finding.render()}")
        raise_on_error_findings(findings, label=label)
    write_dxf(payload, output_path)
    logger.debug(f"wrote DXF: {_display_path(output_path)}")


def run_script_generator(
    spec: EntrySpec,
    model_format: str,
    *,
    logger: CliLogger | None = None,
    force: bool = False,
    progress: object | None = None,
    intent: str = "write",
    model_prints_to_stdout: bool = False,
    _defer_reference_scene: bool = False,
) -> LoadedStepScene | None:
    """Run a model script's decorated entry (``@step``/``@dxf``) and return its scene.

    ``intent`` says whether this run will rewrite the model's outputs (``"write"``, the
    default) or merely occupy its generator (``"generate"`` -- an export, a topology
    extraction, an interference check). See :func:`_track_spec_generation`: getting this
    wrong makes an export look like a build to the CAD Viewer.

    ``model_prints_to_stdout`` decides where the MODEL's own ``print()`` output
    lands. The CLI contract is "stdout carries the result; stderr carries
    progress" — and when a generator runs as a subroutine of another verb
    (``inspect``, ``snapshot``, a mesh export), its prints ahead of the verb's
    JSON broke every ``| jq`` pipeline. So the default routes them to stderr
    with the rest of the progress; only the direct build flows (``cadgen step
    build``, ``python model.py``), where the model's stdout is the user's own
    channel, pass True.

    Closure capture is deterministic in every process shape: first-party modules
    are evicted from ``sys.modules`` BEFORE the generator loads (so its full
    dependency closure is freshly imported on every run — warm worker, multi-target
    CLI loop, or cold process alike, and regardless of earlier failed builds), and
    every first-party file EXECUTED during the run is recorded via the ``exec``
    audit event (so dependencies survive even when a generator unloads modules
    from ``sys.modules`` mid-run). Only first-party ``.py`` modules are evicted
    (see :func:`repo_local_loaded_modules`); the running runtime (cadgen, the CLI
    launcher) and C extensions / site-packages (numpy, OCP, build123d) are never
    touched — they cannot reload, must stay warm, and are not freshness inputs.
    """
    logger = logger or CliLogger("cad")
    if model_format not in {"step", "dxf"}:
        raise RuntimeError(f"Unsupported model format: {model_format}")
    if spec.script_path is None or spec.generator_metadata is None:
        raise ValueError(f"{spec.source_ref} is not a generated Python CAD source")
    # A WRITER arrives with the BuildRun that already owns this model's status record and
    # its progress line. An EXPORT arrives with neither, and until the generator run
    # carried a reporter, `cad export` ran the same multi-minute model build a write runs
    # and said nothing on any surface. So the generator run becomes the reporter when
    # nobody above us is one.
    owns_reporting = progress is None
    from cadgen.authoring import settle_child_builds

    # The normal build owns these handles through source publication and save.
    # A standalone generator caller still settles its children before returning.
    with settle_child_builds(only_if_unowned=True), _generator_progress_line(spec, logger=logger, active=owns_reporting) as sink:
        with _track_spec_generation(
            spec, model_format, intent=intent, sink=sink
        ) as generator_run:
            active = generator_run if owns_reporting else progress
            resolve_progress(active).phase(PHASE_GENERATE)
            redirect = (
                contextlib.nullcontext()
                if model_prints_to_stdout
                else contextlib.redirect_stdout(sys.stderr)
            )
            with redirect:
                return _run_script_generator_inner(
                    spec,
                    model_format,
                    logger=logger,
                    force=force,
                    progress=active,
                    _defer_reference_scene=_defer_reference_scene,
                )


@contextlib.contextmanager
def _generator_progress_line(
    spec: EntrySpec, *, logger: CliLogger | None, active: bool
) -> Iterator[Callable[[ProgressEvent], None] | None]:
    """The terminal line for a generator run that owns its own reporting.

    Inactive when a build above us already paints one — two painters on one tty interleave
    into nonsense — and when there is no logger to paint through."""
    if not active:
        yield None
        return
    with cli_progress_line(
        spec.source_ref, logger=logger or CliLogger("cad"), fallback="Building..."
    ) as sink:
        yield sink


def _run_script_generator_inner(
    spec: EntrySpec,
    model_format: str,
    *,
    logger: CliLogger,
    force: bool = False,
    progress: object | None = None,
    _defer_reference_scene: bool = False,
) -> LoadedStepScene | None:
    # Worker-pool admission owns memory policy; this inner call adds no second
    # guard. The pool reports an OS-killed worker with its exit status.
    return _run_script_generator_body(
        spec, model_format, logger=logger, force=force, progress=progress,
        _defer_reference_scene=_defer_reference_scene,
    )


def _run_script_generator_body(
    spec: EntrySpec,
    model_format: str,
    *,
    logger: CliLogger,
    force: bool = False,
    progress: object | None = None,
    _defer_reference_scene: bool = False,
) -> LoadedStepScene | None:
    # Order-stable shape de-duplication (see determinism.py): a re-executed model
    # script should produce the SAME geometry it produced last time, and component
    # identity is its bytes. This has to be in force before the generator's first
    # kernel call, not merely before the tree write.
    from cadgen._internal import determinism

    determinism.install()
    generated_scene: LoadedStepScene | None = None
    # Deterministic closure capture: start from a clean first-party module space, so
    # every first-party file the generator loads and runs executes inside the window
    # and is hashed as it runs (ExecutionHashes), from the source it was compiled from
    # (_first_party_from_source). Alongside it, the trace: every file the build opened,
    # whoever opened it, and the folders its code listed.
    evict_first_party_modules()
    from cadgen.store.closure import ExecutionHashes

    with (
        filetrace.capture() as trace,
        _first_party_from_source(),
        ExecutionHashes() as executed_hashes,
    ):
        with logger.timed(f"load generator {spec.source_ref}"):
            module = _load_generator_module(spec.script_path)
        # `model_format` is the DISPATCH kind ("step"/"dxf" decides which payload
        # contract applies below); the attribute looked up is the decorated entry
        # — the module is imported under a loader name, never __main__, so its
        # `__main__` block does not run and this call is the one execution. The
        # call happens inside `building()`, which is what makes the decorated
        # name run its body (and lets the children it calls compose) instead of
        # starting a build of its own.
        metadata = spec.generator_metadata
        entry_name = getattr(metadata, "entry_function", None) if metadata is not None else None
        if not entry_name:
            raise RuntimeError(f"{_display_path(spec.script_path)} declares no decorated model entry function")
        generator = getattr(module, entry_name, None)
        if not callable(generator):
            raise RuntimeError(f"{_display_path(spec.script_path)} does not define callable {entry_name}()")
        # Bind the run as the ambient reporter for the generator's own code: the entry
        # function takes no arguments and so cannot be handed the run,
        # and without this the longest phase of most builds reports nothing at all. Silent
        # generators are unaffected -- nothing reads the binding unless they ask for it.
        from cadgen._internal.build_timing import model_body
        from cadgen.authoring import building
        # The execution window includes imports during module initialization.
        # The loader already recorded the script's exact compiled source bytes;
        # the audit hook records other first-party modules as they execute.
        with (
            logger.timed(f"run {model_format} model {spec.source_ref}"),
            reporting_as(progress),
            building(spec.script_path, entry_name) as frame,
        ):
            # The model's own code: what a build's time line calls "model code", and
            # all that --profile profiles (cadgen._internal.build_timing).
            with model_body(spec.script_path.parent):
                raw_payload = generator()

    # A model's own outputs are never its inputs: reading one back reads the
    # previous run, so a read the trace saw is dropped here, and a folder its
    # code listed is hashed without them.
    from cadgen.store.closure import build_closure

    own_outputs = _own_outputs(spec, model_format, entry_name)
    read_files, listed = trace.inputs(outputs=own_outputs)
    # The closure a record carries: the script + its static closure (stopping at
    # child models — a result edge is tracked by pin, not by file), every file
    # that executed (hashed AT execution), the data files and folders the run
    # read, as it read them, and the environment variables its code read. Paths
    # are relative to the GENERATOR's folder, never
    # the output's: `out=` routes the output anywhere, and basing the closure
    # there would hash the same source differently depending on where its
    # document is written. Every child the body called, with the tree it resolved
    # to: this waits for any child job the body never forced (called and
    # discarded), whose result is still this build's dependency.
    child_trees = frame.child_trees()
    store_closure = build_closure(
        spec.script_path,
        executed=executed_hashes.hashes,
        inputs=read_files,
        listings=listed,
        outputs=own_outputs,
        children=[child for child, _tree in child_trees],
        sources=executed_hashes.sources,
        environment=trace.environment,
    )
    source_closure = PythonSourceClosure(
        closure_hash=store_closure.hash,
        files=store_closure.files,
        constants=store_closure.constants,
        file_hashes=store_closure.shas,
        names=store_closure.names,
        wholes=store_closure.wholes,
        own=store_closure.own,
    )
    if model_format == "step":
        payload = _normalize_step_payload(raw_payload, script_path=spec.script_path)
        if spec.step_path is None:
            raise RuntimeError(f"{spec.source_ref} has no configured STEP output")
        # Kinematics (validated at decoration) rides the scene into the sidecar.
        declared = _resolve_declared_kinematics(getattr(generator, "__cadgen_model__", None))
        generated_scene = _write_shape_step_payload(
            payload,
            output_path=spec.step_path,
            script_path=spec.script_path,
            logger=logger,
            defer_reference_scene=_defer_reference_scene,
        )
        if declared.block:
            generated_scene.kinematics = declared.block
        generated_scene.materials = declared.materials
        generated_scene.animation = declared.animation
        # Children pinned by the body's calls — recorded from the CALLS, never
        # derived from the tree's links (a modified child is still a dependency).
        generated_scene.store_children = [
            {"model": str(child), "tree": tree} for child, tree in child_trees
        ]
        # Runtime handles never enter objects/records. Source-ready children may
        # still owe their own files; the parent drains these after its preview.
        generated_scene.wait_child_outputs = frame.wait_children
    elif model_format == "dxf":
        if spec.dxf_path is None:
            raise RuntimeError(f"{spec.source_ref} has no configured DXF output")
        # The product IS the .dxf: the run always writes it — the sibling by
        # default, `-o` renames — and the viewer parses that file directly.
        output_path = spec.dxf_path
        frame.wait_children()
        _write_dxf_payload(
            raw_payload, output_path=output_path, script_path=spec.script_path, logger=logger
        )
        # A drawing is a model in the graph (STORE.md §3): the same record, gate and
        # pins as a @step model, with the .dxf as its output and NO tree (gate
        # clause 4 is vacuous). The children its body composed -- a flat pattern of
        # `bracket()` -- are pinned from the calls, so a child's new geometry makes
        # the drawing stale like any parent.
        _write_drawing_record(spec, output_path, source_closure=source_closure, child_trees=child_trees)
    if generated_scene is not None and source_closure is not None:
        generated_scene.source_closure_hash = source_closure.closure_hash
        generated_scene.source_closure_files = source_closure.files
        generated_scene.source_closure_file_hashes = dict(getattr(source_closure, "file_hashes", None) or {})
        generated_scene.source_closure_names = dict(getattr(source_closure, "names", None) or {})
        generated_scene.source_closure_wholes = dict(getattr(source_closure, "wholes", None) or {})
        generated_scene.source_closure_own = dict(getattr(source_closure, "own", None) or {})
        generated_scene.source_closure_constants = dict(source_closure.constants)
    if model_format == "dxf":
        written = spec.dxf_path
        if written is not None and not written.exists():
            raise RuntimeError(
                f"{_display_path(spec.script_path)} did not write {_display_path(written)}"
            )
    return generated_scene if model_format == "step" else None


def _own_outputs(spec: EntrySpec, model_format: str, entry_name: str) -> list[Path]:
    """Every file a build of this model publishes beside its source: the outputs
    its decorators declare and, beside a written STEP, its sidecar -- whether or
    not this build writes one, since an annotation refresh can add it later."""
    from cadgen.metadata import declared_output_paths

    outputs = declared_output_paths(spec.script_path, function=entry_name)
    if model_format == "step" and spec.step_path is not None and spec.step_output:
        from cadgen._internal.source_sidecar import source_sidecar_path

        outputs.append(source_sidecar_path(spec.step_path))
    return outputs


def _is_git_lfs_pointer(step_path: Path) -> bool:
    try:
        with step_path.open("rb") as handle:
            return handle.read(len(GIT_LFS_POINTER_PREFIX)) == GIT_LFS_POINTER_PREFIX
    except OSError:
        return False


def _ensure_step_ready(step_path: Path) -> None:
    if not step_path.exists():
        raise FileNotFoundError(f"STEP file is missing: {_display_path(step_path)}")
    if _is_git_lfs_pointer(step_path):
        raise RuntimeError(
            f"{_display_path(step_path)} is a Git LFS pointer, not the real STEP file.\n"
            "Fetch Git LFS objects before generating CAD artifacts.\n"
            "For Vercel Git deployments, enable Git LFS in Project Settings > Git and redeploy."
        )


@dataclass(frozen=True)
class _ArtifactJob:
    name: str
    run: Callable[[], object]


def _run_artifact_jobs(
    jobs: Sequence[_ArtifactJob],
    *,
    logger: CliLogger | None = None,
) -> dict[str, object]:
    # Always supply a logger: `logger.timed` spans below this boundary are
    # born orphaned whenever a caller drops the logger (the STEP-export spans
    # were invisible for exactly that reason). A default non-verbose CliLogger
    # gives every span a sink and lets verbosity alone decide what prints.
    logger = logger or CliLogger("cad")
    results: dict[str, object] = {}
    for job in jobs:
        with logger.timed(f"write {job.name}"):
            results[job.name] = job.run()
    return results


def _spec_output_dir(spec: EntrySpec, model_format: str) -> str | None:
    """The progress SCOPE for this spec's generator, if it has one.

    Model-path-keyed, NOT the content-keyed result: a rebuild changes the content
    hash, so a run's progress must be findable under an identity that is known
    before any geometry is."""
    if model_format == "step" and spec.step_path is not None:
        return build_scope(spec.entry_path)
    if model_format == "dxf" and spec.script_path is not None:
        return build_scope(spec.script_path)
    return None


def _track_spec_generation(
    spec: EntrySpec,
    model_format: str,
    *,
    intent: str = "write",
    sink: Callable[[ProgressEvent], None] | None = None,
) -> contextlib.AbstractContextManager[object]:
    """Report a generator run under the model's progress scope.

    ``intent`` picks the RECORD. A run that will rewrite the model's outputs already has
    its BuildRun from ``artifact_build`` and reports through that, so this yields None. A
    run that merely OCCUPIES the generator -- an export, an on-demand topology extraction,
    an interference check -- reports through ``generator_busy`` instead, whose record is a
    separate file: reporting it as a build made a fully-current model show `generating`
    with an empty bar for the whole length of an export.

    Nothing here excludes anything. Two runs of one model proceed concurrently and the
    publish rule decides whose result the record points at (STORE.md §7).
    """
    scope = _spec_output_dir(spec, model_format)
    if scope is None or intent != "generate":
        return contextlib.nullcontext()
    # The kind decides which phase set the run reports over, so a drawing generator
    # counts its own phases rather than a STEP package's.
    kind = DRAWING_PACKAGE if model_format == "dxf" else STEP_PACKAGE
    return generator_busy(kind, scope, sink=sink)
