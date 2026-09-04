from __future__ import annotations

from collections.abc import Callable
import contextlib
from dataclasses import dataclass
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
from typing import Iterator
from typing import Sequence

from cadgen._internal.source_hash import PythonSourceClosure
from cadgen._internal.source_hash import PythonSourceHash
from cadgen._internal.source_hash import capture_runtime_closure
from cadgen._internal.source_hash import evict_first_party_modules
from cadgen._internal.source_hash import python_source_hash
from cadgen._internal.source_hash import record_discovered_inputs
from cadgen._internal.source_hash import record_first_party_execution
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


GIT_LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1\n"

def _load_generator_module(script_path: Path) -> object:
    resolved_script_path = script_path.resolve()
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
        source_code = compile(
            resolved_script_path.read_bytes(),
            str(resolved_script_path),
            "exec",
            dont_inherit=True,
        )
    except (OSError, SyntaxError) as error:
        raise RuntimeError(
            f"Failed to load generator module from {_display_path(resolved_script_path)}: {error}"
        ) from error

    module = importlib.util.module_from_spec(module_spec)
    original_sys_path = list(sys.path)
    # Seed sys.path so the generator's module-top imports (its sibling/shared packages such as
    # robot_common / STEP) resolve. Derive everything from the generator script's OWN location —
    # its folder, plus any ancestor that is a package root (contains a STEP/ or robot_common/
    # package) — so resolution is independent of the process working directory. Deliberately NOT
    # seeding the repo root or skills/cad/scripts: a generator must not depend on the repository's
    # skills/ being importable (AGENTS.md skill isolation).
    search_paths = _generator_search_paths(resolved_script_path)
    for candidate in reversed(search_paths):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

    # Another project's modules must not be importable-by-cache here: every
    # cad-project shares the same top-level names (`lib`, sibling models), so a
    # warm process that built project A would hand project B a stale `lib`
    # bound to A's directory. Path-aware eviction at the ONE load choke point
    # makes "which project's lib" unambiguous for every caller.
    from cadgen._internal.source_hash import evict_foreign_first_party_modules

    evict_foreign_first_party_modules(search_paths)
    try:
        sys.modules[module_name] = module
        exec(source_code, module.__dict__)
    finally:
        sys.path[:] = original_sys_path

    return module


def _generator_search_paths(resolved_script_path: Path) -> list[str]:
    """The import roots a generator's module body may rely on: its own folder,
    plus any ancestor that is a package root (holds a ``STEP/`` or
    ``robot_common/`` package). Seeded onto ``sys.path`` for the module body
    ONLY (see ``_load_generator_module``); named again by the teaching error a
    function-level import of one of these roots' modules raises."""
    search_paths = [str(resolved_script_path.parent)]
    for parent in resolved_script_path.parents:
        if (
            (parent / "STEP" / "__init__.py").is_file()
            or (parent / "robot_common" / "__init__.py").is_file()
        ):
            search_paths.append(str(parent))
    return search_paths


@contextlib.contextmanager
def _without_bytecode_writes():
    """Write no ``.pyc`` for anything imported inside this window.

    The purge below can only delete what it is allowed to delete. On POSIX an
    unlink succeeds whatever holds the file, so the purge always lands; on
    Windows a ``__pycache__`` entry held open by a scanner, an editor, or a
    sibling interpreter refuses deletion, and the purge swallows it
    (``ignore_errors=True``). What survives is a stale ``.pyc`` that CPython
    will then accept, because it validates by (whole-second mtime, size) -- two
    same-length edits inside one second is exactly an agent's edit loop. The
    result is a build against code that is not on disk: silently wrong output,
    which is worse than any crash.

    So the guarantee stops resting on a delete succeeding. Nothing cadgen
    imports for a model writes bytecode at all, which means there is nothing to
    go stale and nothing to validate wrongly. Model libraries are small and this
    window runs once per job, so recompiling from source costs the milliseconds
    the entry script already pays (it is compiled from bytes at :58-63 for this
    same reason).
    """
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous


def _purge_stale_bytecode(script_path: Path) -> None:
    """Drop ``__pycache__`` beside the generator and its static import closure, once per job.

    CPython validates a ``.pyc`` by (whole-second mtime, size): two same-length
    edits inside one second load STALE BYTECODE on re-import -- exactly the
    cadence of an agent-driven edit loop. The job boundary is the one place the
    first-party module space is rebuilt, so it is the one place this belongs
    (the scope layer used to do it on every miss, mid-job, alongside an eviction
    that broke lazy imports).

    Best-effort by design, and no longer the guarantee: ``ignore_errors=True``
    hides a Windows refusal to delete an open ``.pyc``, so correctness rests on
    :func:`_without_bytecode_writes` instead -- cadgen writes no bytecode for
    model code, so after this sweep there is nothing left to go stale. This
    clears what OTHER tools left behind."""
    import shutil

    from cadgen._internal import scope_capture

    resolved = script_path.resolve()
    parents = {resolved.parent}
    for root in _generator_search_paths(resolved):
        try:
            parents |= {f.parent for f in scope_capture.static_import_closure(resolved, root)}
        except Exception:  # noqa: BLE001 - a closure that cannot be traced still gets the script's own folder purged
            continue
    for parent in parents:
        shutil.rmtree(parent / "__pycache__", ignore_errors=True)


def _sibling_module_root(name: str | None, script_path: Path) -> str | None:
    """The generator search root that WOULD have satisfied ``import name``, or
    None when the missing module is not a first-party sibling at all."""
    if not name:
        return None
    top = name.partition(".")[0]
    for root in _generator_search_paths(script_path.resolve()):
        base = Path(root) / top
        if base.is_dir() or base.with_suffix(".py").is_file():
            return root
    return None


def _teach_function_level_import(error: ModuleNotFoundError, script_path: Path) -> None:
    """Turn ``ModuleNotFoundError: No module named 'lib'`` raised INSIDE the model
    function into the rule it broke.

    The loader seeds the generator's folder onto ``sys.path`` for the module
    body and restores it afterwards, so a ``from lib import fasteners`` at the
    top of a helper module works while the same line inside a function, run
    later by the pipeline, does not -- and the bare error names neither the
    rule nor the fix. Only a module that a search root would have satisfied is
    re-raised this way; a genuinely missing third-party package keeps its own
    error."""
    root = _sibling_module_root(getattr(error, "name", None), script_path)
    if root is None:
        return
    raise RuntimeError(
        f"{_display_path(script_path)}: `import {error.name}` ran inside the model function, "
        f"where {_display_path(Path(root))} is no longer on sys.path. The pipeline seeds the "
        "generator's folder (and its package roots) onto sys.path only while the module body "
        "loads, then restores it before calling the model. Move the import to module top level "
        "-- in the model script and in every helper module it imports."
    ) from error


@dataclass(frozen=True)
class _DeclaredKinematics:
    """What the decorator declared, resolved for the build: the kinematics
    block, the bake pose, the animation module's TEXT, and the files those
    declarations were read from (``inputs``)."""

    block: dict | None
    bake_pose: dict | None
    animation_source: str | None
    inputs: tuple[Path, ...]


def _resolve_declared_kinematics(defn: object, *, script_path: Path) -> _DeclaredKinematics:
    """The model's kinematics block, bake pose, and animation module TEXT.

    The block comes validated from the decoration-time normalizer; axis refs
    resolve against real geometry later in the package build. The animation
    path is an authoring-time input only: its text is read HERE and copied
    into the sidecar, so no generated file ever references the source tree.

    The animation file is also a FRESHNESS INPUT, returned in ``inputs`` so the
    caller folds it into the source closure exactly like a vendor STEP read
    through ``cadgen.read_step``. The sidecar carries a COPY of the module's
    text, and the documented way to ship an edited clip is to re-run the
    model — which only works if the edit makes the model stale. Without this
    the ``.anim.js`` sat outside the gate: the model stayed ``current``, the
    stale copy shipped, and the viewer kept playing the old clip through any
    number of reloads."""
    kinematics_def = getattr(defn, "kinematics", None)
    block = dict(kinematics_def.block) if kinematics_def is not None else None
    bake_pose = dict(getattr(defn, "bake_pose", None) or {}) or None
    animation = getattr(defn, "animation", None)
    animation_source: str | None = None
    inputs: list[Path] = []
    if animation:
        candidate = Path(animation)
        resolved = (candidate if candidate.is_absolute() else script_path.parent / candidate).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(
                f"{_display_path(script_path)} animation module not found: {animation} "
                "(animation= names a .js file beside the script; the declared "
                "file must exist — there is no convention discovery)"
            )
        animation_source = resolved.read_text(encoding="utf-8")
        inputs.append(resolved)
    return _DeclaredKinematics(
        block=block, bake_pose=bake_pose, animation_source=animation_source, inputs=tuple(inputs)
    )


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


def _shape_payload_entry_kind(shape: object, *, fallback: str) -> str:
    if fallback not in {"part", "assembly"}:
        raise RuntimeError(f"Unsupported generated STEP kind: {fallback}")
    if (
        fallback == "assembly"
        or _shape_has_explicit_children(shape)
        or _shape_is_multi_child_compound(shape)
    ):
        return "assembly"
    return "part"


def _shape_has_explicit_children(shape: object) -> bool:
    try:
        from build123d import Shape as Build123dShape
    except ImportError:  # build123d is optional for this heuristic; no build123d means no explicit children
        return False
    if not isinstance(shape, Build123dShape):
        return False
    try:
        return bool(tuple(getattr(shape, "children", ()) or ()))
    except TypeError:
        return False


def _shape_is_multi_child_compound(shape: object) -> bool:
    try:
        from OCP.TopAbs import TopAbs_COMPOUND
        from OCP.TopoDS import TopoDS_Iterator
        from build123d import Shape as Build123dShape
    except ImportError:  # build123d/OCP optional; unavailable means the compound heuristic cannot run
        return False
    if not isinstance(shape, Build123dShape):
        return False
    wrapped = getattr(shape, "wrapped", None)
    if wrapped is None:
        return False
    try:
        if wrapped.ShapeType() != TopAbs_COMPOUND:
            return False
    except Exception:  # noqa: BLE001 - OCP ShapeType() can raise on unexpected wrapper contents
        return False
    iterator = TopoDS_Iterator(wrapped)
    count = 0
    while iterator.More():
        count += 1
        if count > 1:
            return True
        iterator.Next()
    return False


def _mark_scene_step_payload(
    scene: LoadedStepScene,
    *,
    entry_kind: str,
    payload_kind: str,
) -> LoadedStepScene:
    if isinstance(scene, LoadedStepScene):
        scene.text_to_cad_entry_kind = entry_kind
        scene.step_payload_kind = payload_kind
    return scene


def _scene_entry_kind(scene: LoadedStepScene | None) -> str | None:
    if scene is None:
        return None
    entry_kind = str(getattr(scene, "text_to_cad_entry_kind", "") or "").strip().lower()
    return entry_kind if entry_kind in {"part", "assembly"} else None


def _effective_step_spec_for_scene(spec: EntrySpec, scene: LoadedStepScene | None) -> EntrySpec:
    entry_kind = _scene_entry_kind(scene)
    if entry_kind is None or entry_kind == spec.kind:
        return spec
    return replace(spec, kind=entry_kind)


def _write_shape_step_payload(
    payload: dict[str, object],
    *,
    output_path: Path,
    script_path: Path,
    logger: CliLogger,
    entry_kind: str,
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
    scene = build_build123d_step_scene(
        shape,
        output_path,
        source_kind="python",
        source_hash=source_identity.source_hash,
    )
    _mark_scene_python_backed(scene, source_identity=source_identity, source_path=script_path)
    _mark_scene_step_payload(scene, entry_kind=entry_kind, payload_kind="shape")
    # Stash the pre-bake compound: the component-package emit job introspects its located
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

    model_path = Path(spec.script_path).resolve()
    written = Path(output_path).resolve()
    closure_files = list(source_closure.files)
    closure_hash = str(source_closure.closure_hash)
    record = {
        "entryKind": "drawing",
        "sourceKind": "python",
        "tree": None,
        "closure": {"hash": closure_hash, "files": closure_files, "static": False},
        "constants": dict(getattr(source_closure, "constants", None) or {}),
        "children": [{"model": str(child), "tree": tree} for child, tree in child_trees],
        "outputs": {str(written): {"sha256": hashlib.sha256(written.read_bytes()).hexdigest()}},
        "stepHash": "",
    }
    decision = decide(model_path, ran_closure_hash=closure_hash, ran_files=closure_files)
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
    with _generator_progress_line(spec, logger=logger, active=owns_reporting) as sink:
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
) -> LoadedStepScene | None:
    # No memory guard: unlimited memory is the operating assumption (STORE.md §9). A
    # build that the OS kills is reported by the pool as a dead worker, with its exit.
    return _run_script_generator_body(
        spec, model_format, logger=logger, force=force, progress=progress
    )


def _run_script_generator_body(
    spec: EntrySpec,
    model_format: str,
    *,
    logger: CliLogger,
    force: bool = False,
    progress: object | None = None,
) -> LoadedStepScene | None:
    # Kernel-op memoization (design/incremental-generation.md): installed here so
    # every generator run — cold CLI or warm daemon worker — re-executes the model
    # script against memoized build123d choke points. The cache lives in
    # cadgen._internal.op_memo, which module eviction never touches, so a warm
    # worker keeps it across requests. CADGEN_OP_MEMO=0 disables.
    from cadgen._internal import op_memo

    op_memo.install()
    # Order-stable shape de-duplication (see determinism.py). Installed in the
    # same breath as the op memo and for the same reason: both exist so that a
    # re-executed model script produces the SAME geometry it produced last time.
    # A memo that hands back identical shapes is worthless if the code consuming
    # them re-keys the components anyway, so this has to be in force before the
    # generator's first kernel call, not merely before the package write.
    from cadgen._internal import determinism

    determinism.install()
    generated_scene: LoadedStepScene | None = None
    # Deterministic closure capture (see run_script_generator's docstring): start from a
    # clean first-party module space, then record every first-party file executed while
    # the generator loads and runs. The recorded set is complete even if the generator
    # unloads modules mid-run; the sys.modules delta stays as a belt-and-braces union.
    # Alongside it, the DISCOVERED-input window: a model's Python reach announces
    # itself, but a data file it reads does not, so `cadgen.read_step` declares one
    # here and it joins the closure like any other input.
    evict_first_party_modules()
    _purge_stale_bytecode(spec.script_path)
    modules_before_load = set(sys.modules)
    with (
        _without_bytecode_writes(),
        record_first_party_execution() as executed_files,
        record_discovered_inputs() as read_files,
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
        # Bind the run as the ambient reporter for the generator's own code. This is
        # the in-process twin of `run_node_builder`, which lets a Node child describe its
        # work over a pipe: the entry function takes no arguments and so cannot be handed the run,
        # and without this the longest phase of most builds reports nothing at all. Silent
        # generators are unaffected -- nothing reads the binding unless they ask for it.
        from cadgen.authoring import building
        from cadgen.store.closure import ExecutionHashes

        # Hash at execution: every first-party file is hashed the moment it runs
        # (the exec audit hook) — never after the body — so an edit landing
        # mid-build cannot be hashed into the record over the old source's
        # geometry. The script's own bytes were compiled above from disk; hash
        # them now, before the body runs.
        with (
            logger.timed(f"run {model_format} model {spec.source_ref}"),
            reporting_as(progress),
            ExecutionHashes() as executed_hashes,
            building(spec.script_path) as frame,
        ):
            executed_hashes.note(spec.script_path)
            try:
                raw_payload = generator()
            except ModuleNotFoundError as error:
                _teach_function_level_import(error, spec.script_path)
                raise

    source_closure: PythonSourceClosure | None = None
    if model_format == "step":
        payload = _normalize_step_payload(raw_payload, script_path=spec.script_path)
        if spec.step_path is None:
            raise RuntimeError(f"{spec.source_ref} has no configured STEP output")
        # Kinematics + bake pose + animation text (validated at decoration);
        # they ride the scene into the sidecar exactly like provenance does.
        # Resolved BEFORE the closure is captured, because the declared
        # animation file is one of its inputs: the sidecar ships a copy of
        # that file's text, so an edit to it must make the model stale.
        declared = _resolve_declared_kinematics(
            getattr(generator, "__cadgen_model__", None), script_path=spec.script_path
        )
        # Record paths relative to the model folder so the descriptor stays
        # portable. The base is the GENERATOR's folder, never the output's:
        # with an explicit `--write <path>` the step_path moves to the output
        # location, and basing the closure there changed every recorded
        # relpath — the same source hashed differently depending on where its
        # export was written, defeating every closure-keyed reuse.
        # The closure a record carries: the script + its static closure (stopping at
        # child models — a result edge is tracked by pin, not by file), every file
        # that executed (hashed AT execution), and the data files the run declared.
        from cadgen.store.closure import build_closure

        for read_path in [*read_files, *declared.inputs]:
            executed_hashes.note(read_path)
        # Every child the body called, with the tree it resolved to. Waits for
        # any child job the body never forced (called and discarded): its
        # result is still this build's dependency.
        child_trees = frame.child_trees()
        store_closure = build_closure(
            spec.script_path,
            executed=executed_hashes.hashes,
            discovered_inputs=[*read_files, *declared.inputs],
            children=[child for child, _tree in child_trees],
        )
        source_closure = PythonSourceClosure(
            closure_hash=store_closure.hash,
            files=store_closure.files,
            constants=store_closure.constants,
        )
        generated_scene = _write_shape_step_payload(
            payload,
            output_path=spec.step_path,
            script_path=spec.script_path,
            logger=logger,
            entry_kind=_shape_payload_entry_kind(payload.get("shape"), fallback=spec.kind),
        )
        if declared.block:
            generated_scene.kinematics = declared.block
            generated_scene.bake_pose = declared.bake_pose
        generated_scene.animation_source = declared.animation_source
        # Children pinned by the body's calls — recorded from the CALLS, never
        # derived from the tree's links (a modified child is still a dependency).
        generated_scene.store_children = [
            {"model": str(child), "tree": tree} for child, tree in child_trees
        ]
    elif model_format == "dxf":
        if spec.dxf_path is None:
            raise RuntimeError(f"{spec.source_ref} has no configured DXF output")
        # The same closure a @step model records (relative to the model folder).
        # Code reuse is a freshness link: a drawing that imports a helper records it
        # (and its imports) here. Non-Python inputs are intentionally NOT tracked.
        source_closure = capture_runtime_closure(
            modules_before_load,
            spec.script_path,
            base=spec.script_path.parent,
            executed_files=executed_files,
            discovered_inputs=read_files,
        )
        # The product IS the .dxf: the run always writes it — the sibling by
        # default, `-o` renames — and the viewer parses that file directly.
        output_path = spec.dxf_export_path if spec.dxf_export_path is not None else spec.dxf_path
        _write_dxf_payload(
            raw_payload, output_path=output_path, script_path=spec.script_path, logger=logger
        )
        # A drawing is a model in the graph (STORE.md §3): the same record, gate and
        # pins as a @step model, with the .dxf as its output and NO tree (gate
        # clause 4 is vacuous). The children its body composed -- a flat pattern of
        # `bracket()` -- are pinned from the calls, so a child's new geometry makes
        # the drawing stale like any parent.
        _write_drawing_record(
            spec, output_path, source_closure=source_closure, child_trees=frame.child_trees()
        )
    if generated_scene is not None and source_closure is not None:
        generated_scene.source_closure_hash = source_closure.closure_hash
        generated_scene.source_closure_files = source_closure.files
        generated_scene.source_closure_constants = dict(source_closure.constants)
    if model_format == "dxf":
        written = spec.dxf_export_path if spec.dxf_export_path is not None else spec.dxf_path
        if written is not None and not written.exists():
            raise RuntimeError(
                f"{_display_path(spec.script_path)} did not write {_display_path(written)}"
            )
    return generated_scene if model_format == "step" else None


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


