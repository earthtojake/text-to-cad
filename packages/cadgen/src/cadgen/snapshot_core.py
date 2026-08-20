"""Snapshot render core shared by the CAD and DXF skills.

Everything here is format-agnostic: the headless browser driver, the job normalisation
(camera, theme, display, size profile), the mesh render path, and output writing. It
knows nothing about STEP topology, drawings, or implicit models -- a caller resolves its
own input to an asset URL and hands the result to :func:`render_resolved_job_packet`.

It lives in cadgen rather than in a skill because two skills need it and a skill may not
import another skill's code (AGENTS.md). It was extracted verbatim from the CAD skill's
snapshot CLI, which remains its largest caller and keeps every STEP-specific resolver.

The one thing the core cannot know is where the browser runtime (render.html and
snapshot-render.js) lives: each skill bundles its own copy. So `runtime_dir` is passed in
by the caller rather than derived here.
"""

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
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from cadgen.coordination import PHASE_RENDER, resolve as resolve_progress


SNAPSHOT_ORIGIN = "http://snapshot.local"
SNAPSHOT_RENDER_URL = f"{SNAPSHOT_ORIGIN}/render.html"
SNAPSHOT_ROUTE_GLOB = f"{SNAPSHOT_ORIGIN}/**"
# A snapshot is usually READ by an agent rather than looked at by a person, so it does not
# default to a viewer theme at all: `snapshot` is Workbench Light with the ground grid and
# origin axis removed (themeSettings.js RENDER_ONLY_THEME_PRESETS). Those two are helpful
# orientation in a live viewport and are geometry-shaped contrast in a still image --
# straight low-contrast lines crossing the model, indistinguishable from a silhouette edge.
# Materials, lighting and background are Workbench Light unchanged, so parts read exactly as
# they do in the viewer.
DEFAULT_RENDER_THEME_ID = "snapshot"
# The viewer theme `snapshot` is derived from, and the id its default dimensions follow.
VIEWER_DEFAULT_THEME_ID = "workbench-light"
DEFAULT_TIMEOUT_SECONDS = 300
RENDER_BROWSER_STARTUP_TIMEOUT_MS = 15_000
# `animate` is implicit-only: it sweeps a model's own declared animation. The STEP
# analogue is an animated --params sweep, which stays in `view`.
SUPPORTED_RENDER_MODES = {"view", "orbit", "section", "list", "animate"}
MESH_INPUT_KINDS = {"glb", "stl", "3mf"}
MESH_SUPPORTED_RENDER_MODES = {"view", "orbit", "list"}
TOPOLOGY_DISPLAY_MODES = {"hidden_edges", "hidden_lines_removed"}
# Every id that IS the workbench theme, because this set decides a render's default
# dimensions (see default_render_size). With only the legacy "workbench" in it, asking for
# the viewer's real preset by name -- `--theme workbench-light` -- fell through to the
# non-workbench branch and silently rendered at 1200x900 instead of 1600x1200, despite
# resolving to the identical theme in the browser. Pinned against the viewer's preset table
# by tests/python/global/test_snapshot_viewer_theme_parity.py.
WORKBENCH_RENDER_THEME_IDS = {"snapshot", "workbench", "workbench-light", "workbench-dark"}
SUPPORTED_JOB_KEYS = frozenset(
    {
        "input",
        "mode",
        "outputs",
        "theme",
        "display",
        "render",
        "camera",
        "selection",
        "stepParameters",
        "stepParametersPath",
        # Implicit CAD's own three surfaces. `graphics` is a THIRD viewer tab beside Theme
        # and Display (detail, shadows, ambient occlusion, model colours), so it is a third
        # option rather than being folded into --display. Parameters and animation are the
        # implicit analogues of stepParameters: named separately because an implicit model
        # is parameterized by its own descriptor, not by a STEP sidecar.
        "graphics",
        "implicitParameters",
        "implicitAnimation",
        # A robot's pose. The STEP analogue is stepParameters; a robot is posed by joint
        # angle, so it gets its own key rather than overloading one that means a sidecar.
        "jointValues",
        "sizeProfile",
        "width",
        "height",
        "scale",
        "sceneScale",
        "debug",
        "timeoutSeconds",
    }
)
SELECTION_SHAPED_JOB_KEYS = ("hide", "focus", "refs")
SUPPORTED_OUTPUT_KEYS = frozenset(
    {
        "path",
        "width",
        "height",
        "sizeProfile",
        "camera",
        "label",
        "viewLabel",
        "dataUrl",
        "text",
    }
)
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
DISPLAY_OPTION_KEYS = {"projection", "mode", "clip", "exploded", "edges"}
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
    "theme": "rendered",
    "material": "rendered",
    "materials": "rendered",
    "wireframe": "wireframe",
    "wire_frame": "wireframe",
    "wire": "wireframe",
}
THEME_OPTION_KEYS = {
    "materials",
    "background",
    "floor",
    "environment",
    "lighting",
    "colorMode",
    "projection",
    # normalizeThemeSettings() emits modeColors unconditionally, so it is part
    # of the settings shape by construction. Rejecting it meant the repo's own
    # cloneThemePresetSettings() output could not be passed back to
    # --theme without hand-stripping a key first.
    "modeColors",
}
SETTINGS_KEY_HOMES = {
    "edges": "display",
    "mode": "display",
    "exploded": "display",
    "clip": "display",
    "materials": "theme",
    "background": "theme",
    "floor": "theme",
    "environment": "theme",
    "lighting": "theme",
    "colorMode": "theme",
    "projection": "theme",
    "modeColors": "theme",
}
class SnapshotError(RuntimeError):
    pass
class RouteFileError(SnapshotError):
    def __init__(self, message: str, *, status: int = 404) -> None:
        super().__init__(message)
        self.status = status
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
    # Underscore-prefixed keys are comments. JSON has none of its own, and an
    # authored theme is exactly the kind of file that needs to explain why its
    # numbers are what they are; rejecting `_comment` as an unsupported setting
    # pushes that rationale out of the file.
    payload = {key: value for key, value in parsed.items() if not str(key).startswith("_")}
    unknown_keys = [key for key in payload if key not in allowed_keys]
    if unknown_keys:
        misplaced = [
            f"{key} belongs in {SETTINGS_KEY_HOMES[key]} JSON"
            for key in unknown_keys
            if key in SETTINGS_KEY_HOMES
        ]
        detail = f"; {', '.join(misplaced)}" if misplaced else ""
        raise SnapshotError(
            f"{option_name} JSON must be the {setting_label} object directly; "
            f"unsupported keys: {', '.join(unknown_keys)}{detail}"
        )
    if not payload:
        raise SnapshotError(f"{option_name} JSON must include at least one {setting_label} field: {source_label}")
    return payload
def validate_display_settings_values(payload: Mapping[str, object], *, source_label: str) -> None:
    """Reject typo'd closed-set display VALUES up front. The renderer silently falls back
    to defaults on unknown projection/mode values (e.g. ``projection:"ortho"`` renders
    perspective), so a late no-op produces a wrong image with no error — catch it here.

    Only closed-set, typo-prone fields are validated; alias-rich/coerced fields are left
    to the renderer's lenient normalization to avoid false rejections of inputs the
    browser accepts."""
    # An empty/whitespace value means "unset": the renderer treats it as absent and falls
    # back to the default (it does not error), so validating it here would be a false
    # rejection of input the browser accepts. Only validate genuinely-present values.
    projection = str(payload.get("projection") or "").strip().lower()
    if projection and projection not in {"orthographic", "perspective"}:
        raise SnapshotError(
            f"--display projection must be orthographic or perspective; "
            f"got {payload.get('projection')!r} ({source_label})"
        )
    mode = str(payload.get("mode") or "").strip()
    if mode:
        normalized_mode = re.sub(r"[\s-]+", "_", mode.lower())
        if normalized_mode not in DISPLAY_MODE_ALIASES:
            supported = ", ".join(sorted(set(DISPLAY_MODE_ALIASES.values())))
            raise SnapshotError(
                f"--display mode must be one of: {supported}; got {payload.get('mode')!r} ({source_label})"
            )
    exploded = payload.get("exploded")
    if is_plain_object(exploded):
        # The exploded view is enabled + amount only; the layout is automatic.
        # Any other key is a typo or a retired step-document/auto-hint field the
        # renderer now ignores entirely — reject loudly instead of rendering a
        # default the caller did not ask for.
        unknown = sorted(set(exploded) - {"enabled", "amount"})
        if unknown:
            raise SnapshotError(
                f"--display exploded supports only enabled and amount (the exploded layout "
                f"is automatic); unsupported keys: {', '.join(unknown)} ({source_label})"
            )
def load_display_option(raw_display: object, *, cwd: Path) -> dict[str, object]:
    display = str(raw_display or "").strip()
    if not display:
        raise SnapshotError("--display requires a JSON object, JSON file path, or display mode")
    if display.startswith("{"):
        payload = validate_direct_settings_payload(
            load_json_text(display, "--display"),
            option_name="--display",
            source_label="--display",
            allowed_keys=DISPLAY_OPTION_KEYS,
            setting_label="display settings",
        )
        validate_display_settings_values(payload, source_label="--display")
        return payload

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
    payload = validate_direct_settings_payload(
        load_json_text(display_path.read_text(encoding="utf-8"), str(display_path)),
        option_name="--display",
        source_label=str(display_path),
        allowed_keys=DISPLAY_OPTION_KEYS,
        setting_label="display settings",
    )
    validate_display_settings_values(payload, source_label=str(display_path))
    return payload
def load_theme_option(raw_theme: object, *, cwd: Path) -> object:
    theme = str(raw_theme or DEFAULT_RENDER_THEME_ID).strip() or DEFAULT_RENDER_THEME_ID
    if theme.startswith("{"):
        return validate_direct_settings_payload(
            load_json_text(theme, "--theme"),
            option_name="--theme",
            source_label="--theme",
            allowed_keys=THEME_OPTION_KEYS,
            setting_label="theme settings",
        )

    theme_path = Path(theme) if Path(theme).is_absolute() else cwd / theme
    looks_like_file = theme.lower().endswith(".json") or "/" in theme or "\\" in theme
    if not looks_like_file and not theme_path.exists():
        return theme
    if not theme_path.exists():
        raise SnapshotError(f"Theme JSON file does not exist: {theme}")
    return validate_direct_settings_payload(
        load_json_text(theme_path.read_text(encoding="utf-8"), str(theme_path)),
        option_name="--theme",
        source_label=str(theme_path),
        allowed_keys=THEME_OPTION_KEYS,
        setting_label="theme settings",
    )
def path_is_inside_or_equal(child: Path, parent: Path) -> bool:
    resolved_child = child.resolve()
    resolved_parent = parent.resolve()
    try:
        resolved_child.relative_to(resolved_parent)
        return True
    except ValueError:
        return False
def encode_path_param(value: str) -> str:
    return "/".join(quote(part) for part in value.replace(os.sep, "/").split("/"))
def asset_url_for_path(file_path: Path, root_path: Path) -> str:
    if not path_is_inside_or_equal(file_path, root_path):
        raise SnapshotError(f"Render asset must be inside the snapshot render root: {file_path}")
    resolved_path = file_path.resolve()
    relative_path = resolved_path.relative_to(root_path.resolve()).as_posix()
    base_url = f"/__render_asset/{encode_path_param(relative_path)}"
    try:
        file_stat = resolved_path.stat()
    except FileNotFoundError:
        # Same-stem generator inputs resolve to a STEP path that is never written
        # (the generator runs with skip_step_write=True), so there is nothing to
        # version; keep the unversioned URL for those. Any other stat failure is
        # left to propagate: silently falling back to an unversioned URL would
        # re-enable the very collision this key exists to prevent.
        return base_url
    cache_identity = "\0".join(
        (
            str(resolved_path),
            str(file_stat.st_size),
            str(file_stat.st_mtime_ns),
        )
    )
    cache_key = sha256(cache_identity.encode("utf-8")).hexdigest()[:16]
    return f"{base_url}?v={cache_key}"
def theme_id_for_job(job: Mapping[str, object]) -> str:
    theme = job.get("theme")
    if isinstance(theme, str):
        return theme.strip().lower() or DEFAULT_RENDER_THEME_ID
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
    if profile == "diagnostic" or theme_id_for_job(job) in WORKBENCH_RENDER_THEME_IDS:
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
def normalize_common_job(
    job: dict[str, object],
    *,
    mode: str,
    resolved_cwd: Path,
    timestamp: str | None,
) -> dict[str, object]:
    """Kind-independent job normalization shared by every input kind: the outputs
    guard, render clip-stripping + scene-scale coercion, timestamped output
    resolution with per-output camera defaults, and the common return shape.
    Kind resolvers run their capability checks first, then call this, so a
    STEP/mesh/implicit job all normalize identically; the caller attaches its
    kind-specific ``resolved`` payload to the returned job."""
    outputs = job.get("outputs") if isinstance(job.get("outputs"), list) else []
    if mode != "list" and not outputs:
        raise SnapshotError("render job must include outputs for non-list modes")

    # A .gif output only animates in orbit mode or under animated stepParameters;
    # anything else would silently save a single-frame GIF that looks like a
    # broken animation, so reject it with the fix spelled out.
    if mode != "orbit" and not step_parameter_render_values_are_animated(job.get("stepParameters")):
        for output in outputs:
            output_path_text = str((output.get("path") if is_plain_object(output) else output) or "")
            if output_path_text.strip().lower().endswith(".gif"):
                raise SnapshotError(
                    f"a .gif output in {mode} mode with static parameters renders a single frame; "
                    "use --mode orbit (job \"mode\": \"orbit\") for a turntable GIF or animate "
                    "--params values for a parameter-sweep GIF"
                )

    # A job's own `theme` string gets the SAME treatment as the
    # `--theme` flag: a saved-theme name stays a name, but a path or an
    # inline JSON object is loaded into real settings here.
    #
    # Without this a job saying `"theme": "path/to/theme.json"` fell all
    # the way through to `theme_id_for_job()`, which lowercases the
    # string and treats it as a saved-theme id. The lookup missed, the renderer
    # silently used the default workbench theme, and — because the resolved id
    # was then `workbench` — the size-profile logic further down also quietly
    # switched to diagnostic dimensions. Exit 0, no warning, a plausible but
    # wrong image. The CLI help has always promised that a file path works.
    raw_theme = job.get("theme")
    if isinstance(raw_theme, str) and raw_theme.strip():
        job["theme"] = load_theme_option(raw_theme, cwd=resolved_cwd)

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
        # Honour the requested scale. This used to force "cad" unconditionally, so a job
        # asking for the URDF profile (robots are authored in metres, CAD in millimetres)
        # was accepted, validated, and then silently overwritten — the model rendered
        # correctly but framed for a workpiece a thousand times its size.
        if raw_scale not in {"cad", "urdf"}:
            raise SnapshotError(f"Unsupported scene scale: {raw_scale} (expected cad or urdf)")
        normalized_render["scale"] = raw_scale

    normalized_outputs: list[dict[str, object]] = []
    resolved_timestamp = timestamp or snapshot_timestamp()
    for index, output in enumerate(outputs):
        # A bare string is the obvious shorthand and the .gif guard above
        # already reads one as a path; without this it was coerced to {} and the
        # caller's path silently discarded, producing a full-cost render that
        # wrote nothing and said nothing.
        if isinstance(output, str):
            output = {"path": output}
        output_object = dict(output if is_plain_object(output) else {})
        # Outputs share the job's closed-schema treatment: a "selection" (or
        # any other job-level key) nested in an output used to be dropped
        # silently, so the render completed with nothing hidden/focused.
        unknown_output_keys = sorted(set(output_object) - SUPPORTED_OUTPUT_KEYS)
        if unknown_output_keys:
            if "selection" in unknown_output_keys:
                raise SnapshotError(
                    f"render output {index} carries a selection; selection applies at job "
                    "level only — to hide or focus parts for one view, split it into its "
                    'own job in a "jobs" array'
                )
            raise SnapshotError(
                f"render output {index} has unknown key(s): {', '.join(unknown_output_keys)}; "
                f"supported output keys: {', '.join(sorted(SUPPORTED_OUTPUT_KEYS))}"
            )
        width, height = resolve_output_size({**job, "mode": mode}, output_object)
        output_path = str(output_object.get("path") or "")
        if mode != "list" and not output_path:
            # list mode legitimately carries no output files; every other mode
            # rendering to nowhere is a silent no-op, not a valid request.
            raise SnapshotError(
                f"render output {index} has no path; each output must be a path "
                'string or an object with a "path"'
            )
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

    # Preflight the animation frame budget.
    #
    # Every frame of an animated render is held before the GIF is encoded, so
    # the cost is frames x pixels, not frames alone. Past roughly 120 Mpx the
    # headless browser is killed mid-run and the whole render is lost:
    #
    #     playwright._impl._errors.TargetClosedError:
    #     Target page, context or browser has been closed
    #
    # Measured on this machine: 144 frames @1200x750 (130 Mpx) fine,
    # 203 @860x645 (113 Mpx) fine, 252 @1000x740 (186 Mpx) killed. The failure
    # arrives minutes in, after all the expensive work, so say so up front.
    # This is advisory: the ceiling is machine-dependent and a bigger box may
    # well cope, so it must not block a render that would have succeeded.
    if step_parameter_render_values_are_animated(job.get("stepParameters")):
        raw_params = job.get("stepParameters") if is_plain_object(job.get("stepParameters")) else {}
        fps = float(raw_params.get("fps") or 18)
        seconds = float(raw_params.get("durationSeconds") or raw_params.get("duration") or 4)
        frames = max(2, min(round(fps * seconds), 720))
        pixels = sum(
            int(out.get("width") or 0) * int(out.get("height") or 0)
            for out in normalized_outputs
        )
        megapixels = frames * pixels / 1_000_000
        if megapixels > 120:
            sys.stderr.write(
                f"warning: animated render is about {megapixels:.0f} Mpx "
                f"({frames} frames x {pixels / 1_000_000:.2f} Mpx). Past roughly "
                "120 Mpx the headless browser is often killed mid-run "
                "(TargetClosedError) and the render is lost after doing all the "
                "work. Lower fps, shorten durationSeconds, or reduce the output "
                "size — or render in segments and stitch.\n"
            )

    job.pop("clip", None)
    job.pop("clipSettings", None)
    return {
        **job,
        "mode": mode,
        "display": job.get("display") if is_plain_object(job.get("display")) else {"mode": "solid"},
        "render": normalized_render,
        "outputs": normalized_outputs,
    }
def has_step_parameter_render_values(value: object) -> bool:
    return value is not None
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

def positive_integer(value: object, label: str) -> int:
    try:
        parsed = int(str(value or ""), 10)
    except ValueError as exc:
        raise SnapshotError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise SnapshotError(f"{label} must be a positive integer")
    return parsed
def step_parameter_render_values_are_animated(value: object) -> bool:
    return is_plain_object(value) and is_plain_object(value.get("animate")) and bool(value["animate"])

def resolve_mesh_render_job(
    job: dict[str, object],
    *,
    kind: str,
    input_path: Path,
    root_path: Path,
    resolved_cwd: Path,
    timestamp: str | None,
    **_kind_context: object,
) -> dict[str, object]:
    """Resolve a direct mesh input (GLB/STL/3MF) that carries no STEP topology.

    Meshes render through the shared mesh path, so this skips the STEP artifact/package
    pipeline entirely and hands the renderer a plain asset URL. STEP-only options are
    rejected up front with clear errors rather than silently ignored downstream."""
    label = kind.upper()

    # Selector focus/hide/refs need the selector index built from STEP topology.
    if selection_filter_values(job):
        raise SnapshotError(
            f"selection focus/hide/refs require STEP topology; {label} mesh inputs have no "
            "part/subassembly selectors"
        )
    # stepParameters drive a STEP parameter sidecar module.
    if has_step_parameter_render_values(job.get("stepParameters")):
        raise SnapshotError(
            f"stepParameters require a STEP model; {label} mesh inputs are not parametric"
        )
    if job.get("stepParametersPath") is not None:
        raise SnapshotError(
            f"stepParametersPath requires a STEP model; {label} mesh inputs are not parametric"
        )

    mode = str(job.get("mode") or "view").strip().lower()
    if mode not in SUPPORTED_RENDER_MODES:
        raise SnapshotError(f"Unsupported render mode: {mode or '(missing)'}")
    if mode not in MESH_SUPPORTED_RENDER_MODES:
        supported = ", ".join(sorted(MESH_SUPPORTED_RENDER_MODES))
        raise SnapshotError(
            f"{mode} mode requires STEP topology; {label} mesh inputs support: {supported}"
        )

    # Meshes render shaded solid (no CAD topology for edges/materials). Projection is
    # honored by the renderer, but any non-solid display mode would be silently dropped,
    # so reject it up front with a clear error instead of returning a misleading image.
    display = job.get("display") if is_plain_object(job.get("display")) else {}
    raw_display_mode = re.sub(r"[\s-]+", "_", str(display.get("mode") or "").strip().lower())
    canonical_display_mode = DISPLAY_MODE_ALIASES.get(raw_display_mode, raw_display_mode)
    if canonical_display_mode in TOPOLOGY_DISPLAY_MODES:
        raise SnapshotError(
            f"{canonical_display_mode} display requires STEP CAD edges; {label} mesh inputs "
            "render shaded without CAD linework"
        )
    if canonical_display_mode and canonical_display_mode != "solid":
        raise SnapshotError(
            f"{canonical_display_mode} display mode is not supported for {label} mesh inputs; "
            "meshes render shaded solid (STEP models support the full display-mode set)"
        )
    exploded = display.get("exploded") if is_plain_object(display.get("exploded")) else None
    if exploded is not None and exploded.get("enabled"):
        raise SnapshotError(
            f"exploded view requires STEP assembly occurrence structure; {label} mesh inputs "
            "cannot be exploded"
        )

    asset_url = asset_url_for_path(input_path, root_path)
    resolved: dict[str, object] = {
        "rootPath": str(root_path),
        "inputPath": str(input_path),
        "inputUrl": asset_url,
        "kind": kind,
        "url": asset_url,
    }
    if bool(job.get("debug")):
        resolved["debug"] = {"meshSource": {"kind": kind}}

    normalized = normalize_common_job(job, mode=mode, resolved_cwd=resolved_cwd, timestamp=timestamp)
    normalized["resolved"] = resolved
    return normalized
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
    if path.suffix.lower() == ".stl":
        return "model/stl"
    if path.suffix.lower() == ".3mf":
        return "model/3mf"
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"
def route_file(pathname: str, prefix: str, root: Path) -> Path:
    relative_path = unquote(pathname[len(prefix) :])
    file_path = (root / relative_path.lstrip("/")).resolve()
    if not path_is_inside_or_equal(file_path, root):
        raise RouteFileError(f"forbidden route path: {pathname}", status=403)
    return file_path
def resolve_snapshot_route_file(
    raw_url: str,
    *,
    runtime_dir: Path,
    active_root_path: Path | None = None,
) -> Path:
    parsed = urlparse(raw_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin != SNAPSHOT_ORIGIN:
        raise RouteFileError(f"unsupported snapshot origin: {origin}", status=403)
    if parsed.path == "/render.html":
        return Path(runtime_dir) / "render.html"
    if parsed.path.startswith("/__render_asset/"):
        if active_root_path is None:
            raise RouteFileError("snapshot render asset requested without an active render root")
        return route_file(parsed.path, "/__render_asset/", active_root_path)
    if parsed.path == "/snapshot-render.js":
        return Path(runtime_dir) / "snapshot-render.js"
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
    def __init__(self, runtime_dir: Path) -> None:
        # Each skill bundles its own render.html/snapshot-render.js, so the driver is told
        # where they are rather than locating them relative to itself.
        self.runtime_dir = Path(runtime_dir)
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
        except Exception:  # noqa: BLE001 - any startup failure must still tear down the browser, then re-raise
            await self.close()
            raise

    async def handle_route(self, route: Any) -> None:
        request = route.request
        if request.method != "GET":
            await route.fulfill(status=405, content_type="text/plain; charset=utf-8", body="method not allowed")
            return
        try:
            file_path = resolve_snapshot_route_file(
                request.url,
                runtime_dir=self.runtime_dir,
                active_root_path=self.active_root_path,
            )
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
            except Exception:  # noqa: BLE001 - best-effort teardown; a failing close must not mask the original error
                pass
            self.context = None
        if self.browser is not None:
            try:
                await self.browser.close()
            except Exception:  # noqa: BLE001 - best-effort teardown; a failing close must not mask the original error
                pass
            self.browser = None
        if self.playwright is not None:
            try:
                await self.playwright.stop()
            except Exception:  # noqa: BLE001 - best-effort teardown; a failing close must not mask the original error
                pass
            self.playwright = None
        self.page = None
        self.started = False
# --- progress ----------------------------------------------------------------------
# A snapshot was silent for its ENTIRE run, then grew a progress class of its own: free-text
# phases, its own tty handling, its own clear(). Two implementations of one idea, sharing
# nothing, guaranteed to drift.
#
# It reports through the shared phase model now (SNAPSHOT in coordination/kinds.py). The
# per-job counter that used to be formatted INTO a phase name ("rendering 3/12 model.step")
# is a real done/total, so a reader can render it as a bar like any other counted phase --
# and the CLI line, the tty handling and the non-tty degradation all come from one place.



async def render_resolved_job_packet(
    packet: Mapping[str, object],
    *,
    runtime_dir: Path,
    renderer: BatchSnapshotRenderer | None = None,
    progress: object | None = None,
) -> dict[str, object]:
    snapshot_renderer = renderer or BatchSnapshotRenderer(runtime_dir)
    report = resolve_progress(progress)
    started = time.perf_counter()
    results: list[dict[str, object]] = []
    total = len(packet["jobs"])
    # The job list is known in full before the first render, so this is a real count rather
    # than a number formatted into a phase name. Same shape as meshing components.
    report.phase(PHASE_RENDER, total=total)
    try:
        for job in packet["jobs"]:
            report.detail(str(job.get("input") or ""))
            result = await snapshot_renderer.render(job)
            # The browser result knows nothing about artifact resolution; --debug
            # diagnostics are attached at resolve time, so merge them into the
            # emitted result here or they never reach --json output.
            resolved = job.get("resolved") if is_plain_object(job.get("resolved")) else {}
            debug_info = resolved.get("debug")
            if is_plain_object(debug_info) and is_plain_object(result):
                result = {**result, "debug": debug_info}
            results.append(result if packet["single"] else {"input": job.get("input"), **result})
            report.advance()
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
# stdout is read by an agent far more often than by a person, and indentation is pure
# volume: on a 600-part list payload it was 38% of 294 KB. A human who wants it laid out
# pipes through `jq .`; an agent that has to pay for the whitespace cannot get it back.
_JSON = {"separators": (",", ":")}

# How the browser hands rendered bytes back for write_output_payload to decode. By the time
# anything prints, that has already written the file -- the CLI writes before it prints -- so
# these are a verbatim second copy of it, and the `path` beside them is what a caller needs.
# Printing them put a base64 PNG on stdout (228 KB for one 1600x1200 view) or an entire orbit
# GIF (1.7 MB, ~445k tokens), in the one output this release has spent its effort making
# cheap: see the note above _JSON, which strips indentation for a fraction of that. Nothing
# reads either key back from stdout.
_OUTPUT_PAYLOAD_KEYS = ("dataUrl", "text")


def _without_output_payloads(result: Mapping[str, object]) -> dict:
    """``result`` minus the output payload blobs.

    Returns a COPY, so a caller that still needs the payload -- write_output_payload reads the
    same dict -- is unaffected by print order.
    """
    printable = dict(result)
    jobs = printable.get("jobs")
    if isinstance(jobs, list):
        printable["jobs"] = [
            _without_output_payloads(job) if is_plain_object(job) else job for job in jobs
        ]
    outputs = printable.get("outputs")
    if isinstance(outputs, list):
        printable["outputs"] = [
            {key: value for key, value in output.items() if key not in _OUTPUT_PAYLOAD_KEYS}
            if is_plain_object(output)
            else output
            for output in outputs
        ]
    return printable


def print_render_result(result: Mapping[str, object], *, json_output: bool = False, stdout: Any = sys.stdout) -> None:
    if json_output:
        stdout.write(f"{json.dumps(_without_output_payloads(result), **_JSON)}\n")
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
        # Nothing to summarise as "saved snapshot:" lines, so fall back to the raw result --
        # stripped the same way, so an unexpected shape cannot reintroduce the payload.
        stdout.write(f"{json.dumps(_without_output_payloads(result), **_JSON)}\n")
        return
    if result.get("mode") == "list":
        stdout.write(f"{json.dumps(result.get('parts') or [], **_JSON)}\n")
        return
    for output in outputs:
        if is_plain_object(output) and output.get("path"):
            stdout.write(f"saved snapshot: {output['path']}\n")
    for warning in result.get("warnings") or []:
        stdout.write(f"warning: {warning}\n")
