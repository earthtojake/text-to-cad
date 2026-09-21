"""Snapshot below the options boundary: job resolution and the run loop.

There is no parser here any more. Snapshot used to be the schema's one ADAPTER
— a hand-written argv scanner plus a declared option surface a policy test
pinned — and that exception is retired: the verbs in
:mod:`cadgen._internal.snapshot_door` are MIRRORS, and their generated parsers
hand this module a :class:`SnapshotOptions` already built. What remains is
everything downstream of that:

    run_snapshot(options, kinds=("step", "stp"), runtime_dir=...)

The split against :mod:`cadgen.snapshot_core` is by ROLE, not by format: the core owns the
headless browser, the job/render/display normalisation and output writing; this module owns
the options-to-job step and the per-kind resolution that decides what a given input even is.

Every input kind resolves here, and each door enables a subset
(:data:`cadgen._internal.snapshot_door.DOOR_KINDS`). An input the running door does not
enable is refused BY NAME with what the door does accept, so a `.urdf` handed to
`cadgen step snapshot` is told so rather than failing on a missing resolver.

A job goes through two steps, and the split between them is the output contract.
PREPARING a job decides every refusal that can be decided from the request and the
input's kind, and builds nothing; only then are the declared outputs cleared.
RESOLVING it builds what the render needs (the STEP tree, a drawing's payload). So a
refused request leaves an existing OUT untouched, and a failed build or render
leaves no file at all.
"""

from __future__ import annotations

import asyncio
import copy
import functools
import json
import math
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import cadgen.cad_ref_syntax as cad_ref_syntax
import cadgen.lookup as lookup
from cadgen.assets import browser_runtime_dir
from cadgen._internal.doors import document_snapshot
from cadgen.store.view import view_dir_for
from cadgen.step_targets import ResolvedStepTarget, StepTopologyArtifact, StepTopologyArtifactError

from cadgen.cli_logging import CliLogger
from cadgen.coordination import PHASE_BROWSER, SNAPSHOT, ProgressReporter
# GROUP occurrence refs use cadgen.occurrence_groups so snapshots and scene
# readers agree on which document occurrences a selector names. Re-exported here because
# callers of this module have always reached for these names through it.
from cadgen.occurrence_groups import (
    UnknownOccurrenceSelector,
)
from cadgen.occurrence_groups import (
    expand_occurrence_selector as _expand_occurrence_selector,
)
from cadgen.cli_progress import cli_progress_line
from cadgen.results import SnapshotResult
from cadgen.snapshot_core import (
    SELECTION_KEYS,
    SUPPORTED_JOB_KEYS,
    SnapshotError,
    asset_url_for_path,
    check_mesh_render_job,
    clear_render_output_targets,
    declared_output_path,
    display_modes_for_kind,
    is_plain_object,
    load_display_option,
    load_json_text,
    normalize_common_job,
    normalize_render_mode,
    normalize_snapshot_job_packet,
    parse_camera_option,
    parse_section_option,
    path_is_inside_or_equal,
    refuse_cad_model_requests,
    render_snapshot,
    resolve_mesh_render_job,
    has_kinematics_render_values,
    selection_filter_values,
    selection_value_list,
    snapshot_timestamp,
    validate_display_for_kind,
    validate_selection_keys,
)
from cadgen.snapshot_video import (
    ffmpeg_binary,
    normalize_video_request,
    parse_video_option,
    video_container_for_path,
)


# Snapshot artifact resolution stays kernel-free. Kept module-level so callers
# testing request resolution can substitute the artifact boundary.
ensure_step_topology_artifact = None


@dataclass(slots=True)
class SnapshotOptions:
    """Every snapshot flag, as a field.

    ``slots=True`` so a typo'd assignment fails loudly. The parser mutates this
    object attribute by attribute, and on a plain dataclass
    ``options.size_profle = ...`` silently created a NEW attribute: the flag
    parsed, the run succeeded, and the setting was never applied. There is
    nothing left for a slot to hide behind.
    """

    job: str = ""
    input: str = ""
    output: str = ""
    mode: str = "view"
    mode_specified: bool = False
    display: object = ""
    display_specified: bool = False
    camera: object = None
    camera_specified: bool = False
    width: int | None = None
    height: int | None = None
    size_profile: str = ""
    kinematics: object = None
    kinematics_specified: bool = False
    animation: object = None
    animation_time: object = None
    animation_specified: bool = False
    video: object = None
    video_specified: bool = False
    section: object = None
    section_specified: bool = False
    joint_values: object = None
    joint_values_specified: bool = False
    focus: list[str] | None = None
    focus_specified: bool = False
    hide: list[str] | None = None
    hide_specified: bool = False
    view_labels: bool = False
    debug: bool = False


# The frame request's closed vocabulary: the clip and the moment, nothing else.
ANIMATION_REQUEST_KEYS = frozenset({"clip", "time"})


def normalize_animation_request(value: object, *, where: str) -> dict[str, object]:
    """``{"clip": <name>, "time": <seconds>}`` — the job's ``animation`` field.

    Both spellings of the request (the flag pair and a job packet's field) land
    here, so one validator holds the shape: a non-empty clip name, a finite
    non-negative time in seconds defaulting to 0, and no other keys.
    """
    if not is_plain_object(value):
        raise SnapshotError(
            f'{where} must be a {{"clip": name, "time": seconds}} object, got {json.dumps(value)}'
        )
    unknown = sorted(set(value) - ANIMATION_REQUEST_KEYS)
    if unknown:
        raise SnapshotError(
            f"{where} has unknown key(s): {', '.join(unknown)}; "
            f"supported keys: {', '.join(sorted(ANIMATION_REQUEST_KEYS))}"
        )
    clip = value.get("clip")
    if not isinstance(clip, str) or not clip.strip():
        raise SnapshotError(f"{where} must name a clip: {{\"clip\": name, \"time\": seconds}}")
    raw_time = value.get("time", 0)
    try:
        if isinstance(raw_time, bool):
            raise ValueError("bool")
        time_seconds = float(raw_time)
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"{where} time must be seconds >= 0, got {json.dumps(raw_time)}") from exc
    if not math.isfinite(time_seconds) or time_seconds < 0:
        raise SnapshotError(f"{where} time must be seconds >= 0, got {raw_time}")
    return {"clip": clip.strip(), "time": time_seconds}


def parse_animation_option(raw_animation: object, raw_time: object = None) -> dict[str, object]:
    """``--animation CLIP [--time SECONDS]`` in job form: ``{"clip": name, "time": seconds}``.

    Already an object when it came from a ``<format>.snapshot(animation={...})``
    call; from argv it is one string, told apart by shape the way ``--kinematics``
    is: text that opens with ``{`` is the inline JSON request, anything else is
    the NAME of a clip the document's embedded animation source
    declares. ``--time`` is the
    second half of the same request — the moment, in seconds, defaulting to 0 —
    and is folded in here, so the job carries ONE field either way. Resolving
    the name needs the sidecar, which only the resolver has loaded, so it travels
    through unresolved and is checked against the declared clips there.
    """
    if is_plain_object(raw_animation):
        request = dict(raw_animation)
    else:
        text = str(raw_animation or "")
        if text.lstrip().startswith("{"):
            parsed = load_json_text(text, "--animation")
            if not is_plain_object(parsed):
                raise SnapshotError('--animation must be a clip name or a {"clip": name, "time": seconds} object')
            request = parsed
        else:
            request = {"clip": text}
    if raw_time is not None:
        if "time" in request:
            raise SnapshotError(
                "the animation time was given twice: pass it as --time SECONDS or inside "
                'the {"clip": name, "time": seconds} request, not both'
            )
        request["time"] = raw_time
    return normalize_animation_request(request, where="--animation")


def parse_kinematics_option(raw_kinematics: object) -> dict[str, object] | str:
    """``--kinematics`` in job form: a values object, or a PRESET NAME.

    Already an object when it came from a ``<format>.snapshot(kinematics={...})``
    call rather than argv; see the note above parse_camera_option. From argv it
    is one string, and the two spellings are told apart by shape rather than by
    a second flag: text that opens with ``{`` is inline JSON, anything else is
    the name of a pose the model DECLARES. Resolving that name needs the
    kinematics declaration, which only the renderer has loaded, so the name
    travels through unresolved and the job's `kinematics` key carries either shape.
    """
    if is_plain_object(raw_kinematics):
        return dict(raw_kinematics)
    text = str(raw_kinematics or "")
    if not text.lstrip().startswith("{"):
        return text
    parsed = load_json_text(text, "--kinematics")
    if not is_plain_object(parsed):
        raise SnapshotError("--kinematics must be a pose preset name or a JSON object")
    return parsed


def parse_joint_values_option(raw_joint_values: object) -> dict[str, object]:
    """``--joint-values`` in job form: ``{joint: degrees}``.

    A robot description declares no named poses — its articulation is the joint
    list in the file — so unlike ``--kinematics`` there is no preset spelling to
    tell apart, and anything that is not an object is an error.
    """
    if is_plain_object(raw_joint_values):
        return dict(raw_joint_values)
    parsed = load_json_text(str(raw_joint_values or ""), "--joint-values")
    if not is_plain_object(parsed):
        raise SnapshotError("--joint-values must be a {joint: degrees} JSON object")
    return parsed


def option_focus_hide_specified(options: SnapshotOptions) -> bool:
    return options.focus_specified or options.hide_specified or bool(options.focus or options.hide)


def merge_focus_hide_options(job: dict[str, object], options: SnapshotOptions) -> None:
    if not option_focus_hide_specified(options):
        return
    if options.focus and options.hide:
        raise SnapshotError("--focus and --hide cannot be used in the same snapshot command")
    selection = dict(job.get("selection") if is_plain_object(job.get("selection")) else {})
    if options.focus:
        selection["focus"] = list(options.focus)
    if options.hide:
        selection["hide"] = list(options.hide)
    job["selection"] = selection


def option_display_modes(options: SnapshotOptions) -> frozenset[str] | None:
    """The preset vocabulary a bad ``--display`` word is told: TARGET's kind's."""
    return display_modes_for_kind(input_kind(Path(options.input))) if options.input else None


def apply_option_overrides_to_job(job: object, options: SnapshotOptions, *, cwd: Path) -> object:
    if not is_plain_object(job):
        return job
    if not any(
        [
            options.mode_specified,
            options.view_labels,
            options.debug,
            options.size_profile,
            options.width is not None,
            options.height is not None,
            options.kinematics_specified,
            options.animation_specified,
            options.video_specified,
            options.section_specified,
            options.joint_values_specified,
            options.display_specified,
            options.camera_specified,
            option_focus_hide_specified(options),
        ]
    ):
        return job
    next_job = copy.deepcopy(job)
    if options.mode_specified:
        next_job["mode"] = normalize_render_mode(options.mode)
    if options.debug:
        next_job["debug"] = True
    merge_focus_hide_options(next_job, options)
    if options.kinematics_specified:
        next_job["kinematics"] = parse_kinematics_option(options.kinematics)
    if options.joint_values_specified:
        next_job["jointValues"] = parse_joint_values_option(options.joint_values)
    if options.display_specified:
        next_job["display"] = load_display_option(options.display, cwd=cwd)
    if options.camera_specified:
        next_job["camera"] = parse_camera_option(options.camera)
    if options.animation_specified:
        next_job["animation"] = parse_animation_option(options.animation, options.animation_time)
    if options.video_specified:
        next_job["video"] = parse_video_option(options.video, cwd=cwd)
    if options.section_specified:
        next_job["section"] = parse_section_option(options.section)
    if options.width is not None or options.height is not None:
        # Size lives on each output, so the override lands on every one of them —
        # the same "every job in the packet" reach the other overrides have.
        outputs = []
        for output in next_job.get("outputs") if isinstance(next_job.get("outputs"), list) else []:
            sized = {"path": output} if isinstance(output, str) else dict(output) if is_plain_object(output) else output
            if is_plain_object(sized):
                if options.width is not None:
                    sized["width"] = options.width
                if options.height is not None:
                    sized["height"] = options.height
            outputs.append(sized)
        next_job["outputs"] = outputs
    output_settings = dict(next_job.get("output") if is_plain_object(next_job.get("output")) else {})
    if options.view_labels:
        output_settings["viewLabels"] = True
    if options.size_profile:
        output_settings["sizeProfile"] = options.size_profile
    if output_settings:
        next_job["output"] = output_settings
    return next_job


def apply_option_overrides_to_payload(payload: object, options: SnapshotOptions, *, cwd: Path) -> object:
    if isinstance(payload, list):
        return [apply_option_overrides_to_job(job, options, cwd=cwd) for job in payload]
    if is_plain_object(payload) and isinstance(payload.get("jobs"), list):
        next_payload = copy.deepcopy(payload)
        next_payload["jobs"] = [apply_option_overrides_to_job(job, options, cwd=cwd) for job in payload["jobs"]]
        return next_payload
    return apply_option_overrides_to_job(payload, options, cwd=cwd)


def read_job_file(raw_job: str, *, cwd: Path) -> object:
    """The render-job JSON ``--job`` names. A job is a FILE: there is no stdin form."""
    if raw_job.strip() == "-":
        raise SnapshotError(
            "--job takes the path of a render-job JSON file; reading a job from stdin "
            "(--job -) was removed — write the job to a file and pass its path"
        )
    job_path = (cwd / Path(raw_job).expanduser()).resolve()
    if not job_path.exists():
        raise SnapshotError(f"--job file does not exist: {raw_job}")
    if job_path.is_dir():
        raise SnapshotError(f"--job names a directory, not a render-job JSON file: {raw_job}")
    try:
        text = job_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SnapshotError(f"Cannot read --job file {raw_job}: {exc}") from exc
    return load_json_text(text, str(job_path))


def load_job_from_options(options: SnapshotOptions, *, cwd: Path | None = None) -> object:
    resolved_cwd = (cwd or Path.cwd()).resolve()
    if options.job:
        return apply_option_overrides_to_payload(
            read_job_file(options.job, cwd=resolved_cwd), options, cwd=resolved_cwd
        )

    if not options.input:
        raise SnapshotError("render requires a TARGET or --job: snapshot TARGET OUT")
    mode = normalize_render_mode(options.mode)
    if mode != "list" and not options.output:
        raise SnapshotError("render requires an OUT path for non-list modes: snapshot TARGET OUT")

    output: dict[str, object] = {
        "path": options.output,
    }
    if options.camera_specified:
        output["camera"] = parse_camera_option(options.camera)
    if options.width is not None:
        output["width"] = options.width
    if options.height is not None:
        output["height"] = options.height

    job: dict[str, object] = {
        "input": options.input,
        "mode": mode,
        "outputs": [] if mode == "list" else [output],
    }
    output_settings: dict[str, object] = {}
    if options.view_labels:
        output_settings["viewLabels"] = True
    if options.size_profile:
        output_settings["sizeProfile"] = options.size_profile
    if output_settings:
        job["output"] = output_settings
    if options.display_specified:
        job["display"] = load_display_option(
            options.display, cwd=resolved_cwd, modes=option_display_modes(options)
        )
    if options.kinematics_specified:
        job["kinematics"] = parse_kinematics_option(options.kinematics)
    if options.animation_specified:
        job["animation"] = parse_animation_option(options.animation, options.animation_time)
    if options.video_specified:
        job["video"] = parse_video_option(options.video, cwd=resolved_cwd)
    if options.section_specified:
        job["section"] = parse_section_option(options.section)
    if options.joint_values_specified:
        job["jointValues"] = parse_joint_values_option(options.joint_values)
    if options.debug:
        job["debug"] = True
    merge_focus_hide_options(job, options)
    return job


def input_kind(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".step":
        return "step"
    if suffix == ".stp":
        return "stp"
    if suffix == ".dxf":
        return "dxf"
    if suffix == ".py":
        # DOCUMENTS-ONLY: a model script is a program. The kind survives only so
        # the resolver can refuse it by naming the run.
        return "python"
    if suffix == ".glb":
        return "glb"
    if suffix == ".stl":
        return "stl"
    if suffix == ".3mf":
        return "3mf"
    if suffix in {".urdf", ".srdf", ".sdf"}:
        return suffix[1:]
    return ""


def resolve_input_path(raw_input: object, *, cwd: Path) -> Path:
    input_text = str(raw_input or "").strip()
    if not input_text:
        raise SnapshotError("render job is missing input")
    raw_path = Path(input_text).expanduser()
    selected = raw_path.resolve() if raw_path.is_absolute() else (cwd / raw_path).resolve()
    if not selected.exists():
        raise SnapshotError(f"Render input does not exist: {input_text}")
    return selected


def reference_root_for_input(input_path: Path, cwd: Path) -> Path:
    return cwd if path_is_inside_or_equal(input_path, cwd) else input_path.parent


def cad_ref_for_step_path(repo_root: Path, step_path: Path) -> str:
    try:
        relative = step_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        relative = step_path.resolve().as_posix()
    suffix = step_path.suffix
    return relative[: -len(suffix)] if suffix else relative


def load_ensure_step_topology_artifact():
    global ensure_step_topology_artifact
    if ensure_step_topology_artifact is None:
        ensure_step_topology_artifact = _ensure_snapshot_step_artifact
    return ensure_step_topology_artifact


def _ensure_snapshot_step_artifact(target, *, require_selector=False, debug=None):
    """Resolve saved bytes through the artifact pool, without importing a kernel.

    A snapshot needs the surface view and, for a selection, the selector tables
    composed from its descriptor. Compiling a document the store has no tree for
    belongs to the pool (:func:`cadgen._internal.doors.document_snapshot`).
    """
    from cadgen.selector_types import SelectorBundle

    document_hash, tree = document_snapshot(target.step_path)
    package_dir = view_dir_for(tree, document_hash=document_hash)
    descriptor = json.loads((package_dir / "assembly.json").read_text(encoding="utf-8"))
    if debug is not None:
        # What this resolution actually selected — nothing here is a constant.
        debug.update(
            documentHash=document_hash,
            tree=tree,
            view=str(package_dir),
            componentCount=len(descriptor.get("components") or {}),
            occurrenceCount=len(descriptor.get("occurrences") or []),
            selectorIndex=bool(require_selector),
        )
    return StepTopologyArtifact(
        cad_path=target.cad_path, source_path=target.source_path,
        step_path=target.step_path, artifact_path=package_dir, manifest=descriptor,
        selector_bundle=SelectorBundle(manifest=descriptor) if require_selector else None,
    )


def selector_value_requires_topology(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    parsed = cad_ref_syntax.parse_selector(text)
    return parsed is not None and parsed.selector_type != "opaque"


def selection_requires_selector_topology(job: Mapping[str, object]) -> bool:
    return any(selector_value_requires_topology(value) for value in selection_filter_values(job))


def ensure_render_job_step_artifact(
    job: Mapping[str, object],
    *,
    reference_root: Path,
    input_path: Path,
    step_path: Path,
    require_selector: bool = False,
    debug_info: dict[str, object] | None = None,
) -> StepTopologyArtifact:
    target = ResolvedStepTarget(
        cad_path=cad_ref_for_step_path(reference_root, step_path),
        source_path=input_path,
        step_path=step_path,
    )
    try:
        ensure_artifact = load_ensure_step_topology_artifact()
        return ensure_artifact(
            target,
            require_selector=require_selector,
            debug=debug_info,
        )
    except StepTopologyArtifactError as exc:
        raise SnapshotError(str(exc)) from exc


def artifact_selector_index(artifact: StepTopologyArtifact | None) -> lookup.SelectorIndex | None:
    selector_bundle = artifact.selector_bundle if artifact is not None else None
    if selector_bundle is None:
        return None
    manifest = selector_bundle.manifest if isinstance(selector_bundle.manifest, dict) else None
    if manifest is None:
        return None
    buffers = selector_bundle.buffers if isinstance(selector_bundle.buffers, Mapping) else None
    index = lookup.build_selector_index(manifest, buffers=buffers)
    # The bundle is extracted from the COMPOSED compound, which has no instance tree, so it
    # describes even a 160-part assembly as one occurrence -- and `--focus`/`--hide` rejected
    # every ref `--mode list` had just handed out. See `cadgen.assembly_lookup`.
    from cadgen.assembly_lookup import index_with_assembly_occurrences

    return index_with_assembly_occurrences(index, artifact)


def expand_occurrence_selector(
    selector: str, *, selector_index: lookup.SelectorIndex | None, source_label: str
) -> list[str]:
    """The rendered occurrences a selection ref covers, as a snapshot error on failure."""
    try:
        return _expand_occurrence_selector(
            selector, selector_index=selector_index, source_label=source_label
        )
    except UnknownOccurrenceSelector as error:
        raise SnapshotError(str(error)) from error


def normalize_selection_selector(
    raw_value: str,
    *,
    selector_index: lookup.SelectorIndex | None,
    source_label: str,
    expected_cad_path: str = "",
) -> list[str]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    # A copied ref may carry a file prefix (`plate.step.py#o1.2`). Accept it when it names the
    # model being rendered, refuse it when it names another -- rendering a different file's ref
    # against this model would focus the wrong geometry and look like it worked.
    if "#" in text:
        prefix, _, remainder = text.partition("#")
        if prefix.strip():
            try:
                cad_ref_syntax.ensure_ref_file_matches(
                    prefix, expected_cad_path, source_label=f"{source_label} ref {text!r}"
                )
            except ValueError as error:
                raise SnapshotError(str(error)) from error
        text = remainder.strip()
        if not text:
            return []
    parsed = cad_ref_syntax.parse_selector(text)
    if parsed is None:
        return []
    if parsed.label:
        # Labels become numeric here, before any validation or job building, so everything
        # downstream -- including the JS render runtime -- only ever sees occurrence ids.
        from cadgen.label_refs import LabelResolutionError, resolve_label_selectors

        alias_map = getattr(selector_index, "label_aliases", None) if selector_index else None
        try:
            resolved = resolve_label_selectors([text], alias_map)
        except LabelResolutionError as error:
            raise SnapshotError(f"{source_label} {error}") from error
        parsed = cad_ref_syntax.parse_selector(resolved[0]) if resolved else None
        if parsed is None:
            return []
    if parsed.selector_type == "opaque":
        return [parsed.canonical]
    if parsed.selector_type != "occurrence":
        raise SnapshotError(
            f"{source_label} supports only part/subassembly occurrence refs; "
            f"got {parsed.selector_type} selector {text!r}"
        )
    # A GROUP ref expands to its subtree here — including a label that resolved to a group
    # id, which takes this same path, so labels and ids behave identically wherever the
    # label already exists.
    return expand_occurrence_selector(
        parsed.canonical, selector_index=selector_index, source_label=source_label
    )


def normalize_selection_filter_values(
    value: object,
    *,
    expected_cad_path: str,
    selector_index: lookup.SelectorIndex | None,
    source_label: str,
) -> list[str]:
    # Deduped, first-seen order. A group ref expands to its subtree, so naming a
    # subassembly AND one of its parts (or two overlapping groups) is an ordinary thing to
    # do and must not put the same occurrence in the job twice.
    selectors: dict[str, None] = {}
    for raw_value in selection_value_list(value):
        for selector in normalize_selection_selector(
            raw_value,
            selector_index=selector_index,
            source_label=source_label,
            expected_cad_path=expected_cad_path,
        ):
            selectors.setdefault(selector, None)
    return list(selectors)


def normalize_render_job_selection(
    job: Mapping[str, object],
    *,
    expected_cad_path: str,
    selector_index: lookup.SelectorIndex | None,
) -> dict[str, object] | None:
    selection = job.get("selection") if is_plain_object(job.get("selection")) else None
    if selection is None:
        return None
    normalized = dict(selection)
    for key in SELECTION_KEYS:
        if key not in selection:
            continue
        normalized[key] = normalize_selection_filter_values(
            selection.get(key),
            expected_cad_path=expected_cad_path,
            selector_index=selector_index,
            source_label=f"selection.{key}",
        )
    return normalized


# The shapes the renderer can draw. Kept beside the door because "renderable" is a RENDERER
# fact, not a validity one: `cadgen sdf validate` accepts every shape SDFormat defines.
SDF_RENDERABLE_GEOMETRY = ("box", "cylinder", "mesh", "sphere")


def unrenderable_sdf_geometry(input_path: Path) -> list[tuple[str, str]]:
    """``(link, kind)`` for every VISUAL shape the renderer cannot draw.

    A capsule, plane, ellipsoid, heightmap or polyline has no mesh in the renderer, so the
    composer drops it and the model renders as EMPTY SPACE at exit 0. The browser parser
    refuses these too — that is what the Viewer shows — but the door answers first so the
    CLI fails before starting a browser, and says the same thing.

    COLLISION geometry is deliberately not checked. It is never drawn, so an undrawable one
    costs the picture nothing, and a ``<plane>`` ground collision is the single most common
    shape in a real Gazebo world — refusing those would block loading and snapshotting every
    one of them for no visual gain. The Viewer counts them in its SDF sheet instead; this
    door has no non-blocking channel of its own (a snapshot's ``warnings`` come back from the
    renderer, not from job resolution), so it passes over them in silence.

    Returns [] when the file cannot be read: a description this cannot parse is left to the
    renderer exactly as before, so the check never refuses more than it understands.
    """
    import xml.etree.ElementTree as ET

    def local(tag: object) -> str:
        return str(tag).rsplit("}", 1)[-1]

    try:
        root = ET.parse(input_path).getroot()
    except Exception:
        return []
    found: list[tuple[str, str]] = []
    for link in root.iter():
        if local(link.tag) != "link":
            continue
        link_name = link.get("name") or "(unnamed)"
        for container in link:
            if local(container.tag) != "visual":
                continue
            geometry = next((c for c in container if local(c.tag) == "geometry"), None)
            shapes = [local(c.tag) for c in geometry] if geometry is not None else []
            kind = shapes[0] if shapes else "missing"
            if kind not in SDF_RENDERABLE_GEOMETRY:
                found.append((link_name, kind))
    return found


def _robot_name(description: Path) -> str | None:
    """The root ``<robot name>`` of a URDF or SRDF, or None when it cannot be read."""
    import xml.etree.ElementTree as ET

    try:
        for _event, element in ET.iterparse(str(description), events=("start",)):
            if str(element.tag).rsplit("}", 1)[-1] != "robot":
                return None
            return str(element.attrib.get("name") or "").strip() or None
    except (OSError, ET.ParseError):
        return None
    return None


def paired_urdf_for_srdf(srdf_path: Path) -> Path:
    """The URDF whose geometry an SRDF renders, or a refusal naming the search.

    An SRDF carries planning semantics only. It pairs with the same-folder
    ``.urdf`` whose ``<robot name>`` matches — the rule ``cadgen srdf validate``
    and the Viewer use — and exactly one may match. Anything else used to reach
    the browser with no URDF at all and come back as a stack trace.
    """
    from cadgen.srdf_validation import find_paired_urdf

    folder = srdf_path.parent
    robot_name = _robot_name(srdf_path)
    rule = (
        "An SRDF renders the geometry of the same-folder .urdf whose <robot name> "
        "matches its own, and exactly one may match (check with `cadgen srdf validate`)."
    )
    if not robot_name:
        raise SnapshotError(
            f"{srdf_path.name} has no readable <robot name>, so its URDF cannot be found. {rule}"
        )
    paired, matches = find_paired_urdf(robot_name, folder)
    if paired is not None:
        return paired
    if matches:
        raise SnapshotError(
            f"{srdf_path.name} is ambiguous: {len(matches)} .urdf files in {folder} declare "
            f"<robot name={robot_name!r}> ({', '.join(match.name for match in matches)}). {rule}"
        )
    candidates = sorted(folder.glob("*.urdf"))
    found = (
        "; it holds " + ", ".join(
            f"{candidate.name} (robot {(_robot_name(candidate) or 'unreadable')!r})"
            for candidate in candidates[:6]
        ) + (f" and {len(candidates) - 6} more" if len(candidates) > 6 else "")
        if candidates
        else "; it holds no .urdf files"
    )
    raise SnapshotError(
        f"{srdf_path.name} has no paired URDF: no .urdf in {folder} declares "
        f"<robot name={robot_name!r}>{found}. {rule}"
    )


def robot_joint_names(kind: str, description: Path) -> frozenset[str] | None:
    """The joint names a pose request may name, or None when they cannot be read.

    The browser is what ASSEMBLES a robot, so this module never had the joint list and a
    misspelled `--joint-values` name was dropped in silence: the door reported success and
    rendered the rest pose, which is the one failure a posed review cannot survive. The
    STEP door already refuses an unknown DOF by name; robots now do the same.

    ``description`` is the file that DECLARES the joints: the SDF or URDF itself, or an
    SRDF's paired URDF. The answer is only ever used to REFUSE a name that is definitely
    not in the description. A description this cannot parse returns None and renders
    exactly as before, so the check can never make the door stricter about geometry than
    the renderer that has to draw it.
    """
    try:
        if kind == "sdf":
            from cadgen.sdf_source import read_sdf_source

            return frozenset(joint.name for joint in read_sdf_source(description).joints)
        import warnings

        from cadgen.urdf_source import read_urdf_source

        # The reader doubles as the validator and advises about inertials, materials and
        # the like. Those belong to `cadgen urdf validate`; a render that only needs the
        # joint names must not start narrating them over the snapshot's own output.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return frozenset(joint.name for joint in read_urdf_source(description).joints)
    except Exception:
        return None


def check_robot_render_job(
    job: dict[str, object],
    *,
    kind: str,
    input_path: Path,
    mode: str,
    **_context: object,
) -> dict[str, object]:
    """What a robot description (`.urdf` / `.srdf` / `.sdf`) cannot be asked for.

    Everything here is decided from the request and the description's own XML, before
    anything is cleared: the STEP-only options, undrawable SDF geometry, the SRDF's
    pairing, and the joint names a pose may use."""
    label = kind.upper()
    refuse_cad_model_requests(
        job,
        mode=mode,
        subject=f"{label} robots",
        pose_hint=f"pose a {label} robot with jointValues",
        tessellation_hint="a robot's link meshes are existing meshes",
        joints=True,
    )

    if kind == "sdf":
        unrenderable = unrenderable_sdf_geometry(input_path)
        if unrenderable:
            listed = "; ".join(
                f"link {name} visual uses <{shape}>" if shape != "missing"
                else f"link {name} visual has no <geometry>"
                for name, shape in unrenderable[:4]
            )
            more = f" (and {len(unrenderable) - 4} more)" if len(unrenderable) > 4 else ""
            raise SnapshotError(
                f"{input_path.name} has visual geometry this renderer cannot draw: {listed}{more}. "
                f"Supported: {', '.join(SDF_RENDERABLE_GEOMETRY)}. "
                "Replace the shape or reference a mesh file — rendering it would silently "
                "leave those links out of the picture."
            )

    # An SRDF carries semantics; its geometry and its joints are the paired URDF's.
    urdf_path = paired_urdf_for_srdf(input_path) if kind == "srdf" else None

    joint_values = job.get("jointValues")
    if joint_values is not None and not is_plain_object(joint_values):
        raise SnapshotError("jointValues must be an object of joint name to angle")
    if joint_values:
        for name, value in joint_values.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise SnapshotError(f"jointValues[{name}] must be a number (degrees)")
        declared = robot_joint_names(kind, urdf_path or input_path)
        if declared is not None:
            unknown = sorted(str(name) for name in joint_values if str(name) not in declared)
            if unknown:
                raise SnapshotError(
                    f"Unknown joint(s): {', '.join(unknown)}. "
                    f"This {label} declares: {', '.join(sorted(declared)) or '(none)'}"
                )

    # Robots are authored in METRES; the CAD profile assumes millimetres, and its floor,
    # grid and lighting radii are sized accordingly. Default the robot profile so a robot
    # frames like a robot without the caller having to know the unit convention.
    if not str(job.get("scale") or "").strip():
        job["scale"] = "urdf"
    return {"urdf_path": urdf_path}


def resolve_robot_render_job(
    job: dict[str, object],
    *,
    kind: str,
    input_path: Path,
    root_path: Path,
    urdf_path: Path | None = None,
    **_kind_context: object,
) -> dict[str, object]:
    """Resolve a robot description (`.urdf` / `.srdf` / `.sdf`).

    The browser assembles the robot: the parser resolves each link mesh against the
    description's own URL, so this hands over one asset URL and the pose, and the shared
    mesh backend renders the result."""
    # Link meshes are referenced relative to the description, so the served root has to
    # contain both. The description's own directory is the natural root and matches how the
    # viewer serves a robot from its model folder.
    asset_url = asset_url_for_path(input_path, root_path)
    resolved: dict[str, object] = {
        "rootPath": str(root_path),
        "inputPath": str(input_path),
        "inputUrl": asset_url,
        "kind": kind,
        "url": asset_url,
    }
    if urdf_path is not None:
        resolved["urdfUrl"] = asset_url_for_path(urdf_path, root_path)
    if job.get("jointValues"):
        resolved["jointValues"] = dict(job["jointValues"])
    if bool(job.get("debug")):
        resolved["debug"] = {"robotSource": {"kind": kind}}
    return {**job, "resolved": resolved}


@dataclass(slots=True)
class PreparedRenderJob:
    """One job whose REQUEST has been accepted, with nothing built for it yet."""

    #: The commonly-normalized job (:func:`cadgen.snapshot_core.normalize_common_job`).
    job: dict[str, object]
    kind: str
    input_path: Path
    root_path: Path
    reference_root: Path
    resolved_cwd: Path
    #: What the kind's check learned that its resolver needs (an SRDF's paired URDF).
    context: dict[str, object]


def prepare_render_job(
    raw_job: object,
    *,
    cwd: Path | None = None,
    timestamp: str | None = None,
    kinds: frozenset[str] | None = None,
    job_index: int = 0,
    job_count: int = 1,
) -> PreparedRenderJob:
    """Accept or refuse one job's REQUEST. Builds nothing and deletes nothing.

    Every refusal that can be decided from the request, the input's kind and the
    files beside it happens here, so the caller can clear the declared outputs
    only once the whole packet has been accepted.
    """
    if not is_plain_object(raw_job):
        raise SnapshotError("render job must be an object")
    job = copy.deepcopy(raw_job)

    # Every key must come from the closed job schema; anything else is named
    # with the supported set so a typo fails here instead of rendering as if
    # the key were absent.
    unknown_keys = sorted(set(job) - SUPPORTED_JOB_KEYS)
    if unknown_keys:
        # --focus/--hide are the one flag pair whose job spelling is not the
        # bare flag name: they nest under "selection". Name that, or the
        # generic message sends the author back to a flag list that is right.
        misplaced = [key for key in unknown_keys if key in SELECTION_KEYS]
        hint = (
            f" ({', '.join(misplaced)} nest under the selection object: "
            f'"selection": {{"{misplaced[0]}": ["#o1.2"]}})'
            if misplaced
            else ""
        )
        raise SnapshotError(
            f"unknown render job key(s): {', '.join(unknown_keys)}; "
            f"supported keys: {', '.join(sorted(SUPPORTED_JOB_KEYS))}{hint}"
        )

    resolved_cwd = (cwd or Path.cwd()).resolve()
    raw_input = str(job.get("input") or "").strip()
    if not raw_input:
        raise SnapshotError("render job is missing input")

    if job.get("camera") is not None:
        job["camera"] = parse_camera_option(job["camera"])

    input_path = resolve_input_path(raw_input, cwd=resolved_cwd)
    kind = input_kind(input_path)
    if kind == "python":
        # Scripts are RUN, never rendered: `python <script>` writes the
        # document, and snapshot renders the document.
        from cadgen._internal.doors import script_target_message

        raise SnapshotError(script_target_message(input_path))
    if kinds is not None:
        reject_unsupported_kind(kind, input_path, kinds)
    if kind not in KIND_RESOLVERS:
        raise SnapshotError(
            f"snapshot cannot render {input_path.suffix or 'that file'} inputs: {input_path}"
        )

    # After the refusals above: a script or a foreign file is told what IT is,
    # not what its display settings would have meant. A job's own `display` gets
    # the same treatment as the --display flag — a mode name, an inline JSON
    # object, or a path to a display JSON — and is validated ONCE: here, unless
    # the flag already put a validated one on the job.
    display = load_display_option(
        job["display"] if job.get("display") is not None else {},
        cwd=resolved_cwd,
        modes=display_modes_for_kind(kind),
    )
    validate_display_for_kind(display, kind=kind, input_label=input_path.name)
    job["display"] = display
    mode = normalize_render_mode(job.get("mode"))
    lighting = display.get("lighting")
    lighting_enabled = (
        lighting.get("enabled", True) if is_plain_object(lighting) else display.get("mode") == "render"
    )
    if lighting_enabled and mode != "view":
        raise SnapshotError("Render display supports only view mode")

    validate_selection_keys(job)
    selection = job.get("selection") if is_plain_object(job.get("selection")) else {}
    if selection_value_list(selection.get("focus")) and selection_value_list(selection.get("hide")):
        raise SnapshotError("selection.focus and selection.hide cannot be used in the same snapshot job")

    context = KIND_CHECKS[kind](job, kind=kind, input_path=input_path, mode=mode) or {}
    normalized = normalize_common_job(
        job,
        mode=mode,
        resolved_cwd=resolved_cwd,
        timestamp=timestamp,
        job_index=job_index,
        job_count=job_count,
    )
    return PreparedRenderJob(
        job=normalized,
        kind=kind,
        input_path=input_path,
        root_path=input_path.parent.resolve(),
        reference_root=reference_root_for_input(input_path, resolved_cwd),
        resolved_cwd=resolved_cwd,
        context=dict(context),
    )


def resolve_prepared_render_job(prepared: PreparedRenderJob) -> dict[str, object]:
    """Build what an accepted job's render needs and attach it as ``resolved``."""
    return KIND_RESOLVERS[prepared.kind](
        prepared.job,
        kind=prepared.kind,
        input_path=prepared.input_path,
        root_path=prepared.root_path,
        reference_root=prepared.reference_root,
        resolved_cwd=prepared.resolved_cwd,
        **prepared.context,
    )


def resolve_render_job(
    raw_job: object,
    *,
    cwd: Path | None = None,
    timestamp: str | None = None,
    kinds: frozenset[str] | None = None,
    job_index: int = 0,
    job_count: int = 1,
) -> dict[str, object]:
    return resolve_prepared_render_job(
        prepare_render_job(
            raw_job, cwd=cwd, timestamp=timestamp, kinds=kinds,
            job_index=job_index, job_count=job_count,
        )
    )


def check_step_render_job(
    job: dict[str, object],
    *,
    kind: str,
    input_path: Path,
    mode: str,
    **_context: object,
) -> None:
    """What a STEP request can be refused for without its tree.

    The request shapes, the mode rules, the video's container and encoder, and —
    read from the sidecar beside the document, which costs a hash rather than a
    compile — the pose and clip NAMES. Selection refs are the one STEP refusal
    left to resolution: they are checked against the tree itself.
    """
    if job.get("jointValues") is not None:
        raise SnapshotError(
            "jointValues pose a robot description (URDF, SRDF or SDF); "
            "pose a STEP model with kinematics"
        )
    has_param_render = has_kinematics_render_values(job.get("kinematics"))
    # The frame request is validated for SHAPE here (a packet may carry it
    # directly, so it did not necessarily pass through the flag parser).
    animation_request: dict[str, object] | None = None
    if job.get("animation") is not None:
        animation_request = normalize_animation_request(job["animation"], where="render job animation")
        job["animation"] = animation_request
    # A video is the SPAN of a clip, so it needs the clip, and it cannot also be
    # a moment of one. The flag pair is refused at the door (snapshot_door);
    # this holds the same two rules for a packet that carries the fields
    # directly, and resolves ffmpeg before anything expensive runs.
    if job.get("video") is not None:
        video_request = normalize_video_request(job["video"], where="render job video")
        if animation_request is None:
            raise SnapshotError(
                "video requires animation: name the clip the sequence renders"
            )
        # `animation.time` and `video.start` are the same number, and a video
        # reads only the second. A time of 0 is indistinguishable from an unset
        # one (the normalizer fills it, and so does the --animation flag), so
        # only a time that would actually be ignored is refused.
        if animation_request["time"]:
            raise SnapshotError(
                "a video renders a span, not a moment: the animation names time "
                f"{animation_request['time']}, which a sequence ignores — say where it "
                "begins with video start instead"
            )
        job["video"] = video_request
        # A typo in a file extension is not worth the minutes a cold STEP takes to
        # compile, and an encoder discovered missing at the end of those same
        # minutes is the other failure this ordering exists to prevent.
        for output in job.get("outputs") or []:
            video_container_for_path(declared_output_path(output))
        ffmpeg_binary()
    if has_param_render and mode != "view":
        raise SnapshotError("kinematics values support only view mode; set display.mode for display-style changes")
    if animation_request is not None and mode != "view":
        raise SnapshotError("an animation frame supports only view mode; set display.mode for display-style changes")
    if has_param_render or animation_request is not None:
        from cadgen._internal.source_sidecar import read_source_sidecar

        check_step_pose_and_clip_names(
            job, read_source_sidecar(input_path) or {}, input_name=input_path.name
        )


def check_step_pose_and_clip_names(
    job: Mapping[str, object], sidecar: Mapping[str, object], *, input_name: str
) -> None:
    """A pose NAME, every DOF id and the clip name, against what the model declares.

    A typo must fail as a clean CLI error naming what the model has, not as a
    stack trace out of the browser runtime — which repeats these checks, with the
    compiled clips in hand, as the backstop and the authority for a module that
    builds its clips indirectly.
    """
    kinematics_block = sidecar.get("kinematics") if isinstance(sidecar.get("kinematics"), dict) else None
    preset = job.get("kinematics")
    if kinematics_block:
        if isinstance(preset, str) and preset.strip():
            poses = kinematics_block.get("poses")
            declared = sorted(poses) if isinstance(poses, dict) else []
            if preset.strip() not in declared:
                raise SnapshotError(
                    f"Unknown kinematics pose: {preset.strip()}. "
                    + (
                        f"This model declares: {', '.join(declared)}"
                        if declared
                        else "This model declares no poses; pass {dof: value} JSON instead"
                    )
                )
        elif is_plain_object(preset):
            from cadgen.kinematics import kinematics_dof_ids

            dofs = set(kinematics_dof_ids(kinematics_block))
            unknown = sorted(str(key) for key in preset if str(key) not in dofs)
            if unknown:
                raise SnapshotError(
                    f"Unknown kinematics DOF(s): {', '.join(unknown)}. "
                    f"This model declares: {', '.join(sorted(dofs)) or '(none)'}"
                )
    elif has_kinematics_render_values(preset):
        raise SnapshotError(
            f"{input_name} declares no kinematics, so pose values have nothing to "
            "drive — declare kinematics= (typed mates) on the model's @step; "
            "see the cad skill's kinematics reference"
        )
    animation_request = job.get("animation")
    if is_plain_object(animation_request):
        animation_block = sidecar.get("animation")
        if animation_block is None:
            raise SnapshotError(
                f"{input_name} has no animation in its sidecar. "
                "Declare animation= on @step or pass --animation to cadgen step build."
            )
        from cadgen._internal.animation_source import declared_clip_ids

        clip_name = str(animation_request["clip"])
        declared_clips = declared_clip_ids(animation_block["source"])
        if declared_clips is not None and clip_name not in declared_clips:
            raise SnapshotError(
                f"Unknown animation clip: {clip_name}. "
                + (
                    f"This model declares: {', '.join(declared_clips)}"
                    if declared_clips
                    else "This model declares no animation clips"
                )
            )


def resolve_step_render_job(
    job: dict[str, object],
    *,
    kind: str,
    input_path: Path,
    root_path: Path,
    reference_root: Path,
    **_kind_context: object,
) -> dict[str, object]:
    """Build what a STEP render needs: its tree, its selector index, its sidecar.

    ``job`` is the prepared job (:func:`check_step_render_job` accepted the
    request). A render is a READ of the tree behind the document's bytes, compiled
    from them on demand when the store has none. Whether the document's source has
    moved on is its model's business, never a render's.
    """
    debug_enabled = bool(job.get("debug"))
    step_artifact_debug: dict[str, object] | None = {} if debug_enabled else None
    artifact = ensure_render_job_step_artifact(
        job,
        reference_root=reference_root,
        input_path=input_path,
        step_path=input_path,
        require_selector=selection_requires_selector_topology(job),
        debug_info=step_artifact_debug,
    )
    normalized_selection = normalize_render_job_selection(
        job,
        expected_cad_path=cad_ref_for_step_path(reference_root, input_path),
        selector_index=artifact_selector_index(artifact),
    )

    # Select the document digest and tree in one lookup. Materialising by that
    # tree, rather than resolving the mutable path again, keeps every component
    # URL and the sidecar binding on the same revision.
    document_hash, selected_tree = document_snapshot(input_path)
    package_dir = view_dir_for(selected_tree, document_hash=document_hash)
    if not package_dir.is_dir():
        raise SnapshotError(f"STEP/STP render input has no tree in the store: {package_dir}")

    resolved: dict[str, object] = {
        "rootPath": str(root_path),
        "inputPath": str(input_path),
        "inputUrl": asset_url_for_path(input_path, root_path),
        "kind": kind,
        # The hash of the tree this job renders: the geometry's identity in the
        # result (cadgen.results.SnapshotFile.tree), never a directory.
        "tree": selected_tree,
    }
    # tree (the canonical render artifact for every STEP model): inline
    # the assembly.json and pre-resolve one asset URL per unique component so the renderer
    # fetches and composes them in world space.
    descriptor = json.loads((package_dir / "assembly.json").read_text(encoding="utf-8"))
    artifact_manifest = getattr(artifact, "manifest", None)
    if isinstance(artifact_manifest, Mapping) and artifact_manifest != descriptor:
        raise SnapshotError(
            "STEP/STP render input changed while its topology was being resolved; retry the snapshot"
        )
    # This is the renderer's private descriptor loaded from the selected view,
    # never the immutable tree object.
    descriptor["documentHash"] = document_hash
    from cadgen.snapshot_core import asset_url_for_store_path

    component_urls = {
        cid: asset_url_for_store_path(package_dir / str(entry.get("surf", "")))
        for cid, entry in (descriptor.get("components") or {}).items()
    }
    resolved["package"] = {"descriptor": descriptor, "componentUrls": component_urls}
    from cadgen._internal.source_sidecar import (
        read_source_sidecar,
        source_sidecar_path,
        validate_appearance_targets,
    )

    resolved["documentHash"] = document_hash
    # Kinematics, animation and materials come from the same pinned annotation
    # snapshot. The pose and clip names were checked when the job was prepared.
    sidecar = read_source_sidecar(input_path, document_hash=document_hash) or {}
    if sidecar.get("appearance") is not None:
        # Validate canonical occurrence targets here for a clean CLI error;
        # the browser repeats the same check before it composes its own copy.
        validate_appearance_targets(descriptor, sidecar["appearance"])
    if sidecar:
        # The shared JS source resolver validates the same document binding and
        # composes appearance into its private descriptor. Inline data avoids a
        # second browser fetch and leaves the store descriptor untouched.
        resolved["sourceSidecar"] = sidecar
    if isinstance(sidecar.get("kinematics"), dict) and sidecar["kinematics"]:
        # Typed mates are the articulation mechanism: --kinematics DOF values
        # fold through the shared FK evaluator (@hardcore/core kinematicsModule),
        # which reads the sidecar's kinematics section.
        resolved["stepParameterUrl"] = asset_url_for_path(source_sidecar_path(input_path), root_path)
    if debug_enabled:
        resolved["debug"] = {"stepArtifact": step_artifact_debug}

    resolved_job = {**job, "resolved": resolved}
    if normalized_selection is not None:
        resolved_job["selection"] = normalized_selection
    return resolved_job


# A DXF is DRAWN, not staged: `cadgen dxf snapshot` paints the same
# `cadgen.drawing_payload` the CAD Viewer's DXF pane paints, with the same
# core code (@hardcore/core/lib/drawing2d), so the CLI cannot show a picture
# the viewer cannot. Everything below is what that costs the option surface.
#
# `appearance` is the whole of a drawing's display: it picks the background,
# and therefore the colour of an entity with no pen of its own (ACI 7).
DRAWING_DISPLAY_KEYS = frozenset({"appearance"})
# Output settings that still mean something for a picture with no scene.
DRAWING_OUTPUT_SETTINGS_KEYS = frozenset({"sizeProfile", "renderScale", "transparent"})
# ...and why each of the others does not.
DRAWING_OUTPUT_SETTING_REASONS = {
    "padding": (
        "a drawing is fitted with the fixed gutter the viewer leaves around it, "
        "and there is no camera to pull further back"
    ),
    "viewLabels": "a drawing has no camera, so there is no view name to burn into the image",
    "tightFrame": (
        "a tight frame re-fits a camera to projected geometry; a drawing is already "
        "framed on the bounds of what it draws"
    ),
}
# What a drawing IS, said once: every refusal below opens with it.
_DRAWING_IS = "a DXF is drawn as a flat 2D drawing, fitted to the image and painted head on"


def _drawing_output_cameras(job: Mapping[str, object]) -> bool:
    outputs = job.get("outputs") if isinstance(job.get("outputs"), list) else []
    return any(is_plain_object(output) and output.get("camera") is not None for output in outputs)


def _drawing_output_labels(job: Mapping[str, object]) -> list[str]:
    outputs = job.get("outputs") if isinstance(job.get("outputs"), list) else []
    return sorted({
        key
        for output in outputs
        if is_plain_object(output)
        for key in ("label", "viewLabel")
        if output.get(key) is not None
    })


def check_drawing_render_job(
    job: Mapping[str, object], *, input_path: Path, mode: str, **_context: object
) -> None:
    """What a drawing cannot be asked for: anything that describes a 3D scene.

    This door used to render a DXF as a 3D flat pattern, so it took a camera,
    display settings and a render mode. It does not any more — the viewer shows
    a drawing, and what the viewer cannot show the CLI does not render — and
    every one of those requests is refused BY NAME here rather than accepted
    and quietly ignored. This is also the path `cadgen snapshot` routes a `.dxf`
    through, so the two cannot disagree.
    """
    label = input_path.name
    display = job.get("display") if is_plain_object(job.get("display")) else {}
    scene = sorted(f"display.{key}" for key in set(display) - DRAWING_DISPLAY_KEYS)
    if scene:
        raise SnapshotError(
            f"{', '.join(scene)} {'describes' if len(scene) == 1 else 'describe'} a 3D scene — "
            f"a render mode, surfaces, lighting, a floor; {_DRAWING_IS}, so {label} has none of "
            "them. Light or dark is the whole of a drawing's appearance: pass "
            '--appearance light|dark (in a job, "display": {"appearance": "dark"}).'
        )
    if job.get("camera") is not None or _drawing_output_cameras(job):
        raise SnapshotError(
            f"camera poses a model in space; {_DRAWING_IS}, so {label} has no camera and no views "
            "to choose between — it is always shown whole, the way it was drawn."
        )
    if mode != "view" or job.get("section") is not None:
        raise SnapshotError(
            f"{_DRAWING_IS}: it has no parts to list and no solid to section, so view is the only "
            f"mode {label} renders in."
        )
    if job.get("scale") is not None:
        raise SnapshotError(
            f"scale picks the units a 3D scene is lit and framed for (cad or urdf); {_DRAWING_IS} "
            f"in its own drawing units, so {label} has no scene to scale."
        )
    labels = _drawing_output_labels(job)
    if labels:
        raise SnapshotError(
            f"an output's {' and '.join(labels)} names the view burnt into the image; {_DRAWING_IS} "
            f"and {label} has no view to name."
        )
    settings = job.get("output") if is_plain_object(job.get("output")) else {}
    unsupported = sorted(set(settings) - DRAWING_OUTPUT_SETTINGS_KEYS)
    if unsupported:
        # Every one of them, with its own reason: fixing them one refusal per run
        # is three runs to learn what one message can say.
        reasons = "; ".join(
            f"{key} — {DRAWING_OUTPUT_SETTING_REASONS.get(key, _DRAWING_IS)}" for key in unsupported
        )
        named = ", ".join(f"output.{key}" for key in unsupported)
        raise SnapshotError(
            f"{named} {'has' if len(unsupported) == 1 else 'have'} no meaning for a DXF "
            f"({reasons}). A drawing's output takes: "
            f"{', '.join(sorted(DRAWING_OUTPUT_SETTINGS_KEYS))}."
        )
    # The refusals every non-STEP input shares (selection, poses, clips, videos,
    # tessellation). Mode and section are already decided above, with a sentence
    # about drawings rather than about mesh inputs.
    refuse_cad_model_requests(
        job,
        mode=mode,
        subject="DXF drawings",
        pose_hint="a DXF drawing has no kinematics",
        tessellation_hint="a DXF drawing is line work, not a tessellated surface",
    )


def resolve_drawing_render_job(
    job: dict[str, object],
    *,
    kind: str,
    input_path: Path,
    **_kind_context: object,
) -> dict[str, object]:
    """Resolve a `.dxf` drawing: its 2D render payload, on a path the page can fetch.

    There is no drawing package and nothing to build — the `.dxf` IS the
    product. What the render needs is the SAME payload
    (:mod:`cadgen.drawing_payload`) the Viewer's `GET /__cad/drawing` answers
    with: ezdxf flattens the modelspace once, the store caches it by the
    document's content hash, and the page draws it.
    """
    payload_path = drawing_payload_file(input_path)
    serve_root = payload_path.parent
    resolved: dict[str, object] = {
        "rootPath": str(serve_root),
        "inputPath": str(input_path),
        "kind": kind,
        "drawingUrl": asset_url_for_path(payload_path, serve_root),
    }
    if bool(job.get("debug")):
        resolved["debug"] = {"drawingSource": {"kind": kind, "payloadBytes": payload_path.stat().st_size}}
    return {**job, "resolved": resolved}


@functools.lru_cache(maxsize=1)
def _drawing_payload_dir() -> Path:
    """One directory per process for resolved drawing payloads, removed at exit.

    The page fetches the payload over the host's loopback asset server, which
    serves FILES; inlining a megabyte of JSON into the job would instead push it
    through the Playwright driver pipe as one escaped protocol message, which is
    the transport that fails on real drawings. The expensive half — ezdxf — is
    cached in the store, so this is only ever a write of bytes already in hand.
    """
    import atexit
    import shutil
    import tempfile

    directory = Path(tempfile.mkdtemp(prefix="cadgen-drawing-payload-"))
    atexit.register(shutil.rmtree, directory, True)
    return directory


def drawing_payload_file(source: Path) -> Path:
    """The `.dxf`'s 2D render payload, written where the render can fetch it.

    Named by the payload's own content hash, so two jobs over the same drawing
    (and two runs in one process) share one file.
    """
    from hashlib import sha256

    from cadgen._internal.atomic_replace import write_bytes_atomic
    from cadgen.drawing_payload import DrawingReadError, drawing_payload_bytes

    if not source.name.lower().endswith(".dxf"):
        raise SnapshotError(f"snapshot input must be a .dxf document: {source}")
    if not source.is_file():
        raise SnapshotError(f"snapshot input does not exist: {source}")
    try:
        data = drawing_payload_bytes(source)
    except DrawingReadError as error:
        # The payload reader's messages already name the file and what to do
        # about it; this only moves them onto the snapshot's error type.
        raise SnapshotError(str(error)) from None
    payload_path = _drawing_payload_dir() / f"{sha256(data).hexdigest()}.drawing.json"
    if not payload_path.is_file():
        write_bytes_atomic(payload_path, data)
    return payload_path


# Kind dispatch for render-job resolution. Every resolver takes the same
# signature (job plus the resolved input-kind context) and returns the common
# normalized job shape with a kind-specific ``resolved`` payload — adding a new
# input kind is one table entry, not another if-chain arm plus a copied tail.
_STEP_KIND = (check_step_render_job, resolve_step_render_job)
_MESH_KIND = (check_mesh_render_job, resolve_mesh_render_job)
_ROBOT_KIND = (check_robot_render_job, resolve_robot_render_job)
_KINDS: dict[str, tuple[Callable[..., object], Callable[..., dict[str, object]]]] = {
    "step": _STEP_KIND,
    "stp": _STEP_KIND,
    "glb": _MESH_KIND,
    "stl": _MESH_KIND,
    "3mf": _MESH_KIND,
    "dxf": (check_drawing_render_job, resolve_drawing_render_job),
    "urdf": _ROBOT_KIND,
    "srdf": _ROBOT_KIND,
    "sdf": _ROBOT_KIND,
}
# Each kind is a CHECK (what its request can be refused for, deciding nothing
# that needs a build) and a RESOLVER (what its render needs built).
KIND_CHECKS = {kind: check for kind, (check, _resolve) in _KINDS.items()}
KIND_RESOLVERS = {kind: resolve for kind, (_check, resolve) in _KINDS.items()}


# What each kind is called in errors, and the order a reader wants them listed
# in. Help is the verb signature's business now; this survives because a refusal
# still has to say what the door DOES take.
KIND_LABELS: dict[str, str] = {
    "step": ".step", "stp": ".stp",
    "glb": ".glb", "stl": ".stl", "3mf": ".3mf",
    "dxf": ".dxf",
    "urdf": ".urdf", "srdf": ".srdf", "sdf": ".sdf",
}

_KIND_HELP_ORDER = ("step", "stp", "3mf", "glb", "stl", "dxf", "urdf", "srdf", "sdf")


def enabled_kinds(kinds: Sequence[str]) -> frozenset[str]:
    """A door's declared kinds, checked against the kinds that resolve at all."""
    resolved: set[str] = set()
    for kind in kinds:
        name = str(kind).strip().lower()
        if not name:
            continue
        if name not in KIND_RESOLVERS:
            raise SnapshotError(f"unknown snapshot input kind: {kind!r}")
        resolved.add(name)
    return frozenset(resolved)


# The cadgen command that owns each mesh format's snapshot. Named in the refusal
# because these moved: `cadgen step snapshot` rendered meshes until the door split,
# so a caller reaching the STEP door with a `.stl` is following instructions that
# were right, and "it accepts .step" alone does not tell them where it went. Safe
# to name, unlike a SKILL: every one of these ships in this same distribution.
MESH_SNAPSHOT_DOORS: dict[str, str] = {
    "stl": "cadgen stl snapshot",
    "3mf": "cadgen 3mf snapshot",
    "glb": "cadgen glb snapshot",
}


def reject_unsupported_kind(kind: str, input_path: Path, enabled: frozenset[str]) -> None:
    """Refuse an input this door does not render.

    A shared implementation makes every door CAPABLE of every format, so the gate is the
    only thing keeping `step snapshot` from quietly rendering a robot. It states what this
    door takes and stops there: naming another SKILL would assume that skill is installed,
    and skills ship independently. A sibling cadgen COMMAND is different — it is in the
    same distribution, so the mesh doors are named outright.
    """
    if kind in enabled:
        return
    label = KIND_LABELS.get(kind, f".{kind}") if kind else input_path.suffix or "that file"
    accepted = ", ".join(
        KIND_LABELS[name]
        for name in _KIND_HELP_ORDER
        if name in enabled and name in KIND_LABELS
    )
    door = MESH_SNAPSHOT_DOORS.get(kind)
    where = f" Mesh inputs have their own door: `{door} TARGET OUT`." if door else ""
    raise SnapshotError(
        f"snapshot does not render {label} inputs: {input_path}.{where} "
        f"It accepts: {accepted or '(nothing)'}."
    )


def prepare_render_job_packet(
    raw_payload: object,
    *,
    cwd: Path | None = None,
    kinds: frozenset[str] | None = None,
) -> tuple[bool, list[PreparedRenderJob]]:
    """Accept or refuse every job in the packet; build and delete nothing."""
    single, jobs = normalize_snapshot_job_packet(raw_payload)
    # ONE timestamp for the whole packet: a multi-view run reads as one run, not
    # as N runs that happened to be close together. That is also why every
    # generated name in the packet needs a discriminator that covers the job as
    # well as the output (see generated_output_name).
    timestamp = snapshot_timestamp()
    return single, [
        prepare_render_job(
            job,
            cwd=cwd,
            timestamp=timestamp,
            kinds=kinds,
            job_index=index,
            job_count=len(jobs),
        )
        for index, job in enumerate(jobs)
    ]


def resolve_prepared_job_packet(single: bool, prepared: Sequence[PreparedRenderJob]) -> dict[str, object]:
    return {"single": single, "jobs": [resolve_prepared_render_job(job) for job in prepared]}


def resolve_render_job_packet(
    raw_payload: object,
    *,
    cwd: Path | None = None,
    kinds: frozenset[str] | None = None,
) -> dict[str, object]:
    single, prepared = prepare_render_job_packet(raw_payload, cwd=cwd, kinds=kinds)
    return resolve_prepared_job_packet(single, prepared)


def snapshot_narrator(logger: CliLogger) -> Callable[[str], None] | None:
    """Words for a run the progress line cannot paint, or None when it can.

    `cli_progress_line` disables itself on a non-tty, so a snapshot run from a
    script, a pipe or an agent's tool call shows nothing for as long as it takes —
    and `--video` takes minutes. These lines fill exactly that gap. Under
    --verbose the bar stands down for the logger, and lines are what the caller
    asked for anyway.

    None when the bar IS painting -- the two together smear, because the live
    line repaints with \\r and a printed line lands on top of it.
    """
    if logger.verbose:
        return logger.info
    stream = logger.stream if logger.stream is not None else sys.stderr
    if getattr(stream, "isatty", lambda: False)():
        return None
    return logger.info


def snapshot_progress_label(packet: object) -> str:
    """The header the progress line commits: what this run is rendering."""
    jobs = packet.get("jobs") if isinstance(packet, dict) else None
    if not isinstance(jobs, list) or not jobs:
        return "snapshot"
    if len(jobs) == 1:
        return str(jobs[0].get("input") or "snapshot")
    return f"snapshot ({len(jobs)} jobs)"


async def run_snapshot_async(
    options: SnapshotOptions,
    *,
    kinds: Sequence[str],
    runtime_dir: Path | None = None,
    cwd: Path | None = None,
) -> SnapshotResult:
    """Render whatever ``options`` describes and report what was written.

    THE snapshot implementation: the CLI parses argv into ``options`` and prints
    what comes back, and the public ``<format>.snapshot()`` verbs build the same
    options object. Nothing here prints, so the two cannot report differently.
    """
    enabled = enabled_kinds(kinds)
    raw_payload = load_job_from_options(options, cwd=cwd)
    # Accept the whole request FIRST. A refused request -- an unknown key, a
    # setting this input cannot take, options that conflict -- was never going to
    # write anything, so it must leave an existing OUT exactly as it found it.
    single, prepared = prepare_render_job_packet(raw_payload, cwd=cwd, kinds=enabled)
    # Then clear the declared outputs, BEFORE resolution, which is where a bad
    # input actually fails. The path a caller names is the path it gets, and that
    # is only safe to promise if a run that never renders leaves nothing behind for
    # the caller to read as though it had.
    clear_render_output_targets(
        normalize_snapshot_job_packet(raw_payload)[1], resolved_cwd=cwd or Path.cwd()
    )
    # Resolution is where a STEP tree gets compiled, and on a cold model that is
    # the SLOWEST part of a snapshot -- longer than the render. It is deliberately NOT
    # wrapped in a phase of ours: that build reports its own phases through artifact_build,
    # and a second painter on the same terminal would both interleave with it and replace
    # its detail with the single word "resolving".
    packet = resolve_prepared_job_packet(single, prepared)
    logger = CliLogger("snapshot", verbose=False)
    with cli_progress_line(
        snapshot_progress_label(packet), logger=logger, fallback="Rendering..."
    ) as sink:
        progress = ProgressReporter(
            sinks=[sink] if sink is not None else (),
            phases=SNAPSHOT.phases,
            labels=SNAPSHOT.labels,
        )
        progress.phase(PHASE_BROWSER)
        result = await render_snapshot(
            packet,
            runtime_dir=browser_runtime_dir(runtime_dir),
            progress=progress,
            narrate=snapshot_narrator(logger),
        )
        progress.finish()
    return result


def run_snapshot(
    options: SnapshotOptions,
    *,
    kinds: Sequence[str],
    runtime_dir: Path | None = None,
    cwd: Path | None = None,
) -> SnapshotResult:
    """:func:`run_snapshot_async` for a synchronous caller (the CLI, the verbs)."""
    return asyncio.run(run_snapshot_async(options, kinds=kinds, runtime_dir=runtime_dir, cwd=cwd))
