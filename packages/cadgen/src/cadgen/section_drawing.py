"""``cadgen step snapshot --mode section``: the exact cut, as a 2D drawing.

Each placed occurrence's component is cut by the requested plane in its own
coordinates (``cadgen.store.sections``: an OCCT section of the exact BREP, a
build-pool job, cached by component and plane). This module places those loops
in the world, projects them onto the plane and emits ONE drawing payload -- the
same shape ``cadgen.drawing_payload`` gives a DXF, which the snapshot page paints
with the viewer's own 2D painter (``@text-to-cad/core/lib/drawing2d``) -- plus
the SVG of that payload, which is written here and never touches a browser.

Coordinates are the plane's own, y up: ``XY`` draws (X, Y), ``XZ`` draws
(X, Z), ``YZ`` draws (Y, Z), in model units. A circle the plane cuts is drawn
as cubic Beziers of its exact centre and radius (four to a full turn), lines as
lines, and any other curve as the polyline its cut was sampled to.

What is drawn, in order: each occurrence's closed loops filled (even-odd, so a
hole is a hole), hatched at 45 degrees, red dash-dot centre lines through the
cut's box, and every loop's outline. The hatch pitch and the dash lengths are
stated in output pixels and converted with the scale the page will fit the
drawing at, so they look the same at every model size.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = ["SECTION_FRAMES", "SectionDrawing", "locator_fraction", "section_drawing"]

# Each plane: its normal (the axis the offset moves along), and the two axes it
# draws as x and y. The plane is named by the two axes it contains.
SECTION_FRAMES: dict[str, tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...], str]] = {
    "XY": ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), "Z"),
    "XZ": ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), "Y"),
    "YZ": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), "X"),
}

# The look, in output pixels where it is a size. The cut's fill and hatch, the
# centre lines' dash-dot, and the outline that carries the picture.
FILL_COLOR, FILL_OPACITY = "#d1d5db", 0.72
# The hatch pitch is measured along a horizontal: its lines are 14 px apart there.
HATCH_COLOR, HATCH_OPACITY, HATCH_WIDTH_PX, HATCH_PITCH_PX = "#111827", 0.2, 1.0, 14.0
CENTERLINE_COLOR, CENTERLINE_OPACITY, CENTERLINE_WIDTH_PX = "#ef4444", 0.75, 1.5
CENTERLINE_DASHES_PX = (10.0, 8.0, 2.0, 8.0)
OUTLINE_WIDTH_PX = 3.0
# The share of the output's shorter side left clear around the cut (at least
# PADDING_MIN_PX), and the gutter the page's fit leaves on its own
# (drawing2d DRAWING_FIT_MARGIN).
PADDING_SHARE, PADDING_MIN_PX, PAGE_FIT_MARGIN_PX = 0.12, 20.0, 16.0
# A span narrower than this many model units is framed as this wide, so a
# sliver does not fill the picture.
MIN_FRAMED_SPAN = 1.0
_DECIMALS = 4
# How finely a circular arc is sampled for the hatch's inside test.
_ARC_SAMPLE_RADIANS = math.radians(2.0)


@dataclass
class SectionDrawing:
    """One job's section: the drawing payload, its SVG, and what the picture says about it."""

    payload: dict
    svg: str
    label: str
    warnings: list[str] = field(default_factory=list)


# --- geometry ------------------------------------------------------------------


def _rows(matrix: Sequence[float]) -> tuple[tuple[float, float, float], ...]:
    return ((matrix[0], matrix[1], matrix[2]), (matrix[4], matrix[5], matrix[6]), (matrix[8], matrix[9], matrix[10]))


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def occurrence_plane(matrix: Sequence[float], normal: Sequence[float], offset: float):
    """The world plane ``normal . x == offset`` in an occurrence's own coordinates.

    ``x = A p + t``, so ``(A^T normal) . p == offset - normal . t``.
    """
    rows = _rows(matrix)
    local = tuple(sum(rows[row][column] * normal[row] for row in range(3)) for column in range(3))
    translation = (matrix[3], matrix[7], matrix[11])
    return local, offset - _dot(normal, translation)


class _Placement:
    """An occurrence's transform composed with the plane's projection: local -> 2D."""

    def __init__(self, matrix: Sequence[float], frame) -> None:
        _normal, u, v, _axis = frame
        rows = _rows(matrix)
        translation = (matrix[3], matrix[7], matrix[11])
        # 2D = (u . (A p + t), v . (A p + t)): two rows of a 2x3 plus an offset.
        self.u = tuple(sum(u[row] * rows[row][column] for row in range(3)) for column in range(3))
        self.v = tuple(sum(v[row] * rows[row][column] for row in range(3)) for column in range(3))
        self.offset = (_dot(u, translation), _dot(v, translation))

    def point(self, p) -> tuple[float, float]:
        return (_dot(self.u, p) + self.offset[0], _dot(self.v, p) + self.offset[1])


def _rotated(point, center, axis, angle):
    """``point`` turned ``angle`` radians about the line through ``center`` along ``axis`` (Rodrigues)."""
    length = math.sqrt(_dot(axis, axis)) or 1.0
    k = tuple(component / length for component in axis)
    r = tuple(point[index] - center[index] for index in range(3))
    cos, sin = math.cos(angle), math.sin(angle)
    cross = (k[1] * r[2] - k[2] * r[1], k[2] * r[0] - k[0] * r[2], k[0] * r[1] - k[1] * r[0])
    along = _dot(k, r) * (1 - cos)
    return tuple(center[index] + r[index] * cos + cross[index] * sin + k[index] * along for index in range(3))


def _arc_2d(placement: _Placement, arc: Mapping[str, Any]):
    """``(center, radius, start angle, signed sweep)`` of an arc as drawn.

    Which way it turns on the page is read off the arc itself -- its start and a
    point a little further along, both placed and projected -- so a placement
    that mirrors the part turns its arcs the other way, as it must.
    """
    center = placement.point(arc["center"])
    start = placement.point(arc["start"])
    radius = math.hypot(start[0] - center[0], start[1] - center[1])
    begin = math.atan2(start[1] - center[1], start[0] - center[0])
    sweep = float(arc["sweep"])
    ahead = placement.point(_rotated(arc["start"], arc["center"], arc["axis"], math.copysign(0.1, sweep)))
    turn = (start[0] - center[0]) * (ahead[1] - center[1]) - (start[1] - center[1]) * (ahead[0] - center[0])
    return center, radius, begin, abs(sweep) if turn >= 0 else -abs(sweep)


def _arc_beziers(center, radius, begin, sweep):
    """Cubic Beziers (control, control, end) for an arc, at most a quarter turn each."""
    count = max(1, math.ceil(abs(sweep) / (math.pi / 2) - 1e-9))
    step = sweep / count
    k = 4.0 / 3.0 * math.tan(step / 4.0)
    out = []
    angle = begin
    for _ in range(count):
        end = angle + step
        c0, s0, c1, s1 = math.cos(angle), math.sin(angle), math.cos(end), math.sin(end)
        out.append((
            (center[0] + radius * (c0 - k * s0), center[1] + radius * (s0 + k * c0)),
            (center[0] + radius * (c1 + k * s1), center[1] + radius * (s1 - k * c1)),
            (center[0] + radius * c1, center[1] + radius * s1),
        ))
        angle = end
    return out


def _arc_samples(center, radius, begin, sweep):
    count = max(2, math.ceil(abs(sweep) / _ARC_SAMPLE_RADIANS))
    return [
        (center[0] + radius * math.cos(begin + sweep * index / count),
         center[1] + radius * math.sin(begin + sweep * index / count))
        for index in range(count + 1)
    ]


@dataclass
class _Loop:
    commands: list  # path commands, unrounded
    polyline: list  # sampled points, for the hatch
    closed: bool


def _loop_2d(placement: _Placement, loop: Mapping[str, Any]) -> _Loop:
    commands: list = []
    polyline: list = []
    last = None

    def move_or_join(point):
        nonlocal last
        if last is None:
            commands.append(["M", *point])
            polyline.append(point)
        elif math.hypot(point[0] - last[0], point[1] - last[1]) > 1e-9:
            commands.append(["L", *point])
            polyline.append(point)
        last = point

    for edge in loop.get("edges") or []:
        if "line" in edge:
            start, end = (placement.point(p) for p in edge["line"])
            move_or_join(start)
            commands.append(["L", *end])
            polyline.append(end)
            last = end
        elif "arc" in edge:
            center, radius, begin, sweep = _arc_2d(placement, edge["arc"])
            move_or_join((center[0] + radius * math.cos(begin), center[1] + radius * math.sin(begin)))
            for c1, c2, end in _arc_beziers(center, radius, begin, sweep):
                commands.append(["C", *c1, *c2, *end])
                last = end
            polyline.extend(_arc_samples(center, radius, begin, sweep)[1:])
        elif "points" in edge:
            points = [placement.point(p) for p in edge["points"]]
            if not points:
                continue
            move_or_join(points[0])
            for point in points[1:]:
                commands.append(["L", *point])
                polyline.append(point)
                last = point
    closed = bool(loop.get("closed"))
    if closed and commands:
        commands.append(["Z"])
    return _Loop(commands, polyline, closed)


def _hatch(loops: Sequence[_Loop], pitch: float) -> list[list[float]]:
    """45-degree hatch segments inside ``loops`` (even-odd), ``pitch`` model units apart.

    A scanline in the hatch's own frame: ``a`` runs along a hatch line (+x+y),
    ``b`` across them. Every edge of every closed loop's polyline is crossed with
    each line ``b = k * pitch``; the crossings, sorted along the line, pair into
    the inside spans.
    """
    import numpy as np

    rings = [np.asarray(loop.polyline, dtype=float) for loop in loops if loop.closed and len(loop.polyline) >= 3]
    if not rings or not pitch > 0:
        return []
    root = math.sqrt(0.5)
    starts, ends = [], []
    for ring in rings:
        closed = np.vstack([ring, ring[:1]])
        starts.append(closed[:-1])
        ends.append(closed[1:])
    p0, p1 = np.vstack(starts), np.vstack(ends)
    a0, b0 = (p0[:, 0] + p0[:, 1]) * root, (p0[:, 1] - p0[:, 0]) * root
    a1, b1 = (p1[:, 0] + p1[:, 1]) * root, (p1[:, 1] - p1[:, 0]) * root
    low, high = np.minimum(b0, b1), np.maximum(b0, b1)
    first, last = math.ceil(float(low.min()) / pitch), math.floor(float(high.max()) / pitch)
    segments = []
    for k in range(first, last + 1):
        b = k * pitch
        # Half-open in b, so a vertex exactly on the line is counted once.
        crossing = (low <= b) & (high > b)
        if not crossing.any():
            continue
        t = (b - b0[crossing]) / (b1[crossing] - b0[crossing])
        a = np.sort(a0[crossing] + t * (a1[crossing] - a0[crossing]))
        for start, end in zip(a[0::2], a[1::2]):
            if end - start > 1e-12:
                segments.append([
                    (start - b) * root, (start + b) * root, (end - b) * root, (end + b) * root,
                ])
    return segments


def _dashes(start, end, pattern: Sequence[float]) -> list[list[float]]:
    """``pattern`` (on, off, on, off, ... in model units) laid along a segment."""
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if not length > 0 or not sum(pattern) > 0:
        return []
    direction = ((end[0] - start[0]) / length, (end[1] - start[1]) / length)
    out, at, index = [], 0.0, 0
    while at < length:
        step = pattern[index % len(pattern)]
        if index % 2 == 0:
            stop = min(at + step, length)
            out.append([start[0] + direction[0] * at, start[1] + direction[1] * at,
                        start[0] + direction[0] * stop, start[1] + direction[1] * stop])
        at += step
        index += 1
    return out


# --- the payload ----------------------------------------------------------------


def _number(value: float):
    number = round(float(value), _DECIMALS)
    if number == 0:
        return 0
    integral = int(number)
    return integral if integral == number else number


def _rounded_commands(commands) -> list:
    return [[command[0], *(_number(value) for value in command[1:])] for command in commands]


def _command_points(commands):
    for command in commands:
        values = command[1:]
        for index in range(0, len(values), 2):
            yield values[index], values[index + 1]


def _frame_scale(span_x: float, span_y: float, size: tuple[int, int]) -> float:
    """Output pixels per model unit, as the cut has always been framed: the
    padded output fitted to the cut's box."""
    width, height = size
    padding = max(PADDING_MIN_PX, min(width, height) * PADDING_SHARE)
    return max(
        min((width - 2 * padding) / max(span_x, MIN_FRAMED_SPAN), (height - 2 * padding) / max(span_y, MIN_FRAMED_SPAN)),
        1e-9,
    )


def _units(descriptor: Mapping[str, Any]) -> dict:
    units = str(descriptor.get("units") or "mm")
    if units == "mm":
        return {"insunits": 4, "name": "Millimeters", "toMillimetres": 1.0}
    return {"insunits": 0, "name": units, "toMillimetres": None}


def _plane_label(plane: str, offset: float) -> str:
    return f"{plane} @ {SECTION_FRAMES[plane][3]}={float(offset):.3f}"


def section_drawing(
    descriptor: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    *,
    plane: str,
    offset: float,
    size: tuple[int, int],
    outline_color: str | None = None,
) -> SectionDrawing:
    """The section of ``rows`` (``assembly_occurrence_rows``, already selected) by ``plane``.

    ``size`` is the output, in pixels, the drawing is framed for. ``outline_color``
    is the outline's literal colour; ``None`` leaves it the page's foreground.
    """
    from cadgen.daemon.artifacts import SECTIONS_PER_STARTED_WORKER, deal, resolve_artifacts
    from cadgen.drawing_payload import DRAWING_PAYLOAD_SCHEMA_VERSION
    from cadgen.store import sections

    frame = SECTION_FRAMES[plane]
    normal = frame[0]
    components = descriptor.get("components") if isinstance(descriptor.get("components"), Mapping) else {}

    placed = []  # (row, matrix, key)
    items: dict[str, dict] = {}
    for row in rows:
        component = components.get(str(row.get("component") or ""))
        if not isinstance(component, Mapping):
            continue
        matrix = list(row["transform"])
        local_normal, local_offset = occurrence_plane(matrix, normal, float(offset))
        entry = sections.component_entry(dict(component))
        key = sections.section_key(entry, local_normal, local_offset)
        placed.append((row, matrix, key))
        unit, distance = sections.canonical_plane(local_normal, local_offset)
        items.setdefault(key, {"component": entry, "normal": list(unit), "offset": distance})

    cuts = {key: sections.read(key) for key in items}
    missing = [items[key] for key, cut in cuts.items() if cut is None]
    if missing:
        batches = [missing[index:index + 256] for index in range(0, len(missing), 256)]
        resolve_artifacts([{"kind": "sections", "items": dealt}
                           for batch in batches
                           for dealt in deal(batch, per_started_worker=SECTIONS_PER_STARTED_WORKER)])
        cuts.update((key, sections.read(key)) for key, cut in cuts.items() if cut is None)

    shapes = []  # per occurrence: its loops in 2D
    for _row, matrix, key in placed:
        cut = cuts.get(key) or {"loops": []}
        placement = _Placement(matrix, frame)
        loops = [_loop_2d(placement, loop) for loop in cut.get("loops") or []]
        loops = [loop for loop in loops if loop.commands]
        if loops:
            shapes.append(loops)

    label = _plane_label(plane, offset)
    warnings: list[str] = []
    points = [point for loops in shapes for loop in loops for point in _command_points(loop.commands)]
    payload: dict[str, Any] = {
        "schemaVersion": DRAWING_PAYLOAD_SCHEMA_VERSION,
        "units": _units(descriptor),
        "bounds": None,
        "layers": [],
        # A section is lettered by the page's overlay, not by the payload: no text, no fonts.
        "fonts": [],
        "primitives": [],
    }
    if not points:
        warnings.append(f"SECTION {label} does not intersect the model; the section is empty")
        return SectionDrawing(payload, _svg(payload, size), label, warnings)

    xs, ys = [x for x, _ in points], [y for _, y in points]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    scale = _frame_scale(max_x - min_x, max_y - min_y, size)
    # The page fits the payload's bounds inside its own gutter. Bounds padded out
    # to exactly the area that gutter leaves land the cut at the scale above,
    # centred, with the centre lines running edge to edge.
    centre = ((min_x + max_x) / 2, (min_y + max_y) / 2)
    half_w = max((size[0] - 2 * PAGE_FIT_MARGIN_PX) / scale, max_x - min_x) / 2
    half_h = max((size[1] - 2 * PAGE_FIT_MARGIN_PX) / scale, max_y - min_y) / 2
    pixel = 1.0 / scale

    primitives = []
    layer_counts: dict[str, int] = {}

    def add(primitive):
        primitives.append(primitive)
        layer_counts[primitive["layer"]] = layer_counts.get(primitive["layer"], 0) + 1

    for loops in shapes:
        closed = [loop for loop in loops if loop.closed]
        if closed:
            add({"type": "filled-paths", "layer": "section-fill", "color": FILL_COLOR, "opacity": FILL_OPACITY,
                 "geometry": [_rounded_commands(loop.commands) for loop in closed]})
    hatch = [segment for loops in shapes for segment in _hatch(loops, HATCH_PITCH_PX * math.sqrt(0.5) * pixel)]
    if hatch:
        add({"type": "lines", "layer": "section-hatch", "color": HATCH_COLOR, "opacity": HATCH_OPACITY,
             "width": HATCH_WIDTH_PX, "geometry": [[_number(value) for value in line] for line in hatch]})
    pattern = [length * pixel for length in CENTERLINE_DASHES_PX]
    centerlines = (
        _dashes((centre[0], centre[1] + half_h), (centre[0], centre[1] - half_h), pattern)
        + _dashes((centre[0] - half_w, centre[1]), (centre[0] + half_w, centre[1]), pattern)
    )
    add({"type": "lines", "layer": "section-centerline", "color": CENTERLINE_COLOR, "opacity": CENTERLINE_OPACITY,
         "width": CENTERLINE_WIDTH_PX, "geometry": [[_number(value) for value in line] for line in centerlines]})
    for loops in shapes:
        add({"type": "path", "layer": "section-outline", "color": outline_color, "width": OUTLINE_WIDTH_PX,
             "geometry": _rounded_commands([command for loop in loops for command in loop.commands])})

    payload["bounds"] = [_number(centre[0] - half_w), _number(centre[1] - half_h),
                         _number(centre[0] + half_w), _number(centre[1] + half_h)]
    payload["layers"] = [{"name": name, "color": None, "count": count} for name, count in layer_counts.items()]
    payload["primitives"] = primitives
    return SectionDrawing(payload, _svg(payload, size), label, warnings)


def locator_fraction(rows: Sequence[Mapping[str, Any]], plane: str, offset: float) -> float:
    """Where the cut sits across the selected parts along the plane's normal, 0..1."""
    axis = "XYZ".index(SECTION_FRAMES[plane][3])
    lows = [float(row["bbox"]["min"][axis]) for row in rows if isinstance(row.get("bbox"), Mapping)]
    highs = [float(row["bbox"]["max"][axis]) for row in rows if isinstance(row.get("bbox"), Mapping)]
    if not lows:
        return 0.0
    low, high = min(lows), max(highs)
    return min(max((float(offset) - low) / max(high - low, 1e-9), 0.0), 1.0)


# --- SVG ------------------------------------------------------------------------


def _svg_number(value) -> str:
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _svg_path(commands) -> str:
    return " ".join(
        command[0] + ("" if len(command) == 1 else " " + " ".join(_svg_number(value) for value in command[1:]))
        for command in commands
    )


def _svg_style(primitive, *, fill: bool) -> str:
    color = primitive.get("color") or "currentColor"
    opacity = primitive.get("opacity")
    if fill:
        style = f'fill="{color}" fill-rule="evenodd" stroke="none"'
        return style + (f' fill-opacity="{_svg_number(opacity)}"' if opacity is not None else "")
    width = primitive.get("width") or 1.25
    style = (f'fill="none" stroke="{color}" stroke-width="{_svg_number(width)}" '
             'stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"')
    return style + (f' stroke-opacity="{_svg_number(opacity)}"' if opacity is not None else "")


def _svg(payload: Mapping[str, Any], size: tuple[int, int]) -> str:
    """The payload as a standalone SVG, y up as drawn, strokes in screen pixels.

    The default pen (``color: null``) is ``currentColor``: black on its own, and
    whatever colour a page that embeds it sets.
    """
    bounds = payload.get("bounds")
    head = f'<svg xmlns="http://www.w3.org/2000/svg" width="{size[0]}" height="{size[1]}"'
    if not bounds:
        return head + "/>"
    min_x, min_y, max_x, max_y = bounds
    view_box = " ".join(_svg_number(value) for value in (min_x, -max_y, max_x - min_x, max_y - min_y))
    body = []
    for primitive in payload.get("primitives") or []:
        kind, geometry = primitive["type"], primitive["geometry"]
        if kind == "filled-paths":
            data = " ".join(_svg_path(commands) for commands in geometry)
            body.append(f'<path d="{data}" {_svg_style(primitive, fill=True)}/>')
        elif kind == "lines":
            data = " ".join(f"M {_svg_number(x0)} {_svg_number(y0)} L {_svg_number(x1)} {_svg_number(y1)}"
                            for x0, y0, x1, y1 in geometry)
            body.append(f'<path d="{data}" {_svg_style(primitive, fill=False)}/>')
        elif kind == "path":
            body.append(f'<path d="{_svg_path(geometry)}" {_svg_style(primitive, fill=False)}/>')
    return f'{head} viewBox="{view_box}"><g transform="scale(1 -1)">{"".join(body)}</g></svg>'
