from __future__ import annotations

import asyncio
import base64
import copy
import json
import mimetypes
import os
import re
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
PACKAGES_DIR = SCRIPTS_DIR / "packages"
CADPY_SRC_DIR = PACKAGES_DIR / "cadpy" / "src"
for runtime_path in (SCRIPTS_DIR, CADPY_SRC_DIR, PACKAGES_DIR):
    runtime_path_text = str(runtime_path)
    if runtime_path_text not in sys.path:
        sys.path.insert(0, runtime_path_text)

import cadpy.cad_ref_syntax as cad_ref_syntax
import cadpy.lookup as lookup
from cadpy.render import existing_part_glb_path, part_glb_path
from cadpy.step_targets import ResolvedStepTarget, StepTopologyArtifact, StepTopologyArtifactError


SNAPSHOT_ORIGIN = "http://snapshot.local"
SNAPSHOT_RENDER_URL = f"{SNAPSHOT_ORIGIN}/render.html"
SNAPSHOT_ROUTE_GLOB = f"{SNAPSHOT_ORIGIN}/**"
RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
RENDER_HTML_PATH = RUNTIME_DIR / "render.html"
DEFAULT_RENDER_THEME_ID = "workbench"
DEFAULT_TIMEOUT_SECONDS = 300
RENDER_BROWSER_STARTUP_TIMEOUT_MS = 15_000
SUPPORTED_RENDER_MODES = {"view", "orbit", "section", "list"}
WORKBENCH_RENDER_THEME_IDS = {DEFAULT_RENDER_THEME_ID}

SIMPLE_RENDER_WIDTH = 1200
SIMPLE_RENDER_HEIGHT = 900
SIMPLE_SQUARE_RENDER_WIDTH = 1024
SIMPLE_SQUARE_RENDER_HEIGHT = 1024
DIAGNOSTIC_RENDER_WIDTH = 1600
DIAGNOSTIC_RENDER_HEIGHT = 1200
COMPLEX_ASSEMBLY_RENDER_WIDTH = 1800
COMPLEX_ASSEMBLY_RENDER_HEIGHT = 1200
COMPLEX_ASSEMBLY_LARGE_RENDER_WIDTH = 1920
COMPLEX_ASSEMBLY_LARGE_RENDER_HEIGHT = 1440
PRESENTATION_RENDER_WIDTH = 2400
PRESENTATION_RENDER_HEIGHT = 1600
PRESENTATION_LARGE_RENDER_WIDTH = 2800
PRESENTATION_LARGE_RENDER_HEIGHT = 1800
ORBIT_RENDER_WIDTH = 960
ORBIT_RENDER_HEIGHT = 640
CONTACT_SHEET_RENDER_WIDTH = 2400
CONTACT_SHEET_RENDER_HEIGHT = 1600

DISPLAY_OPTION_KEYS = {"mode", "clip"}
DISPLAY_MODE_ALIASES = {
    "solid": "solid",
    "edges": "solid",
    "edge": "solid",
    "shaded_edges": "solid",
    "shaded_with_edges": "solid",
    "with_edges": "solid",
    "shaded": "rendered",
    "shaded_without_edges": "rendered",
    "without_edges": "rendered",
    "transparent": "transparent",
    "translucent": "transparent",
    "xray": "transparent",
    "x_ray": "transparent",
    "see_through": "transparent",
    "hidden_edges": "hidden_edges",
    "hidden_edge": "hidden_edges",
    "hidden_edges_visible": "hidden_edges",
    "hidden_edge_display": "hidden_edges",
    "shaded_hidden_edges": "hidden_edges",
    "hidden_lines_removed": "hidden_lines_removed",
    "hidden_line_removed": "hidden_lines_removed",
    "hidden_lines": "hidden_lines_removed",
    "hidden_edges_removed": "hidden_lines_removed",
    "visible_edges": "hidden_lines_removed",
    "visible_edges_only": "hidden_lines_removed",
    "unshaded": "unshaded",
    "flat": "unshaded",
    "rendered": "rendered",
    "appearance": "rendered",
    "material": "rendered",
    "materials": "rendered",
    "wireframe": "wireframe",
    "wire_frame": "wireframe",
    "wire": "wireframe",
}
APPEARANCE_OPTION_KEYS = {
    "materials",
    "edges",
    "background",
    "floor",
    "environment",
    "lighting",
}


ensure_step_topology_artifact = None


@dataclass
class SnapshotOptions:
    job: str = ""
    input: str = ""
    output: str = ""
    mode: str = "view"
    appearance: object = DEFAULT_RENDER_THEME_ID
    appearance_specified: bool = False
    display: object = ""
    display_specified: bool = False
    camera: object = "iso"
    camera_specified: bool = False
    width: int | None = None
    height: int | None = None
    size_profile: str = ""
    params: object = None
    params_specified: bool = False
    focus: list[str] | None = None
    hide: list[str] | None = None
    view_labels: bool = False
    json: bool = False
    help: bool = False


class SnapshotError(RuntimeError):
    pass


class RouteFileError(SnapshotError):
    def __init__(self, message: str, *, status: int = 404) -> None:
        super().__init__(message)
        self.status = status


def help_text() -> str:
    return """Usage:
  python scripts/snapshot --job render-job.json
  python scripts/snapshot --job -
  python scripts/snapshot --input models/part.step --output /tmp/part.png --appearance workbench

Shortcut flags are for common STEP/STP snapshots. --job accepts one render job, an array of render jobs, or { "jobs": [...] }. Every job input must be a relative or absolute .step/.stp path, or a same-stem Python generator; direct GLB/STL/3MF/DXF/G-code/robot-description inputs are unsupported. The default appearance is the workbench saved theme. --appearance accepts a saved theme name, an inline JSON appearance settings object, or a JSON appearance settings file path. --display accepts solid, rendered, transparent, hidden_edges, hidden_lines_removed, unshaded, wireframe, an inline JSON display settings object, or a JSON display settings file path. --camera accepts a preset, azimuth:elevation pair, or JSON object with preset, position, target, up, and zoom fields. --focus and --hide accept one or more selector refs such as #o1.2 for parts or subassemblies; pass the flag repeatedly or list refs after the flag. Option JSON is direct settings JSON, not a wrapped job fragment. Full JSON jobs use top-level appearance and display. Use --view-labels to burn the camera/view label into shortcut outputs. Use --params with STEP parameter sidecar JSON values, and --size-profile for default dimensions such as simple, diagnostic, labeled, assembly, presentation, orbit, or contact-sheet. Output file names are saved with a shared UTC seconds timestamp before the extension.
"""


def positive_integer(value: object, label: str) -> int:
    try:
        parsed = int(str(value or ""), 10)
    except ValueError as exc:
        raise SnapshotError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise SnapshotError(f"{label} must be a positive integer")
    return parsed


def parse_required_value(argv: Sequence[str], index: int, flag: str) -> str:
    try:
        value = argv[index + 1]
    except IndexError as exc:
        raise SnapshotError(f"{flag} requires a value") from exc
    if not value or value.startswith("--"):
        raise SnapshotError(f"{flag} requires a value")
    return value


def parse_required_values(argv: Sequence[str], index: int, flag: str) -> tuple[list[str], int]:
    values: list[str] = []
    cursor = index + 1
    while cursor < len(argv):
        value = argv[cursor]
        if value.startswith("--"):
            break
        if value:
            values.append(value)
        cursor += 1
    if not values:
        raise SnapshotError(f"{flag} requires at least one value")
    return values, cursor - index - 1


def parse_snapshot_args(argv: Sequence[str]) -> SnapshotOptions:
    if argv and argv[0] == "daemon":
        raise SnapshotError("snapshot daemon commands have been removed; use a batch --job snapshot instead")

    options = SnapshotOptions()
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in {"--help", "-h"}:
            options.help = True
        elif arg == "--json":
            options.json = True
        elif arg == "--no-daemon":
            raise SnapshotError("--no-daemon has been removed; snapshot no longer uses a daemon")
        elif arg == "--socket" or arg.startswith("--socket="):
            raise SnapshotError("--socket has been removed; snapshot no longer uses a daemon")
        elif arg == "--view-labels":
            options.view_labels = True
        elif arg == "--job":
            options.job = parse_required_value(argv, index, arg)
            index += 1
        elif arg.startswith("--job="):
            options.job = arg[len("--job=") :]
        elif arg == "--input":
            options.input = parse_required_value(argv, index, arg)
            index += 1
        elif arg.startswith("--input="):
            options.input = arg[len("--input=") :]
        elif arg in {"--output", "-o"}:
            options.output = parse_required_value(argv, index, arg)
            index += 1
        elif arg.startswith("--output="):
            options.output = arg[len("--output=") :]
        elif arg == "--mode":
            options.mode = parse_required_value(argv, index, arg)
            index += 1
        elif arg.startswith("--mode="):
            options.mode = arg[len("--mode=") :]
        elif arg == "--appearance":
            options.appearance = parse_required_value(argv, index, arg)
            options.appearance_specified = True
            index += 1
        elif arg.startswith("--appearance="):
            options.appearance = arg[len("--appearance=") :]
            options.appearance_specified = True
        elif arg == "--display":
            options.display = parse_required_value(argv, index, arg)
            options.display_specified = True
            index += 1
        elif arg.startswith("--display="):
            options.display = arg[len("--display=") :]
            options.display_specified = True
        elif arg == "--params":
            options.params = parse_required_value(argv, index, arg)
            options.params_specified = True
            index += 1
        elif arg.startswith("--params="):
            options.params = arg[len("--params=") :]
            options.params_specified = True
        elif arg == "--focus":
            values, consumed = parse_required_values(argv, index, arg)
            options.focus = [*(options.focus or []), *values]
            index += consumed
        elif arg.startswith("--focus="):
            value = arg[len("--focus=") :]
            if not value:
                raise SnapshotError("--focus requires at least one value")
            options.focus = [*(options.focus or []), value]
        elif arg == "--hide":
            values, consumed = parse_required_values(argv, index, arg)
            options.hide = [*(options.hide or []), *values]
            index += consumed
        elif arg.startswith("--hide="):
            value = arg[len("--hide=") :]
            if not value:
                raise SnapshotError("--hide requires at least one value")
            options.hide = [*(options.hide or []), value]
        elif arg == "--size-profile":
            options.size_profile = parse_required_value(argv, index, arg)
            index += 1
        elif arg.startswith("--size-profile="):
            options.size_profile = arg[len("--size-profile=") :]
        elif arg == "--camera":
            options.camera = parse_required_value(argv, index, arg)
            options.camera_specified = True
            index += 1
        elif arg.startswith("--camera="):
            options.camera = arg[len("--camera=") :]
            options.camera_specified = True
        elif arg == "--width":
            options.width = positive_integer(parse_required_value(argv, index, arg), arg)
            index += 1
        elif arg.startswith("--width="):
            options.width = positive_integer(arg[len("--width=") :], "--width")
        elif arg == "--height":
            options.height = positive_integer(parse_required_value(argv, index, arg), arg)
            index += 1
        elif arg.startswith("--height="):
            options.height = positive_integer(arg[len("--height=") :], "--height")
        else:
            raise SnapshotError(f"Unknown argument: {arg}")
        index += 1
    if options.focus and options.hide:
        raise SnapshotError("--focus and --hide cannot be used in the same snapshot command")
    return options


def is_plain_object(value: object) -> bool:
    return isinstance(value, dict)


def load_json_text(text: str, source_label: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"Failed to parse JSON from {source_label}: {exc}") from exc


def parse_camera_option(raw_camera: object) -> object:
    camera = str(raw_camera or "").strip()
    if not camera:
        raise SnapshotError("--camera requires a preset, azimuth:elevation pair, or JSON camera object")
    if not camera.startswith("{"):
        return camera
    parsed = load_json_text(camera, "--camera")
    if not is_plain_object(parsed):
        raise SnapshotError("--camera must be a preset, azimuth:elevation pair, or JSON object")
    return parsed


def parse_params_option(raw_params: object) -> dict[str, object]:
    parsed = load_json_text(str(raw_params or ""), "--params")
    if not is_plain_object(parsed):
        raise SnapshotError("--params must be a STEP parameter JSON object")
    return parsed


def option_focus_hide_specified(options: SnapshotOptions) -> bool:
    return bool(options.focus or options.hide)


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


def validate_direct_settings_payload(
    parsed: object,
    *,
    option_name: str,
    source_label: str,
    allowed_keys: set[str],
    setting_label: str,
) -> dict[str, object]:
    if not is_plain_object(parsed):
        raise SnapshotError(f"{option_name} JSON must be a {setting_label} object: {source_label}")
    unknown_keys = [key for key in parsed if key not in allowed_keys]
    if unknown_keys:
        raise SnapshotError(
            f"{option_name} JSON must be the {setting_label} object directly; "
            f"unsupported keys: {', '.join(unknown_keys)}"
        )
    if not parsed:
        raise SnapshotError(f"{option_name} JSON must include at least one {setting_label} field: {source_label}")
    return dict(parsed)


def load_display_option(raw_display: object, *, cwd: Path) -> dict[str, object]:
    display = str(raw_display or "").strip()
    if not display:
        raise SnapshotError("--display requires a JSON object, JSON file path, or display mode")
    if display.startswith("{"):
        return validate_direct_settings_payload(
            load_json_text(display, "--display"),
            option_name="--display",
            source_label="--display",
            allowed_keys=DISPLAY_OPTION_KEYS,
            setting_label="display settings",
        )

    display_path = Path(display) if Path(display).is_absolute() else cwd / display
    looks_like_file = display.lower().endswith(".json") or "/" in display or "\\" in display
    if not looks_like_file and not display_path.exists():
        normalized_mode = re.sub(r"[\s-]+", "_", display.lower())
        if normalized_mode not in DISPLAY_MODE_ALIASES:
            supported = ", ".join(sorted(set(DISPLAY_MODE_ALIASES.values())))
            raise SnapshotError(f"Unsupported display mode: {display}. Supported modes: {supported}")
        return {"mode": DISPLAY_MODE_ALIASES[normalized_mode]}
    if not display_path.exists():
        raise SnapshotError(f"Display JSON file does not exist: {display}")
    return validate_direct_settings_payload(
        load_json_text(display_path.read_text(encoding="utf-8"), str(display_path)),
        option_name="--display",
        source_label=str(display_path),
        allowed_keys=DISPLAY_OPTION_KEYS,
        setting_label="display settings",
    )


def load_appearance_option(raw_appearance: object, *, cwd: Path) -> object:
    appearance = str(raw_appearance or DEFAULT_RENDER_THEME_ID).strip() or DEFAULT_RENDER_THEME_ID
    if appearance.startswith("{"):
        return validate_direct_settings_payload(
            load_json_text(appearance, "--appearance"),
            option_name="--appearance",
            source_label="--appearance",
            allowed_keys=APPEARANCE_OPTION_KEYS,
            setting_label="appearance settings",
        )

    appearance_path = Path(appearance) if Path(appearance).is_absolute() else cwd / appearance
    looks_like_file = appearance.lower().endswith(".json") or "/" in appearance or "\\" in appearance
    if not looks_like_file and not appearance_path.exists():
        return appearance
    if not appearance_path.exists():
        raise SnapshotError(f"Appearance JSON file does not exist: {appearance}")
    return validate_direct_settings_payload(
        load_json_text(appearance_path.read_text(encoding="utf-8"), str(appearance_path)),
        option_name="--appearance",
        source_label=str(appearance_path),
        allowed_keys=APPEARANCE_OPTION_KEYS,
        setting_label="appearance settings",
    )


def apply_option_overrides_to_job(job: object, options: SnapshotOptions, *, cwd: Path) -> object:
    if not is_plain_object(job):
        return job
    if not any(
        [
            options.view_labels,
            options.size_profile,
            options.params_specified,
            options.display_specified,
            options.appearance_specified,
            options.camera_specified,
            option_focus_hide_specified(options),
        ]
    ):
        return job
    next_job = copy.deepcopy(job)
    merge_focus_hide_options(next_job, options)
    if options.appearance_specified:
        next_job["appearance"] = load_appearance_option(options.appearance, cwd=cwd)
    if options.params_specified:
        next_job["stepParameters"] = parse_params_option(options.params)
    if options.display_specified:
        next_job["display"] = load_display_option(options.display, cwd=cwd)
    if options.camera_specified:
        next_job["camera"] = parse_camera_option(options.camera)
    render = dict(next_job.get("render") if is_plain_object(next_job.get("render")) else {})
    if options.view_labels:
        render["viewLabels"] = True
    if options.size_profile:
        render["sizeProfile"] = options.size_profile
    next_job["render"] = render
    return next_job


def apply_option_overrides_to_payload(payload: object, options: SnapshotOptions, *, cwd: Path) -> object:
    if isinstance(payload, list):
        return [apply_option_overrides_to_job(job, options, cwd=cwd) for job in payload]
    if is_plain_object(payload) and isinstance(payload.get("jobs"), list):
        next_payload = copy.deepcopy(payload)
        next_payload["jobs"] = [apply_option_overrides_to_job(job, options, cwd=cwd) for job in payload["jobs"]]
        return next_payload
    return apply_option_overrides_to_job(payload, options, cwd=cwd)


def load_job_from_options(
    options: SnapshotOptions,
    *,
    stdin: Any = sys.stdin,
    cwd: Path | None = None,
) -> object:
    resolved_cwd = (cwd or Path.cwd()).resolve()
    if options.job:
        if options.job == "-":
            text = stdin.read()
            source_label = "stdin"
        else:
            job_path = (resolved_cwd / options.job).resolve()
            text = job_path.read_text(encoding="utf-8")
            source_label = str(job_path)
        return apply_option_overrides_to_payload(load_json_text(text, source_label), options, cwd=resolved_cwd)

    if not stdin.isatty() and not options.input:
        text = stdin.read()
        if text.strip():
            return apply_option_overrides_to_payload(load_json_text(text, "stdin"), options, cwd=resolved_cwd)

    if not options.input:
        raise SnapshotError("render requires --job, stdin JSON, or --input")
    if options.mode != "list" and not options.output:
        raise SnapshotError("render shortcut requires --output for non-list modes")

    output: dict[str, object] = {
        "path": options.output,
        "camera": parse_camera_option(options.camera),
    }
    if options.width:
        output["width"] = options.width
    if options.height:
        output["height"] = options.height

    job: dict[str, object] = {
        "input": options.input,
        "mode": options.mode,
        "outputs": [] if options.mode == "list" else [output],
        "appearance": load_appearance_option(options.appearance, cwd=resolved_cwd),
        "render": {"viewLabels": options.view_labels},
    }
    if options.size_profile:
        job["render"]["sizeProfile"] = options.size_profile
    if options.display_specified:
        job["display"] = load_display_option(options.display, cwd=resolved_cwd)
    if options.params_specified:
        job["stepParameters"] = parse_params_option(options.params)
    merge_focus_hide_options(job, options)
    return job


def path_is_inside_or_equal(child: Path, parent: Path) -> bool:
    resolved_child = child.resolve()
    resolved_parent = parent.resolve()
    try:
        resolved_child.relative_to(resolved_parent)
        return True
    except ValueError:
        return False


def input_kind(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".step":
        return "step"
    if suffix == ".stp":
        return "stp"
    if suffix == ".py":
        return "python"
    return ""


def logical_step_path_for_python_source(source_path: Path) -> Path:
    return source_path.with_suffix(".step")


def same_stem_python_generator_path(step_path: Path) -> Path | None:
    candidate = step_path.with_suffix(".py")
    try:
        return candidate if re.search(r"\bgen_step\s*\(", candidate.read_text(encoding="utf-8")) else None
    except OSError:
        return None


def resolve_input_path(raw_input: object, *, cwd: Path) -> Path:
    input_text = str(raw_input or "").strip()
    if not input_text:
        raise SnapshotError("render job is missing input")
    raw_path = Path(input_text)
    selected = raw_path.resolve() if raw_path.is_absolute() else (cwd / raw_path).resolve()
    if not selected.exists():
        if selected.suffix.lower() in {".step", ".stp"} and same_stem_python_generator_path(selected):
            return selected
        raise SnapshotError(f"Render input does not exist: {input_text}")
    return selected


def encode_path_param(value: str) -> str:
    return "/".join(quote(part) for part in value.replace(os.sep, "/").split("/"))


def asset_url_for_path(file_path: Path, root_path: Path) -> str:
    if not path_is_inside_or_equal(file_path, root_path):
        raise SnapshotError(f"Render asset must be inside the snapshot render root: {file_path}")
    return f"/__render_asset/{encode_path_param(file_path.resolve().relative_to(root_path.resolve()).as_posix())}"


def step_parameter_path_for_step_source(source_path: Path) -> Path:
    return source_path.with_name(f".{source_path.stem}.step.js")


def has_step_parameter_render_values(value: object) -> bool:
    return value is not None


def step_parameter_render_values_are_animated(value: object) -> bool:
    return is_plain_object(value) and is_plain_object(value.get("animate")) and bool(value["animate"])


def appearance_theme_id_for_job(job: Mapping[str, object]) -> str:
    appearance = job.get("appearance")
    if isinstance(appearance, str):
        return appearance.strip().lower() or DEFAULT_RENDER_THEME_ID
    return DEFAULT_RENDER_THEME_ID


def normalize_size_profile(value: object) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def explicit_size_profile(job: Mapping[str, object], output: Mapping[str, object]) -> str:
    render = job.get("render") if is_plain_object(job.get("render")) else {}
    return normalize_size_profile(output.get("sizeProfile") or render.get("sizeProfile") or job.get("sizeProfile") or "")


def default_render_size(job: Mapping[str, object], output: Mapping[str, object]) -> tuple[int, int]:
    mode = str(job.get("mode") or "view").strip().lower()
    profile = explicit_size_profile(job, output)
    if profile in {"simple-square", "square"}:
        return SIMPLE_SQUARE_RENDER_WIDTH, SIMPLE_SQUARE_RENDER_HEIGHT
    if profile in {"simple", "simple-part", "unlabeled"}:
        return SIMPLE_RENDER_WIDTH, SIMPLE_RENDER_HEIGHT
    if profile in {"presentation-large", "hero", "large-presentation"}:
        return PRESENTATION_LARGE_RENDER_WIDTH, PRESENTATION_LARGE_RENDER_HEIGHT
    if profile == "presentation":
        return PRESENTATION_RENDER_WIDTH, PRESENTATION_RENDER_HEIGHT
    if profile in {"complex-assembly-large", "assembly-large"}:
        return COMPLEX_ASSEMBLY_LARGE_RENDER_WIDTH, COMPLEX_ASSEMBLY_LARGE_RENDER_HEIGHT
    if profile in {"complex-assembly", "assembly"}:
        return COMPLEX_ASSEMBLY_RENDER_WIDTH, COMPLEX_ASSEMBLY_RENDER_HEIGHT
    if profile in {"contact-sheet", "contactsheet"}:
        return CONTACT_SHEET_RENDER_WIDTH, CONTACT_SHEET_RENDER_HEIGHT
    if profile == "orbit" or mode == "orbit" or step_parameter_render_values_are_animated(job.get("stepParameters")):
        return ORBIT_RENDER_WIDTH, ORBIT_RENDER_HEIGHT
    render = job.get("render") if is_plain_object(job.get("render")) else {}
    if (
        profile in {"dimensioned", "section", "labeled"}
        or mode == "section"
        or render.get("viewLabels") is True
        or output.get("viewLabel")
        or output.get("label")
    ):
        return DIAGNOSTIC_RENDER_WIDTH, DIAGNOSTIC_RENDER_HEIGHT
    if profile == "diagnostic" or appearance_theme_id_for_job(job) in WORKBENCH_RENDER_THEME_IDS:
        return DIAGNOSTIC_RENDER_WIDTH, DIAGNOSTIC_RENDER_HEIGHT
    return SIMPLE_RENDER_WIDTH, SIMPLE_RENDER_HEIGHT


def resolve_output_size(job: Mapping[str, object], output: Mapping[str, object]) -> tuple[int, int]:
    default_width, default_height = default_render_size(job, output)
    return (
        positive_integer(output.get("width") or job.get("width") or default_width, "output width"),
        positive_integer(output.get("height") or job.get("height") or default_height, "output height"),
    )


def snapshot_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def timestamp_output_path(output_path: str, timestamp: str) -> str:
    if not output_path:
        return ""
    path = Path(output_path)
    return str(path.with_name(f"{path.stem}_{timestamp}{path.suffix}"))


def normalize_snapshot_job_packet(raw_payload: object) -> tuple[bool, list[object]]:
    if isinstance(raw_payload, list):
        return False, raw_payload
    if is_plain_object(raw_payload) and isinstance(raw_payload.get("jobs"), list):
        return False, list(raw_payload["jobs"])
    return True, [raw_payload]


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
        from cadpy.step_artifacts import ensure_step_topology_artifact as imported_ensure

        ensure_step_topology_artifact = imported_ensure
    return ensure_step_topology_artifact


def selection_value_list(value: object) -> list[str]:
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(selection_value_list(item))
        return values
    text = str(value or "").strip()
    if not text:
        return []
    return [entry.strip() for entry in text.split(",") if entry.strip()]


def selection_filter_values(job: Mapping[str, object]) -> list[str]:
    selection = job.get("selection") if is_plain_object(job.get("selection")) else {}
    values: list[str] = []
    for key in ("focus", "refs", "hide"):
        values.extend(selection_value_list(selection.get(key)))
    return values


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
) -> StepTopologyArtifact:
    target = ResolvedStepTarget(
        cad_path=cad_ref_for_step_path(reference_root, step_path),
        kind="part",
        source_path=input_path,
        step_path=step_path,
    )
    try:
        ensure_artifact = load_ensure_step_topology_artifact()
        return ensure_artifact(target, owner="cad-snapshot", require_selector=require_selector)
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
    return lookup.build_selector_index(manifest, buffers=buffers)


def validate_occurrence_selector(selector: str, *, selector_index: lookup.SelectorIndex | None, source_label: str) -> None:
    if selector_index is None:
        return
    if selector not in selector_index.occurrence_by_id:
        raise SnapshotError(f"{source_label} references unknown part/subassembly occurrence selector: {selector}")


def normalize_selection_selector(
    raw_value: str,
    *,
    selector_index: lookup.SelectorIndex | None,
    source_label: str,
) -> list[str]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    parsed = cad_ref_syntax.parse_selector(text)
    if parsed is None:
        return []
    if parsed.selector_type == "opaque":
        return [parsed.canonical]
    if parsed.selector_type != "occurrence":
        raise SnapshotError(
            f"{source_label} supports only part/subassembly occurrence refs; "
            f"got {parsed.selector_type} selector {text!r}"
        )
    validate_occurrence_selector(parsed.canonical, selector_index=selector_index, source_label=source_label)
    return [parsed.canonical]


def normalize_selection_filter_values(
    value: object,
    *,
    expected_cad_path: str,
    selector_index: lookup.SelectorIndex | None,
    source_label: str,
) -> list[str]:
    _ = expected_cad_path
    selectors: list[str] = []
    for raw_value in selection_value_list(value):
        selectors.extend(
            normalize_selection_selector(raw_value, selector_index=selector_index, source_label=source_label)
        )
    return selectors


def normalize_render_job_selection(
    job: Mapping[str, object],
    *,
    expected_cad_path: str,
    selector_index: lookup.SelectorIndex | None,
) -> dict[str, object] | None:
    selection = job.get("selection") if is_plain_object(job.get("selection")) else None
    if selection is None:
        return None
    if any(selection_value_list(selection.get(key)) for key in ("focus", "refs")) and selection_value_list(
        selection.get("hide")
    ):
        raise SnapshotError("selection.focus/refs and selection.hide cannot be used in the same snapshot job")
    normalized = dict(selection)
    for key in ("focus", "refs", "hide"):
        if key not in selection:
            continue
        normalized[key] = normalize_selection_filter_values(
            selection.get(key),
            expected_cad_path=expected_cad_path,
            selector_index=selector_index,
            source_label=f"selection.{key}",
        )
    return normalized


def resolve_render_job(
    raw_job: object,
    *,
    cwd: Path | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    if not is_plain_object(raw_job):
        raise SnapshotError("render job must be an object")
    job = copy.deepcopy(raw_job)
    if "theme" in job:
        raise SnapshotError("render jobs use appearance; theme is reserved for saved appearance settings")
    if "params" in job:
        raise SnapshotError("render jobs use stepParameters; params is reserved for shortcut --params parsing")
    forbidden_root_fields = [field for field in ("workspaceRoot", "rootDir") if field in job]
    if forbidden_root_fields:
        raise SnapshotError(
            "snapshot jobs no longer accept workspaceRoot or rootDir; pass a relative or absolute input path instead"
        )

    resolved_cwd = (cwd or Path.cwd()).resolve()
    raw_input = str(job.get("input") or "").strip()
    if not raw_input:
        raise SnapshotError("render job is missing input")

    input_path = resolve_input_path(raw_input, cwd=resolved_cwd)
    root_path = input_path.parent.resolve()
    reference_root = reference_root_for_input(input_path, resolved_cwd)
    kind = input_kind(input_path)
    source_path = input_path
    if kind == "python":
        input_path = logical_step_path_for_python_source(input_path)
        root_path = input_path.parent.resolve()
        kind = "step"
    if kind not in {"step", "stp"}:
        raise SnapshotError("Snapshot supports only STEP/STP inputs or same-stem Python generators")

    artifact = ensure_render_job_step_artifact(
        job,
        reference_root=reference_root,
        input_path=source_path,
        step_path=input_path,
        require_selector=selection_requires_selector_topology(job),
    )
    expected_cad_path = cad_ref_for_step_path(reference_root, input_path)
    normalized_selection = normalize_render_job_selection(
        job,
        expected_cad_path=expected_cad_path,
        selector_index=artifact_selector_index(artifact),
    )

    glb_path = existing_part_glb_path(input_path) or part_glb_path(input_path)
    if not glb_path.exists():
        raise SnapshotError(f"STEP/STP render input is missing its CAD Viewer GLB artifact: {glb_path}")

    has_param_render = has_step_parameter_render_values(job.get("stepParameters"))
    animated_params = step_parameter_render_values_are_animated(job.get("stepParameters"))
    step_parameter_path = step_parameter_path_for_step_source(input_path)

    mode = str(job.get("mode") or "view").strip().lower()
    if mode not in SUPPORTED_RENDER_MODES:
        raise SnapshotError(f"Unsupported render mode: {mode or '(missing)'}")
    if has_param_render and mode != "view":
        raise SnapshotError("stepParameters support only view mode; set display.mode for display-style changes")
    if has_param_render and not step_parameter_path.exists():
        raise SnapshotError(
            f"STEP/STP render stepParameters require a CAD Viewer STEP parameter sidecar: {step_parameter_path}"
        )

    outputs = job.get("outputs") if isinstance(job.get("outputs"), list) else []
    if mode != "list" and not outputs:
        raise SnapshotError("render job must include outputs for non-list modes")
    if animated_params and len(outputs) != 1:
        raise SnapshotError("animated stepParameters require exactly one output")

    normalized_render = dict(job.get("render") if is_plain_object(job.get("render")) else {})
    normalized_render.pop("clip", None)
    normalized_render.pop("clipSettings", None)
    raw_scale = str(
        normalized_render.get("scale")
        or normalized_render.get("sceneScale")
        or normalized_render.get("sceneScaleMode")
        or job.get("scale")
        or job.get("sceneScale")
        or ""
    ).strip().lower()
    if raw_scale:
        normalized_render["scale"] = "cad"

    normalized_outputs: list[dict[str, object]] = []
    resolved_timestamp = timestamp or snapshot_timestamp()
    for output in outputs:
        output_object = dict(output if is_plain_object(output) else {})
        width, height = resolve_output_size({**job, "mode": mode}, output_object)
        output_path = str(output_object.get("path") or "")
        timestamped_output_path = timestamp_output_path(output_path, resolved_timestamp)
        normalized_outputs.append(
            {
                **output_object,
                "path": str((resolved_cwd / timestamped_output_path).resolve()) if timestamped_output_path else "",
                "width": width,
                "height": height,
                "camera": output_object.get("camera") or job.get("camera") or "iso",
            }
        )

    job.pop("clip", None)
    job.pop("clipSettings", None)
    resolved: dict[str, object] = {
        "rootPath": str(root_path),
        "inputPath": str(input_path),
        "inputUrl": asset_url_for_path(input_path, root_path),
        "kind": kind,
        "glbPath": str(glb_path),
        "glbUrl": asset_url_for_path(glb_path, root_path),
    }
    if step_parameter_path.exists():
        resolved["stepParameterPath"] = str(step_parameter_path)
        resolved["stepParameterUrl"] = asset_url_for_path(step_parameter_path, root_path)

    if normalized_selection is not None:
        job["selection"] = normalized_selection

    return {
        **job,
        "mode": mode,
        "display": job.get("display") if is_plain_object(job.get("display")) else {"mode": "solid"},
        "render": normalized_render,
        "outputs": normalized_outputs,
        "resolved": resolved,
    }


def resolve_render_job_packet(raw_payload: object, *, cwd: Path | None = None) -> dict[str, object]:
    single, jobs = normalize_snapshot_job_packet(raw_payload)
    timestamp = snapshot_timestamp()
    return {
        "single": single,
        "jobs": [resolve_render_job(job, cwd=cwd, timestamp=timestamp) for job in jobs],
    }


def content_type_for_path(path: Path) -> str:
    if path.suffix.lower() == ".mjs":
        return "text/javascript; charset=utf-8"
    if path.suffix.lower() == ".js":
        return "text/javascript; charset=utf-8"
    if path.suffix.lower() == ".html":
        return "text/html; charset=utf-8"
    if path.suffix.lower() == ".wasm":
        return "application/wasm"
    if path.suffix.lower() == ".glb":
        return "model/gltf-binary"
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def route_file(pathname: str, prefix: str, root: Path) -> Path:
    relative_path = unquote(pathname[len(prefix) :])
    file_path = (root / relative_path.lstrip("/")).resolve()
    if not path_is_inside_or_equal(file_path, root):
        raise RouteFileError(f"forbidden route path: {pathname}", status=403)
    return file_path


def resolve_snapshot_route_file(raw_url: str, *, active_root_path: Path | None = None) -> Path:
    parsed = urlparse(raw_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin != SNAPSHOT_ORIGIN:
        raise RouteFileError(f"unsupported snapshot origin: {origin}", status=403)
    if parsed.path == "/render.html":
        return RENDER_HTML_PATH
    if parsed.path.startswith("/__render_asset/"):
        if active_root_path is None:
            raise RouteFileError("snapshot render asset requested without an active render root")
        return route_file(parsed.path, "/__render_asset/", active_root_path)
    if parsed.path == "/snapshot-render.js":
        return RUNTIME_DIR / "snapshot-render.js"
    raise RouteFileError(f"snapshot route not found: {parsed.path}")


def max_output_size(job: Mapping[str, object]) -> tuple[int, int]:
    outputs = job.get("outputs") if isinstance(job.get("outputs"), list) and job.get("outputs") else []
    if not outputs:
        return SIMPLE_RENDER_WIDTH, SIMPLE_RENDER_HEIGHT
    widths = [int(output.get("width") or SIMPLE_RENDER_WIDTH) for output in outputs if is_plain_object(output)]
    heights = [int(output.get("height") or SIMPLE_RENDER_HEIGHT) for output in outputs if is_plain_object(output)]
    return max(widths or [SIMPLE_RENDER_WIDTH], default=SIMPLE_RENDER_WIDTH), max(heights or [SIMPLE_RENDER_HEIGHT], default=SIMPLE_RENDER_HEIGHT)


async def with_snapshot_timeout(awaitable: Any, timeout_seconds: object, label: str = "snapshot") -> object:
    timeout = max(1, float(timeout_seconds or DEFAULT_TIMEOUT_SECONDS))
    try:
        return await asyncio.wait_for(awaitable, timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise SnapshotError(f"{label} timed out after {timeout_seconds}s") from exc


class BatchSnapshotRenderer:
    def __init__(self) -> None:
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.active_root_path: Path | None = None
        self.started = False

    async def start(self) -> None:
        if self.started:
            return
        try:
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise SnapshotError(
                    "CAD snapshot requires the Python playwright package. "
                    "Install the CAD skill requirements, then run `python -m playwright install chromium` if needed."
                ) from exc
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                timeout=RENDER_BROWSER_STARTUP_TIMEOUT_MS,
            )
            self.context = await self.browser.new_context(
                viewport={"width": SIMPLE_RENDER_WIDTH, "height": SIMPLE_RENDER_HEIGHT},
                device_scale_factor=1,
            )
            self.page = await self.context.new_page()
            await self.page.route(SNAPSHOT_ROUTE_GLOB, self.handle_route)
            await self.page.goto(SNAPSHOT_RENDER_URL, wait_until="load", timeout=DEFAULT_TIMEOUT_SECONDS * 1000)
            await self.page.wait_for_function(
                "typeof window.__snapshotRender === 'function'",
                timeout=DEFAULT_TIMEOUT_SECONDS * 1000,
            )
            self.started = True
        except Exception:
            await self.close()
            raise

    async def handle_route(self, route: Any) -> None:
        request = route.request
        if request.method != "GET":
            await route.fulfill(status=405, content_type="text/plain; charset=utf-8", body="method not allowed")
            return
        try:
            file_path = resolve_snapshot_route_file(request.url, active_root_path=self.active_root_path)
        except RouteFileError as exc:
            await route.fulfill(status=exc.status, content_type="text/plain; charset=utf-8", body=str(exc))
            return
        except Exception as exc:
            await route.fulfill(status=500, content_type="text/plain; charset=utf-8", body=str(exc))
            return
        if not file_path.is_file():
            await route.fulfill(status=404, content_type="text/plain; charset=utf-8", body="not found")
            return
        await route.fulfill(
            status=200,
            content_type=content_type_for_path(file_path),
            headers={"cache-control": "no-store"},
            body=file_path.read_bytes(),
        )

    async def render(self, job: Mapping[str, object]) -> dict[str, object]:
        await self.start()
        resolved = job.get("resolved") if is_plain_object(job.get("resolved")) else {}
        self.active_root_path = Path(str(resolved.get("rootPath") or "")).resolve()
        width, height = max_output_size(job)
        await self.page.set_viewport_size({"width": width, "height": height})
        timeout_seconds = job.get("timeoutSeconds") or DEFAULT_TIMEOUT_SECONDS
        result = await with_snapshot_timeout(
            self.page.evaluate("(renderJob) => window.__snapshotRender(renderJob)", dict(job)),
            timeout_seconds,
        )
        if not is_plain_object(result) or not result.get("ok"):
            message = result.get("error") if is_plain_object(result) else ""
            raise SnapshotError(str(message or "unknown browser snapshot failure"))
        return result

    async def close(self) -> None:
        if self.context is not None:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:
                pass
            self.browser = None
        if self.playwright is not None:
            try:
                await self.playwright.stop()
            except Exception:
                pass
            self.playwright = None
        self.page = None
        self.started = False


async def render_resolved_job_packet(packet: Mapping[str, object], *, renderer: BatchSnapshotRenderer | None = None) -> dict[str, object]:
    snapshot_renderer = renderer or BatchSnapshotRenderer()
    started = time.perf_counter()
    results: list[dict[str, object]] = []
    try:
        for job in packet["jobs"]:
            result = await snapshot_renderer.render(job)
            results.append(result if packet["single"] else {"input": job.get("input"), **result})
    finally:
        await snapshot_renderer.close()
    if packet["single"]:
        return results[0]
    return {
        "ok": all(result.get("ok") is not False for result in results),
        "jobs": results,
        "timings": {
            "jobCount": len(results),
            "totalMs": (time.perf_counter() - started) * 1000,
        },
    }


def write_output_payload(output: Mapping[str, object]) -> None:
    output_path = str(output.get("path") or "")
    if not output_path:
        return
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = output.get("text")
    if isinstance(text, str):
        path.write_text(text, encoding="utf-8")
        return
    data_url = str(output.get("dataUrl") or "")
    match = re.match(r"^data:([^;]+);base64,(.+)$", data_url)
    if not match:
        raise SnapshotError(f"Snapshot output did not include a base64 data URL: {output_path}")
    path.write_bytes(base64.b64decode(match.group(2)))


def write_render_outputs(result: Mapping[str, object]) -> None:
    if isinstance(result.get("jobs"), list):
        for job_result in result["jobs"]:
            if is_plain_object(job_result):
                write_render_outputs(job_result)
        return
    outputs = result.get("outputs") if isinstance(result.get("outputs"), list) else []
    for output in outputs:
        if is_plain_object(output):
            write_output_payload(output)


def print_render_result(result: Mapping[str, object], *, json_output: bool = False, stdout: Any = sys.stdout) -> None:
    if json_output:
        stdout.write(f"{json.dumps(result, indent=2)}\n")
        return
    if isinstance(result.get("jobs"), list):
        for job_result in result["jobs"]:
            if is_plain_object(job_result):
                print_render_result(job_result, json_output=False, stdout=stdout)
        for warning in result.get("warnings") or []:
            stdout.write(f"warning: {warning}\n")
        return
    outputs = result.get("outputs")
    if not isinstance(outputs, list):
        stdout.write(f"{json.dumps(result, indent=2)}\n")
        return
    if result.get("mode") == "list":
        stdout.write(f"{json.dumps(result.get('parts') or [], indent=2)}\n")
        return
    for output in outputs:
        if is_plain_object(output) and output.get("path"):
            stdout.write(f"saved snapshot: {output['path']}\n")
    for warning in result.get("warnings") or []:
        stdout.write(f"warning: {warning}\n")


async def run_render_cli_async(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    stdout: Any = sys.stdout,
    stdin: Any = sys.stdin,
) -> int:
    options = parse_snapshot_args(argv)
    if options.help:
        stdout.write(help_text())
        return 0
    raw_payload = load_job_from_options(options, stdin=stdin, cwd=cwd)
    packet = resolve_render_job_packet(raw_payload, cwd=cwd)
    result = await render_resolved_job_packet(packet)
    write_render_outputs(result)
    print_render_result(result, json_output=options.json, stdout=stdout)
    return 0


def run_render_cli(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    stdout: Any = sys.stdout,
    stderr: Any = sys.stderr,
    stdin: Any = sys.stdin,
) -> int:
    try:
        return asyncio.run(run_render_cli_async(argv, cwd=cwd, stdout=stdout, stdin=stdin))
    except SnapshotError as exc:
        stderr.write(f"{exc}\n")
        return 1
    except Exception as exc:
        stderr.write(f"{exc}\n")
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    return run_render_cli(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
