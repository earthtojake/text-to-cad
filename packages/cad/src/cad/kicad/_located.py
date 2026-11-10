"""What a DRC finding names, read off the board: ``cad.kicad_pcb.drc``'s items and its copper slivers' places.

KiCad's JSON report names each item of a finding by its uuid, its position and a sentence ("Track [GND] on
F.Cu, length 2.0 mm"). :func:`board_items` reads the saved board once for what each uuid is -- its kind, its
layers, its net, the board reference that names it (``#track:<uuid>``, ``#U3.7``, ``#U3``) -- so a finding's
items can be looked up, lit and edited without matching geometry by hand.

KiCad reports a copper sliver with no item and no position (its sliver checker marks a point of a layer's
merged copper that it never writes to the report). :func:`slivers` finds them again in the saved copper of
that layer as KiCad's checker does: a convex corner of a fill or a filled copper shape sharper than
``SLIVER_ANGLE`` degrees that no other copper on the layer covers. It runs on the board as saved: the fills
KiCad last wrote, which are what its DRC checked (``cad kicad_pcb drc`` does not refill).

The standard library alone: it runs where the check runs, in the environment of ``cad[kicad]``.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Sequence

from cad.engine.formats.kicad import sexpr
from cad.engine.formats.kicad.board_index import (
    canonical_copper, copper_layers, expand_copper, footprint_property, item_id, item_layers, net_of, net_table,
    read_index,
)

__all__ = ["LAYER_SUFFIX", "PAD_WORDS", "SLIVER_ANGLE", "board_items", "layer_names", "slivers"]

#: KiCad's sliver checker's defaults (its advanced config's ``SliverAngleTolerance`` and ``SliverMinimumLength``):
#: a corner sharper than this many degrees, and the edges shorter than this (mm) passed over to find its sides.
SLIVER_ANGLE = 20.0
SLIVER_MINIMUM_LENGTH = 0.0008

XY = tuple[float, float]

_KINDS = {"segment": "track", "arc": "track", "via": "via", "zone": "zone", "dimension": "dimension",
          "gr_text": "text", "gr_text_box": "text", "fp_text": "text", "fp_text_box": "text", "property": "field",
          "footprint": "footprint", "pad": "pad", "group": "group", "image": "image", "target": "target"}
#: The kinds a board reference names by uuid (``#track:<uuid>``).
_BY_UUID = {"track": "track", "via": "via", "zone": "zone", "dimension": "dimension", "text": "text", "shape": "shape"}


def layer_names(tree: list) -> dict[str, str]:
    """Every name KiCad shows a layer by (its user name, ``B.Silkscreen``, as its report writes it) and its
    file name (``B.SilkS``), to the file name: the layers the board's table declares."""
    names: dict[str, str] = {}
    for entry in (sexpr.find(tree, "layers") or [])[1:]:
        if isinstance(entry, list) and len(entry) >= 2:
            name = str(entry[1])
            names[name] = name
            if len(entry) >= 4 and isinstance(entry[3], str):
                names[str(entry[3])] = name
    return names


def _kind(head: str) -> str | None:
    if head in _KINDS:
        return _KINDS[head]
    if head.startswith(("gr_", "fp_")):
        return "shape"
    return None


def board_items(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """What each uuid of the saved board ``path`` is: ``{uuid: {"kind", "layers", "net", "ref", "part"}}``
    (``layers`` its copper spelled out -- a through pad's or a via's every layer it joins -- and its other
    layers as the file names them; ``ref`` the board reference that names it, or ``None`` for one the
    references do not name; ``part`` the footprint holding it), and the board's layer names
    (:func:`layer_names`)."""
    tree = canonical_copper(sexpr.parse(Path(path).read_text(encoding="utf-8")))
    table, copper = net_table(tree), copper_layers(tree)
    found: dict[str, dict[str, Any]] = {}

    def layers_of(node: list) -> list[str]:
        named = item_layers(node)
        if sexpr.head(node) == "via" and len(named) == 2 and all(layer in copper for layer in named):
            low, high = sorted(copper.index(layer) for layer in named)
            return copper[low:high + 1]  # a via joins every copper layer between its two
        spelled = expand_copper(named, copper)
        return spelled + [layer for layer in named if layer not in spelled and not layer.endswith(".Cu")
                          and "*" not in layer and "&" not in layer]

    def add(node: list, part: str | None) -> None:
        uid = item_id(node)
        kind = _kind(str(sexpr.head(node)))
        if kind is None or (uid is not None and uid in found):
            return
        ref = None
        if kind == "footprint" or kind == "field":
            ref = f"#{part}" if part else None
        elif kind == "pad":
            number = node[1] if len(node) > 1 and isinstance(node[1], (str, int)) else None
            ref = f"#{part}.{number}" if part and number not in (None, "") and "." not in str(number) else (
                f"#{part}" if part else None)
        elif kind in _BY_UUID and not part:
            ref = f"#{_BY_UUID[kind]}:{uid}"
        elif part:
            ref = f"#{part}"
        what = {"kind": kind, "layers": layers_of(node), "net": net_of(node, table), "ref": ref,
                "part": part if kind != "footprint" else None}
        if uid:
            found[uid] = what
        if kind == "pad" and part and len(node) > 1 and isinstance(node[1], (str, int)):
            # A pad KiCad's report names by a uuid the file does not hold (a pad saved without one gets a new
            # uuid each load) is found by its part and number, as the report's words name it.
            found.setdefault(f"pad:{part}.{node[1]}", what)

    for node in tree[1:]:
        if not isinstance(node, list):
            continue
        if sexpr.head(node) == "footprint":
            reference = footprint_property(node, "Reference")
            part = str(reference) if reference else None
            add(node, part)
            for child in node[1:]:
                if isinstance(child, list):
                    add(child, part)
        else:
            add(node, None)
    return found, layer_names(tree)


# --- copper slivers ---------------------------------------------------------------------------------------


def _inside(point: XY, ring: Sequence[XY]) -> bool:
    """Even-odd: whether ``point`` lies inside the closed ``ring``."""
    x, y = point
    inside = False
    count = len(ring)
    for index in range(count):
        (ax, ay), (bx, by) = ring[index], ring[index - 1]
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax:
            inside = not inside
    return inside


def _segment_distance(point: XY, a: XY, b: XY) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length))
    return math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dy)


def _corners(ring: Sequence[XY]) -> list[XY]:
    """The convex corners of ``ring`` sharper than ``SLIVER_ANGLE``: each vertex's sides found past edges shorter
    than ``SLIVER_MINIMUM_LENGTH``, as KiCad's checker finds them. A vertex the ring visits twice (the slit a
    saved fill joins a hole to its outline by) is no corner."""
    points = list(ring)
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    count = len(points)
    if count <= 5:  # KiCad's checker passes over an outline this small
        return []
    twice = {point for point, seen in _counts(points).items() if seen > 1}
    turning = sum(points[i - 1][0] * points[i][1] - points[i][0] * points[i - 1][1] for i in range(count))
    found = []
    for index, point in enumerate(points):
        if point in twice:
            continue
        before = after = None
        for step in range(1, count):
            other = points[(index - step) % count]
            if abs(other[0] - point[0]) >= SLIVER_MINIMUM_LENGTH or abs(other[1] - point[1]) >= SLIVER_MINIMUM_LENGTH:
                before = (other[0] - point[0], other[1] - point[1])
                break
        for step in range(1, count):
            other = points[(index + step) % count]
            if abs(other[0] - point[0]) >= SLIVER_MINIMUM_LENGTH or abs(other[1] - point[1]) >= SLIVER_MINIMUM_LENGTH:
                after = (other[0] - point[0], other[1] - point[1])
                break
        if before is None or after is None:
            continue
        cross = before[0] * after[1] - before[1] * after[0]
        # Convex: the ring turns the way it winds at this vertex (the incoming edge, -before, crossed with the
        # outgoing, after, has the sign of the ring's area).
        if -cross * turning <= 0:
            continue
        angle = math.degrees(abs(math.atan2(cross, before[0] * after[0] + before[1] * after[1])))
        if angle < SLIVER_ANGLE:
            found.append(point)
    return found


def _counts(points: Sequence[XY]) -> dict[XY, int]:
    counted: dict[XY, int] = {}
    for point in points:
        counted[point] = counted.get(point, 0) + 1
    return counted


#: How far round a sharp corner the copper is sampled (mm), and in how many directions: a corner of the
#: layer's merged copper is a sliver when the copper fills less than ``SLIVER_ANGLE`` of that circle.
_PROBE_RADIUS = 0.03
_PROBE_DIRECTIONS = 144


def _box(points: Sequence[XY], grow: float = 0.0) -> tuple[float, float, float, float]:
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    return min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow


def slivers(path: Path, layer: str) -> list[XY]:
    """Where the saved copper of ``layer`` on the board ``path`` has a sliver, as KiCad's sliver checker finds
    one in the layer's copper merged: a sharp convex corner (:func:`_corners`) of a zone's fill or a filled
    copper shape round which the layer's copper -- every fill, shape, track, via and pad on it, merged --
    fills less than ``SLIVER_ANGLE`` degrees of a small circle (a corner that other copper abuts or covers is no
    corner of the merged copper). Ordered top to bottom, then left to right, in KiCad's millimetres (y down)."""
    index = read_index(Path(path).read_text(encoding="utf-8"))
    rings: list[tuple[XY, ...]] = []
    for zone in index.zones:
        if zone.layer == layer:
            rings += [fill for fill in zone.fills if len(fill) > 2]
    for shape in index.shapes:
        if shape.layer == layer and shape.filled and len(shape.points) > 2:
            rings.append(shape.points)
    side = {"F.Cu": "top", "B.Cu": "bottom"}.get(layer)
    pads = [pad.polygon for pad in index.pads if len(pad.polygon) > 2 and (pad.side == "both" or pad.side == side)]
    areas = [(_box(ring), ring) for ring in [*rings, *pads]]
    strokes = [(_box((a, b), track.width / 2), a, b, track.width / 2) for track in index.tracks if track.layer == layer
               for a, b in zip(track.points, track.points[1:])]
    discs = [(via.at, via.diameter / 2) for via in index.vias if layer in _via_layers(via.layers, index.layers)]

    def copper_at(point: XY, near: list, lines: list, rounds: list) -> bool:
        return (any(_inside(point, ring) for _box_, ring in near) or any(_segment_distance(point, a, b) < half
                                                                          for _box_, a, b, half in lines)
                or any(math.dist(point, at) < radius for at, radius in rounds))

    found: list[XY] = []
    for ring in rings:
        for corner in _corners(ring):
            reach = _PROBE_RADIUS
            x0, y0, x1, y1 = corner[0] - reach, corner[1] - reach, corner[0] + reach, corner[1] + reach
            near = [(box, other) for box, other in areas if box[0] <= x1 and box[2] >= x0 and box[1] <= y1 and box[3] >= y0]
            lines = [line for line in strokes if line[0][0] <= x1 and line[0][2] >= x0 and line[0][1] <= y1 and line[0][3] >= y0]
            rounds = [(at, radius) for at, radius in discs if math.dist(at, corner) < radius + reach]
            filled = sum(copper_at((corner[0] + reach * math.cos(2 * math.pi * k / _PROBE_DIRECTIONS),
                                    corner[1] + reach * math.sin(2 * math.pi * k / _PROBE_DIRECTIONS)), near, lines, rounds)
                         for k in range(_PROBE_DIRECTIONS))
            if filled * 360 / _PROBE_DIRECTIONS < SLIVER_ANGLE:
                found.append((round(corner[0], 4), round(corner[1], 4)))
    return sorted(dict.fromkeys(found), key=lambda point: (point[1], point[0]))


def _via_layers(layers: Sequence[str], board_layers: Sequence[str]) -> list[str]:
    copper = [layer for layer in board_layers if layer.endswith(".Cu")] or ["F.Cu", "B.Cu"]
    if len(layers) == 2 and all(layer in copper for layer in layers):
        low, high = sorted(copper.index(layer) for layer in layers)
        return copper[low:high + 1]
    return list(layers)


#: A pad as KiCad's report names it: ``Pad 2 [GND] of J1``, ``PTH pad 1 of R3 on F.Cu``.
PAD_WORDS = re.compile(r"\bpad (\S+)(?: \[[^\]]*\])? of (\S+)", re.IGNORECASE)
#: A finding's layer, as KiCad's description ends with it: ``Copper sliver (F.Cu)``.
LAYER_SUFFIX = re.compile(r"\(([A-Za-z0-9_.&]+)\)\s*$")
