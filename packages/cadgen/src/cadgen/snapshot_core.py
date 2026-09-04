"""Snapshot render core shared by the CAD and DXF skills.

Everything here is format-agnostic: the headless browser driver, the job normalisation
(camera, theme, display, size profile), the mesh render path, and output writing. It
knows nothing about STEP topology, drawings, or robot descriptions -- a caller resolves its
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
import struct
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from cadgen.coordination import PHASE_RENDER, resolve as resolve_progress
from cadgen.results import SnapshotFile, SnapshotResult, SnapshotTimings
from cadgen._internal.atomic_replace import replace_atomic, write_bytes_atomic


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
SUPPORTED_RENDER_MODES = {"view", "section", "list"}
MESH_INPUT_KINDS = {"glb", "stl", "3mf"}
MESH_SUPPORTED_RENDER_MODES = {"view", "list"}
TOPOLOGY_DISPLAY_MODES = {"hidden_edges", "hidden_lines_removed"}
# Every id that IS the workbench theme, because this set decides a render's default
# dimensions (see default_render_size). A workbench preset missing from it silently
# renders at 1200x900 instead of 1600x1200 despite resolving to the identical theme in
# the browser. Pinned against the viewer's preset table by
# tests/python/global/test_snapshot_viewer_theme_parity.py.
WORKBENCH_RENDER_THEME_IDS = {"snapshot", "workbench-light", "workbench-dark"}
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
        # A STEP model's pose: a declared preset name, or {dof: value}. Named for the
        # thing it drives (the model's kinematics= declaration) and spelled the same as
        # the --kinematics flag and the sidecar section.
        "kinematics",
        # A robot's pose. The STEP analogue is kinematics; a robot is posed by joint
        # angle, so it gets its own key rather than overloading one that means a sidecar.
        "jointValues",
        # One frozen frame of a STEP model's choreography: {"clip": name, "time":
        # seconds}. Named for the sidecar section it reads (the model's animation=
        # declaration) and spelled the same as the --animation flag. Layered over
        # the kinematics pose exactly as the viewer layers its Animation tab.
        "animation",
        "sizeProfile",
        "width",
        "height",
        "scale",
        "sceneScale",
        "debug",
        "timeoutSeconds",
    }
)
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
# --- option values: a string from argv, or the real thing from a verb call ---------
#
# Every option below arrives as TEXT from the CLI and has to be parsed. The public
# `<format>.snapshot()` verbs hand the same options over as Python values -- a dict
# for a theme, a dict for a camera -- and stringifying one of those would produce
# "{'materials': ...}", which parses as a saved-theme NAME and silently renders the
# default. So each loader takes the already-parsed shape as itself.


def parse_camera_option(raw_camera: object) -> object:
    if is_plain_object(raw_camera):
        return raw_camera
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
    if is_plain_object(raw_theme):
        return validate_direct_settings_payload(
            raw_theme,
            option_name="--theme",
            source_label="theme settings",
            allowed_keys=THEME_OPTION_KEYS,
            setting_label="theme settings",
        )
    theme = str(raw_theme or DEFAULT_RENDER_THEME_ID).strip() or DEFAULT_RENDER_THEME_ID
    if theme.startswith("{"):
        return validate_direct_settings_payload(
            load_json_text(theme, "--theme"),
            option_name="--theme",
            source_label="--theme",
            allowed_keys=THEME_OPTION_KEYS,
            setting_label="theme settings",
        )

    theme_path = Path(theme).expanduser()
    if not theme_path.is_absolute():
        theme_path = cwd / theme_path
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
def asset_url_for_store_path(file_path: Path) -> str:
    """Asset URL for a file in the render-package store (outside any render
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
    guard, render scene-scale coercion, output-path resolution with per-output
    camera defaults, and the common return shape.
    Kind resolvers run their capability checks first, then call this, so a
    STEP/mesh/robot job all normalize identically; the caller attaches its
    kind-specific ``resolved`` payload to the returned job.

    ``job_index``/``job_count`` are this job's place in its packet, needed only
    so a directory-valued output's generated name can discriminate across jobs
    as well as within one (see :func:`generated_output_name`)."""
    outputs = job.get("outputs") if isinstance(job.get("outputs"), list) else []
    if mode != "list" and not outputs:
        raise SnapshotError("render job must include outputs for non-list modes")

    # GIF export is deleted: snapshot writes PNG stills only. Refuse the
    # output up front so an old recipe fails loudly instead of rendering a
    # still into a .gif name.
    for output in outputs:
        output_path_text = str((output.get("path") if is_plain_object(output) else output) or "")
        if output_path_text.strip().lower().endswith(".gif"):
            raise SnapshotError(
                "snapshot renders PNG stills: name a .png output "
                "(motion review lives in the CAD Viewer)"
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
        normalized_outputs.append(
            {
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
                "camera": output_object.get("camera") or job.get("camera") or "iso",
            }
        )

    return {
        **job,
        "mode": mode,
        "display": job.get("display") if is_plain_object(job.get("display")) else {"mode": "solid"},
        "render": normalized_render,
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
            f"an animation frame requires a STEP model with a sidecar; {label} mesh inputs have no clips"
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
# cache the mesh-export CLI uses (~/.cache/cadgen/meshes/<key>.tess; codec and
# key scheme in packages/cadgen-js/src/lib/surf/tessellationCache.js). The page
# cannot touch the filesystem, so the host serves the cache: GET
# /__tess_cache/<key>.tess is a read, POST is a best-effort write-back after
# an in-page tessellation miss. CADGEN_MESH_CACHE=0 turns both directions
# off. Entries are opaque bytes here: Python never decodes them, it only
# stores and serves what the one JS codec produced.
#
# TRANSPORT: bulk bytes must NOT go through Playwright's route.fulfill. CDP
# serializes every fulfilled body as base64 over the devtools pipe at
# ~20 MB/s, which made a warm moonwatch snapshot spend ~8s moving ~180 MB of
# surfs + cache entries. So the renderer runs a loopback HTTP server and the
# intercepted snapshot.local routes for /__render_asset/ and /__tess_cache/
# answer with a 307 to it — the tiny redirect crosses CDP, the payload rides
# Chromium's native network stack. The page's origin stays snapshot.local, so
# the loopback responses carry CORS headers for that origin (and answer the
# preflight the redirected POST triggers).

TESS_CACHE_ROUTE_PREFIX = "/__tess_cache/"
# <cid>-t<tessellator-version>-l<chord>-a<angle>.tess with exponential-notation
# tolerances (the key scheme's home is tessellationCache.js); anything else
# (path separators, dots-runs, empty) is refused before touching disk.
TESS_CACHE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]*\.tess$")


def tessellation_cache_enabled() -> bool:
    return os.environ.get("CADGEN_MESH_CACHE") != "0"


def read_tessellation_cache_entry(pathname: str) -> bytes | None:
    """One entry's bytes, from the mesh index (``index/mesh`` -> object); None
    for a refused name, a miss, or a disabled cache."""
    from cadgen.viewer.tess_cache import read_tess_cache_entry

    if not tessellation_cache_enabled():
        return None
    status, data = read_tess_cache_entry(pathname)
    return data if status == 200 else None


def write_tessellation_cache_entry(pathname: str, body: bytes | None) -> bool:
    """Best-effort write-back; False only for an invalid name (a 403)."""
    from cadgen.viewer.tess_cache import write_tess_cache_entry

    return write_tess_cache_entry(pathname, body) != 403


# POST /__tess_cache/batch: one round trip for N entries — a many-component
# assembly otherwise pays ~2 requests per component. Request body is JSON
# {"names": ["<key>.tess", ...]}; the response is the TESB container defined
# in packages/cadgen-js/src/lib/surf/tessellationCache.js (that file is the
# format's single home; Python only frames the opaque entry bytes): "TESB"
# u32, version u32, count u32, then per entry u32 byteLength (0 = miss) +
# bytes padded to a 4-byte boundary.
TESS_CACHE_BATCH_PATH = "/__tess_cache/batch"
TESS_CACHE_BATCH_MAGIC = 0x42534554  # "TESB" little-endian
TESS_CACHE_BATCH_VERSION = 1
TESS_CACHE_BATCH_MAX_NAMES = 4096


def read_tessellation_cache_batch(body: bytes | None) -> bytes | None:
    """The TESB response for a batch request body, or None for a malformed
    request (the route answers 400). Invalid names and read failures are
    per-entry MISSES, never errors — the page's fallback is per-key gets."""
    try:
        names = json.loads((body or b"").decode("utf-8")).get("names")
    except (ValueError, UnicodeDecodeError, AttributeError):
        return None
    if not isinstance(names, list) or len(names) > TESS_CACHE_BATCH_MAX_NAMES:
        return None
    entries: list[bytes] = []
    for name in names:
        entry = b""
        if isinstance(name, str):
            data = read_tessellation_cache_entry(f"{TESS_CACHE_ROUTE_PREFIX}{name}")
            if data is not None:
                entry = data
        entries.append(entry)
    parts = [struct.pack("<III", TESS_CACHE_BATCH_MAGIC, TESS_CACHE_BATCH_VERSION, len(entries))]
    for entry in entries:
        parts.append(struct.pack("<I", len(entry)))
        parts.append(entry)
        padding = (-len(entry)) % 4
        if padding:
            parts.append(b"\x00" * padding)
    return b"".join(parts)


RENDER_ASSET_ROUTE_PREFIX = "/__render_asset/"
STORE_ASSET_ROUTE_PREFIX = "/__store_asset/"


def _store_packages_root() -> Path:
    from cadgen.store.view import views_root

    return views_root()


class SnapshotAssetServer:
    """Loopback HTTP server for the snapshot page's BULK bytes.

    Serves exactly two path families — ``/__render_asset/`` (files under the
    active render root, same containment rule as the CDP route) and
    ``/__tess_cache/`` (the shared tessellation cache) — to whatever origin
    the snapshot page runs as (CORS ``*``; the socket is loopback-only and
    carries the same files the CDP route already served). ``root_provider``
    is read per request so one server follows the renderer across jobs.
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
                self.send_header("cache-control", "no-store")
                self.send_header("content-type", content_type)
                self.send_header("content-length", str(length))
                self.end_headers()

            def _send(self, status: int, body: bytes = b"", content_type: str = "application/octet-stream") -> None:
                self._headers(status, content_type, len(body))
                if body:
                    self.wfile.write(body)

            def do_OPTIONS(self) -> None:  # noqa: N802 - http.server naming
                self.send_response(204)
                self.send_header("access-control-allow-origin", "*")
                self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
                self.send_header("access-control-allow-headers", "content-type")
                self.send_header("content-length", "0")
                self.end_headers()

            def do_GET(self) -> None:  # noqa: N802 - http.server naming
                pathname = urlparse(self.path).path
                if pathname.startswith(TESS_CACHE_ROUTE_PREFIX):
                    body = read_tessellation_cache_entry(pathname)
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
                length = int(self.headers.get("content-length") or 0)
                body = self.rfile.read(length) if length > 0 else b""
                if pathname == TESS_CACHE_BATCH_PATH:
                    batch = read_tessellation_cache_batch(body)
                    if batch is None:
                        self._send(400, b"bad batch request", "text/plain; charset=utf-8")
                        return
                    self._send(200, batch)
                    return
                accepted = write_tessellation_cache_entry(pathname, body)
                self._send(204 if accepted else 403)

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
        # Each skill bundles its own render.html/snapshot-render.js, so the driver is told
        # where they are rather than locating them relative to itself.
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
        try:
            try:
                self.asset_server = SnapshotAssetServer(lambda: self.active_root_path)
            except OSError:
                # No loopback socket (sandboxed run): bulk bytes fall back to
                # the CDP route below — slower, never wrong.
                self.asset_server = None
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
                # The page origin is the intercepted (insecure) snapshot.local,
                # and its bulk assets 307 to the loopback server. Chromium's
                # Private Network Access blocks insecure-public -> loopback
                # subresources, which would silently force every byte back
                # through the ~20 MB/s CDP fulfill path. This renderer loads
                # no web content — only our own runtime and files.
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
        parsed = urlparse(request.url)
        bulk = (
            parsed.path.startswith(TESS_CACHE_ROUTE_PREFIX)
            or parsed.path.startswith(RENDER_ASSET_ROUTE_PREFIX)
            or parsed.path.startswith(STORE_ASSET_ROUTE_PREFIX)
        )
        if bulk and self.asset_server is not None and request.url.startswith(SNAPSHOT_ORIGIN):
            # 307 preserves method and body, so the cache write-back POST
            # redirects too; the payload then rides the loopback socket
            # instead of the CDP pipe (see the transport note above).
            await route.fulfill(
                status=307,
                headers={"location": f"{self.asset_server.base_url}{parsed.path}"},
                body="",
            )
            return
        if parsed.path.startswith(TESS_CACHE_ROUTE_PREFIX):
            await self.handle_tess_cache_route(route, request, parsed.path)
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

    async def handle_tess_cache_route(self, route: Any, request: Any, pathname: str) -> None:
        # Same origin gate the file routes get; the cache lives outside any
        # model root, so it must never be reachable through a bad name.
        if not request.url.startswith(SNAPSHOT_ORIGIN):
            await route.fulfill(status=403, content_type="text/plain; charset=utf-8", body="forbidden")
            return
        if request.method == "GET":
            body = read_tessellation_cache_entry(pathname)
            if body is None:
                await route.fulfill(status=404, content_type="text/plain; charset=utf-8", body="miss")
                return
            await route.fulfill(
                status=200,
                content_type="application/octet-stream",
                headers={"cache-control": "no-store"},
                body=body,
            )
            return
        if request.method == "POST":
            if pathname == TESS_CACHE_BATCH_PATH:
                # CDP fallback for the batch route (no loopback server). The
                # container crosses the slow fulfill path, but it is still one
                # round trip instead of N.
                batch = read_tessellation_cache_batch(request.post_data_buffer)
                if batch is None:
                    await route.fulfill(status=400, content_type="text/plain; charset=utf-8", body="bad batch request")
                    return
                await route.fulfill(
                    status=200,
                    content_type="application/octet-stream",
                    headers={"cache-control": "no-store"},
                    body=batch,
                )
                return
            accepted = write_tessellation_cache_entry(pathname, request.post_data_buffer)
            await route.fulfill(status=204 if accepted else 403, content_type="text/plain; charset=utf-8", body="")
            return
        await route.fulfill(status=405, content_type="text/plain; charset=utf-8", body="method not allowed")

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



async def render_resolved_job_packet(
    packet: Mapping[str, object],
    *,
    runtime_dir: Path,
    renderer: BatchSnapshotRenderer | None = None,
    progress: object | None = None,
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
                )
            )
        parts.extend(part for part in (job_result.get("parts") or []) if is_plain_object(part))
        warnings.extend(str(warning) for warning in (job_result.get("warnings") or []))
        info = job_result.get("debug")
        if is_plain_object(info):
            # --debug diagnostics are attached at RESOLVE time and merged into the
            # browser result by the render loop; the input rides alongside so a
            # multi-job packet's entries stay attributable.
            entry = dict(info)
            if job_result.get("input"):
                entry = {"input": str(job_result["input"]), **entry}
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
        packet, runtime_dir=runtime_dir, renderer=renderer, progress=progress
    )
    write_render_outputs(result)
    return snapshot_result(
        result, total_ms=(time.perf_counter() - started) * 1000, packet=packet
    )
