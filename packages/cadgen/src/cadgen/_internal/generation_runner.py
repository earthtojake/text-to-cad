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

from cadgen._internal.cli_locking import lock_wait_notice
from cadgen._internal.file_metadata import text_to_cad_identity_metadata
from cadgen._internal.file_metadata import write_dxf_text_to_cad_metadata
from cadgen._internal.source_hash import PythonSourceClosure
from cadgen._internal.source_hash import PythonSourceHash
from cadgen._internal.source_hash import capture_runtime_closure
from cadgen._internal.source_hash import evict_first_party_modules
from cadgen._internal.source_hash import python_source_hash
from cadgen._internal.source_hash import record_first_party_execution
from cadgen._internal.step_scene import LoadedStepScene
from cadgen.catalog import render_package_dir
from cadgen.cli_logging import CliLogger
from cadgen.cli_progress import cli_progress_line
from cadgen.coordination import DRAWING_PACKAGE
from cadgen.coordination import PHASE_GENERATE
from cadgen.coordination import ProgressEvent
from cadgen.coordination import STEP_PACKAGE
from cadgen.coordination import generator_busy
from cadgen.coordination import reporting_as
from cadgen.coordination import resolve as resolve_progress
from cadgen.coordination.lock import exclusive
from cadgen.coordination.paths import write_lock_path
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

    module = importlib.util.module_from_spec(module_spec)
    original_sys_path = list(sys.path)
    # Seed sys.path so the generator's module-top imports (its sibling/shared packages such as
    # robot_common / STEP) resolve. Derive everything from the generator script's OWN location —
    # its folder, plus any ancestor that is a package root (contains a STEP/ or robot_common/
    # package) — so resolution is independent of the process working directory. Deliberately NOT
    # seeding the repo root or skills/cad/scripts: a generator must not depend on the repository's
    # skills/ being importable (AGENTS.md skill isolation).
    search_paths = [str(resolved_script_path.parent)]
    for parent in resolved_script_path.parents:
        if (
            (parent / "STEP" / "__init__.py").is_file()
            or (parent / "robot_common" / "__init__.py").is_file()
        ):
            search_paths.append(str(parent))
    for candidate in reversed(search_paths):
        if candidate not in sys.path:
            sys.path.insert(0, candidate)

    try:
        sys.modules[module_name] = module
        module_spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_sys_path

    return module


def _resolve_params_sidecar(params: object, *, script_path: Path) -> Path:
    """Resolve the optional gen_step() ``params`` value — a filepath to a hand-authored
    JS sidecar (the step-module manifest: parameters/features/animations/update) — to an
    absolute path. A relative path is resolved against the generator file's directory.
    The sidecar is hand-authored source, so it must already exist on disk."""
    if not isinstance(params, (str, Path)):
        raise TypeError(
            f"{_display_path(script_path)} gen_step() envelope field 'params' must be a "
            f"filepath string, got {type(params).__name__}"
        )
    candidate = Path(params)
    resolved = (candidate if candidate.is_absolute() else script_path.parent / candidate).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(
            f"{_display_path(script_path)} gen_step() params sidecar not found: {params}"
        )
    return resolved


def _normalize_step_payload(
    result: object,
    *,
    script_path: Path,
) -> dict[str, object]:
    from build123d import Shape as Build123dShape

    if isinstance(result, Build123dShape):
        return {"shape": result}
    if isinstance(result, dict):
        # stl / 3mf / mesh_tolerance / mesh_angular_tolerance are consumed via the static
        # metadata path (per-generator STL/3MF outputs + mesh tolerances); keep allowing them.
        allowed_fields = {"shape", "params", "stl", "3mf", "mesh_tolerance", "mesh_angular_tolerance"}
        extra_fields = sorted(str(key) for key in result if key not in allowed_fields)
        if extra_fields:
            joined = ", ".join(extra_fields)
            raise TypeError(f"{_display_path(script_path)} gen_step() envelope has unsupported field(s): {joined}")
        if "shape" not in result:
            raise TypeError(
                f"{_display_path(script_path)} gen_step() envelope must define 'shape'"
            )
        envelope: dict[str, object] = {"shape": result["shape"]}
        params = result.get("params")
        if params is not None:
            envelope["params"] = _resolve_params_sidecar(params, script_path=script_path)
        return envelope
    raise TypeError(
        f"{_display_path(script_path)} gen_step() must return a build123d Shape "
        "or a {'shape': ..., 'params': ...} envelope"
    )


def _normalize_dxf_payload(result: object, *, script_path: Path) -> dict[str, object]:
    if isinstance(result, dict):
        allowed_fields = {"document"}
        extra_fields = sorted(str(key) for key in result if key not in allowed_fields)
        if extra_fields:
            joined = ", ".join(extra_fields)
            raise TypeError(f"{_display_path(script_path)} gen_dxf() envelope has unsupported field(s): {joined}")
        if "document" not in result:
            raise TypeError(f"{_display_path(script_path)} gen_dxf() envelope must define 'document'")
        return {"document": result["document"]}
    return {"document": result}


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
    envelope: dict[str, object],
    *,
    output_path: Path,
    script_path: Path,
    logger: CliLogger,
    entry_kind: str,
) -> LoadedStepScene:
    shape = envelope.get("shape")
    from build123d import Shape as Build123dShape

    if not isinstance(shape, Build123dShape):
        raise TypeError(
            f"{_display_path(script_path)} gen_step() envelope field 'shape' must be a build123d Shape, "
            f"got {type(shape).__name__}"
        )
    # gen_step builds the render scene in memory and does NOT write a text STEP — STEP is
    # written on demand from scene.source_compound (`scripts/gen --write-step`, or the
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
    params_abs = envelope.get("params")
    if params_abs is not None:
        # Record the hand-authored JS sidecar model-folder-relative, like sourcePath, so the
        # descriptor stays portable. The viewer reads this back from assembly.json.
        scene.params_path = relative_to_file(Path(params_abs), scene.step_path)
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


def _write_dxf_payload(
    envelope: dict[str, object],
    *,
    output_path: Path,
    script_path: Path,
    logger: CliLogger,
) -> None:
    document = envelope.get("document")
    saveas = getattr(document, "saveas", None)
    if not callable(saveas):
        raise TypeError(
            f"{_display_path(script_path)} gen_dxf() envelope field 'document' must be a DXF document, "
            f"got {type(document).__name__}"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    saveas(str(output_path))
    source_identity = python_source_hash(script_path)
    write_dxf_text_to_cad_metadata(
        output_path,
        text_to_cad_identity_metadata(
            source_path=relative_to_file(script_path, output_path),
            source_hash=source_identity.source_hash,
        ),
    )
    logger.debug(f"wrote DXF: {_display_path(output_path)}")


def run_script_generator(
    spec: EntrySpec,
    generator_name: str,
    *,
    logger: CliLogger | None = None,
    force: bool = False,
    reset_runtime_closure: bool = False,
    progress: object | None = None,
    lock_intent: str = "write",
) -> LoadedStepScene | None:
    """Run a generator's ``gen_step``/``gen_dxf`` and return its scene.

    ``lock_intent`` says whether this run will rewrite the model's render package
    (``"write"``, the default) or merely occupy its generator (``"generate"`` -- an export,
    a topology extraction, an interference check). See :func:`_track_spec_generation`:
    getting this wrong makes an export look like a build to the CAD Viewer.

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

    ``reset_runtime_closure`` is retained for API compatibility (the warm worker
    passes it) but is now a no-op: the pre-run eviction supersedes it.
    """
    logger = logger or CliLogger("cad")
    if generator_name not in {"gen_step", "gen_dxf"}:
        raise RuntimeError(f"Unsupported generator: {generator_name}")
    if spec.script_path is None or spec.generator_metadata is None:
        raise ValueError(f"{spec.source_ref} is not a generated Python CAD source")
    # A WRITER arrives with the BuildRun that already owns this model's status record and
    # its progress line. An EXPORT arrives with neither: it takes the generator lock instead
    # of the write lock, and until that lock carried a reporter, `cad export` ran the same
    # multi-minute gen_step() a build runs and said nothing on any surface. So the run the
    # lock yields becomes the reporter when nobody above us is one.
    owns_reporting = progress is None
    with _generator_progress_line(spec, logger=logger, active=owns_reporting) as sink:
        with _track_spec_generation(
            spec, generator_name, intent=lock_intent, logger=logger, sink=sink
        ) as generator_run:
            active = generator_run if owns_reporting else progress
            # The phase opens INSIDE the lock: before this it opened first, so a run queued
            # behind a peer reported "building geometry" for the whole time it was waiting.
            resolve_progress(active).phase(PHASE_GENERATE)
            return _run_script_generator_inner(
                spec,
                generator_name,
                logger=logger,
                force=force,
                reset_runtime_closure=reset_runtime_closure,
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
    generator_name: str,
    *,
    logger: CliLogger,
    force: bool = False,
    reset_runtime_closure: bool = False,
    progress: object | None = None,
) -> LoadedStepScene | None:
    del reset_runtime_closure  # superseded by the pre-run eviction below; kept for API compat
    generated_scene: LoadedStepScene | None = None
    # Deterministic closure capture (see run_script_generator's docstring): start from a
    # clean first-party module space, then record every first-party file executed while
    # the generator loads and runs. The recorded set is complete even if the generator
    # unloads modules mid-run; the sys.modules delta stays as a belt-and-braces union.
    evict_first_party_modules()
    modules_before_load = set(sys.modules)
    with record_first_party_execution() as executed_files:
        with logger.timed(f"load generator {spec.source_ref}"):
            module = _load_generator_module(spec.script_path)
        generator = getattr(module, generator_name, None)
        if not callable(generator):
            raise RuntimeError(f"{_display_path(spec.script_path)} does not define callable {generator_name}()")
        # Bind the lock holder as the ambient reporter for the generator's own code. This is
        # the in-process twin of `run_node_builder`, which lets a Node child describe its
        # work over a pipe: gen_step() takes no arguments and so cannot be handed the run,
        # and without this the longest phase of most builds reports nothing at all. Silent
        # generators are unaffected -- nothing reads the binding unless they ask for it.
        with logger.timed(f"run {generator_name} {spec.source_ref}"), reporting_as(progress):
            raw_payload = generator()

    source_closure: PythonSourceClosure | None = None
    if generator_name == "gen_step":
        envelope = _normalize_step_payload(raw_payload, script_path=spec.script_path)
        if spec.step_path is None:
            raise RuntimeError(f"{spec.source_ref} has no configured STEP output")
        # Record paths relative to the model folder so the descriptor stays portable.
        source_closure = capture_runtime_closure(
            modules_before_load,
            spec.script_path,
            base=spec.step_path.parent,
            executed_files=executed_files,
        )
        generated_scene = _write_shape_step_payload(
            envelope,
            output_path=spec.step_path,
            script_path=spec.script_path,
            logger=logger,
            entry_kind=_shape_payload_entry_kind(envelope.get("shape"), fallback=spec.kind),
        )
    elif generator_name == "gen_dxf":
        from cadgen._internal.drawing_package import write_drawing_package
        from cadgen.drawing_checks import raise_on_error_findings, validate_drawing_document

        envelope = _normalize_dxf_payload(raw_payload, script_path=spec.script_path)
        if spec.dxf_path is None:
            raise RuntimeError(f"{spec.source_ref} has no configured DXF output")
        # Validation happens IN generation: the in-memory document is checked once,
        # gating the drawing package and every export alike. Fail closed — anything
        # that is not a real drawing document is rejected rather than skipped.
        document = envelope.get("document")
        if not (hasattr(document, "modelspace") and hasattr(document, "header")):
            raise TypeError(
                f"{_display_path(spec.script_path)} gen_dxf() must return an ezdxf "
                f"document, got {type(document).__name__}"
            )
        findings = validate_drawing_document(document)
        for finding in findings:
            if finding.severity != "error":
                logger.info(f"{spec.source_ref} {finding.render()}")
        raise_on_error_findings(findings, label=_display_path(spec.script_path))
        # Mirror gen_step: capture the generator's closure (relative to the model
        # folder) so the drawing package records the freshness inputs the viewer's
        # staleness gate reads. Code reuse is the freshness link: a drawing that
        # path-loads its .step.py records it (and its imports) here. Non-Python inputs
        # (e.g. an imported vendor .step) are intentionally NOT tracked — like a
        # gen_step that composes imported STEPs, the drawing does not rebuild when
        # they change. Then the default build product is the drawing package; the
        # sibling/exported .dxf is written on demand only.
        source_closure = capture_runtime_closure(
            modules_before_load,
            spec.script_path,
            base=spec.script_path.parent,
            executed_files=executed_files,
        )
        # `progress` is the BuildRun holding this package's lock. It is threaded down here
        # because writing the package now includes baking preview.glb in a Node child, and
        # that child reports its phases -- and proves its run id against the lock sentinel --
        # through the very run that is holding the lock (design §4.3, §7.4.2).
        write_drawing_package(
            envelope.get("document"),
            script_path=spec.script_path,
            source_closure=source_closure,
            run=progress,
        )
        logger.debug(
            f"wrote drawing package: {_display_path(render_package_dir(spec.script_path))}"
        )
        if spec.dxf_export_path is not None:
            _write_dxf_payload(
                envelope, output_path=spec.dxf_export_path, script_path=spec.script_path, logger=logger
            )
    if generated_scene is not None and source_closure is not None:
        generated_scene.source_closure_hash = source_closure.closure_hash
        generated_scene.source_closure_files = source_closure.files
    if (
        generator_name == "gen_dxf"
        and spec.dxf_export_path is not None
        and not spec.dxf_export_path.exists()
    ):
        raise RuntimeError(
            f"{_display_path(spec.script_path)} did not write {_display_path(spec.dxf_export_path)}"
        )
    return generated_scene if generator_name == "gen_step" else None


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
    results: dict[str, object] = {}
    for job in jobs:
        if logger is not None:
            with logger.timed(f"write {job.name}"):
                results[job.name] = job.run()
        else:
            results[job.name] = job.run()
    return results


def _spec_output_dir(spec: EntrySpec, generator_name: str) -> Path | None:
    """The coordinated output directory for this spec's generator, if it has one."""
    if generator_name == "gen_step" and spec.step_path is not None:
        return render_package_dir(spec.entry_path)
    if generator_name == "gen_dxf" and spec.script_path is not None:
        return render_package_dir(spec.script_path)
    return None


def _track_spec_generation(
    spec: EntrySpec,
    generator_name: str,
    *,
    intent: str = "write",
    logger: CliLogger | None = None,
    sink: Callable[[ProgressEvent], None] | None = None,
) -> contextlib.AbstractContextManager[object]:
    """Coordinate a generator run against the model's render package.

    ``intent`` picks the SENTINEL, and the distinction is the whole point of there being
    two. A run that will rewrite the package takes the writer lock, which makes a reader
    hide the artifact and show a build. A run that merely OCCUPIES the generator and
    writes the package nothing -- an export, an on-demand topology extraction, an
    interference check -- takes the generator lock instead. Taking the writer lock for
    those made a fully-current model report `generating` with an empty bar for the whole
    length of an export.

    The two sentinels are different files, so they do NOT exclude each other: a build and
    an export of one model each run its ``gen_step()``, concurrently, in separate
    processes. That is duplicated work rather than a hazard (no shared in-process state,
    different outputs), and it is the price of letting a reader tell "being rewritten"
    from "generator busy" -- see :func:`cadgen.coordination.generator_busy`.
    """
    output_dir = _spec_output_dir(spec, generator_name)
    if output_dir is None:
        return contextlib.nullcontext()
    on_wait = lock_wait_notice(logger, spec.source_ref)
    if intent == "generate":
        # The kind decides which phase set the run reports over, so a drawing generator
        # counts its own phases rather than a STEP package's.
        kind = DRAWING_PACKAGE if generator_name == "gen_dxf" else STEP_PACKAGE
        return generator_busy(kind, output_dir, on_wait=on_wait, sink=sink)
    # A writer already has its BuildRun from artifact_build; this only needs the lock, and
    # yields None so the caller's `progress or this` choice stays a simple one.
    return _write_lock_without_reporting(write_lock_path(output_dir), on_wait=on_wait)


@contextlib.contextmanager
def _write_lock_without_reporting(
    path: Path, *, on_wait: Callable[[float], None] | None
) -> Iterator[None]:
    with exclusive(path, on_wait=on_wait):
        yield None


