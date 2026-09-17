"""Snapshot render core shared by the CAD and DXF skills.

Everything here is format-agnostic: the headless browser driver, the job normalisation
(camera, Render scene, display, output, quality), the mesh render path, and output writing. It
knows nothing about STEP topology, drawings, or robot descriptions -- a caller resolves its
own input to an asset URL and hands the result to :func:`render_resolved_job_packet`.

It lives in cadgen rather than in a skill because two skills need it and a skill may not
import another skill's code (AGENTS.md). It was extracted verbatim from the CAD skill's
snapshot CLI, which remains its largest caller and keeps every STEP-specific resolver.

The one thing the core cannot know is where the browser runtime (render.html and
snapshot-render.js) lives: a caller may point at a directory of its own. So `runtime_dir`
is passed in rather than derived here, and it is validated once, when the renderer starts,
by :func:`cadgen.assets.require_browser_runtime` -- an absent bundle is a message naming
how to produce it rather than a 404 inside a headless page.
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
from math import isfinite
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from cadgen.assets import require_browser_runtime
from cadgen.coordination import PHASE_RENDER, resolve as resolve_progress
from cadgen.results import SnapshotFile, SnapshotResult, SnapshotTimings
from cadgen._internal.atomic_replace import write_bytes_atomic


# `localhost` is a potentially trustworthy origin under the Secure Contexts
# rules even over HTTP. The page is still entirely intercepted below; this
# spelling gives its shared TESS provider the SubtleCrypto object required to
# verify immutable cache bodies before use.
SNAPSHOT_ORIGIN = "http://localhost"
SNAPSHOT_RENDER_URL = f"{SNAPSHOT_ORIGIN}/render.html"
SNAPSHOT_ROUTE_GLOB = f"{SNAPSHOT_ORIGIN}/**"
# A normal snapshot leaves ``render`` absent and retains the deterministic CAD
# scene. An explicit render envelope opts into the photographic renderer.
RENDER_STUDIO_IDS = frozenset({"light", "dark"})
RENDER_QUALITY_IDS = frozenset({"preview", "final"})
DEFAULT_TIMEOUT_SECONDS = 300
# Tearing a video sequence down is one dispose call over objects already in
# hand, so it gets a short deadline of its own rather than the job's: the
# failure it is bounded against is a frame that already blew ITS timeout and
# left JavaScript running, which this call would then queue behind forever.
VIDEO_TEARDOWN_TIMEOUT_SECONDS = 30
# How often a video says where it is when nothing is painting a progress bar.
VIDEO_NARRATE_INTERVAL_SECONDS = 15.0
RENDER_BROWSER_STARTUP_TIMEOUT_MS = 15_000
SUPPORTED_RENDER_MODES = {"view", "section", "list"}
MESH_INPUT_KINDS = {"glb", "stl", "3mf"}
MESH_SUPPORTED_RENDER_MODES = {"view", "list"}
TOPOLOGY_DISPLAY_MODES = {"hidden_edges", "hidden_lines_removed"}
SUPPORTED_JOB_KEYS = frozenset(
    {
        "input",
        "mode",
        "outputs",
        "display",
        "render",
        "output",
        "quality",
        "camera",
        "selection",
        # A STEP model's pose: a declared preset name, or {dof: value}. Named for the
        # thing it drives (the model's kinematics= declaration) and spelled the same as
        # the --kinematics flag and the sidecar section.
        "kinematics",
        # A robot's pose. The STEP analogue is kinematics; a robot is posed by joint
        # angle, so it gets its own key rather than overloading one that means a sidecar.
        "jointValues",
        # One frozen frame of a STEP document's choreography: {"clip": name,
        # "time": seconds}. The clips come from animation.source in the document sidecar;
        # spelled the same as the --animation flag.
        # Layered over the kinematics pose exactly as the viewer layers its
        # Animation tab.
        "animation",
        # The SPAN of that choreography rather than one moment of it:
        # {fps, seconds, start, quality, loop}, encoded to the .mp4/.gif the
        # output names. Meaningless without `animation` (cadgen.snapshot_video).
        "video",
        "scale",
        "debug",
        "timeoutSeconds",
    }
)
SUPPORTED_RENDER_KEYS = frozenset(
    {"studio", "quality", "exposure", "lighting", "backdrop", "camera"}
)
RENDER_INCOMPATIBLE_JOB_KEYS = frozenset(
    {"camera", "display", "selection", "jointValues", "quality"}
)
RENDER_LIGHTING_KEYS = frozenset({"rotation", "size", "fill"})
RENDER_BACKDROP_KEYS = frozenset({"color", "transparent", "ground", "groundPlacement"})
SUPPORTED_OUTPUT_SETTINGS_KEYS = frozenset(
    {"sizeProfile", "padding", "paddingPercent", "viewLabels", "tightFrame", "transparent", "renderScale"}
)
SUPPORTED_QUALITY_KEYS = frozenset({"tessellation"})
# Floors for `quality.tessellation`. Chord tolerance is RELATIVE to each
# component's bounding diagonal and angle tolerance is radians, so these are
# ~100x finer than the tessellator's defaults (1.5e-3 / 0.35 rad) and past any
# display need at any output size. Below them the page tessellates until the
# renderer dies, and the caller sees a lost Playwright driver connection rather
# than a rejected request — so the request is rejected here, before a browser
# is launched. Mirrored as RENDER_TESSELLATION_FLOORS in
# packages/core/src/common/source.js (that file validates the same job in
# the page; the parity is tested).
MIN_RENDER_TESSELLATION = {"chordTolerance": 1e-5, "angleTolerance": 5e-3}
SUPPORTED_OUTPUT_KEYS = frozenset(
    {
        "path",
        "width",
        "height",
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
CONTACT_SHEET_RENDER_WIDTH = 2400
CONTACT_SHEET_RENDER_HEIGHT = 1600
DISPLAY_OPTION_KEYS = {"mode", "clip", "exploded", "edges", "guides", "partColor"}
DISPLAY_MODES = frozenset(
    {"shaded", "shaded_edges", "transparent", "hidden_edges", "hidden_lines_removed", "unshaded", "wireframe"}
)
PART_COLOR_MODES = frozenset({"original", "single", "by_part"})
DISPLAY_CLIP_KEYS = frozenset({"enabled", "axis", "offset", "offsets", "invert"})
DISPLAY_EXPLODED_KEYS = frozenset({"enabled", "amount"})
DISPLAY_EDGE_KEYS = frozenset({"enabled", "silhouette"})
DISPLAY_GUIDE_KEYS = frozenset({"grid", "axis"})
DISPLAY_GRID_GUIDE_KEYS = frozenset({"enabled"})
DISPLAY_AXIS_GUIDE_KEYS = frozenset({"enabled", "color", "opacity"})
DISPLAY_PART_COLOR_KEYS = frozenset({"mode", "color", "colors"})
DISPLAY_MODE_ALIASES = {mode: mode for mode in DISPLAY_MODES}
CAMERA_OPTION_KEYS = frozenset(
    {
        "preset", "name", "projection", "position", "target", "up", "direction", "zoom",
        "orthographicHalfHeight", "focalLength",
    }
)
SETTINGS_KEY_HOMES = {
    "edges": "display",
    "mode": "display",
    "exploded": "display",
    "clip": "display",
    "guides": "display",
    "partColor": "display",
    "projection": "camera",
    "orthographicHalfHeight": "camera",
    "focalLength": "camera",
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
# --- option values: a string from argv, or the real thing from a verb call ---------
#
# Every option below arrives as TEXT from the CLI and has to be parsed. The public
# `<format>.snapshot()` verbs hand the same options over as Python values -- a dict
# for a Render envelope, a dict for a camera -- and stringifying one of those would produce
# "{'settings': ...}", which cannot be parsed as JSON. So each loader takes the
# already-parsed shape as itself.


def parse_camera_option(raw_camera: object) -> object:
    if is_plain_object(raw_camera):
        return validate_camera_option(raw_camera, source_label="camera settings")
    camera = str(raw_camera or "").strip()
    if not camera:
        raise SnapshotError("--camera requires a preset, azimuth:elevation pair, or JSON camera object")
    if not camera.startswith("{"):
        presets = {"front", "back", "right", "left", "top", "bottom", "iso", "isometric", "side"}
        parts = camera.split(":")
        angle_pair = len(parts) >= 2
        if angle_pair:
            try:
                angle_pair = all(isfinite(float(part)) for part in parts)
            except ValueError:
                angle_pair = False
        if camera.lower() not in presets and not angle_pair:
            raise SnapshotError(f"Unknown camera preset: {camera}")
        return camera
    parsed = load_json_text(camera, "--camera")
    if not is_plain_object(parsed):
        raise SnapshotError("--camera must be a preset, azimuth:elevation pair, or JSON object")
    return validate_camera_option(parsed, source_label="--camera")


def validate_camera_option(value: object, *, source_label: str) -> dict[str, object]:
    if not is_plain_object(value):
        raise SnapshotError(f"camera must be a preset name or camera object ({source_label})")
    payload = dict(value)
    unknown = sorted(set(payload) - CAMERA_OPTION_KEYS)
    if unknown:
        raise SnapshotError(
            f"camera has unknown key(s): {', '.join(unknown)}; "
            f"supported keys: {', '.join(sorted(CAMERA_OPTION_KEYS))} ({source_label})"
        )
    projection = str(payload.get("projection") or "").strip().lower()
    if projection and projection not in {"orthographic", "perspective"}:
        raise SnapshotError(
            f"camera projection must be orthographic or perspective; "
            f"got {payload.get('projection')!r} ({source_label})"
        )
    for key in ("position", "target", "up", "direction"):
        if key not in payload:
            continue
        vector = payload[key]
        if not isinstance(vector, (list, tuple)) or len(vector) != 3 or any(
            isinstance(item, bool) or not isinstance(item, (int, float)) or not isfinite(float(item))
            for item in vector
        ):
            raise SnapshotError(f"camera {key} must be a three-number array ({source_label})")
        if key in {"up", "direction"} and sum(float(item) ** 2 for item in vector) <= 1e-12:
            raise SnapshotError(f"camera {key} must not be the zero vector ({source_label})")
    if "zoom" in payload:
        zoom = payload["zoom"]
        if isinstance(zoom, bool) or not isinstance(zoom, (int, float)) or not isfinite(float(zoom)) or zoom <= 0:
            raise SnapshotError(f"camera zoom must be a positive finite number ({source_label})")
    if "orthographicHalfHeight" in payload:
        half_height = payload["orthographicHalfHeight"]
        if (
            isinstance(half_height, bool)
            or not isinstance(half_height, (int, float))
            or not isfinite(float(half_height))
            or half_height <= 0
        ):
            raise SnapshotError(
                f"camera orthographicHalfHeight must be a positive finite number ({source_label})"
            )
    if "focalLength" in payload:
        focal_length = payload["focalLength"]
        if (
            isinstance(focal_length, bool)
            or not isinstance(focal_length, (int, float))
            or not isfinite(float(focal_length))
            or float(focal_length) < 20
            or float(focal_length) > 200
        ):
            raise SnapshotError(
                f"camera focalLength must be a finite number between 20 and 200 ({source_label})"
            )
    return payload
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
    # authored settings file is exactly the kind of file that needs to explain why its
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
    mode = str(payload.get("mode") or "").strip()
    if mode:
        normalized_mode = re.sub(r"[\s-]+", "_", mode.lower())
        if normalized_mode not in DISPLAY_MODES:
            supported = ", ".join(sorted(DISPLAY_MODES))
            raise SnapshotError(
                f"--display mode must be one of: {supported}; got {payload.get('mode')!r} ({source_label})"
            )
    clip = payload.get("clip")
    if clip is not None:
        if not is_plain_object(clip):
            raise SnapshotError(f"display clip must be an object ({source_label})")
        unknown = sorted(set(clip) - DISPLAY_CLIP_KEYS)
        if unknown:
            raise SnapshotError(f"display clip has unknown key(s): {', '.join(unknown)} ({source_label})")
        for key in ("enabled", "invert"):
            if key in clip:
                _render_boolean(clip[key], f"display.clip.{key}")
        if "axis" in clip and clip["axis"] not in {"x", "y", "z"}:
            raise SnapshotError("display.clip.axis must be x, y, or z")
        if "offset" in clip:
            _render_number(clip["offset"], "display.clip.offset", 0, 1)
        if "offsets" in clip:
            offsets = clip["offsets"]
            if not is_plain_object(offsets):
                raise SnapshotError(f"display clip.offsets must be an object ({source_label})")
            unknown = sorted(set(offsets) - {"x", "y", "z"})
            if unknown:
                raise SnapshotError(f"display clip.offsets has unknown key(s): {', '.join(unknown)} ({source_label})")
            for axis, value in offsets.items():
                _render_number(value, f"display.clip.offsets.{axis}", 0, 1)

    exploded = payload.get("exploded")
    if exploded is not None:
        if not is_plain_object(exploded):
            raise SnapshotError(f"display exploded must be an object ({source_label})")
        unknown = sorted(set(exploded) - DISPLAY_EXPLODED_KEYS)
        if unknown:
            raise SnapshotError(
                f"--display exploded supports only enabled and amount (the exploded layout "
                f"is automatic); unsupported keys: {', '.join(unknown)} ({source_label})"
            )
        if "enabled" in exploded:
            _render_boolean(exploded["enabled"], "display.exploded.enabled")
        if "amount" in exploded:
            _render_number(exploded["amount"], "display.exploded.amount", 0, 1)

    edges = payload.get("edges")
    if edges is not None:
        if not is_plain_object(edges):
            raise SnapshotError(f"display edges must be an object ({source_label})")
        unknown = sorted(set(edges) - DISPLAY_EDGE_KEYS)
        if unknown:
            raise SnapshotError(f"display edges has unknown key(s): {', '.join(unknown)} ({source_label})")
        for key in ("enabled", "silhouette"):
            if key in edges:
                _render_boolean(edges[key], f"display.edges.{key}")
    guides = payload.get("guides")
    if guides is not None:
        if not is_plain_object(guides):
            raise SnapshotError(f"display guides must be an object ({source_label})")
        unknown = sorted(set(guides) - DISPLAY_GUIDE_KEYS)
        if unknown:
            raise SnapshotError(f"display guides has unknown key(s): {', '.join(unknown)} ({source_label})")
        for name, keys in {
            "grid": DISPLAY_GRID_GUIDE_KEYS,
            "axis": DISPLAY_AXIS_GUIDE_KEYS,
        }.items():
            value = guides.get(name)
            if value is None:
                continue
            if not is_plain_object(value):
                raise SnapshotError(f"display guides.{name} must be an object ({source_label})")
            nested_unknown = sorted(set(value) - keys)
            if nested_unknown:
                raise SnapshotError(
                    f"display guides.{name} has unknown key(s): {', '.join(nested_unknown)} ({source_label})"
                )
            if "enabled" in value:
                _render_boolean(value["enabled"], f"display.guides.{name}.enabled")
            for key in (() if name == "grid" else ("color",)):
                if key in value:
                    _render_color(value[key], f"display.guides.{name}.{key}")
            if "opacity" in value:
                _render_number(value["opacity"], f"display.guides.{name}.opacity", 0, 1)
    part_color = payload.get("partColor")
    if part_color is not None:
        if not is_plain_object(part_color):
            raise SnapshotError(f"display partColor must be an object ({source_label})")
        unknown = sorted(set(part_color) - DISPLAY_PART_COLOR_KEYS)
        if unknown:
            raise SnapshotError(f"display partColor has unknown key(s): {', '.join(unknown)} ({source_label})")
        color_mode = str(part_color.get("mode") or "").strip().lower()
        if color_mode and color_mode not in PART_COLOR_MODES:
            raise SnapshotError(
                f"display partColor.mode must be original, single, or by_part ({source_label})"
            )
        color = part_color.get("color")
        if color is not None:
            _render_color(color, "display.partColor.color")
        colors = part_color.get("colors")
        if colors is not None:
            if not isinstance(colors, list) or not 1 <= len(colors) <= 50:
                raise SnapshotError(
                    f"display partColor.colors must contain 1 to 50 hex colors ({source_label})"
                )
            for index, item in enumerate(colors):
                _render_color(item, f"display.partColor.colors[{index}]")
def load_display_option(raw_display: object, *, cwd: Path) -> dict[str, object]:
    if is_plain_object(raw_display):
        payload = validate_direct_settings_payload(
            raw_display,
            option_name="--display",
            source_label="display settings",
            allowed_keys=DISPLAY_OPTION_KEYS,
            setting_label="display settings",
        )
        validate_display_settings_values(payload, source_label="display settings")
        return payload
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

    display_path = Path(display).expanduser()
    if not display_path.is_absolute():
        display_path = cwd / display_path
    looks_like_file = display.lower().endswith(".json") or "/" in display or "\\" in display
    if not looks_like_file and not display_path.exists():
        normalized_mode = re.sub(r"[\s-]+", "_", display.lower())
        if normalized_mode not in DISPLAY_MODES:
            supported = ", ".join(sorted(DISPLAY_MODES))
            raise SnapshotError(f"Unsupported display mode: {display}. Supported modes: {supported}")
        return {"mode": normalized_mode}
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
def _render_number(value: object, field: str, minimum: float, maximum: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
        or float(value) < minimum
        or float(value) > maximum
    ):
        raise SnapshotError(f"{field} must be a finite number between {minimum} and {maximum}")


def _render_color(value: object, field: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"#(?:[0-9a-fA-F]{3}){1,2}", value.strip()):
        raise SnapshotError(f"{field} must be a hex color")


def _render_boolean(value: object, field: str) -> None:
    if not isinstance(value, bool):
        raise SnapshotError(f"{field} must be a boolean")


def validate_render_option(value: object, *, source_label: str) -> dict[str, object]:
    if not is_plain_object(value):
        raise SnapshotError(f"--render JSON must be a render object: {source_label}")
    payload = dict(value)
    unknown = sorted(set(payload) - SUPPORTED_RENDER_KEYS)
    if unknown:
        raise SnapshotError(
            f"render has unknown key(s): {', '.join(unknown)}; "
            f"supported keys: {', '.join(sorted(SUPPORTED_RENDER_KEYS))} ({source_label})"
        )
    if "studio" in payload:
        if not isinstance(payload["studio"], str) or payload["studio"] not in RENDER_STUDIO_IDS:
            raise SnapshotError("render.studio must be light or dark")
    if "quality" in payload:
        if not isinstance(payload["quality"], str) or payload["quality"] not in RENDER_QUALITY_IDS:
            raise SnapshotError("render.quality must be preview or final")
    if "exposure" in payload:
        _render_number(payload["exposure"], "render.exposure", -5, 5)
    if "lighting" in payload:
        lighting = payload["lighting"]
        if not is_plain_object(lighting):
            raise SnapshotError(f"render.lighting must be an object ({source_label})")
        unknown_lighting = sorted(set(lighting) - RENDER_LIGHTING_KEYS)
        if unknown_lighting:
            raise SnapshotError(
                f"render.lighting has unknown key(s): {', '.join(unknown_lighting)}; "
                f"supported keys: {', '.join(sorted(RENDER_LIGHTING_KEYS))}"
            )
        for key, bounds in {
            "rotation": (-180, 180),
            "size": (0.25, 3),
            "fill": (0, 1),
        }.items():
            if key in lighting:
                _render_number(lighting[key], f"render.lighting.{key}", *bounds)
    if "backdrop" in payload:
        backdrop = payload["backdrop"]
        if not is_plain_object(backdrop):
            raise SnapshotError(f"render.backdrop must be an object ({source_label})")
        unknown_backdrop = sorted(set(backdrop) - RENDER_BACKDROP_KEYS)
        if unknown_backdrop:
            raise SnapshotError(
                f"render.backdrop has unknown key(s): {', '.join(unknown_backdrop)}; "
                f"supported keys: {', '.join(sorted(RENDER_BACKDROP_KEYS))}"
            )
        if "color" in backdrop:
            _render_color(backdrop["color"], "render.backdrop.color")
        for key in ("transparent", "ground"):
            if key in backdrop:
                _render_boolean(backdrop[key], f"render.backdrop.{key}")
        if "groundPlacement" in backdrop and backdrop["groundPlacement"] not in ("origin", "lowest"):
            raise SnapshotError("render.backdrop.groundPlacement must be origin or lowest")
    if "camera" in payload:
        camera = payload["camera"]
        payload["camera"] = parse_camera_option(camera)
    return payload


def snapshot_render_payload(value: object, *, source_label: str) -> dict[str, object]:
    """Validate a Render envelope and bind the snapshot frontdoor's light default.

    Render JSON keeps ``studio`` optional so the same object can follow an app's
    appearance. A snapshot process has no app appearance, so its deterministic
    fallback is the light photographic studio.
    """
    payload = validate_render_option(value, source_label=source_label)
    payload.setdefault("studio", "light")
    return payload


def load_render_option(raw_render: object, *, cwd: Path) -> dict[str, object]:
    if is_plain_object(raw_render):
        return snapshot_render_payload(raw_render, source_label="render settings")
    render = str(raw_render or "").strip()
    if not render:
        raise SnapshotError("--render requires a studio id, JSON object, or JSON file path")
    if render.startswith("{"):
        return snapshot_render_payload(load_json_text(render, "--render"), source_label="--render")
    render_path = Path(render).expanduser()
    if not render_path.is_absolute():
        render_path = cwd / render_path
    looks_like_file = render.lower().endswith(".json") or "/" in render or "\\" in render
    if not looks_like_file and not render_path.exists():
        return snapshot_render_payload({"studio": render}, source_label="--render")
    if not render_path.exists():
        raise SnapshotError(f"Render JSON file does not exist: {render}")
    return snapshot_render_payload(
        load_json_text(render_path.read_text(encoding="utf-8"), str(render_path)),
        source_label=str(render_path),
    )


def validate_output_settings(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not is_plain_object(value):
        raise SnapshotError("output must be an object")
    output = dict(value)
    unknown = sorted(set(output) - SUPPORTED_OUTPUT_SETTINGS_KEYS)
    if unknown:
        raise SnapshotError(
            f"output has unknown key(s): {', '.join(unknown)}; "
            f"supported keys: {', '.join(sorted(SUPPORTED_OUTPUT_SETTINGS_KEYS))}"
        )
    return output


def validate_quality_settings(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if not is_plain_object(value):
        raise SnapshotError("quality must be an object")
    quality = dict(value)
    unknown = sorted(set(quality) - SUPPORTED_QUALITY_KEYS)
    if unknown:
        raise SnapshotError(
            f"quality has unknown key(s): {', '.join(unknown)}; "
            f"supported keys: {', '.join(sorted(SUPPORTED_QUALITY_KEYS))}"
        )
    validate_render_tessellation(quality.get("tessellation"))
    return quality


def effective_display_request(job: Mapping[str, object]) -> dict[str, object]:
    """Return the CAD display request that can affect this snapshot.

    Photographic Render owns a private shaded presentation. Its top-level CAD
    display controls have already been rejected by
    :func:`validate_render_job_compatibility`.
    """
    display = job.get("display") if is_plain_object(job.get("display")) else {}
    return copy.deepcopy(dict(display))


def validate_render_job_compatibility(
    job: Mapping[str, object], *, mode: object | None = None,
) -> dict[str, object]:
    """Reject normal-CAD scene state paired with photographic Render.

    Presence is the contract: ``null`` and empty objects are still explicit
    inputs, so they fail instead of being silently treated as absent. Callers
    validate raw jobs before clearing outputs or resolving an input.
    """
    if "render" not in job:
        return dict(job)
    render_mode = str(mode if mode is not None else (job.get("mode") or "view")).strip().lower()
    if render_mode != "view":
        raise SnapshotError("Photographic Render supports only view mode")
    conflicts = sorted(set(job) & RENDER_INCOMPATIBLE_JOB_KEYS)
    if conflicts:
        raise SnapshotError(
            "Photographic Render cannot be combined with top-level CAD control(s): "
            f"{', '.join(conflicts)}. Put photographic camera and quality settings "
            "inside render."
        )
    return dict(job)


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
def asset_url_for_store_path(file_path: Path) -> str:
    """Asset URL for a file in the store (outside any render
    root): served by the ``/__store_asset/`` route, confined to the store's
    ``packages/`` tier. Same mtime/size version key as root assets."""
    from cadgen.store.view import views_root

    resolved_path = Path(file_path).resolve()
    base = views_root().resolve()
    if not path_is_inside_or_equal(resolved_path, base):
        raise SnapshotError(f"Store asset must be inside the store: {file_path}")
    relative_path = resolved_path.relative_to(base).as_posix()
    base_url = f"{STORE_ASSET_ROUTE_PREFIX}{encode_path_param(relative_path)}"
    try:
        file_stat = resolved_path.stat()
    except FileNotFoundError:
        return base_url
    cache_identity = "\0".join(
        (str(resolved_path), str(file_stat.st_size), str(file_stat.st_mtime_ns))
    )
    return f"{base_url}?v={sha256(cache_identity.encode('utf-8')).hexdigest()[:16]}"


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
def normalize_size_profile(value: object) -> str:
    return str(value or "").strip().lower().replace("_", "-")
def explicit_size_profile(job: Mapping[str, object], output: Mapping[str, object]) -> str:
    del output
    output_settings = job.get("output") if is_plain_object(job.get("output")) else {}
    return normalize_size_profile(output_settings.get("sizeProfile") or "")
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
    output_settings = job.get("output") if is_plain_object(job.get("output")) else {}
    if (
        profile in {"dimensioned", "section", "labeled"}
        or mode == "section"
        or output_settings.get("viewLabels") is True
        or output.get("viewLabel")
        or output.get("label")
    ):
        return DIAGNOSTIC_RENDER_WIDTH, DIAGNOSTIC_RENDER_HEIGHT
    if profile == "diagnostic" or not profile:
        return DIAGNOSTIC_RENDER_WIDTH, DIAGNOSTIC_RENDER_HEIGHT
    return SIMPLE_RENDER_WIDTH, SIMPLE_RENDER_HEIGHT
def resolve_output_size(job: Mapping[str, object], output: Mapping[str, object]) -> tuple[int, int]:
    default_width, default_height = default_render_size(job, output)
    return (
        positive_integer(output.get("width") or default_width, "output width"),
        positive_integer(output.get("height") or default_height, "output height"),
    )
def snapshot_timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


# --- output paths: if you name it, you get it; if you don't, we name it -------------
#
# A snapshot used to append a datetimestamp to the filename it was ASKED for, so
# `--output tmp/plate.png` wrote `tmp/plate_20260830T033855Z.png`. The reason was
# stale imagery: a failed render left the previous file sitting at the requested
# path, and an agent that read it anyway reasoned confidently about yesterday's
# pixels. Unique names made that read impossible.
#
# It bought that with the wrong mechanism -- the command's output differed from its
# declaration, every downstream step had to parse the "saved snapshot:" line instead
# of knowing the path it had just written, and tmp/ filled with orphans. The guard
# lives in `clear_render_output_targets` now: the target is DELETED before the render
# starts, so a failure leaves NO file rather than an old one. That is strictly
# stronger (the stale read is still impossible, and the failure is visible as a
# missing file) and it costs the success path nothing, so the declared path is
# honoured exactly.
#
# What survives of the timestamp is the case where the caller expressed no opinion:
# a DIRECTORY output gets a generated name inside it, and that name is timestamped.


def output_path_names_a_directory(output_path: str, resolved_path: Path) -> bool:
    """True when this output names a directory to generate a name INSIDE.

    A trailing separator says so outright, and is read off the raw STRING because
    ``Path`` drops it -- that is the one way to name a directory that does not
    exist yet. Otherwise a path that already IS one counts (``.`` and ``..``
    included). Anything else is an explicit file path, whether or not it exists:
    naming a file that is not there yet is the whole point of asking for one.

    A trailing separator on a path that already exists as a FILE is neither: it
    asks for a directory and names something that cannot become one. Left alone
    it resolved to ``<the file>/<generated name>``, which nothing detects until
    the write -- a ``NotADirectoryError`` from inside the atomic replace, after
    the whole render has been paid for. It raises HERE instead, at the first
    resolution of the path, which for a CLI run is before the input is even
    read.
    """
    if output_path.endswith(("/", "\\")):
        if resolved_path.exists() and not resolved_path.is_dir():
            raise SnapshotError(
                f"snapshot output {output_path!r} ends in a path separator, which names a "
                f"directory to generate a name inside, but {resolved_path} is an existing "
                "file; drop the trailing separator to write that file, or name a directory"
            )
        return True
    return resolved_path.is_dir()


def generated_output_name(
    job: Mapping[str, object],
    *,
    index: int,
    output_count: int,
    timestamp: str,
    job_index: int = 0,
    job_count: int = 1,
) -> str:
    """The name a directory-mode output is given: ``<input-stem>[_j<m>][_<n>]_<ts>.png``.

    Every output in a packet shares one timestamp -- that is what makes a
    multi-view run read as one run -- so the discriminator is the ONLY thing
    keeping two generated names apart, and it has to cover both axes a packet
    varies along. The output index alone was not enough: a packet of one-output
    jobs rendering the same model from different cameras into one directory gave
    every job the identical ``<stem>_<ts>.png``, so N renders finished and one
    file survived. Each half appears only when it discriminates something, so
    the common single-job single-output case still reads as ``<stem>_<ts>.png``.
    """
    stem = Path(str(job.get("input") or "")).stem or "snapshot"
    parts = []
    if job_count > 1:
        parts.append(f"j{job_index + 1}")
    if output_count > 1:
        parts.append(str(index + 1))
    discriminator = f"_{'_'.join(parts)}" if parts else ""
    return f"{stem}{discriminator}_{timestamp}.png"


def resolve_output_target(
    output_path: str,
    *,
    resolved_cwd: Path,
    generated_name: str,
) -> str:
    """The absolute path an output writes to, under the one output rule.

    An explicit file path is used EXACTLY as given -- a relative one against the
    invoking process's working directory -- and a directory gets ``generated_name``
    inside it.
    """
    if not output_path:
        return ""
    candidate = Path(output_path).expanduser()
    resolved = candidate if candidate.is_absolute() else resolved_cwd / candidate
    if output_path_names_a_directory(output_path, resolved):
        return str((resolved / generated_name).resolve())
    return str(resolved.resolve())


def declared_output_path(output: object) -> str:
    """The path an output declares, before or after normalization.

    A raw output is a bare string or an object with a ``path``; a normalized one
    is always the object. Both shapes are read here so the clear below can run
    against a payload that has not been resolved yet.
    """
    if isinstance(output, str):
        return output
    if is_plain_object(output):
        return str(output.get("path") or "")
    return ""


def clear_render_output_targets(jobs: object, *, resolved_cwd: Path | None = None) -> None:
    """Delete every declared output target, before any work is done for it.

    This is the guard the filename timestamp used to be (see the note above), and
    it is why a declared path can now be honoured exactly: whatever happens next,
    the only thing that can appear at that path is this run's output.

    "Before any work" is stronger than "before the browser starts", and the
    difference is the common failure. Resolution builds the STEP package, and that
    is where a bad input fails -- minutes in, and long before the renderer is
    reached. Clearing at render time would leave the previous image sitting at the
    requested path for exactly the runs most likely to be read anyway.

    Directory-valued outputs are skipped: their name is generated fresh, so there
    is nothing of theirs to delete, and unlinking the directory itself would be
    wrong. A target that cannot be removed is a target that cannot be honestly
    written, so that failure is raised here -- before the expensive work, naming
    the path -- rather than after the render has already been paid for.
    """
    base = (resolved_cwd or Path.cwd()).resolve()
    for job in jobs or []:
        if not is_plain_object(job):
            continue
        for output in job.get("outputs") or []:
            declared = declared_output_path(output)
            if not declared:
                continue
            candidate = Path(declared)
            target = candidate if candidate.is_absolute() else base / candidate
            if output_path_names_a_directory(declared, target):
                continue
            try:
                target.unlink(missing_ok=True)
            except OSError as exc:
                raise SnapshotError(f"Cannot clear the snapshot output path: {target} ({exc})") from exc
def normalize_snapshot_job_packet(raw_payload: object) -> tuple[bool, list[object]]:
    if isinstance(raw_payload, list):
        return False, raw_payload
    if is_plain_object(raw_payload) and isinstance(raw_payload.get("jobs"), list):
        return False, list(raw_payload["jobs"])
    return True, [raw_payload]
def validate_render_tessellation(value: object) -> None:
    """Refuse an unusable ``quality.tessellation`` here, where the caller still
    gets a message. The page validates the same field (source.js) because it
    also serves the viewer, but by then the cost of an absurd request is a dead
    renderer and no explanation."""
    if value is None:
        return
    if not is_plain_object(value):
        raise SnapshotError("quality.tessellation must be an object of chordTolerance/angleTolerance")
    unknown = sorted(set(value) - set(MIN_RENDER_TESSELLATION))
    if unknown:
        raise SnapshotError(
            f"quality.tessellation has unknown key(s): {', '.join(unknown)}; "
            f"supported keys: {', '.join(sorted(MIN_RENDER_TESSELLATION))}"
        )
    for key, floor in MIN_RENDER_TESSELLATION.items():
        if key not in value:
            continue
        raw = value[key]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not isfinite(float(raw)) or float(raw) <= 0:
            raise SnapshotError(f"quality.tessellation.{key} must be a positive finite number")
        if float(raw) < floor:
            raise SnapshotError(
                f"quality.tessellation.{key} must be at least {floor}; finer sampling "
                "exhausts the renderer instead of improving the image"
            )


def normalize_common_job(
    job: dict[str, object],
    *,
    mode: str,
    resolved_cwd: Path,
    timestamp: str | None,
    job_index: int = 0,
    job_count: int = 1,
) -> dict[str, object]:
    """Kind-independent job normalization shared by every input kind: the outputs
    guard, scene/output/quality validation, output-path resolution, and the
    common return shape.
    Kind resolvers run their capability checks first, then call this, so a
    STEP/mesh/robot job all normalize identically; the caller attaches its
    kind-specific ``resolved`` payload to the returned job.

    ``job_index``/``job_count`` are this job's place in its packet, needed only
    so a directory-valued output's generated name can discriminate across jobs
    as well as within one (see :func:`generated_output_name`)."""
    job = validate_render_job_compatibility(job, mode=mode)
    outputs = job.get("outputs") if isinstance(job.get("outputs"), list) else []
    if mode != "list" and not outputs:
        raise SnapshotError("render job must include outputs for non-list modes")

    # What an output may be named follows from whether this job asked for a
    # sequence. A still writes PNG, so a VIDEO name is refused up front: writing
    # a PNG into one answers a motion question with a frozen image under a name
    # no player opens, at exit 0. A video writes exactly one file, and its
    # extension picks the container. Both halves read the same table, so the
    # names a video may be given and the names a still may not cannot drift.
    video = job.get("video")
    if video is not None:
        from cadgen.snapshot_video import validate_video_output

        if len(outputs) != 1:
            raise SnapshotError(
                f"a video renders one clip to one file; this job declares {len(outputs)} "
                "outputs (split the cameras into their own jobs)"
            )
        # `video` is the NORMALIZED request by the time it gets here (the kind
        # resolver validated its shape), so only the output half is left.
        validate_video_output(video, declared_output_path(outputs[0]))
    else:
        from cadgen.snapshot_video import VIDEO_CONTAINERS

        for output in outputs:
            output_path_text = str((output.get("path") if is_plain_object(output) else output) or "")
            if Path(output_path_text.strip()).suffix.lower() in VIDEO_CONTAINERS:
                raise SnapshotError(
                    f"snapshot renders PNG stills: {output_path_text.strip()} names a video "
                    "container, so name a .png output, or pass --video with --animation to "
                    "render the clip into it"
                )

    normalized_render = None
    if "render" in job:
        normalized_render = snapshot_render_payload(job.get("render"), source_label="job render")

    output_settings = validate_output_settings(job.get("output"))
    quality = validate_quality_settings(job.get("quality"))

    raw_scale = str(job.get("scale") or "").strip().lower()
    if raw_scale:
        # Honour the requested scale. This used to force "cad" unconditionally, so a job
        # asking for the URDF profile (robots are authored in metres, CAD in millimetres)
        # was accepted, validated, and then silently overwritten — the model rendered
        # correctly but framed for a workpiece a thousand times its size.
        if raw_scale not in {"cad", "urdf"}:
            raise SnapshotError(f"Unsupported scene scale: {raw_scale} (expected cad or urdf)")
        job["scale"] = raw_scale

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
        normalized_output = {
                **output_object,
                "path": resolve_output_target(
                    output_path,
                    resolved_cwd=resolved_cwd,
                    generated_name=generated_output_name(
                        {**job, "mode": mode},
                        index=index,
                        output_count=len(outputs),
                        timestamp=resolved_timestamp,
                        job_index=job_index,
                        job_count=job_count,
                    ),
                ),
                "width": width,
                "height": height,
            }
        explicit_camera = output_object.get("camera")
        if explicit_camera is None and normalized_render is None:
            explicit_camera = job.get("camera")
        if explicit_camera is not None:
            normalized_output["camera"] = parse_camera_option(explicit_camera)
        normalized_outputs.append(normalized_output)

    return {
        **job,
        "mode": mode,
        **({"render": normalized_render} if normalized_render is not None else {}),
        "output": output_settings,
        **({"quality": quality} if normalized_render is None else {}),
        "outputs": normalized_outputs,
    }
def has_kinematics_render_values(value: object) -> bool:
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
def resolve_mesh_render_job(
    job: dict[str, object],
    *,
    kind: str,
    input_path: Path,
    root_path: Path,
    resolved_cwd: Path,
    timestamp: str | None,
    job_index: int = 0,
    job_count: int = 1,
    **_kind_context: object,
) -> dict[str, object]:
    """Resolve a direct mesh input (GLB/STL/3MF) that carries no STEP topology.

    Meshes render through the shared mesh path, so this skips the STEP artifact/package
    pipeline entirely and hands the renderer a plain asset URL. STEP-only options are
    rejected up front with clear errors rather than silently ignored downstream."""
    job = validate_render_job_compatibility(job)
    label = kind.upper()

    # Selector focus/hide/refs need the selector index built from STEP topology.
    if selection_filter_values(job):
        raise SnapshotError(
            f"selection focus/hide/refs require STEP topology; {label} mesh inputs have no "
            "part/subassembly selectors"
        )
    # kinematics values drive the model's declared kinematics block.
    if has_kinematics_render_values(job.get("kinematics")):
        raise SnapshotError(
            f"kinematics values require a STEP model; {label} mesh inputs are not parametric"
        )
    if job.get("animation") is not None:
        raise SnapshotError(
            f"an animation frame requires a STEP document with animation in its sidecar; "
            f"{label} mesh inputs have no clips"
        )
    if job.get("video") is not None:
        raise SnapshotError(
            f"a video renders an animation clip; {label} mesh inputs have no clips to render"
        )
    quality = job.get("quality") if is_plain_object(job.get("quality")) else {}
    if quality.get("tessellation") is not None:
        raise SnapshotError(
            f"quality.tessellation requires an exact-surface STEP package; {label} is an existing mesh"
        )

    mode = str(job.get("mode") or "view").strip().lower()
    if mode not in SUPPORTED_RENDER_MODES:
        raise SnapshotError(f"Unsupported render mode: {mode or '(missing)'}")
    if mode not in MESH_SUPPORTED_RENDER_MODES:
        supported = ", ".join(sorted(MESH_SUPPORTED_RENDER_MODES))
        raise SnapshotError(
            f"{mode} mode requires STEP topology; {label} mesh inputs support: {supported}"
        )

    # A normal mesh snapshot has no CAD topology for edge modes or exploded views.
    # Photographic Render's incompatible CAD display request has already failed.
    display = effective_display_request(job)
    raw_display_mode = re.sub(r"[\s-]+", "_", str(display.get("mode") or "").strip().lower())
    canonical_display_mode = DISPLAY_MODE_ALIASES.get(raw_display_mode, raw_display_mode)
    if canonical_display_mode in {"shaded_edges", *TOPOLOGY_DISPLAY_MODES}:
        raise SnapshotError(
            f"{canonical_display_mode} display requires STEP CAD edges; {label} mesh inputs "
            "have no CAD edge topology"
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

    normalized = normalize_common_job(
        job,
        mode=mode,
        resolved_cwd=resolved_cwd,
        timestamp=timestamp,
        job_index=job_index,
        job_count=job_count,
    )
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
# --- shared component-tessellation cache (design/unified-tessellation.md) ----
#
# The snapshot page resolves component tessellations through the SAME disk
# cache the mesh-export CLI uses (immutable objects plus index/mesh; codec and
# key scheme in packages/core/src/lib/surf/tessellationCache.js). The page
# cannot touch the filesystem, so the host serves the cache: GET
# /__tess_cache/<key>.tess is a read, POST is a best-effort write-back after
# an in-page tessellation miss. CADGEN_MESH_CACHE=0 turns both directions
# off. Python validates the shared TESS input identity, header and content hash;
# metadata probes and exact-object reads enforce admission before body transfer.
#
# TRANSPORT: bulk bytes must NOT go through Playwright at all. CDP serializes
# every fulfilled body as base64 over the devtools pipe at ~20 MB/s, which made
# a warm moonwatch snapshot spend ~8s moving ~180 MB of surfs + cache entries.
# Worse, INTERCEPTION alone costs the pipe in the other direction: a routed
# request's body reaches the driver as escaped text in one protocol message, so
# a 92 MB cache write-back exceeded Node's string limit and killed the renderer
# (reported to the caller as a lost driver connection). A 307 to loopback
# cannot save such a request — by then the body has already crossed.
#
# So the renderer runs a loopback HTTP server and the page addresses it by its
# ABSOLUTE origin for the cache (window.__cadgenSnapshotAssetOrigin, injected
# in BatchSnapshotRenderer.start): those requests are never intercepted, in
# either direction, at any size. Page-relative asset URLs (/__render_asset/,
# the store prefix) are GET-only, so they stay intercepted and answer with a
# tiny 307 to the same server. The intercepted page uses localhost (a secure
# context for its required SubtleCrypto checks), while the loopback responses
# carry CORS headers and answer the preflight their distinct origin triggers.
# Without that server there is no working transport, so start() raises instead
# of degrading.

TESS_CACHE_ROUTE_PREFIX = "/__tess_cache/"
# The route's safe filename envelope. The store additionally requires the
# current exact surface-input/algorithm/payload/binary64-tolerance key.
TESS_CACHE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]*\.tess$")


def tessellation_cache_enabled() -> bool:
    return os.environ.get("CADGEN_MESH_CACHE") != "0"


def _tessellation_cache_key(pathname: str) -> str | None:
    name = str(pathname or "")[len(TESS_CACHE_ROUTE_PREFIX):]
    if not TESS_CACHE_NAME_PATTERN.fullmatch(name) or ".." in name:
        return None
    return name[:-len(".tess")]


def read_tessellation_cache_entry(pathname: str, *, expected_object=None, max_bytes=None) -> bytes | None:
    """One entry's bytes, from the mesh index (``index/mesh`` -> object); None
    for a refused name, a miss, or a disabled cache."""
    from cadgen.store.tess_cache import read_tessellation_cache
    key = _tessellation_cache_key(pathname)
    if key is None or not tessellation_cache_enabled():
        return None
    try:
        return read_tessellation_cache(
            key, expected_object=expected_object, max_bytes=max_bytes,
        )
    except ValueError:
        return None


def write_tessellation_cache_entry(pathname: str, body: bytes | None) -> bool:
    """Best-effort write-back; False for an invalid or conflicting entry."""
    return _write_tessellation_cache_entry_status(pathname, body) == 204


def _write_tessellation_cache_entry_status(pathname: str, body: bytes | None) -> int:
    key = _tessellation_cache_key(pathname)
    if key is None:
        return 403
    if body:
        from cadgen.store.meshes import MeshConflictError
        from cadgen.store.tess_cache import write_tessellation_cache
        try:
            write_tessellation_cache(key, body)
        except MeshConflictError:
            return 409
        except (ValueError, TypeError, KeyError, OverflowError, struct.error):
            return 400
    return 204


# Probe small index facts, then request only admitted exact objects. The shared
# TESB container stays unchanged; store.tess_cache owns both hosts' framing.
TESS_CACHE_BATCH_PATH = "/__tess_cache/batch"
TESS_CACHE_BATCH_MAGIC = 0x42534554  # "TESB" little-endian
TESS_CACHE_BATCH_VERSION = 1
TESS_CACHE_BATCH_MAX_NAMES = 256
TESS_CACHE_PROBE_PATH = "/__tess_cache/probe"


def read_tessellation_cache_batch(body: bytes | None) -> bytes | None:
    """One shared bounded exact-object TESB route for viewer and snapshots."""
    from cadgen.store.tess_cache import read_tess_cache_batch

    return read_tess_cache_batch(body)


RENDER_ASSET_ROUTE_PREFIX = "/__render_asset/"
STORE_ASSET_ROUTE_PREFIX = "/__store_asset/"


def _store_packages_root() -> Path:
    from cadgen.store.view import views_root

    return views_root()


def _write_http_body(output, body: bytes) -> None:
    """Send large mesh batches without exceeding a platform socket-write limit."""
    view = memoryview(body)
    for start in range(0, len(view), 16 * 1024 * 1024):
        output.write(view[start : start + 16 * 1024 * 1024])


class SnapshotAssetServer:
    """Loopback HTTP server for the snapshot page's BULK bytes.

    Serves exactly two path families — ``/__render_asset/`` (files under the
    active render root, same containment rule as the CDP route for the page
    itself) and ``/__tess_cache/`` (the shared tessellation cache) — to
    whatever origin the snapshot page runs as (CORS ``*``; the socket is
    loopback-only and serves only what the page may already read).
    ``root_provider`` is read per request so one server follows the renderer
    across jobs. There is no fallback: the renderer refuses to start without
    this server, because the CDP transport cannot carry these payloads.
    """

    def __init__(self, root_provider) -> None:
        import http.server

        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args) -> None:  # noqa: D102 - quiet by design
                return

            def _headers(self, status: int, content_type: str, length: int) -> None:
                self.send_response(status)
                self.send_header("access-control-allow-origin", "*")
                self.send_header("access-control-expose-headers", "content-length")
                self.send_header("cache-control", "no-store")
                self.send_header("content-type", content_type)
                self.send_header("content-length", str(length))
                self.end_headers()

            def _send(self, status: int, body: bytes = b"", content_type: str = "application/octet-stream") -> None:
                self._headers(status, content_type, len(body))
                if body:
                    _write_http_body(self.wfile, body)

            def do_OPTIONS(self) -> None:  # noqa: N802 - http.server naming
                self.send_response(204)
                self.send_header("access-control-allow-origin", "*")
                self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
                self.send_header("access-control-allow-headers", "content-type")
                self.send_header("content-length", "0")
                self.end_headers()

            def do_GET(self) -> None:  # noqa: N802 - http.server naming
                parsed = urlparse(self.path)
                pathname = parsed.path
                if pathname.startswith(TESS_CACHE_ROUTE_PREFIX):
                    query = parse_qs(parsed.query)
                    from cadgen.store.tess_cache import parse_tess_cache_admission

                    try:
                        digest, limit = parse_tess_cache_admission(
                            query.get("object", [None])[0], query.get("maxBytes", [None])[0],
                        )
                    except (TypeError, ValueError):
                        self._send(400)
                        return
                    body = read_tessellation_cache_entry(
                        pathname, expected_object=digest, max_bytes=limit,
                    )
                    if body is None:
                        self._send(404, b"miss", "text/plain; charset=utf-8")
                        return
                    self._send(200, body)
                    return
                if pathname.startswith(STORE_ASSET_ROUTE_PREFIX):
                    try:
                        file_path = route_file(pathname, STORE_ASSET_ROUTE_PREFIX, _store_packages_root())
                    except RouteFileError as exc:
                        self._send(exc.status, str(exc).encode(), "text/plain; charset=utf-8")
                        return
                    if not file_path.is_file():
                        self._send(404, b"not found", "text/plain; charset=utf-8")
                        return
                    self._send(200, file_path.read_bytes(), content_type_for_path(file_path))
                    return
                if pathname.startswith(RENDER_ASSET_ROUTE_PREFIX):
                    root = server.root_provider()
                    if root is None:
                        self._send(404, b"no active render root", "text/plain; charset=utf-8")
                        return
                    try:
                        file_path = route_file(pathname, RENDER_ASSET_ROUTE_PREFIX, root)
                    except RouteFileError as exc:
                        self._send(exc.status, str(exc).encode(), "text/plain; charset=utf-8")
                        return
                    if not file_path.is_file():
                        self._send(404, b"not found", "text/plain; charset=utf-8")
                        return
                    self._send(200, file_path.read_bytes(), content_type_for_path(file_path))
                    return
                self._send(404, b"not found", "text/plain; charset=utf-8")

            def do_POST(self) -> None:  # noqa: N802 - http.server naming
                pathname = urlparse(self.path).path
                if not pathname.startswith(TESS_CACHE_ROUTE_PREFIX):
                    self._send(404, b"not found", "text/plain; charset=utf-8")
                    return
                from cadgen.store.tess_cache import TESS_CACHE_METADATA_MAX_BYTES

                try:
                    length = int(self.headers.get("content-length") or 0)
                    if length < 0 or self.headers.get("transfer-encoding"):
                        raise ValueError("unsupported request framing")
                except ValueError:
                    self.close_connection = True
                    self._send(400)
                    return
                maximum = TESS_CACHE_METADATA_MAX_BYTES if pathname in (TESS_CACHE_PROBE_PATH, TESS_CACHE_BATCH_PATH) else 256 * 1024 * 1024
                if length > maximum:
                    self.close_connection = True
                    self._send(413, b"oversized cache request")
                    return
                body = self.rfile.read(length) if length > 0 else b""
                if pathname == TESS_CACHE_PROBE_PATH:
                    from cadgen.store.tess_cache import read_tess_cache_probe

                    result = read_tess_cache_probe(body)
                    if result is None:
                        self._send(400, b"bad tessellation probe request")
                        return
                    self._send(200, json.dumps(result, separators=(",", ":")).encode(), "application/json")
                    return
                if pathname == TESS_CACHE_BATCH_PATH:
                    batch = read_tessellation_cache_batch(body)
                    if batch is None:
                        self._send(400, b"bad batch request", "text/plain; charset=utf-8")
                        return
                    self._send(200, batch)
                    return
                self._send(_write_tessellation_cache_entry_status(pathname, body))

        self.root_provider = root_provider
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        import threading

        self._thread = threading.Thread(target=self._httpd.serve_forever, name="snapshot-assets", daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except OSError:
            pass


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
    if parsed.path.startswith(STORE_ASSET_ROUTE_PREFIX):
        return route_file(parsed.path, STORE_ASSET_ROUTE_PREFIX, _store_packages_root())
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
        # The driver is told where render.html/snapshot-render.js are rather than locating
        # them relative to itself; start() is where their absence is reported, so that
        # constructing a renderer stays free of filesystem work.
        self.runtime_dir = Path(runtime_dir)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.active_root_path: Path | None = None
        self.asset_server: SnapshotAssetServer | None = None
        self.started = False

    async def start(self) -> None:
        if self.started:
            return
        # Before Playwright, before the asset server: a missing bundle otherwise surfaced
        # as a blank page that had 404'd on its own script.
        require_browser_runtime(self.runtime_dir)
        try:
            try:
                self.asset_server = SnapshotAssetServer(lambda: self.active_root_path)
            except OSError as exc:
                # The loopback server is the ONLY transport for bulk mesh bytes.
                # The old fallback (Playwright's route) hands every intercepted
                # body to the driver as escaped text in one protocol message, so
                # a large assembly killed the renderer with ERR_STRING_TOO_LONG
                # and reported it as a lost driver connection. A snapshot that
                # cannot bind a loopback socket must say so, not silently take
                # the transport that fails on real models.
                raise SnapshotError(
                    "CAD snapshot needs a loopback HTTP server on 127.0.0.1 for its mesh "
                    f"bytes and could not start one: {exc}. Allow a local socket "
                    "(the port is ephemeral and never leaves this machine) and retry."
                ) from exc
            try:
                from playwright.async_api import async_playwright
            except ImportError as exc:
                raise SnapshotError(
                    "CAD snapshot requires the Python playwright package. "
                    "Install the invoking skill's own requirements.txt (it ships playwright), "
                    "then run `python -m playwright install chromium` if needed."
                ) from exc
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                timeout=RENDER_BROWSER_STARTUP_TIMEOUT_MS,
                # The intercepted localhost page and its 127.0.0.1 bulk server
                # are distinct origins. Keep the Private Network Access flags
                # that make this cross-origin loopback transport work across
                # Chromium generations; otherwise a blocked redirect silently
                # forces bytes back through the ~20 MB/s CDP fulfill path. This
                # renderer loads no web content — only our own runtime and files.
                # Feature names cover the PNA generations: Chromium ~94-130
                # shipped BlockInsecurePrivateNetworkRequests + the two
                # preflight flags; newer builds renamed the check to
                # PrivateNetworkAccessChecks / LocalNetworkAccessChecks (the
                # one this bundled build enforces — verified by repro).
                args=[
                    "--disable-features=BlockInsecurePrivateNetworkRequests,"
                    "PrivateNetworkAccessSendPreflights,"
                    "PrivateNetworkAccessRespectPreflightResults,"
                    "PrivateNetworkAccessChecks,"
                    "LocalNetworkAccessChecks",
                    # Headless Chromium defaults to SOFTWARE WebGL
                    # (SwiftShader); on a moonwatch-class model that software
                    # rasterization dominated the whole warm snapshot (~4.6s
                    # of a ~6.8s render loop, measured via stageTimings).
                    # Metal ANGLE uses the real GPU on macOS; elsewhere the
                    # platform default stands.
                    *(["--use-angle=metal"] if sys.platform == "darwin" else []),
                ],
            )
            self.context = await self.browser.new_context(
                viewport={"width": SIMPLE_RENDER_WIDTH, "height": SIMPLE_RENDER_HEIGHT},
                device_scale_factor=1,
            )
            self.page = await self.context.new_page()
            # The page addresses the cache server DIRECTLY. Injected before any
            # page script so the runtime's provider is built with it (see the
            # transport note above: an intercepted URL costs the pipe, even
            # when the route only answers with a redirect).
            await self.context.add_init_script(
                f"window.__cadgenSnapshotAssetOrigin = {json.dumps(self.asset_server.base_url)};"
            )
            await self.page.route(SNAPSHOT_ROUTE_GLOB, self.handle_route)
            await self.page.goto(SNAPSHOT_RENDER_URL, wait_until="load", timeout=DEFAULT_TIMEOUT_SECONDS * 1000)
            await self.page.wait_for_function(
                "typeof window.__snapshotRender === 'function' && "
                "typeof window.__snapshotRenderSequence === 'function'",
                timeout=DEFAULT_TIMEOUT_SECONDS * 1000,
            )
            self.started = True
        except Exception:  # noqa: BLE001 - any startup failure must still tear down the browser, then re-raise
            await self.close()
            raise

    async def handle_route(self, route: Any) -> None:
        request = route.request
        parsed = urlparse(request.url)
        bulk = (
            parsed.path.startswith(RENDER_ASSET_ROUTE_PREFIX)
            or parsed.path.startswith(STORE_ASSET_ROUTE_PREFIX)
        )
        if bulk and request.url.startswith(SNAPSHOT_ORIGIN):
            # These asset URLs are page-relative (the job names files, not
            # origins), so they are intercepted and redirected: a tiny 307
            # crosses the pipe and the payload rides the loopback socket. GETs
            # only — nothing POSTs a body here, which is why the redirect is
            # enough for them and not for the cache (see the transport note).
            await route.fulfill(
                status=307,
                headers={"location": f"{self.asset_server.base_url}{parsed.path}"},
                body="",
            )
            return
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

    async def render_video(
        self,
        job: Mapping[str, object],
        *,
        progress: object | None = None,
        narrate: object | None = None,
    ) -> dict[str, object]:
        """Render one job's animation clip as a video and report what was written.

        The page prepares the source, embedded animation and model ONCE and
        then answers one capture request per frame: fetching and tessellating a
        document 1800 times is not a slower video, it is no video at all. The
        frames come back a PNG at a time for the same reason the mesh bytes ride
        a loopback socket (see the transport note above) -- an array of every
        frame is a protocol message no driver pipe can carry.

        The frames land in a temp directory and ffmpeg encodes them. Neither the
        frames nor their bytes appear in the result: what a caller gets is the
        path, which is what it asked for.

        ``narrate`` is how a video says what it is doing where nothing paints a
        bar. This is the one render whose work is measured in thousands of units
        and tens of minutes, and the door that serves it (``cadgen step
        snapshot``) always runs in a daemon worker, whose stderr is a frame relay
        and not a tty -- so the frame counter below reaches nobody there. A
        caller that IS painting passes nothing and gets none of these lines.
        """
        import tempfile

        from cadgen.snapshot_video import (
            VIDEO_FRAME_PATTERN,
            encode_video,
            video_container_for_path,
        )

        await self.start()
        report = resolve_progress(progress)
        say = narrate if callable(narrate) else (lambda message: None)
        resolved = job.get("resolved") if is_plain_object(job.get("resolved")) else {}
        self.active_root_path = Path(str(resolved.get("rootPath") or "")).resolve()
        width, height = max_output_size(job)
        await self.page.set_viewport_size({"width": width, "height": height})
        timeout_seconds = job.get("timeoutSeconds") or DEFAULT_TIMEOUT_SECONDS
        video = job["video"] if is_plain_object(job.get("video")) else {}
        output = job["outputs"][0]
        output_path = Path(str(output.get("path") or ""))
        container = video_container_for_path(str(output_path))

        # The preparation loads, builds, and walks the clip once to find the
        # bounds the camera is locked to, so on a very long clip it is the one
        # call whose cost grows with the frame count. It shares the job's
        # `timeoutSeconds` with everything else; a clip that needs longer than
        # that to be MEASURED raises it there.
        report.detail(f"{job.get('input') or ''} (preparing)")
        say(f"video: preparing {job.get('input') or ''}")
        prepared = await with_snapshot_timeout(
            self.page.evaluate("(renderJob) => window.__snapshotRenderSequence(renderJob)", dict(job)),
            timeout_seconds,
            "video preparation",
        )
        if not is_plain_object(prepared) or not prepared.get("ok"):
            raise SnapshotError("the browser could not prepare the video sequence")
        # The frame count comes from the PAGE because the clip does: choreography
        # is JavaScript, so the duration and the loop flag that decide the default
        # span are only readable there.
        frames = int(prepared.get("frames") or 0)
        fps = int(prepared.get("fps") or video.get("fps") or 0)
        seconds = float(prepared.get("seconds") or 0.0)
        warnings: list[str] = []
        # The camera the PAGE resolved, reported the way a still reports it. The
        # request is not a substitute: an explicit-position camera is an object,
        # and echoing it puts a Python repr in a machine-readable field.
        resolved_camera = ""
        # Said before frame 0, because it is the only disclosure of how long this
        # will run: a typo'd `{"seconds": 300, "fps": 120}` and a deliberate 20 s
        # clip look identical from outside until the frame total is named.
        say(f"video: {frames} frames at {fps} fps ({seconds:g}s) -> {output_path}")
        counted_at = time.perf_counter()
        try:
            with tempfile.TemporaryDirectory(prefix="cadgen-video-") as frames_dir:
                frames_path = Path(frames_dir)
                # A frame is a unit of work the caller can watch. Under the
                # packet's job counter a 1800-frame render reports 0/1 for
                # minutes; the packet loop restores its own total afterwards.
                report.phase(PHASE_RENDER, total=frames, detail=str(job.get("input") or ""))
                for index in range(frames):
                    frame = await with_snapshot_timeout(
                        self.page.evaluate(
                            "(index) => window.__snapshotRenderSequenceFrame(index)", index
                        ),
                        timeout_seconds,
                        f"video frame {index}",
                    )
                    if not is_plain_object(frame) or not frame.get("dataUrl"):
                        raise SnapshotError(f"the browser returned no image for video frame {index}")
                    match = re.match(r"^data:([^;]+);base64,(.+)$", str(frame["dataUrl"]))
                    if not match:
                        raise SnapshotError(f"video frame {index} did not include a base64 data URL")
                    (frames_path / (VIDEO_FRAME_PATTERN % index)).write_bytes(
                        base64.b64decode(match.group(2))
                    )
                    resolved_camera = resolved_camera or str(frame.get("camera") or "")
                    report.advance()
                    # On the clock rather than every N frames: one frame is
                    # milliseconds on a bracket and seconds on an assembly, and
                    # what a watcher needs is evidence of movement at a human
                    # rate either way.
                    if time.perf_counter() - counted_at >= VIDEO_NARRATE_INTERVAL_SECONDS:
                        counted_at = time.perf_counter()
                        say(f"video: frame {index + 1}/{frames}")
                say(f"video: encoding {frames} frames as {container}")
                encode_video(
                    frames_path,
                    output_path=output_path,
                    fps=fps,
                    container=container,
                    quality=str(video.get("quality") or ""),
                    loop=bool(video.get("loop", True)),
                )
        finally:
            # The prepared model holds GPU buffers for the whole encode, so it is
            # freed whatever happened -- and a teardown that fails must not mask
            # the failure that got us here. It is on a timeout of its own for the
            # same reason: cancelling a frame's await does not stop the
            # JavaScript it was waiting on, so a clip that wedges inside
            # `update` leaves this call queued behind it, and an untimed await
            # here would swallow the frame timeout the caller needs to see.
            try:
                teardown = await with_snapshot_timeout(
                    self.page.evaluate("() => window.__snapshotRenderSequenceDispose()"),
                    VIDEO_TEARDOWN_TIMEOUT_SECONDS,
                    "video teardown",
                )
            except Exception:  # noqa: BLE001 - best-effort teardown
                teardown = None
            if is_plain_object(teardown):
                warnings = [str(warning) for warning in (teardown.get("warnings") or [])]
        return {
            "ok": True,
            "mode": "view",
            "outputs": [
                {
                    "path": str(output_path),
                    "camera": resolved_camera,
                    "width": width,
                    "height": height,
                    "mimeType": f"video/{container}",
                    # The encoder already wrote the file, so this output carries
                    # a DESCRIPTION rather than bytes -- see write_output_payload.
                    "video": {
                        "frames": frames,
                        "fps": fps,
                        "seconds": seconds,
                        "start": float(prepared.get("start") or 0.0),
                    },
                }
            ],
            "warnings": warnings,
        }

    async def close(self) -> None:
        if self.asset_server is not None:
            try:
                self.asset_server.close()
            except Exception:  # noqa: BLE001 - best-effort teardown
                pass
            self.asset_server = None
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



def _browser_stage_timings(value: object) -> dict[str, object]:
    """Keep measured durations, never the browser's image payload or metadata."""
    if not is_plain_object(value):
        return {}

    def durations(source: Mapping[str, object], fields: tuple[str, ...]) -> dict[str, object]:
        measured = {}
        for name in fields:
            duration = source.get(name)
            if type(duration) not in (int, float):
                continue
            try:
                valid = isfinite(duration) and duration >= 0
            except OverflowError:
                valid = False
            if valid:
                measured[name] = duration
        return measured

    timings = durations(value, (
        "loadSourceMs", "preparePoseMs", "buildModelMs", "prepareViewportMs",
        "waitViewportMs", "captureMs",
    ))
    source_load = value.get("sourceLoad")
    if is_plain_object(source_load):
        measured = durations(source_load, (
            "probeMs", "cacheReadMs", "cacheDecodeMs", "meshBuildMs", "surfaceReadMs",
            "tessellateMs", "cacheWriteMs", "composeMs",
        ))
        for name in ("componentCount", "cacheBatchCount", "cacheHitCount", "cacheMissCount"):
            count = source_load.get(name)
            if type(count) is int and 0 <= count <= 2**53 - 1:
                measured[name] = count
        if measured:
            timings["sourceLoad"] = measured
    outputs = []
    for output in value.get("outputs", []) if isinstance(value.get("outputs"), list) else []:
        if not is_plain_object(output):
            continue
        measured = durations(output, (
            "updateModelMs", "frameCameraMs", "prepareStudioMs", "drawSubmitMs", "encodeImageMs",
        ))
        if measured:
            if isinstance(output.get("path"), str) and output["path"]:
                measured = {"path": output["path"], **measured}
            outputs.append(measured)
    if outputs:
        timings["outputs"] = outputs
    return timings


async def render_resolved_job_packet(
    packet: Mapping[str, object],
    *,
    runtime_dir: Path,
    renderer: BatchSnapshotRenderer | None = None,
    progress: object | None = None,
    narrate: object | None = None,
) -> dict[str, object]:
    snapshot_renderer = renderer or BatchSnapshotRenderer(runtime_dir)
    # The CLI already cleared these before resolution; repeating it costs an
    # unlink of an absent file and makes the invariant hold for a caller that
    # builds a packet itself and comes straight here.
    clear_render_output_targets(packet["jobs"])
    report = resolve_progress(progress)
    started = time.perf_counter()
    results: list[dict[str, object]] = []
    total = len(packet["jobs"])
    # The job list is known in full before the first render, so this is a real count rather
    # than a number formatted into a phase name. Same shape as meshing components.
    report.phase(PHASE_RENDER, total=total)
    try:
        for index, job in enumerate(packet["jobs"]):
            report.detail(str(job.get("input") or ""))
            if job.get("video") is not None:
                result = await snapshot_renderer.render_video(
                    job, progress=report, narrate=narrate
                )
                # A video counts FRAMES, not jobs, so render_video re-entered
                # the phase with its own total; the packet's counter is restored
                # here with the jobs already finished credited to it.
                report.phase(PHASE_RENDER, total=total, detail=str(job.get("input") or ""))
                report.advance(index + 1)
            else:
                result = await snapshot_renderer.render(job)
                report.advance()
            # Keep resolution and measured browser work together under --debug.
            # The typed result otherwise intentionally drops browser internals.
            resolved = job.get("resolved") if is_plain_object(job.get("resolved")) else {}
            debug_info = dict(resolved["debug"]) if is_plain_object(resolved.get("debug")) else {}
            if job.get("debug"):
                stages = _browser_stage_timings(result.get("stageTimings"))
                if stages:
                    debug_info["stageTimings"] = stages
            if debug_info:
                result = {**result, "debug": debug_info}
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
    """Write one finished output to its declared path, atomically.

    Temp file plus rename, so the target either does not exist (the state
    `clear_render_output_targets` left it in) or holds the complete render.
    There is no intermediate a reader can catch: the exact-path contract would
    be worth much less if a crashed write could leave half a PNG at the name the
    caller is about to read.
    """
    output_path = str(output.get("path") or "")
    if not output_path:
        return
    if is_plain_object(output.get("video")):
        # A video was written by the encoder, through this same temp-plus-rename
        # contract, as the last step of its render. The output carries what the
        # file IS -- frames, fps, seconds -- and no bytes at all, which is the
        # point: a 1800-frame sequence has no payload that could ride a result.
        return
    path = Path(output_path)
    text = output.get("text")
    if isinstance(text, str):
        write_bytes_atomic(path, text.encode("utf-8"))
        return
    data_url = str(output.get("dataUrl") or "")
    match = re.match(r"^data:([^;]+);base64,(.+)$", data_url)
    if not match:
        raise SnapshotError(f"Snapshot output did not include a base64 data URL: {output_path}")
    write_bytes_atomic(path, base64.b64decode(match.group(2)))
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


# --- the typed result -------------------------------------------------------------
#
# The renderer answers with a BROWSER payload: base64 image bytes, viewport
# internals, per-stage timings, the echoed job. None of that is what a caller
# asked for. The files are already on disk by the time this runs -- the write
# happens before anything is reported -- so the payload keys are a verbatim
# second copy of bytes the caller can read from the path beside them, and
# printing one put a 228 KB base64 PNG on
# stdout.
#
# So the boundary is a dataclass rather than a filtered dict. Filtering was the
# old fix, and it is the weaker one: it has to KNOW every payload key, so a new
# one in the browser reaches stdout by default. A SnapshotResult cannot carry a
# payload at all, because it has no field for one -- and `--json` becomes
# `dataclasses.asdict`, the same serialization every other cadgen verb uses
# (design/format-doors.md).


def _output_kind(output: Mapping[str, object], path: Path) -> str:
    """What was actually encoded: the mime subtype, else the path's suffix.

    The renderer's mime type is authoritative because the encoding follows the
    RENDER, not the request -- an SVG served under a ``.png`` name is still SVG.
    """
    mime = str(output.get("mimeType") or "")
    subtype = mime.rsplit("/", 1)[-1].strip().lower() if "/" in mime else ""
    if subtype:
        return "svg" if subtype.startswith("svg") else subtype
    return path.suffix.lstrip(".").lower()


def _job_source_identity(job: object) -> tuple[str, str]:
    """(input path, tree hash) for one resolved packet job.

    The tree hash is the geometry's identity, carried on the resolved job as
    ``tree`` by the STEP resolver. Nothing in a result used to name which
    geometry it rendered, so a render of an older tree was indistinguishable
    from a fresh one; the identity exists at resolve time and only needed
    surfacing. Inputs that render without a tree (meshes, drawings, robots)
    carry an empty string.
    """
    if not is_plain_object(job):
        return "", ""
    resolved = job.get("resolved") if is_plain_object(job.get("resolved")) else {}
    input_text = str(job.get("input") or resolved.get("inputPath") or "")
    return input_text, str(resolved.get("tree") or "")


def snapshot_result(
    result: Mapping[str, object],
    *,
    total_ms: float = 0.0,
    packet: Mapping[str, object] | None = None,
) -> SnapshotResult:
    """The typed answer for one finished render packet.

    Reads both packet shapes -- a single job's result verbatim, or the
    ``{"jobs": [...]}`` envelope -- because that distinction is a detail of how
    the renderer was called, not something a caller should have to branch on.

    ``packet`` is the RESOLVED packet the renders came from; when given, each
    file carries its job's input path and document content hash, so a caller
    can tell which geometry a render actually framed.
    """
    job_results = [
        job
        for job in (result["jobs"] if isinstance(result.get("jobs"), list) else [result])
        if is_plain_object(job)
    ]
    packet_jobs = list(packet.get("jobs") or []) if packet is not None else []
    # Identities zip by position; the render loop emits results in packet order.
    identities = (
        [_job_source_identity(job) for job in packet_jobs]
        if len(packet_jobs) == len(job_results)
        else [("", "")] * len(job_results)
    )
    files: list[SnapshotFile] = []
    parts: list[dict] = []
    warnings: list[str] = []
    debug: list[dict] = []
    for job_result, (input_text, document_hash) in zip(job_results, identities):
        for output in job_result.get("outputs") or []:
            if not is_plain_object(output) or not output.get("path"):
                continue
            path = Path(str(output["path"]))
            # A video's span, or zeros for a still. The frames are the FILE, so
            # nothing here carries their bytes (see the note above).
            video = output.get("video") if is_plain_object(output.get("video")) else {}
            files.append(
                SnapshotFile(
                    path=path,
                    kind=_output_kind(output, path),
                    # The camera the renderer RESOLVED, not the one requested: a
                    # preset name, an azimuth:elevation pair, or the burnt-in view
                    # label. A list-mode run has no view and reports none.
                    view=str(
                        output.get("viewLabel") or output.get("label") or output.get("camera") or ""
                    ),
                    input=input_text,
                    tree=document_hash,
                    frames=int(video.get("frames") or 0),
                    fps=int(video.get("fps") or 0),
                    seconds=float(video.get("seconds") or 0.0),
                )
            )
        parts.extend(part for part in (job_result.get("parts") or []) if is_plain_object(part))
        warnings.extend(str(warning) for warning in (job_result.get("warnings") or []))
        info = job_result.get("debug")
        if is_plain_object(info):
            # Resolution and browser diagnostics are merged by the render loop;
            # selected input identity attributes single and multi-job entries.
            entry = dict(info)
            if input_text or job_result.get("input"):
                entry = {"input": input_text or str(job_result["input"]), **entry}
            debug.append(entry)
    return SnapshotResult(
        ok=bool(result.get("ok", True)) and all(job.get("ok") is not False for job in job_results),
        files=tuple(files),
        parts=tuple(parts),
        warnings=tuple(warnings),
        timings=SnapshotTimings(job_count=len(job_results), total_ms=total_ms),
        debug=tuple(debug),
    )


async def render_snapshot(
    packet: Mapping[str, object],
    *,
    runtime_dir: Path,
    renderer: BatchSnapshotRenderer | None = None,
    progress: object | None = None,
    narrate: object | None = None,
) -> SnapshotResult:
    """Render a resolved packet, write its outputs, and report what was written.

    The three steps are one call because their ORDER is the exact-path contract:
    every declared target was cleared before resolution, the bytes land through a
    temp file and a rename, and only then does anything describe them. A caller
    that could render without writing could also be handed a path holding
    nothing.
    """
    started = time.perf_counter()
    result = await render_resolved_job_packet(
        packet,
        runtime_dir=runtime_dir,
        renderer=renderer,
        progress=progress,
        narrate=narrate,
    )
    write_render_outputs(result)
    return snapshot_result(
        result, total_ms=(time.perf_counter() - started) * 1000, packet=packet
    )
