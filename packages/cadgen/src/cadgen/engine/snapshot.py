"""``cadgen snapshot SRC OUT.png``: a picture of a document or of a file the viewer opens,
drawn by OCCT as the CAD Viewer draws it. One dispatcher by SRC's suffix:

- ``.xbf``, ``.step``: a document, served by the engine (the daemon, so its meshes are the ones
  the viewer and every build share, or with ``daemon=False`` a server in this process; a model's own
  document, which ``Model.snapshot`` and ``cadgen.snapshot(model, ...)`` draw, from its worker's
  memory over its one mesh cache), meshed there and drawn from those meshes (``render/service.py``).
- ``.stl``, ``.3mf``, ``.glb``: a mesh file, read by its reader (``formats/``: numpy, zip and XML,
  OCCT's glTF reader) into a structure and part buffers as a document's are, with the viewer's
  feature edges, and drawn by the documents' own path; a GLB's base colour textures through OCCT.
- ``.urdf``, ``.sdf``, ``.srdf``: a robot, its link meshes placed by the viewer's forward
  kinematics (``formats/robot.py``), drawn as a document is; ``--pose`` poses it.
- ``.dxf``: a drawing, from above, in its pens, in the viewer's 2D look (``render/drawing.py``).

Through the daemon each file drawn gets a render process of its own, warm, read again when a file
it read changes; ``daemon=False`` (Python's alone) draws in this process. Every kind is drawn in the engine's one
look (``render/look.py``). The modes, the camera fit, clip, grid and Preview are the viewer's, in
the look the viewer's viewport resolves for the same display settings. The answer is PNG bytes,
which this writes to OUT.

The request is the snapshot contract's where it applies (``--display`` mode or JSON, ``--grid``,
``--camera``, ``--preview``, ``clip``, the sizes, ``--json``), and what a kind does not offer is
refused by name before anything renders: ``parts`` and ``exploded`` for a file that places a single
part, ``--pose`` for a mesh, and everything but ``appearance`` for a drawing. ``--display
exploded=0.6`` (or ``display.exploded``) moves the parts apart as the viewer's Explode does, by its
amount (0.5 unless one is given). ``--annotation FILE`` draws the viewer's annotation over the
model (its ink on the parts it was drawn on, wherever they stand): an annotation file, or the Quick
Edit packet that carries one (a ``.snapshot.json``). ``--measurements FILE`` draws Measure's
dimensions. ``--camera authored`` draws the picture from the view the ink was drawn in, exactly
(no fit): a mark names its view only by label ("view 1"), and the view -- its camera, size and
projection -- is a job of the packet (``authored``). Nothing is written but OUT.

``--pose`` draws a document's mechanism at a configuration (its name) or at joint and coupling
values (a JSON object, the rest as built): each link placed by its pairs from the ground; a robot's
at a group state of its SRDF or at joint values (degrees, metres) over where the viewer opens it. An
unknown configuration, joint or coupling, a value out of range and a mechanism that is not a tree are
refused by name before anything renders.

``--job PACKET`` replays a Quick Edit packet (the ``.snapshot.json`` the viewer writes) or a job
file in its words (``job_pictures``): every output of every job drawn, each job a view with its
own camera, display (its hidden and isolated parts among it), pose (``jointValues``) and, a
robot's, the visuals it hid (``selection.hide``), the packet's ink and dimensions over each, at
the output settings the job gives (``output``: ``padding``, ``tightFrame``, ``transparent``,
``renderScale``, ``sizeProfile``). A view's own camera with the tight frame off is drawn exactly;
any other camera is fitted with the job's padding. Every request is checked before anything
renders, and a failure writes none of the job's pictures, leaving every output as it was.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cadgen.engine.atomic_replace import replace_atomic, staging

__all__ = ["SnapshotRefused", "Still", "add_parser", "authored", "build_parser", "draw", "draw_pictures", "job_input",
           "job_pictures", "main", "options", "parse_annotation", "parse_camera", "parse_display", "parse_measurements",
           "parse_pose", "picture_path", "run", "snapshot"]

DISPLAY_MODES = ("solid", "shaded", "parts", "xray", "hidden-line", "wireframe")
DISPLAY_KEYS = frozenset({"mode", "grid", "appearance", "camera", "clip", "exploded", "hidden", "isolated"})
# What the viewer's hide and isolate leave out of a picture: each a list of part refs (``refs``), the
# display object's and a Quick Edit packet's alike.
VISIBILITY = ("hidden", "isolated")
APPEARANCES = ("light", "dark")
EXPLODED_KEYS = frozenset({"enabled", "amount"})
# Explode's amount when a request names none: the viewer's own default.
EXPLODED_AMOUNT = 0.5
CAMERA_PRESETS = frozenset({"front", "back", "right", "left", "top", "bottom", "iso"})
CAMERA_KEYS = frozenset({"preset", "name", "position", "target", "up", "direction", "zoom", "orthographicHalfHeight"})
# ``--camera authored``: the view the annotation's ink was drawn in, exactly (``authored``).
AUTHORED = "authored"
# The Quick Edit packets an annotation file is looked for beside (``cadgen.viewer`` writes them).
PACKETS = "*.snapshot.json"
# The viewer's annotation file (``@text-to-cad/core`` ``common/annotation.js``) and Measure's marks.
ANNOTATION_KEYS = frozenset({"units", "parts", "marks"})
MARK_KINDS = ("stroke", "area", "text")
MARK_MAX = 8192  # a still's annotation holds at most this many marks
TEXT_MAX_CHARS, TEXT_MAX_LINES = 10000, 256  # a text mark's words
FONT_PX_MAX, STROKE_WIDTH_MAX = 512.0, 256.0  # a mark sizes a raster from these; bound them
MEASUREMENT_KEYS = frozenset({"start", "end", "label", "color"})
MAX_MEASUREMENTS = 64
# The snapshot contract's size profiles; a request names one or a width and a height.
SIZE_PROFILES = {
    "simple": (1200, 900), "simple-square": (1024, 1024), "diagnostic": (1600, 1200), "labeled": (1600, 1200),
    "assembly": (1800, 1200), "assembly-large": (1920, 1440), "presentation": (2400, 1600),
    "presentation-large": (2800, 1800), "contact-sheet": (2400, 1600),
}
DEFAULT_SIZE = SIZE_PROFILES["diagnostic"]
MAX_SIDE = 8192
# ``--job``: a Quick Edit packet (``cadgen.viewer``'s ``.snapshot.json``), a job, or a list of jobs; each job a
# view, its outputs the pictures it writes, its output settings how they are framed and finished.
PACKET_KEYS = frozenset({"input", "jobs", "annotation", "measurements", "hidden", "isolated"})
JOB_KEYS = frozenset({"input", "camera", "display", "preview", "jointValues", "selection", "annotation", "measurements",
                      "output", "outputs"})
OUTPUT_KEYS = frozenset({"path", "width", "height", "camera", "label"})
SETTINGS_KEYS = frozenset({"sizeProfile", "padding", "tightFrame", "transparent", "renderScale"})
SELECTION_KEYS = {"hide": "hidden", "focus": "isolated"}  # a view's selection, as the display says it
# The frame's margin each side, a share of the picture (the camera fit's), and the supersampling.
PADDING, PADDING_RANGE = 0.04, (0.0, 0.15)
RENDER_SCALE_RANGE = (1.0, 3.0)


class SnapshotRefused(ValueError):
    """A request the snapshot will not draw, said before anything renders."""


# --- the request ---------------------------------------------------------------------------


def _json_or_file(text: str, label: str) -> Any:
    candidate = Path(text)
    if not text.lstrip().startswith(("{", "[")) and candidate.suffix == ".json" and candidate.is_file():
        text = candidate.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise SnapshotRefused(f"{label} is not JSON: {error}") from None


def _amount(text: str) -> float:
    try:
        amount = float(text)
    except ValueError:
        amount = math.nan
    if not 0 <= amount <= 1:
        raise SnapshotRefused(f"exploded={text} is no amount; Explode's amount is 0 (together) to 1 (apart)")
    return amount


def _exploded(value: Any) -> dict[str, Any]:
    """``display.exploded``, checked: ``{"enabled", "amount"}``, the amount 0 to 1 (0.5 unless given)."""
    if not isinstance(value, dict):
        raise SnapshotRefused('display.exploded is {"enabled": true, "amount": 0 to 1}')
    unknown = sorted(set(value) - EXPLODED_KEYS)
    if unknown:
        raise SnapshotRefused(f"display.exploded has no {', '.join(unknown)}; it takes enabled and amount")
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise SnapshotRefused("display.exploded.enabled is true or false")
    amount = value.get("amount", EXPLODED_AMOUNT)
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not 0 <= amount <= 1:
        raise SnapshotRefused("display.exploded.amount is a number from 0 (together) to 1 (apart)")
    return {"enabled": enabled, "amount": float(amount)}


def exploded_amount(display: dict[str, Any]) -> float:
    """How far apart the display moves the parts: 0 when it does not explode them."""
    exploded = display.get("exploded")
    return float(exploded["amount"]) if exploded and exploded.get("enabled") else 0.0


def parse_display(value: str | None, grid: bool) -> dict[str, Any]:
    """``--display``: a mode, ``exploded=AMOUNT``, an appearance (``light``, ``dark``: all a drawing
    takes), several by commas (``hidden-line,exploded=0.6``), or the viewer's display object (JSON,
    or a JSON file)."""
    display: dict[str, Any] = {}
    if value:
        text = value.strip()
        if text.startswith("{") or text.endswith(".json"):
            parsed = _json_or_file(text, "--display")
            if not isinstance(parsed, dict):
                raise SnapshotRefused("--display is a mode or a JSON object")
            display = dict(parsed)
        else:
            for token in (part.strip() for part in text.split(",")):
                name, equals, amount = token.partition("=")
                if name == "exploded" and "exploded" not in display:
                    display["exploded"] = {"enabled": True, "amount": _amount(amount) if equals else EXPLODED_AMOUNT}
                elif token in DISPLAY_MODES and "mode" not in display:
                    display["mode"] = token
                elif token in APPEARANCES and "appearance" not in display:
                    display["appearance"] = token
                else:
                    raise SnapshotRefused(f"--display {token!r} is no display mode; the modes are {', '.join(DISPLAY_MODES)}, "
                                          "exploded=AMOUNT moves the parts apart, and light or dark is the appearance "
                                          "(all a drawing takes; one of each, by commas)")
    if "exploded" in display:
        display["exploded"] = _exploded(display["exploded"])
    unknown = sorted(set(display) - DISPLAY_KEYS)
    if unknown:
        raise SnapshotRefused(f"display has no {', '.join(unknown)}; an engine document's display takes "
                              f"{', '.join(sorted(DISPLAY_KEYS))}")
    if "mode" in display and display["mode"] not in DISPLAY_MODES:
        raise SnapshotRefused(f"display.mode {display['mode']!r} is no display mode; the modes are {', '.join(DISPLAY_MODES)}")
    if "grid" in display and not isinstance(display["grid"], bool):
        raise SnapshotRefused("display.grid is true or false")
    _visibility(display)
    if grid:
        display["grid"] = True
    return display


def _visibility(display: dict[str, Any]) -> None:
    for field in VISIBILITY:
        if field in display and (not isinstance(display[field], list)
                                 or not all(isinstance(ref, str) and ref.strip() for ref in display[field])):
            raise SnapshotRefused(f"display.{field} is a list of part refs (an occurrence's path: hand/finger.2)")


def packet_visibility(value: Any) -> dict[str, list[str]]:
    """What a Quick Edit packet (``--annotation``'s, ``_packet``) hides and isolates, as the viewer
    had it: its ``hidden`` and ``isolated`` part refs; nothing for an annotation file."""
    if value is None:
        return {}
    found = _load(value, "--annotation")
    if not _packet(found):
        return {}
    taken = {field: found[field] for field in VISIBILITY if found.get(field) is not None}
    _visibility(taken)
    return taken


def hidden_instances(structure: dict[str, Any], display: dict[str, Any], name: str) -> frozenset[int]:
    """The instances a picture leaves out: those ``display.hidden``'s refs name, and, where
    ``display.isolated`` is given, every one its refs do not. A ref is a part or an assembly
    (every part below it), in the refs grammar, or -- a robot's -- the viewer's id of a visual
    (``link:v1``, every object it draws, or ``link:v1/object/0``, one), as a robot's view names what
    it hid; one that names nothing, or an element, is refused by name, and so is a choice that
    leaves nothing to draw."""
    if not display.get("hidden") and display.get("isolated") is None:
        return frozenset()
    from cadgen.engine import refs

    visuals: dict[str, set[int]] = {}
    for index, instance in enumerate(structure.get("instances") or []):
        if instance.get("visual"):
            visuals.setdefault(instance["visual"], set()).add(index)
            if instance.get("object") is not None:
                visuals.setdefault(f"{instance['visual']}/object/{instance['object']}", set()).add(index)

    def named(field: str) -> set[int]:
        found: set[int] = set()
        for ref in display.get(field) or ():
            if ref in visuals:
                found.update(visuals[ref])
                continue
            try:
                hits = refs.resolve_structure(structure, ref)
            except refs.RefError as error:
                raise SnapshotRefused(f"display.{field}: {error}") from None
            for hit in hits:
                if hit.kind is not None:
                    raise SnapshotRefused(f"display.{field}: {ref!r} names {hit.kind} {hit.ordinal} of a part; "
                                          "it takes parts and assemblies")
                found.update(node.payload["instance"] for node in hit.node.parts() if "instance" in node.payload)
        return found

    every = set(range(len(structure.get("instances") or [])))
    drawn = (named("isolated") if display.get("isolated") is not None else set(every)) - named("hidden")
    if not drawn:
        raise SnapshotRefused(f"display.hidden and display.isolated leave nothing of {name} to draw")
    return frozenset(every - drawn)


def parse_camera(value: str | None) -> Any:
    """``--camera``: a preset, an ``azimuth:elevation`` pair in degrees, a camera JSON object, or
    ``authored``: the camera the annotation's ink was drawn in (``--annotation``'s ``view``)."""
    if not value:
        return None
    text = value.strip()
    if text.lower() == AUTHORED:
        return AUTHORED
    if text.startswith("{"):
        parsed = _json_or_file(text, "--camera")
        if not isinstance(parsed, dict):
            raise SnapshotRefused("--camera is a preset, an azimuth:elevation pair or a JSON object")
        unknown = sorted(set(parsed) - CAMERA_KEYS)
        if unknown:
            raise SnapshotRefused(f"camera has no {', '.join(unknown)}; its keys are {', '.join(sorted(CAMERA_KEYS))}")
        moved = [key for key in ("projection", "focalLength") if key in parsed]
        if moved:
            raise SnapshotRefused(f"camera {', '.join(moved)} belongs to display.camera")
        return parsed
    if text.lower() in CAMERA_PRESETS:
        return text.lower()
    pair = text.split(":")
    try:
        if len(pair) == 2 and all(math.isfinite(float(part)) for part in pair):
            return text
    except ValueError:
        pass
    raise SnapshotRefused(f"camera {text!r} is no preset ({', '.join(sorted(CAMERA_PRESETS))}), "
                          "azimuth:elevation pair, JSON object or authored")


def _load(value: Any, label: str) -> Any:
    """A flag's JSON: the value itself (a function's), JSON text, or the path of a file of it."""
    if not isinstance(value, (str, Path)):
        return value
    text = str(value).strip()
    if text.startswith(("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise SnapshotRefused(f"{label} is not JSON: {error}") from None
    path = Path(text).expanduser()
    if not path.is_file():
        raise SnapshotRefused(f"{label} {text}: no such file")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SnapshotRefused(f"{label} {path.name} is not JSON: {error}") from None


def _numbers(value: Any, count: int | None = None) -> bool:
    return isinstance(value, list) and (count is None or len(value) == count) and all(
        isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number) for number in value)


def _color(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 7 and value.startswith("#") and all(
        digit in "0123456789abcdefABCDEF" for digit in value[1:])


def _packet(found: Any) -> bool:
    """A Quick Edit packet: an annotation and the views it was drawn in -- the ``.snapshot.json``
    the viewer writes (``jobs``), or the request it posts (``views``)."""
    return isinstance(found, dict) and isinstance(found.get("annotation"), dict) and (
        isinstance(found.get("jobs"), list) or isinstance(found.get("views"), list))


def parse_annotation(value: Any) -> dict[str, Any] | None:
    """``--annotation``: the viewer's annotation (its file's path, its JSON, or a Quick Edit packet
    that carries it), checked where a still reads it: its marks and each part's placement. The page
    and the stills draw it; neither refuses it after this."""
    if value is None:
        return None
    found = _load(value, "--annotation")
    if _packet(found):
        found = found["annotation"]
    if not isinstance(found, dict) or not isinstance(found.get("marks"), list):
        raise SnapshotRefused("--annotation is the viewer's annotation file: an object of units, parts and marks")
    unknown = sorted(set(found) - ANNOTATION_KEYS)
    if unknown:
        raise SnapshotRefused(f"--annotation has no {', '.join(unknown)}; an annotation has {', '.join(sorted(ANNOTATION_KEYS))}")
    if len(found["marks"]) > MARK_MAX:
        raise SnapshotRefused(f"--annotation has at most {MARK_MAX} marks")
    for name, part in (found.get("parts") or {}).items():
        if not isinstance(part, dict) or not _numbers(part.get("placement"), 16):
            raise SnapshotRefused(f"--annotation: parts.{name}.placement is a 4x4 matrix of 16 numbers")
    for index, mark in enumerate(found["marks"]):
        at = f"--annotation: marks[{index}]"
        if not isinstance(mark, dict) or mark.get("kind") not in MARK_KINDS:
            raise SnapshotRefused(f"{at}.kind is one of {', '.join(MARK_KINDS)}")
        points = mark.get("points")
        if not _numbers(points) or not points or len(points) % 3:
            raise SnapshotRefused(f"{at}.points are x, y, z triples")
        if not _color(mark.get("color")):
            raise SnapshotRefused(f"{at}.color is #rrggbb")
        if mark.get("part") is not None and not isinstance(mark["part"], str):
            raise SnapshotRefused(f"{at}.part is an occurrence id or null")
        if mark["kind"] == "text" and len(points) != 12:
            raise SnapshotRefused(f"{at}: a text mark's points are its four corners")
        if mark.get("view") is not None and not isinstance(mark["view"], str):
            raise SnapshotRefused(f"{at}.view is the label of the view it was drawn in")
        text = mark.get("text")
        if text is not None and (not isinstance(text, str) or len(text) > TEXT_MAX_CHARS
                                 or text.count("\n") + 1 > TEXT_MAX_LINES):
            raise SnapshotRefused(f"{at}.text is at most {TEXT_MAX_CHARS} characters on {TEXT_MAX_LINES} lines")
        for key, high in (("fontPx", FONT_PX_MAX), ("width", STROKE_WIDTH_MAX)):
            value = mark.get(key)
            if value is not None and not (isinstance(value, (int, float)) and not isinstance(value, bool)
                                          and math.isfinite(value) and 0 <= value <= high):
                raise SnapshotRefused(f"{at}.{key} is a number from 0 to {high:g}")
    return found


def parse_measurements(value: Any) -> list[dict[str, Any]] | None:
    """``--measurements``: Measure's dimensions, ``[{start, end, label, color}]`` (or one of them,
    as a chip copies it): a file's path, or its JSON."""
    if value is None:
        return None
    found = _load(value, "--measurements")
    found = [found] if isinstance(found, dict) else found
    if not isinstance(found, list) or len(found) > MAX_MEASUREMENTS:
        raise SnapshotRefused(f"--measurements is a list of at most {MAX_MEASUREMENTS} {{start, end, label, color}}")
    marks = []
    for index, mark in enumerate(found):
        at = f"--measurements[{index}]"
        if not isinstance(mark, dict) or set(mark) - MEASUREMENT_KEYS:
            raise SnapshotRefused(f"{at} is {{start, end, label, color}}")
        for key in ("start", "end"):
            if not _numbers(mark.get(key), 3):
                raise SnapshotRefused(f"{at}.{key} is [x, y, z]")
        if not isinstance(mark.get("label"), str):
            raise SnapshotRefused(f"{at}.label is its words")
        if not _color(mark.get("color")):
            raise SnapshotRefused(f"{at}.color is #rrggbb")
        marks.append({"start": list(mark["start"]), "end": list(mark["end"]), "label": mark["label"], "color": mark["color"]})
    return marks


@dataclass
class View:
    """A view an annotation was drawn in, as a Quick Edit packet holds it: its camera (the snapshot
    contract's object: position, target, up, orthographicHalfHeight), its lens (``display.camera``:
    the projection) and its size."""

    camera: Any
    lens: dict[str, Any] | None
    size: tuple[int, int] | None


def _view_of(packet: dict[str, Any], label: str) -> View | None:
    """The view ``label`` names in a packet: a job whose output carries the label (the
    ``.snapshot.json``), or a view of the label (the request the viewer posts)."""
    def size(width: Any, height: Any) -> tuple[int, int] | None:
        return (int(width), int(height)) if isinstance(width, int) and isinstance(height, int) else None

    for job in packet.get("jobs") or []:
        if not isinstance(job, dict):
            continue
        for output in job.get("outputs") or []:
            if isinstance(output, dict) and output.get("label") == label:
                return View(job.get("camera"), (job.get("display") or {}).get("camera"),
                            size(output.get("width"), output.get("height")))
    for view in packet.get("views") or []:
        if isinstance(view, dict) and view.get("label") == label:
            return View(view.get("camera"), (view.get("display") or {}).get("camera"),
                        size(view.get("width"), view.get("height")))
    return None


def authored(camera: Any, annotation: dict[str, Any] | None, source: Any, document: Path) -> tuple[Any, bool, View | None]:
    """The camera a still is drawn with, whether it is drawn exactly so (no fit to the model), and
    the view it came from. ``authored`` is the view the annotation's ink was drawn in: a mark names
    its view by label alone ("view 1", the last mark's), and the view is a job of the Quick Edit
    packet that carried the annotation -- ``source`` itself when it is one (``--annotation`` given a
    ``.snapshot.json``), else the newest packet beside the annotation file that draws ``document``.
    Anything else is itself, fitted. Refused by name when the marks name no view or no packet holds
    it."""
    if camera != AUTHORED:
        return camera, False, None
    if annotation is None:
        raise SnapshotRefused("--camera authored is the view an annotation's ink was drawn in: give --annotation FILE")
    label = next((mark["view"] for mark in reversed(annotation["marks"]) if mark.get("view")), None)
    if label is None:
        raise SnapshotRefused("--camera authored: the annotation's marks name no view they were drawn in")
    given = _load(source, "--annotation") if source is not None else None
    packets: list[dict[str, Any]] = [given] if _packet(given) else []
    beside = None
    if not packets and isinstance(source, (str, Path)) and not str(source).lstrip().startswith("{"):
        beside = Path(source).expanduser().resolve().parent
        for candidate in sorted(beside.glob(PACKETS), key=lambda path: path.stat().st_mtime, reverse=True):
            try:
                found = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if _packet(found) and str(found.get("input") or "") and Path(found["input"]).resolve() == document:
                packets.append(found)
    for packet in packets:
        view = _view_of(packet, label)
        if view is not None and isinstance(view.camera, dict):
            unknown = sorted(set(view.camera) - CAMERA_KEYS)
            if unknown or not all(_numbers(view.camera.get(key), 3) for key in ("position", "target")):
                raise SnapshotRefused(f"--camera authored: {label!r}'s camera is no camera object "
                                      f"({', '.join(unknown) or 'it lacks a position or a target'})")
            return dict(view.camera), True, view
        if view is not None and isinstance(view.camera, str):
            return parse_camera(view.camera), False, view
    where = f"beside {Path(source).name} " if beside is not None else ""
    raise SnapshotRefused(f"--camera authored: the annotation's ink was drawn in {label!r}, and no Quick Edit packet "
                          f"(.snapshot.json) {where}holds that view of {document.name}: give the packet as --annotation")


def parse_pose(value: str | None) -> Any:
    """``--pose``: a configuration's name, or ``{"<joint or coupling>": value}`` (JSON, or a JSON file of it)."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        raise SnapshotRefused("--pose names a configuration, or gives joint values as a JSON object")
    if text.startswith("{") or (text.endswith(".json") and Path(text).is_file()):
        parsed = _json_or_file(text, "--pose")
        if not isinstance(parsed, dict):
            raise SnapshotRefused("--pose is a configuration's name or a JSON object of joint values")
        return parsed
    return text


def parse_size(width: int | None, height: int | None, profile: str | None) -> tuple[int, int]:
    if profile and (width or height):
        raise SnapshotRefused("--size-profile names a size; give it, or --width and --height, not both")
    if profile:
        if profile not in SIZE_PROFILES:
            raise SnapshotRefused(f"--size-profile {profile!r} is not one of {', '.join(SIZE_PROFILES)}")
        return SIZE_PROFILES[profile]
    size = (width or DEFAULT_SIZE[0], height or DEFAULT_SIZE[1])
    for side in size:
        if not 16 <= side <= MAX_SIDE:
            raise SnapshotRefused(f"an image side is 16 to {MAX_SIDE} pixels, not {side}")
    return size


# --- the verb ------------------------------------------------------------------------------


DOCUMENTS = (".xbf", ".step", ".stp")
# The files no document, each read by its reader (``formats.KINDS``): meshes, robots, a drawing.
FILES = (".stl", ".3mf", ".glb", ".urdf", ".sdf", ".srdf", ".dxf")
MESHES = (".stl", ".3mf", ".glb")


@dataclass
class Still:
    """What a picture is asked to show, checked: the display (mode, grid, clip, Explode, the
    projection), the camera and whether it is drawn exactly so (``exact``: ``--camera authored``,
    a job's own view; no fit), Preview, the size, the pose, the annotation and the measurements
    drawn over it, and how it is finished (a job's output settings): the fit's ``padding`` each
    side, a share of the picture, on every drawn vertex (``tight``) or the drawn parts' box, a
    ``transparent`` backdrop, and ``scale`` times the size drawn and brought down (supersampling).
    The request OCCT draws, and what a renderer process is handed (``as_json``)."""

    display: dict[str, Any] = field(default_factory=dict)
    camera: Any = None
    exact: bool = False
    preview: bool = False
    size: tuple[int, int] = DEFAULT_SIZE
    pose: Any = None
    annotation: dict[str, Any] | None = None
    measurements: list[dict[str, Any]] | None = None
    padding: float = PADDING
    tight: bool = True
    transparent: bool = False
    scale: float = 1.0

    def as_json(self) -> dict[str, Any]:
        return {"display": self.display, "camera": self.camera, "exact": self.exact, "preview": self.preview,
                "size": list(self.size), "pose": self.pose, "annotation": self.annotation,
                "measurements": self.measurements, "padding": self.padding, "tight": self.tight,
                "transparent": self.transparent, "scale": self.scale}

    @staticmethod
    def from_json(found: dict[str, Any]) -> "Still":
        return Still(dict(found.get("display") or {}), found.get("camera"), bool(found.get("exact")),
                     bool(found.get("preview")), tuple(found.get("size") or DEFAULT_SIZE), found.get("pose"),
                     found.get("annotation"), found.get("measurements"), float(found.get("padding", PADDING)),
                     bool(found.get("tight", True)), bool(found.get("transparent")), float(found.get("scale") or 1.0))

    @property
    def drawn(self) -> tuple[int, int]:
        """The size the picture is drawn at: its size, times ``scale`` (brought down after)."""
        return (max(1, round(self.size[0] * self.scale)), max(1, round(self.size[1] * self.scale)))


def refusals(still: Still, structure: dict[str, Any], name: str) -> None:
    """What the document's view does not offer, refused by name before anything renders: Parts and
    Explode colour or move placed parts apart, and a document of one has nothing to part."""
    placed = len(structure.get("instances") or [])
    if placed >= 2 or still.preview:
        return
    count = f"{placed} part{'' if placed == 1 else 's'}"
    if still.display.get("mode") == "parts":
        raise SnapshotRefused(f"display.mode parts colours each placed part apart; {name} places {count}. Use solid.")
    if exploded_amount(still.display) > 0:
        raise SnapshotRefused(f"display.exploded moves a document's parts apart; {name} places {count}. "
                              "Remove display.exploded.")


def stamp() -> str:
    """The time a generated picture name carries: UTC, to the second (``20261022T174512Z``)."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def names_a_folder(text: str) -> bool:
    """Whether OUT names a folder to write a generated name into: a trailing separator says so (a
    folder that need not exist yet), else a folder that is there. A trailing separator on a file
    that is there is refused: it names a folder, and what cannot become one."""
    path = Path(text).expanduser()
    if text.endswith(("/", "\\")):
        if path.exists() and not path.is_dir():
            raise SnapshotRefused(f"{text} ends in a separator, which names a folder, and {path} is a file")
        return True
    return path.is_dir()


def stem_of(source: Any) -> str:
    """What a generated picture name starts with: the drawn file's stem, a model's name, or a
    document's id."""
    named = getattr(source, "name", None)
    if isinstance(named, str) and not isinstance(source, Path):
        return named  # a Model
    return Path(os.fspath(source)).stem or "snapshot"


def picture_path(out: Any, source: Any, *, at: str | None = None, job: tuple[int, int] = (0, 1),
                 output: tuple[int, int] = (0, 1)) -> Path:
    """Where a picture is written: OUT as given, or -- OUT a folder (``names_a_folder``) -- a name
    made inside it, ``<stem>[_j<m>][_<n>]_<UTC time>.png`` (``stem_of`` the source; the job's place
    in a packet of several, and the output's in a job of several, where they tell pictures apart;
    ``at`` the one time every picture of a run shares)."""
    text = os.fspath(out)
    if not names_a_folder(text):
        return Path(text).expanduser().resolve()
    told = [f"j{job[0] + 1}"] if job[1] > 1 else []
    told += [str(output[0] + 1)] if output[1] > 1 else []
    return (Path(text).expanduser() / f"{'_'.join([stem_of(source), *told, at or stamp()])}.png").resolve()


def write_png(out: Path, data: bytes) -> None:
    """The one file a snapshot writes: beside ``out`` first, then moved over it, so a failure
    leaves whatever was at ``out`` as it was, and no temporary file beside it."""
    with staging(out) as temporary:
        temporary.write_bytes(data)
        replace_atomic(temporary, out)


def options(display: Any = None, camera: Any = None, grid: bool = False, width: int | None = None,
            height: int | None = None, size_profile: str | None = None) -> tuple[dict[str, Any], Any, tuple[int, int]]:
    """A snapshot's options as a function gives them -- ``display`` a mode, a
    JSON text or the display object -- checked as the verb checks its flags."""
    if isinstance(display, dict):
        display = json.dumps(display)
    return (parse_display(display, bool(grid)), parse_camera(camera if camera is None or isinstance(camera, str)
                                                              else json.dumps(camera)),
            parse_size(width, height, size_profile))


def draw(source: Any, out: Path, *, display: Any = None, camera: Any = None, grid: bool = False,
         preview: bool = False, pose: Any = None, width: int | None = None, height: int | None = None,
         size_profile: str | None = None, annotation: Any = None, measurements: Any = None) -> dict[str, Any]:
    """A build's document (an ``export.Source``, in this process's memory) drawn into ``out``:
    a model's picture (``Model.snapshot``). Served from memory over the process's mesh
    cache, so nothing the build meshed is meshed again."""
    shown, framed, size = options(display, camera, grid, width, height, size_profile)
    path = source.path or Path(out).with_suffix(".xbf")
    return snapshot(path, Path(out), display=shown, camera=framed, preview=preview,
                    size=None if width is None and height is None and size_profile is None else size, pose=pose,
                    source=source, annotation=parse_annotation(annotation), measurements=parse_measurements(measurements),
                    annotation_source=annotation)


def snapshot(document: Path, out: Path, *, display: dict[str, Any] | None = None, camera: Any = None,
             preview: bool = False, size: tuple[int, int] | None = None, daemon: bool = True,
             pose: Any = None, source: Any = None, annotation: dict[str, Any] | None = None,
             measurements: list[dict[str, Any]] | None = None, annotation_source: Any = None) -> dict[str, Any]:
    """Draw ``document`` -- an ``.xbf`` or a ``.step`` the engine serves and meshes, or a file its
    reader reads (``FILES``: a mesh, a robot, a drawing) -- into ``out`` (a ``.png``); returns what
    was drawn and how long each stage took. ``pose``: a configuration's name (a robot's group
    state) or ``{joint: value}``, the engine placing each link by its pairs from the ground (a
    robot's by its joints from its root); None draws the document as built (a robot where the
    viewer opens it); a mesh has no mechanism to pose. ``source``: the document is a
    build's, held in this process (``draw``). ``annotation`` (``parse_annotation``'s) and
    ``measurements`` are drawn over the model; ``camera`` ``authored`` is the view the ink was
    drawn in, read from the Quick Edit packet ``annotation_source`` is (or is beside: ``authored``),
    and its size and projection unless ``size`` and ``display.camera`` say otherwise. ``size`` None
    is the default size. Raises ``SnapshotRefused`` for a request it will not draw, before
    rendering; one refused or failed leaves the file at ``out`` as it was (``write_png``)."""
    started = time.perf_counter()
    document, out = Path(document).resolve(), Path(out).resolve()
    return _snapshot(document, out, display=display, camera=camera, preview=preview, size=size, daemon=daemon,
                     pose=pose, source=source, annotation=annotation, measurements=measurements,
                     annotation_source=annotation_source, started=started)


def _checked(document: Path, out: Path, source: Any = None) -> str:
    """What a picture draws and where it goes, checked before anything renders: SRC a file the
    stills draw, and there (unless a build's ``source`` holds it), or a document's id, OUT a
    ``.png``. SRC's suffix (an id's document is drawn as an ``.xbf``)."""
    if _by_id(document):
        if out.suffix.lower() != ".png":
            raise SnapshotRefused(f"a snapshot is a .png; {out.name} is not one")
        return ".xbf"
    suffix = document.suffix.lower()
    if suffix not in DOCUMENTS and suffix not in FILES:
        raise SnapshotRefused(f"{document.name} is neither a document (.xbf, .step) nor a file the stills draw "
                              f"({', '.join(FILES)})")
    if source is None and not document.is_file():
        raise SnapshotRefused(f"no document {document}")
    if out.suffix.lower() != ".png":
        raise SnapshotRefused(f"a snapshot is a .png; {out.name} is not one")
    return suffix


def _snapshot(document: Path, out: Path, *, display: dict[str, Any] | None, camera: Any, preview: bool,
              size: tuple[int, int] | None, daemon: bool, pose: Any, source: Any, annotation: dict[str, Any] | None,
              measurements: list[dict[str, Any]] | None, annotation_source: Any, started: float) -> dict[str, Any]:
    suffix = _checked(document, out, source)
    framed, exact, view = authored(camera, annotation, annotation_source, document)
    display = dict(display or {})
    # What the viewer hid and isolated when the packet was written, unless the display says.
    for field, refs in packet_visibility(annotation_source).items():
        display.setdefault(field, refs)
    if view is not None and view.lens and "camera" not in display:
        display["camera"] = dict(view.lens)  # the view's projection
    size = size or (view.size if view is not None and view.size else DEFAULT_SIZE)
    still = Still(display, framed, exact, preview, tuple(size), pose, annotation, measurements)
    if suffix in MESHES and pose is not None:
        raise SnapshotRefused(f"--pose poses a document's mechanism; {document.name} is a mesh and has none")
    if not out.parent.is_dir():
        out.parent.mkdir(parents=True, exist_ok=True)
    return _occt(document, out, still, daemon, source, started)


def _occt(document: Path, out: Path, still: Still, daemon: bool, source: Any, started: float) -> dict[str, Any]:
    """A document drawn by OCCT from the engine's meshes, or a file from what its reader read
    (``render/service.py``): by the daemon's render process for it, warm, or in this process
    (``daemon=False``, a model's own document from its worker's memory). The answer is the PNG's
    bytes; this writes the one file. A document named by its id is drawn by the engine from what
    it holds (``api._source``): read, never built."""
    if _by_id(document) and source is None:
        from cadgen.engine import api

        spec = api._source(str(document))
        return api._exported({"op": "export", "source": spec, "destinations": [],
                              "draw_still": {"out": str(out), "still": still.as_json()},
                              "cwd": os.getcwd()}, spec, lambda _text: None, daemon)["drawn"]
    if daemon and source is None:
        from cadgen.engine.client import request

        answer = request({"op": "draw", "path": str(document), "still": still.as_json()})
        if answer is None:
            raise RuntimeError("no engine daemon")
        if "refused" in answer:
            raise SnapshotRefused(answer["refused"])
        if "failed" in answer:
            raise RuntimeError(answer["failed"])
        data, report = base64.b64decode(answer["png"]), answer["report"]
    else:
        from cadgen.engine.formats import FormatError
        from cadgen.engine.render.service import draw_here

        try:
            data, report = draw_here(document, still, source=source)
        except FormatError as error:
            raise SnapshotRefused(str(error)) from None
    return _written(document, out, data, report, started)


def _written(document: Path, out: Path, data: bytes, report: dict[str, Any], started: float) -> dict[str, Any]:
    """A picture drawn, written to ``out``: its warnings said, and what was drawn."""
    _warn(report.get("unmeshed") or {})
    for warning in report.get("warnings") or []:
        print(f"warning: {document.name}: {warning}", file=sys.stderr)
    write_png(out, data)
    report["timings"]["totalMs"] = round((time.perf_counter() - started) * 1000)
    return {"ok": True, "document": str(document), "output": str(out), **report, "bytes": out.stat().st_size}


# --- a job: a Quick Edit packet's views, drawn ---------------------------------------------------


def _by_id(document: Any) -> bool:
    """Whether a picture's document is named by its id: drawn from what the engine holds."""
    from cadgen.engine.ids import is_id

    return is_id(os.fspath(document))


def job_input(job: Any) -> str | None:
    """The file a job draws, as it names it (its first job's, else the packet's), for whoever
    counts what was drawn; None where it names none, or cannot be read."""
    try:
        found = _load(job, "--job")
    except SnapshotRefused:
        return None
    first = found[0] if isinstance(found, list) and found else found
    jobs = first.get("jobs") if isinstance(first, dict) else None
    if isinstance(jobs, list) and jobs and isinstance(jobs[0], dict) and jobs[0].get("input"):
        return str(jobs[0]["input"])
    return str(first["input"]) if isinstance(first, dict) and first.get("input") else None


def _settings(value: Any, where: str, drawing: bool) -> dict[str, Any]:
    """A job's output settings (``output``), checked: ``sizeProfile``, ``padding`` (0 to 0.15 of
    the picture each side), ``tightFrame``, ``transparent``, ``renderScale`` (1 to 3)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SnapshotRefused(f"{where} is an object of {', '.join(sorted(SETTINGS_KEYS))}")
    unknown = sorted(set(value) - SETTINGS_KEYS)
    if unknown:
        raise SnapshotRefused(f"{where} has no {', '.join(unknown)}; it takes {', '.join(sorted(SETTINGS_KEYS))}")
    if "sizeProfile" in value and value["sizeProfile"] not in SIZE_PROFILES:
        raise SnapshotRefused(f"{where}.sizeProfile {value['sizeProfile']!r} is not one of {', '.join(SIZE_PROFILES)}")
    for key, (low, high) in (("padding", PADDING_RANGE), ("renderScale", RENDER_SCALE_RANGE)):
        number = value.get(key)
        if key in value and (isinstance(number, bool) or not isinstance(number, (int, float))
                             or not low <= number <= high):
            raise SnapshotRefused(f"{where}.{key} is a number from {low:g} to {high:g}")
    for key in ("tightFrame", "transparent"):
        if key in value and not isinstance(value[key], bool):
            raise SnapshotRefused(f"{where}.{key} is true or false")
    if drawing:
        framed = [key for key in ("padding", "tightFrame") if key in value]
        if framed:
            raise SnapshotRefused(f"{where} gives {' and '.join(framed)}, which fit a camera to a model; a drawing "
                                  "is framed by its plan view, or fitted whole with the pane's margin")
    return value


def _view_camera(value: Any, where: str, projection: str, tight: bool) -> tuple[Any, bool]:
    """A job's camera (or an output's), and whether it is drawn exactly: the view's own camera --
    a position, a target and, orthographic, its half height -- with the tight frame off is the view
    the person looked through, placed as it is; any other camera is fitted (``--camera``'s)."""
    if value is None:
        return None, False
    camera = parse_camera(value if isinstance(value, str) else json.dumps(value))
    if not isinstance(camera, dict):
        return camera, False
    half = camera.get("orthographicHalfHeight")
    whole = _numbers(camera.get("position"), 3) and _numbers(camera.get("target"), 3) and (
        projection == "perspective" or (isinstance(half, (int, float)) and not isinstance(half, bool) and half > 0))
    if camera.get("up") is not None and not _numbers(camera["up"], 3):
        raise SnapshotRefused(f"{where}.up is [x, y, z]")
    return camera, bool(whole) and not tight


def _job_size(output: dict[str, Any], settings: dict[str, Any], flags: tuple[Any, Any, Any], where: str) -> tuple[int, int]:
    """An output's size: the flags' for every output, else its own, else its job's profile."""
    if any(flag is not None for flag in flags):
        return parse_size(*flags)
    width, height = output.get("width"), output.get("height")
    for key, side in (("width", width), ("height", height)):
        if side is not None and (isinstance(side, bool) or not isinstance(side, int)):
            raise SnapshotRefused(f"{where}.{key} is a number of pixels")
    if width is not None or height is not None:
        return parse_size(width, height, None)
    return SIZE_PROFILES[settings["sizeProfile"]] if settings.get("sizeProfile") else DEFAULT_SIZE


def job_pictures(job: Any, source: Any = None, *, display: Any = None, camera: Any = None, grid: bool = False,
                 preview: bool = False, pose: Any = None, width: int | None = None, height: int | None = None,
                 size_profile: str | None = None, annotation: Any = None,
                 measurements: Any = None) -> list[tuple[Path, Path, Still]]:
    """Every picture a job names (``--job``: a Quick Edit packet, a job, or a list of jobs), each
    ``(the file drawn, the picture written, what it shows)``, checked before anything renders.

    A job is a view: its ``camera`` (an output's own over it), its ``display`` (the parts it hid and
    isolated among it, and -- a robot's -- the visuals its ``selection`` hid), its pose
    (``jointValues``), Preview, the ink and dimensions over it (its own, else the packet's), and its
    output settings (``_settings``); each of its ``outputs`` a picture at its ``path`` (a folder
    gives a name in it: ``picture_path``) and size. ``source`` is drawn in place of every job's
    input; a flag given overrides every job: the display, the grid, the camera, Preview, the pose,
    the ink, the dimensions, and the size of every output."""
    given = _load(job, "--job")
    if isinstance(given, dict) and isinstance(given.get("jobs"), list):
        unknown = sorted(set(given) - PACKET_KEYS)
        if unknown:
            raise SnapshotRefused(f"--job has no {', '.join(unknown)}; a packet has {', '.join(sorted(PACKET_KEYS))}")
        shared, jobs = given, given["jobs"]
    elif isinstance(given, list):
        shared, jobs = {}, given
    elif isinstance(given, dict) and "outputs" in given:
        shared, jobs = {}, [given]
    else:
        raise SnapshotRefused("--job is a Quick Edit packet ({input, jobs, ...}), a job ({input, camera, display, "
                              "outputs, ...}) or a list of jobs")
    if not jobs:
        raise SnapshotRefused("--job names no job")
    shown_flags = parse_display(display, grid) if display is not None else None
    camera_flag = parse_camera(camera if camera is None or isinstance(camera, str) else json.dumps(camera))
    pose_flag = parse_pose(pose) if isinstance(pose, str) else pose
    ink_flag = parse_annotation(annotation)
    dimensions_flag = parse_measurements(measurements)
    sizes = (width, height, size_profile)
    if any(flag is not None for flag in sizes):
        parse_size(*sizes)
    at = stamp()
    pictures: list[tuple[Path, Path, Still]] = []
    for j, view in enumerate(jobs):
        where = f"--job: jobs[{j}]"
        if not isinstance(view, dict):
            raise SnapshotRefused(f"{where} is an object: {{input, camera, display, outputs, ...}}")
        unknown = sorted(set(view) - JOB_KEYS)
        if unknown:
            raise SnapshotRefused(f"{where} has no {', '.join(unknown)}; a job takes {', '.join(sorted(JOB_KEYS))}")
        named = source if source is not None else view.get("input") or shared.get("input")
        if not named:
            raise SnapshotRefused(f"{where} names no input, and no SRC is given")
        document = Path(os.fspath(named))
        if not _by_id(document):
            document = document.expanduser().resolve()
        drawing = document.suffix.lower() == ".dxf"
        settings = _settings(view.get("output"), f"{where}.output", drawing)
        tight, padding = settings.get("tightFrame", True), float(settings.get("padding", PADDING))
        scale = float(settings.get("renderScale", 1.0))
        if shown_flags is not None:
            shown = dict(shown_flags)
        else:
            if view.get("display") is not None and not isinstance(view["display"], dict):
                raise SnapshotRefused(f"{where}.display is the view's display object")
            shown = parse_display(json.dumps(view["display"]), grid) if view.get("display") else (
                {"grid": True} if grid else {})
        selection = view.get("selection")
        if selection is not None:
            if not isinstance(selection, dict) or set(selection) - set(SELECTION_KEYS):
                raise SnapshotRefused(f"{where}.selection is {{hide, focus}}: the parts the view hid, or alone showed")
            for key, field_name in SELECTION_KEYS.items():
                if selection.get(key):
                    shown[field_name] = [*(shown.get(field_name) or []), *selection[key]]
            _visibility(shown)
        projection = (shown.get("camera") or {}).get("projection") or ("perspective" if preview or view.get("preview")
                                                                      else "orthographic")
        ink = ink_flag if annotation is not None else parse_annotation(view.get("annotation", shared.get("annotation")))
        dimensions = dimensions_flag if measurements is not None else parse_measurements(
            view.get("measurements", shared.get("measurements")))
        posed = pose_flag if pose is not None else view.get("jointValues")
        if isinstance(posed, str):
            posed = parse_pose(posed)
        if posed is not None and document.suffix.lower() in MESHES:
            raise SnapshotRefused(f"{where}: --pose poses a document's mechanism; {document.name} is a mesh and has none")
        if view.get("preview") is not None and not isinstance(view["preview"], bool):
            raise SnapshotRefused(f"{where}.preview is true or false")
        outputs = view.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            raise SnapshotRefused(f"{where}.outputs lists the pictures it writes, at least one")
        for o, output in enumerate(outputs):
            at_output = f"{where}.outputs[{o}]"
            output = {"path": output} if isinstance(output, str) else output
            if not isinstance(output, dict) or not output.get("path"):
                raise SnapshotRefused(f"{at_output} is a path, or an object with a path")
            unknown = sorted(set(output) - OUTPUT_KEYS)
            if unknown:
                raise SnapshotRefused(f"{at_output} has no {', '.join(unknown)}; an output takes "
                                      f"{', '.join(sorted(OUTPUT_KEYS))}")
            out = picture_path(output["path"], document, at=at, job=(j, len(jobs)), output=(o, len(outputs)))
            _checked(document, out)
            size = _job_size(output, settings, sizes, at_output)
            if max(size) * scale > 2 * MAX_SIDE:
                raise SnapshotRefused(f"{at_output} is {size[0]}x{size[1]}, which renderScale {scale:g} draws past "
                                      f"{2 * MAX_SIDE} pixels a side")
            framed, exact = (_view_camera(camera_flag, "--camera", projection, tight) if camera is not None
                             else _view_camera(output.get("camera", view.get("camera")), f"{at_output}.camera",
                                               projection, tight))
            if framed == AUTHORED:
                framed, exact, _view = authored(AUTHORED, ink, given if isinstance(given, dict) else None, document)
            pictures.append((document, out, Still(shown, framed, exact, bool(preview or view.get("preview")), size,
                                                  posed, ink, dimensions, padding, tight,
                                                  bool(settings.get("transparent")), scale)))
    written = [out for _document, out, _still in pictures]
    twice = sorted({str(out) for out in written if written.count(out) > 1})
    if twice:
        raise SnapshotRefused(f"--job writes {', '.join(twice)} twice: give each output a path of its own")
    for document, _out, still in pictures:
        if document.suffix.lower() == ".dxf":
            from cadgen.engine.render.drawing import refusals as drawing_refusals

            drawing_refusals(still, document.name)
    return pictures


def draw_pictures(pictures: list[tuple[Path, Path, Still]], *, daemon: bool = True) -> list[dict[str, Any]]:
    """A job's pictures drawn (``job_pictures``), each written to its file: through the daemon, a
    render process warm for each file, or in this process, each file served once for all its
    pictures. All or nothing: every picture is drawn into a staged file beside its output, and
    the staged files are moved over the outputs only once every one is drawn. A picture that
    fails leaves every output as it was and removes only the staged files (``_staged``)."""
    with contextlib.ExitStack() as stages:  # each picture's staging folder, gone with the job
        staged = []
        for document, out, still in pictures:
            out.parent.mkdir(parents=True, exist_ok=True)
            staged.append((document, out, stages.enter_context(staging(out)), still))
        drawn = _draw_staged(staged, daemon)
        for (_document, out, stage, _still), found in zip(staged, drawn):
            replace_atomic(stage, out)
            found["output"] = str(out)
        return drawn


def _draw_staged(staged: list[tuple[Path, Path, Path, Still]], daemon: bool) -> list[dict[str, Any]]:
    """Each picture of a job drawn into its staged file (``draw_pictures``)."""
    if daemon or any(_by_id(document) for document, _out, _stage, _still in staged):
        return [_occt(document, stage, still, daemon, None, time.perf_counter())
                for document, _out, stage, still in staged]
    from cadgen.engine.formats import FormatError
    from cadgen.engine.render.service import draw_here_each

    drawn: list[dict[str, Any]] = []
    at = 0
    while at < len(staged):
        document = staged[at][0]
        # The pictures of one file in a row, drawn from one serve of it.
        group = staged[at:at + next((n for n, picture in enumerate(staged[at:]) if picture[0] != document),
                                    len(staged) - at)]
        started = time.perf_counter()
        try:
            answers = draw_here_each(document, [still for _document, _out, _stage, still in group])
        except FormatError as error:
            raise SnapshotRefused(str(error)) from None
        drawn += [_written(document, stage, data, report, started)
                  for (_document, _out, stage, _still), (data, report) in zip(group, answers)]
        at += len(group)
    return drawn


def _warn(unmeshed: dict[str, list[int]]) -> dict[str, list[int]]:
    """A warning for each part's faces the mesher left without triangles: the picture lacks them."""
    for name, faces in unmeshed.items():
        print(f"warning: {name}: the mesher left face{'s' if len(faces) > 1 else ''} "
              f"{', '.join(map(str, faces))} without triangles, so the picture does not draw "
              f"{'them' if len(faces) > 1 else 'it'}", file=sys.stderr)
    return unmeshed


def _arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.usage = "%(prog)s SRC OUT.png [options] | --job PACKET [SRC] [options]"
    parser.add_argument("document", metavar="SRC", nargs="?",
                        help="a document (.xbf, .step), a mesh file (.glb, .stl, .3mf), a robot (.urdf, .sdf, .srdf), "
                             "a drawing (.dxf), or a document id (a model's, which python SCRIPT.py prints: drawn "
                             "from what the engine holds); with --job, a file drawn in place of every job's input")
    parser.add_argument("out", metavar="OUT.png", nargs="?",
                        help="the .png to write, or a folder (one that is there, or a path ending in a separator) to "
                             "write <SRC's stem>_<UTC time>.png into")
    parser.add_argument("--job", metavar="PACKET",
                        help="a Quick Edit packet (the .snapshot.json the viewer writes), a job or a list of jobs, as "
                             "JSON or a file of it: every picture its outputs name drawn, each job's view as it was -- "
                             "its camera, display, hidden and isolated parts, pose -- with the packet's ink and "
                             "dimensions, at its output settings (padding, tightFrame, transparent, renderScale, "
                             "sizeProfile); the other flags override every job")
    parser.add_argument("--display", help="a mode (solid, shaded, parts, xray, hidden-line, wireframe), exploded=AMOUNT "
                                          "(the parts moved apart, 0 to 1; with a mode: hidden-line,exploded=0.6), or "
                                          "the display JSON object (mode, grid, appearance, camera, clip, exploded, "
                                          "hidden, isolated: part refs the picture leaves out, or alone draws), or "
                                          "a JSON file of it; a drawing takes appearance alone: light or dark, as the word "
                                          "or as {\"appearance\": ...}")
    parser.add_argument("--grid", action="store_true", help="draw the measuring grid")
    parser.add_argument("--camera", help="a preset (iso, front, back, left, right, top, bottom), azimuth:elevation, "
                                         "a camera JSON object, or authored: the view --annotation's ink was drawn "
                                         "in, from its Quick Edit packet, exactly")
    parser.add_argument("--preview", action="store_true", help="Preview's photographic look instead of the mode")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--size-profile", choices=sorted(SIZE_PROFILES))
    parser.add_argument("--pose", help="a configuration's name (a robot's SRDF group state), or joint and coupling "
                                       "values as JSON ('{\"elbow\": 45}', '{\"curl\": 0.6}'; degrees, metres): the "
                                       "mechanism posed there; as built without it (a robot where the viewer opens it)")
    parser.add_argument("--annotation", metavar="FILE", help="the viewer's annotation file, or the Quick Edit packet "
                                                              "(.snapshot.json) that carries it: its ink drawn over the "
                                                              "model, on the parts it was drawn on")
    parser.add_argument("--measurements", metavar="FILE", help="Measure's dimensions (a JSON list of {start, end, label, "
                                                                "color}), drawn over the model")
    parser.add_argument("--json", action="store_true", help="print what was drawn and its timings as JSON")
    return parser


_HELP = "draw a document or a file the viewer opens as the CAD Viewer does, into a PNG"


def add_parser(verbs: Any) -> argparse.ArgumentParser:
    """The ``snapshot`` verb among a command's subcommands (``python -m cadgen.engine snapshot``)."""
    return _arguments(verbs.add_parser("snapshot", help=_HELP, description=_HELP))


def build_parser(prog: str = "cadgen snapshot") -> argparse.ArgumentParser:
    """``cadgen snapshot``'s parser."""
    return _arguments(argparse.ArgumentParser(prog=prog, description=_HELP))


def main(argv: list[str] | None = None, prog: str = "cadgen snapshot", suffixes: tuple[str, ...] = ()) -> int:
    """``cadgen snapshot SRC OUT.png``; with ``suffixes``, a command that draws those files alone
    (``cadgen dxf snapshot`` draws a ``.dxf``), refusing any other SRC by name before anything renders."""
    from cadgen.engine.cli import Failed, answered

    def drawn(args: argparse.Namespace, prog: str) -> int:
        named = args.document if args.job is None or args.document is not None else job_input(args.job)
        if suffixes and named is not None and Path(named).suffix.lower() not in suffixes:
            raise Failed(f"{named} is not a {' or '.join(suffixes)} file", 2)
        return run(args, prog)

    return answered(drawn, build_parser(prog).parse_args(argv), prog)


def run(args: argparse.Namespace, prog: str = "cadgen snapshot") -> int:
    """The verb run from its parsed flags; a failure raised as ``cli.Failed``, which the command
    says (``cli.answered``)."""
    from cadgen.engine.cli import Failed

    if args.job is not None:
        return _run_job(args, prog)
    if args.document is None or args.out is None:
        raise Failed("the following arguments are required: SRC, OUT.png (or --job PACKET)", 2)
    if _by_id(args.document):
        return _run_held(args, prog)
    from cadgen.engine import api
    from cadgen.engine.cli import _shown

    try:
        # The verb as a function (``api.snapshot``), which checks the flags as ``snapshot`` does.
        report = api.snapshot(Path(args.document), args.out, display=args.display, camera=args.camera, grid=args.grid,
                              preview=args.preview, pose=args.pose, width=args.width, height=args.height,
                              size_profile=args.size_profile, annotation=args.annotation,
                              measurements=args.measurements).report
    except SnapshotRefused as error:
        raise Failed(str(error), 2) from None
    except Exception as error:  # noqa: BLE001 - a failed render is the command's answer
        raise Failed(f"{type(error).__name__}: {error}") from None
    if args.json:
        print(json.dumps(report))
    else:
        timings = report["timings"]
        print(f"wrote {_shown(report['output'])} ({report['width']}x{report['height']}, {report['displayMode']}"
              f"{', preview' if report['preview'] else ''}) in {timings['totalMs'] / 1000:.2f}s")
    return 0


def _run_held(args: argparse.Namespace, prog: str) -> int:
    """``cadgen snapshot ID OUT.png``: the document the engine holds of that id, drawn from the
    memory of the worker holding it (``api.snapshot``); nothing is built."""
    from cadgen.engine import api
    from cadgen.engine.cli import Failed, _shown

    try:
        drawn = api.snapshot(args.document, args.out, display=args.display, camera=args.camera, grid=args.grid,
                             preview=args.preview, pose=args.pose, width=args.width, height=args.height,
                             size_profile=args.size_profile, annotation=args.annotation,
                             measurements=args.measurements)
    except (SnapshotRefused, ValueError) as error:
        raise Failed(str(error), 2) from None
    except api.EngineError as error:
        raise Failed(str(error)) from None
    if args.json:
        print(json.dumps(drawn.report))
    else:
        print(f"wrote {_shown(drawn.path)} ({drawn.width}x{drawn.height}) in "
              f"{drawn.report['timings']['totalMs'] / 1000:.2f}s")
    return 0


def _run_job(args: argparse.Namespace, prog: str) -> int:
    """``cadgen snapshot --job PACKET [SRC]``: every picture the job names (``api.snapshot(job=)``),
    a line each; with ``--json``, ``{"ok": true, "pictures": [what each drew]}``."""
    from cadgen.engine import api
    from cadgen.engine.cli import Failed, _shown

    if args.out is not None:
        raise Failed(f"--job writes the pictures its outputs name, so it takes no OUT ({args.out})", 2)
    started = time.perf_counter()
    try:
        drawn = api.snapshot(args.document, job=args.job, display=args.display, camera=args.camera, grid=args.grid,
                                 preview=args.preview, pose=args.pose, width=args.width, height=args.height,
                                 size_profile=args.size_profile, annotation=args.annotation,
                                 measurements=args.measurements)
    except SnapshotRefused as error:
        raise Failed(str(error), 2) from None
    except Exception as error:  # noqa: BLE001 - a failed render is the command's answer
        raise Failed(f"{type(error).__name__}: {error}") from None
    if args.json:
        print(json.dumps({"ok": True, "pictures": [picture.report for picture in drawn],
                          "timings": {"totalMs": round((time.perf_counter() - started) * 1000)}}))
    else:
        for picture in drawn:
            report = picture.report
            print(f"wrote {_shown(picture.path)} ({report['width']}x{report['height']}, {report['displayMode']}"
                  f"{', preview' if report['preview'] else ''}) in {report['timings']['totalMs'] / 1000:.2f}s")
    return 0
