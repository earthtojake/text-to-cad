"""A sheet's cut file (a DXF), checked with ezdxf, build123d's own DXF library (``cad._internal.dfm.sheet``).

The file is read as a cutter reads it: its units (``_units``: the ones it declares, ``$INSUNITS``, or the
ones given, ``--units``; never assumed -- a file that declares none, as every R12 file, is not measured until
they are given), each layer's intent by its name and its layer table (``cad.engine.export.dxf.layer_intent``:
cut, bend, engrave or reference), and the one drawing check every export runs that bears on a cut
(``validate_drawing_document``'s zero-length entities), whose findings are kept.

**Every entity on a cut layer is read, an annotation, or said not read.** ezdxf explodes what holds curves
(``_primitives``): a block reference into its block's entities, its own transform applied and a nested
reference's too (an entity on layer 0 of a block takes the reference's layer), a polyline into its lines
and arcs. Each curve is then a piece in the world's XY (``_pieces``): a line, an arc or a circle where it
lies whatever its OCS (one mirrored, extrusion (0, 0, -1), is read mirrored), a sampled spline or ellipse.
Text, dimensions, hatches and points on a cut layer do not cut (``annotations``). A cut-layer entity that
is neither -- a curve off the sheet's plane, a 3D polyline that is not flat, a mesh, a type this check does
not read -- is not read (``cut_file.unread``), and the check says it did not measure the file's cut
entities (the ``cut_entities`` family, not measured): never a pass of what it did not read. A file with no
cut curve at all is not measured (``Unmeasured``, ``no_cut_geometry``), whatever else it holds: a stray
dimension makes no file a drawing here.

What is drawn closed -- a circle, a closed spline, a full ellipse, a closed polyline -- is a contour as
drawn; the other pieces are chained end to end into closed contours (``_chain``): ends drawn at one point are
one, and ends left dangling within ``_JOIN`` of each other are joined (a gap a cutter's path closes, counted
in ``joined_gaps``). What does not close is open geometry, located by layer, entity handle and the dangling end. Pieces lying on one another are cut
twice: an exact copy of any curve, a spline or an ellipse as a line (``_unique``, one overlap per pair of
entities), and lines and arcs that overlap in part (collinear lines, concentric arcs of one radius, a line
along a polyline's segment: ``_overlaps``); a contour crossing itself or another leaves a sliver, and two that touch (a hole
tangent to the edge, two parts corner to corner) leave no material or no gap between them (``contour_crossings``,
within ``_SAME``; a whole circle crossed and held by its centre and radius); a loop enclosing no area is a
doubled-back line; a run of many short lines turning a little at a time is a curve drawn as chords.

The closed contours are nested (an outline, its holes, an island in a hole: a piece that falls out) and
measured in the plane with ``cad._internal.sheet_plane``, as the flat pattern of a bent part is
(``_dfm_sheet``): each part's size, holes (diameter, slot width), hole-to-edge and hole-to-hole distances
(edge to edge), notches, tabs, the narrowest web of material and the narrowest gap. A bend layer's lines
are read as the bends' centre lines: each hole's distance to the nearest (``hole_to_bend``; a line that
ends on a cutout's edge ends there, the cutout a window or a relief at the bend's end, no hole beside it, and
so does one drawn across a cutout that reaches ``WINDOW_T`` thicknesses to both sides of it)
and each line's distance to the outline either side of it (``flanges``).
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from cad._internal import sheet_plane as plane
from cad._internal.dfm import Unmeasured

__all__ = ["measure"]

#: $INSUNITS codes and their length in millimetres (the others a cutter does not read as lengths).
UNITS = {1: ("in", 25.4), 2: ("ft", 304.8), 4: ("mm", 1.0), 5: ("cm", 10.0), 6: ("m", 1000.0),
         8: ("microinch", 25.4e-6), 9: ("mil", 0.0254), 10: ("yd", 914.4), 13: ("micron", 1e-3),
         14: ("dm", 100.0)}
_ANNOTATIONS = frozenset({"TEXT", "MTEXT", "DIMENSION", "ARC_DIMENSION", "LEADER", "MULTILEADER", "HATCH",
                          "MLEADER", "ATTRIB", "ATTDEF", "IMAGE", "WIPEOUT", "TOLERANCE", "POINT",
                          "SOLID", "TRACE", "VIEWPORT"})
ITEM_CAP = 300
_SAME = 1e-4          # mm: two points this close are one as drawn (a copy of a curve, a curve on another)
#: Two dangling ends this close are joined (mm): a hundredth of a millimetre is far under any cutter's
#: resolution, and an inch file rounded to four decimals leaves ends 0.0025 mm apart. A gap between ``_SAME`` and
#: this is closed and said (``joined_gaps``); a wider one is open geometry.
_JOIN = 0.01
#: A cutout a bend line is drawn across is a window through the bend -- the bend ends at it -- where it reaches
#: this many thicknesses to both sides of the line; short of that it is a hole in the bend. text-to-cad's own
#: reading of a drawing that holds no bend radius: a 90 degree bend's tangent lines lie (pi / 4)(r + K t) either
#: side of its centre line, under 2 t for any inside radius up to 2 t, so such a cutout takes the bend's whole
#: width away.
WINDOW_T = 2.0
#: Block references nested deeper than this are not exploded (a block that holds itself would never end).
_NESTED = 16


@dataclass
class _Piece:
    kind: str                 # "line", "arc" or "curve"
    points: np.ndarray        # (n, 2) in mm, n >= 2
    handle: str               # of the modelspace entity it came from (a block reference's, for a block's curve)
    layer: str
    entity: str               # that entity's type
    closed: bool = False      # a whole circle, a closed spline or a full ellipse
    centre: tuple[float, float] | None = None
    radius: float | None = None
    start: float = 0.0        # an arc's start angle and signed sweep, radians, in the world's XY
    sweep: float = 0.0
    ring: Any = None          # the closed polyline it is a side of (``_primitives``): a loop as drawn
    copy: bool = False        # an exact copy of another entity's piece (``_unique``)

    def ends(self) -> tuple[np.ndarray, np.ndarray]:
        return self.points[0], self.points[-1]


def _where(piece: _Piece, point: Any = None) -> str:
    return f"layer {piece.layer}, {piece.entity} #{piece.handle}"


# --- reading ------------------------------------------------------------------------------------------------


def _primitives(entity: Any, layer: str, depth: int = 0) -> Iterator[tuple[Any, str, str | None, Any]]:
    """``entity`` as what a cutter follows, each with its layer and None -- a block reference exploded, a
    polyline as its lines and arcs, any other entity itself -- or with why it cannot be read; and, for a side
    of a closed polyline, that polyline (its ring: the sides are a loop as drawn)."""
    kind = entity.dxftype()
    if kind == "INSERT":
        if depth >= _NESTED:
            yield entity, layer, f"block references nested more than {_NESTED} deep", None
            return
        skipped: list[tuple[Any, str]] = []
        try:
            references = list(entity.multi_insert()) if entity.mcount > 1 else [entity]
            children = [child for reference in references
                        for child in reference.virtual_entities(skipped_entity_callback=lambda e, why: skipped.append((e, why)))]
            children += list(entity.attribs)
        except Exception as error:  # noqa: BLE001 - a block that does not explode is said, never passed over
            yield entity, layer, f"its block did not explode ({type(error).__name__}: {error})", None
            return
        for child in children:
            own = str(child.dxf.get("layer", "0") or "0")
            yield from _primitives(child, layer if own == "0" else own, depth + 1)
        for child, why in skipped:
            own = str(child.dxf.get("layer", "0") or "0")
            yield child, layer if own == "0" else own, f"not placed by its block reference ({why})", None
        return
    if kind in ("LWPOLYLINE", "POLYLINE"):
        if kind == "POLYLINE" and not (entity.is_2d_polyline or entity.is_3d_polyline):
            yield entity, layer, "a mesh, not a curve", None
            return
        closed = bool(entity.closed if kind == "LWPOLYLINE" else entity.is_closed)
        for child in entity.virtual_entities():
            yield child, layer, None, entity if closed else None
        return
    yield entity, layer, None, None


def _flat(points: list[Any], factor: float) -> str | None:
    """Why the points are no curve of the sheet's plane (they leave one height), or None."""
    heights = [float(point[2]) * factor if len(point) > 2 else 0.0 for point in points]
    if max(heights) - min(heights) > _JOIN:
        return f"not flat in the sheet's plane (its z runs from {min(heights):.4g} to {max(heights):.4g} mm)"
    return None


def _pieces(entity: Any, layer: str, top: str, handle: str, factor: float) -> list[_Piece] | str:
    """A curve's pieces in millimetres, in the world's XY -- or why it is not read."""
    from ezdxf.math import Vec3

    kind = entity.dxftype()
    if kind == "LINE":
        ends = [entity.dxf.start, entity.dxf.end]
        if ends[0].isclose(ends[1], abs_tol=1e-12):
            return []  # no length: a polyline's vertex written twice (a LINE of none is ``zero_length_entity``)
        return _flat(ends, factor) or [_Piece("line", np.array([[p[0], p[1]] for p in ends], dtype=float) * factor,
                                              handle, layer, top)]
    if kind in ("CIRCLE", "ARC"):
        # drawn in its own plane (the OCS): the sheet's where its extrusion is +Z, the sheet's seen from below
        # (x mirrored) where it is -Z, as a mirrored copy is written
        extrusion = Vec3(entity.dxf.get("extrusion", (0, 0, 1))).normalize()
        if abs(extrusion.z) < 1.0 - 1e-9:
            return f"drawn in a plane off the sheet's (extrusion {extrusion.x:.3g}, {extrusion.y:.3g}, {extrusion.z:.3g})"
        centre = entity.ocs().to_wcs(Vec3(entity.dxf.center))
        start, sweep = 0.0, 2 * math.pi
        if kind == "ARC":
            start = math.radians(float(entity.dxf.start_angle))
            sweep = (math.radians(float(entity.dxf.end_angle)) - start) % (2 * math.pi) or 2 * math.pi
        if extrusion.z < 0:
            start, sweep = math.pi - start, -sweep
        c, r = (float(centre.x) * factor, float(centre.y) * factor), float(entity.dxf.radius) * factor
        return [_Piece("arc", plane.arc_points(c, r, start, sweep), handle, layer, top,
                       abs(sweep) >= 2 * math.pi - 1e-12, c, r, start, sweep)]
    if kind in ("ELLIPSE", "SPLINE"):
        try:
            points = list(entity.flattening(plane.CHORD_MM / max(factor, 1e-12)))
        except Exception as error:  # noqa: BLE001 - a curve ezdxf cannot flatten is said, never passed over
            return f"its curve did not flatten ({type(error).__name__}: {error})"
        if len(points) < 2:
            return "its curve has no length"
        flat = np.array([(p[0], p[1]) for p in points], dtype=float) * factor
        # closed where it comes back to its start (one that never leaves it is a short open curve)
        gap, reach = float(np.linalg.norm(flat[0] - flat[-1])), float(np.linalg.norm(flat - flat[0], axis=1).max())
        return _flat(points, factor) or [_Piece("curve", flat, handle, layer, top, gap <= _JOIN and gap < reach / 2)]
    return "a type this check does not read as a curve"


def _read(document: Any, intent: Any, factor: float) -> dict[str, Any]:
    """The modelspace as a cutter reads it: the cut layers' ``pieces``, the bend layers' ``bend_lines``, the
    ``annotations`` and the entities ``unread`` on cut layers, and each layer's record (``layers``)."""
    found: dict[str, Any] = {"pieces": [], "bend_lines": [], "annotations": [], "unread": [], "layers": {}}
    broken: list[Any] = []   # the closed polylines with a side not read: what is left of each is open
    for entity in document.modelspace():
        top = entity.dxftype()
        handle = str(entity.dxf.handle)
        layer = str(entity.dxf.get("layer", "0") or "0")
        record = found["layers"].setdefault(layer, {"layer": layer, "intent": intent(layer), "entities": 0})
        record["entities"] += 1
        for primitive, on, why, ring in _primitives(entity, layer):
            role, kind = intent(on), primitive.dxftype()
            where = f"layer {on}, {top} #{handle}"
            if why is None and kind in _ANNOTATIONS:
                if role == "cut":
                    at = getattr(primitive.dxf, "insert", None) or getattr(primitive.dxf, "location", None)
                    found["annotations"].append({
                        "kind": kind, "detail": f"{kind} #{handle}" if kind == top else f"{kind} in {top} #{handle}",
                        "layer": on, "location": where,
                        "xyz": [round(float(at[0]) * factor, 4), round(float(at[1]) * factor, 4), 0.0]
                        if at is not None else None})
                continue
            pieces = why or _pieces(primitive, on, top, handle, factor)
            if isinstance(pieces, str):
                if ring is not None:
                    broken.append(ring)
                # a block that did not explode may hold cut curves whatever layer its reference is on
                # (and one entity is said once, however many of its lines are off the plane)
                if (role == "cut" or kind == "INSERT") and not any(
                        (item["handle"], item["layer"], item["why"]) == (handle, on, pieces) for item in found["unread"][-8:]):
                    found["unread"].append({"entity": kind if kind == top else f"{kind} in {top}", "handle": handle,
                                            "layer": on, "why": pieces, "location": where})
            elif role == "cut":
                for piece in pieces:
                    piece.ring = ring
                found["pieces"].extend(pieces)
            elif role == "bend":
                found["bend_lines"].extend(piece for piece in pieces if piece.kind == "line")
    for piece in found["pieces"]:
        if any(piece.ring is ring for ring in broken):
            piece.ring = None
    return found


# --- chaining -----------------------------------------------------------------------------------------------


def _cluster(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Each point's cluster number: points within ``tolerance`` in x and in y (chained) are one. Each point
    is tried against those of its own cell of a ``tolerance`` grid and the eight about it."""
    n = len(points)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cells: dict[tuple[int, int], list[int]] = {}
    grid = np.floor(points / tolerance).astype(np.int64).tolist()
    xs, ys = points[:, 0].tolist(), points[:, 1].tolist()
    for i, (cx, cy) in enumerate(grid):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cells.get((cx + dx, cy + dy), ()):
                    if abs(xs[j] - xs[i]) <= tolerance and abs(ys[j] - ys[i]) <= tolerance:
                        a, b = find(i), find(j)
                        if a != b:
                            parent[b] = a
        cells.setdefault((cx, cy), []).append(i)
    roots = [find(i) for i in range(n)]
    numbers = {root: k for k, root in enumerate(dict.fromkeys(roots))}
    return np.array([numbers[root] for root in roots])


def _ring(sides: list[_Piece]) -> list[tuple[_Piece, bool]]:
    """A closed polyline's sides in order, each turned to run on from the last (an arc of a bulge is drawn
    anticlockwise whichever way the polyline goes)."""
    chain: list[tuple[_Piece, bool]] = []
    for k, piece in enumerate(sides):
        start, end = piece.ends()
        if k == 0:
            ahead = np.array(sides[1 % len(sides)].ends())
            reverse = bool(np.linalg.norm(ahead - start, axis=1).min() < np.linalg.norm(ahead - end, axis=1).min())
        else:
            last, was = chain[-1]
            at = last.points[0] if was else last.points[-1]
            reverse = bool(np.linalg.norm(at - end) < np.linalg.norm(at - start))
        chain.append((piece, reverse))
    return chain


def _chain(pieces: list[_Piece]) -> tuple[list[list[tuple[_Piece, bool]]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The pieces as closed loops (each a list of (piece, reversed)); the open geometry, one item per dangling
    end or branching point, located by layer and handle; and the joints closed across a gap.

    What is drawn closed is a loop as drawn, whatever its sides' lengths: a circle, a closed spline, a full
    ellipse, a closed polyline (its sides in order: ``_ring``). The rest are chained end to end: ends drawn at
    one point (within ``_SAME``) are one, and only the ends left dangling by that are then joined across a gap
    of up to ``_JOIN`` (said: ``joined``). So a side shorter than ``_JOIN`` is a side like any other, never two
    ends "meeting" at one point."""
    loops: list[list[tuple[_Piece, bool]]] = [[(piece, False)] for piece in pieces if piece.closed]
    rings: dict[int, list[_Piece]] = {}
    for piece in pieces:
        if piece.ring is not None and not piece.closed:
            rings.setdefault(id(piece.ring), []).append(piece)
    loops.extend(_ring(sides) for sides in rings.values())
    open_pieces = [piece for piece in pieces if not piece.closed and piece.ring is None]
    problems: list[dict[str, Any]] = []
    joined: list[dict[str, Any]] = []
    if not open_pieces:
        return loops, problems, joined
    ends = np.array([point for piece in open_pieces for point in piece.ends()])
    nodes = _cluster(ends, _SAME)
    # a piece whose two ends are one point among others' is no side of anything: a speck inside a joint
    speck = (nodes[0::2] == nodes[1::2]) & (np.bincount(nodes)[nodes[0::2]] > 2)
    live = np.repeat(~speck, 2)
    dangling = np.nonzero(live & (np.bincount(nodes[live], minlength=nodes.max() + 1)[nodes] == 1))[0]
    if len(dangling) > 1:
        across = _cluster(ends[dangling], _JOIN)
        merged: dict[int, int] = {}
        for index, group in zip(dangling, across):
            nodes[index] = merged.setdefault(int(group), int(nodes[index]))
    incident: dict[int, list[tuple[int, int]]] = {}
    for index in range(len(open_pieces)):
        for side in (0, 1):
            if not speck[index]:
                incident.setdefault(int(nodes[2 * index + side]), []).append((index, side))
    used = [bool(flag) for flag in speck]
    for node, touching in sorted(incident.items()):
        index, side = touching[0]
        piece = open_pieces[index]
        point = ends[2 * index + side]
        if len(touching) == 2:
            gap = float(np.linalg.norm(point - ends[2 * touching[1][0] + touching[1][1]]))
            if gap > _SAME:
                joined.append({"gap_mm": round(gap, 6), "layer": piece.layer,
                               "detail": f"ends {gap:.3g} mm apart at {point[0]:.4g}, {point[1]:.4g}",
                               "handles": sorted({open_pieces[i].handle for i, _ in touching}),
                               "location": _where(piece),
                               "xyz": [round(float(point[0]), 4), round(float(point[1]), 4), 0.0]})
            continue
        kind = "dangling end" if len(touching) == 1 else f"{len(touching)} ends meet"
        problems.append({"kind": "open" if len(touching) % 2 else "branch",
                         "detail": f"{kind} at {point[0]:.4g}, {point[1]:.4g} ({piece.entity} #{piece.handle})",
                         "layer": piece.layer, "handles": sorted({open_pieces[i].handle for i, _ in touching}),
                         "location": _where(piece), "xyz": [round(float(point[0]), 4), round(float(point[1]), 4), 0.0]})
    for first in range(len(open_pieces)):
        if used[first]:
            continue
        head = int(nodes[2 * first])
        chain: list[tuple[_Piece, bool]] = []
        index, reverse, closed = first, False, False
        while True:
            used[index] = True
            chain.append((open_pieces[index], reverse))
            exit_node = int(nodes[2 * index + (0 if reverse else 1)])
            if exit_node == head:
                closed = len(incident.get(head, [])) == 2
                break
            touching = incident.get(exit_node, [])
            if len(touching) != 2:
                break
            following = [(i, side) for i, side in touching if (i, side) != (index, 0 if reverse else 1)]
            if not following or used[following[0][0]]:
                break
            index, side = following[0]
            reverse = side == 1
        if closed:
            loops.append(chain)
    return loops, problems, joined


def _loop(chain: list[tuple[_Piece, bool]]) -> plane.Loop:
    points, straight, sources = [], [], []
    for piece, reverse in chain:
        pts = piece.points[::-1] if reverse else piece.points
        if piece.closed and len(chain) == 1:
            pts = pts[:-1] if np.linalg.norm(pts[0] - pts[-1]) <= _JOIN else pts
            points.extend(pts)
            straight.extend([piece.kind == "line"] * len(pts))
            sources.extend([piece] * len(pts))
            continue
        for i in range(len(pts) - 1):
            points.append(pts[i])
            straight.append(piece.kind == "line")
            sources.append(piece)
    loop = plane.Loop(np.array(points), np.array(straight), sources,
                      label=sorted({piece.handle for piece, _ in chain}))
    if len(chain) == 1 and chain[0][0].kind == "arc" and chain[0][0].closed:
        piece = chain[0][0]
        loop.circle = (piece.centre[0], piece.centre[1], piece.radius)
    return loop


# --- overlaps -----------------------------------------------------------------------------------------------


def _overlaps(pieces: list[_Piece], tolerance: float = _SAME) -> list[dict[str, Any]]:
    """Pieces lying on one another over a length: collinear lines overlapping, concentric arcs of one radius
    overlapping in angle, a line along a polyline's straight segment. An exact copy is ``_unique``'s."""
    found = []
    lines = [p for p in pieces if p.kind == "line" and not p.copy]
    arcs = [p for p in pieces if p.kind == "arc" and not p.copy]
    for group in _collinear(lines, tolerance):
        a = np.array([lines[i].points[0] for i in group])
        b = np.array([lines[i].points[-1] for i in group])
        d = b - a
        length = np.linalg.norm(d, axis=1)
        u = d / np.maximum(length, 1e-300)[:, None]
        for i in range(len(group)):
            # lines j > i parallel to i and on its line
            cross_dir = np.abs(u[i + 1:, 0] * u[i, 1] - u[i + 1:, 1] * u[i, 0])
            rel_a = a[i + 1:] - a[i]
            off_a = np.abs(rel_a[:, 0] * u[i, 1] - rel_a[:, 1] * u[i, 0])
            rel_b = b[i + 1:] - a[i]
            off_b = np.abs(rel_b[:, 0] * u[i, 1] - rel_b[:, 1] * u[i, 0])
            along = np.sort(np.column_stack([rel_a @ u[i], rel_b @ u[i]]), axis=1)
            start = np.maximum(along[:, 0], 0.0)
            overlap = np.minimum(along[:, 1], length[i]) - start
            for k in np.nonzero((cross_dir < 1e-7) & (off_a < tolerance) & (off_b < tolerance) & (overlap > tolerance))[0]:
                found.append(_overlap_item(lines[group[i]], lines[group[i + 1 + int(k)]], float(overlap[k]),
                                           a[i] + u[i] * float(start[k] + overlap[k] / 2)))
    if arcs:
        centres = np.array([p.centre for p in arcs])
        radii = np.array([p.radius for p in arcs])
        for i, first in enumerate(arcs):
            same = np.nonzero((np.abs(centres[i + 1:] - centres[i]) <= tolerance).all(axis=1)
                              & (np.abs(radii[i + 1:] - radii[i]) <= tolerance))[0]
            for k in same:
                second = arcs[i + 1 + int(k)]
                overlap = _angular_overlap(first, second) * first.radius
                if overlap > tolerance:
                    found.append(_overlap_item(first, second, overlap, first.points[len(first.points) // 2]))
    return found


def _collinear(lines: list[_Piece], tolerance: float) -> list[list[int]]:
    """The lines grouped by the line they lie on, in the order given: each group's are within 1e-7 rad of one
    direction and ``tolerance`` of one line (chained, so a group may hold a little more: ``_overlaps`` tests
    each pair). Only lines of one group can lie on one another."""
    if len(lines) < 2:
        return []
    a = np.array([p.points[0] for p in lines])
    d = np.array([p.points[-1] for p in lines]) - a
    theta = np.arctan2(d[:, 1], d[:, 0]) % math.pi          # a line's direction, either way along it
    theta = np.where(theta > math.pi - 1e-7, theta - math.pi, theta)
    offset = a[:, 1] * np.cos(theta) - a[:, 0] * np.sin(theta)   # how far the line passes from the origin
    slack = tolerance + 2e-7 * float(np.abs(a).max() + np.abs(d).max())
    groups: list[list[int]] = []
    order = np.argsort(theta, kind="stable")
    for run in np.split(order, np.nonzero(np.diff(theta[order]) > 1e-7)[0] + 1):
        run = run[np.argsort(offset[run], kind="stable")]
        for same in np.split(run, np.nonzero(np.diff(offset[run]) > slack)[0] + 1):
            if len(same) > 1:
                groups.append(sorted(int(i) for i in same))
    return sorted(groups)


def _unique(pieces: list[_Piece]) -> tuple[list[_Piece], list[dict[str, Any]]]:
    """The pieces less exact copies of another entity's (the same kind through the same points, either way; a
    whole circle from any start), and each copy as an overlap, one per pair of entities: a line, an arc, a
    spline or an ellipse drawn twice is cut twice. A closed polyline keeps every side unless all of it is a
    copy (two squares that share a side are two squares, the side cut twice), and it is the loose line along
    one of its sides that is the copy, whichever was drawn first."""
    seen: dict[tuple[Any, ...], _Piece] = {}
    copies: dict[tuple[str, str], dict[str, Any]] = {}
    for piece in sorted(pieces, key=lambda piece: piece.ring is None):
        if piece.closed and piece.kind == "arc":
            key: tuple[Any, ...] = ("circle", *np.round(np.array([*piece.centre, piece.radius]) / (10 * _SAME)).astype(np.int64).tolist())
        else:
            grid = [tuple(point) for point in np.round(piece.points / (10 * _SAME)).astype(np.int64).tolist()]
            key = (piece.kind, *min(grid, grid[::-1]))
        first = seen.setdefault(key, piece)
        if first.handle == piece.handle:
            continue  # one entity doubling back on itself is a zero-area loop, or its own overlap
        piece.copy = True
        length = float(np.linalg.norm(np.diff(piece.points, axis=0), axis=1).sum())
        item = copies.setdefault((first.handle, piece.handle), _overlap_item(first, piece, 0.0, piece.points[len(piece.points) // 2]))
        item.update(kind="duplicate", length_mm=round(item["length_mm"] + length, 4))
        item["detail"] = (f"{piece.entity} #{piece.handle} repeats {first.entity} #{first.handle} for "
                          f"{item['length_mm']:.4g} mm")
    whole = {id(piece.ring) for piece in pieces if piece.ring is not None and not piece.copy}
    return [piece for piece in pieces if not piece.copy or id(piece.ring) in whole], list(copies.values())


def _unexplained(problems: list[dict[str, Any]], overlaps: list[dict[str, Any]],
                 pieces: list[_Piece]) -> list[dict[str, Any]]:
    """The open-geometry items an overlap does not explain: a copy of a curve laid on another meets it at
    three ends (or leaves a dangling end on it), which is the overlap's one defect, reported there."""
    if not overlaps:
        return problems
    by_handle: dict[str, list[_Piece]] = {}
    for piece in pieces:
        by_handle.setdefault(piece.handle, []).append(piece)
    kept = []
    for problem in problems:
        point = np.array(problem["xyz"][:2], dtype=float)
        handles = set(problem.get("handles") or ())
        explained = False
        for overlap in overlaps:
            pair = set(overlap["handles"])
            if not handles & pair:
                continue
            others = pair - handles or pair
            if any(_off(point, piece) <= _JOIN for handle in others for piece in by_handle.get(handle, ())):
                explained = True
                break
        if not explained:
            kept.append(problem)
    return kept


def _off(point: np.ndarray, piece: _Piece) -> float:
    """How far a point lies from a piece's polyline."""
    a, b = piece.points[:-1], piece.points[1:]
    d = b - a
    length = np.maximum((d * d).sum(axis=1), 1e-300)
    s = np.clip(((point - a) * d).sum(axis=1) / length, 0.0, 1.0)
    return float(np.min(np.linalg.norm(a + s[:, None] * d - point, axis=1))) if len(a) else math.inf


def _interval(piece: _Piece) -> tuple[float, float]:
    start = piece.start if piece.sweep >= 0 else piece.start + piece.sweep
    return start % (2 * math.pi), abs(piece.sweep)


def _angular_overlap(first: _Piece, second: _Piece) -> float:
    s1, w1 = _interval(first)
    s2, w2 = _interval(second)
    best = 0.0
    for shift in (-2 * math.pi, 0.0, 2 * math.pi):
        lo, hi = max(s1, s2 + shift), min(s1 + w1, s2 + shift + w2)
        best += max(0.0, hi - lo)
    return min(best, w1, w2)


def _overlap_item(first: _Piece, second: _Piece, length: float, at: np.ndarray) -> dict[str, Any]:
    same = first.handle == second.handle
    return {"kind": "partial" if not same else "self", "length_mm": round(float(length), 4),
            "detail": f"{first.entity} #{first.handle} and {second.entity} #{second.handle} overlap for "
                      f"{length:.4g} mm",
            "handles": sorted({first.handle, second.handle}), "layer": first.layer, "location": _where(first),
            "xyz": [round(float(at[0]), 4), round(float(at[1]), 4), 0.0]}


def _short_runs(loop: plane.Loop, most_turn_deg: float = 20.0, least_count: int = 8) -> list[dict[str, Any]]:
    """Runs of short straight segments turning a little, the same way, at each joint: a curve as chords. One
    item for the contour, at its first run, counting them all: a traced outline is one curve drawn so."""
    pts = loop.points
    n = len(pts)
    if n < least_count + 2 or not loop.straight.any():
        return []
    seg = np.roll(pts, -1, axis=0) - pts
    length = np.linalg.norm(seg, axis=1)
    lo, hi = loop.bbox()
    short = max(0.05, min(5.0, 0.1 * float(np.linalg.norm(hi - lo))))
    direction = seg / np.maximum(length, 1e-300)[:, None]
    nxt = np.roll(direction, -1, axis=0)
    turn = np.degrees(np.arctan2(direction[:, 0] * nxt[:, 1] - direction[:, 1] * nxt[:, 0],
                                 (direction * nxt).sum(axis=1)))
    chord = loop.straight & (length < short) & np.array([getattr(s, "kind", "") == "line" for s in loop.source])
    found = []
    i = 0
    while i < n:
        if not chord[i]:
            i += 1
            continue
        j = i
        sign = 0.0
        while j + 1 < n and chord[j + 1] and 0.05 < abs(turn[j]) < most_turn_deg and \
                (sign == 0.0 or np.sign(turn[j]) == sign):
            sign = np.sign(turn[j])
            j += 1
        count = j - i + 1
        if count >= least_count and float(length[i:j + 1].sum()) > short:  # shorter, and it is a speck, no curve
            source = loop.source[i]
            found.append({"segments": int(count), "length_mm": round(float(length[i:j + 1].sum()), 4),
                          "detail": f"{count} lines under {short:.3g} mm each", "layer": getattr(source, "layer", None),
                          "handles": sorted({getattr(loop.source[k], "handle", "") for k in range(i, j + 1)})[:12],
                          "location": _where(source) if source is not None else None,
                          "xyz": [round(float(pts[i][0]), 4), round(float(pts[i][1]), 4), 0.0]})
        i = j + 1
    if len(found) > 1:
        lines, total = sum(item["segments"] for item in found), sum(item["length_mm"] for item in found)
        found[0].update(segments=int(lines), length_mm=round(float(total), 4), runs=len(found),
                        detail=f"{len(found)} runs, {lines} lines under {short:.3g} mm each")
    return found[:1]


# --- bend lines ---------------------------------------------------------------------------------------------


def _line(piece: _Piece) -> plane.Loop:
    """A bend line as a loop of no area, for the plane's distances and rays."""
    return plane.Loop(piece.points[[0, -1]], np.ones(2, dtype=bool))


def _ends_on(line: _Piece, loop: plane.Loop) -> bool:
    """Whether a bend line ends on a cutout's edge and runs on away from it: the bend ends there (a window
    across the bend line, a relief at its end), so the cutout is no hole beside the bend."""
    a, b = line.points[0], line.points[-1]
    length = float(np.linalg.norm(b - a))
    if length <= 4 * _JOIN:
        return False
    for end, other in ((a, b), (b, a)):
        on_edge = plane.distance(loop, plane.Loop(np.array([end, end]), np.ones(2, dtype=bool)))[0] <= _JOIN
        if on_edge and not plane.inside((end + (other - end) * (2 * _JOIN / length))[None], [loop])[0]:
            return True
    return False


def _window(line: _Piece, loop: plane.Loop, thickness: float | None) -> bool:
    """Whether a cutout the bend line meets reaches ``WINDOW_T`` thicknesses to both sides of it: a window
    through the bend, drawn across or not. With no thickness given nothing says so."""
    if thickness is None:
        return False
    a, b = line.points[0], line.points[-1]
    along = (b - a) / max(float(np.linalg.norm(b - a)), 1e-300)
    normal = np.array([-along[1], along[0]])
    if loop.circle is not None:
        offset = float((np.array(loop.circle[:2]) - a) @ normal)
        reach = (loop.circle[2] + offset, loop.circle[2] - offset)
    else:
        across = (loop.points - a) @ normal
        reach = (float(across.max()), -float(across.min()))
    return min(reach) >= WINDOW_T * float(thickness) * (1.0 - 1e-9)


def _flanges(line: _Piece, outline: plane.Loop, others: list[_Piece]) -> list[dict[str, Any]]:
    """A bend line's flange either side of it: how far the outline (or the next bend line) lies from the
    line, square to it, the least along the line and the length half of it reaches, read at 11 stations on
    the material."""
    a, b = line.points[0], line.points[-1]
    length = float(np.linalg.norm(b - a))
    if length <= 1e-9:
        return []
    along = (b - a) / length
    normal = np.array([-along[1], along[0]])
    stations = a[None] + (length * (0.04 + 0.92 * np.linspace(0.0, 1.0, 11)))[:, None] * along[None]
    on = plane.inside(stations, [outline])
    barriers = [outline] + [_line(other) for other in others if other is not line]
    items = []
    for side, sign in (("left", 1.0), ("right", -1.0)):
        hit, _, _ = plane.cast(stations, np.repeat((sign * normal)[None], len(stations), axis=0), barriers, skip=1e-7)
        reach = hit[on & np.isfinite(hit)]
        if not len(reach):
            continue
        least = float(reach.min())
        at = (a + b) / 2 + sign * normal * least / 2
        items.append({"bend": _where(line), "side": side, "length_centerline_mm": round(least, 4),
                      "length_centerline_half_mm": round(float(np.median(reach)), 4), "stations": int(len(reach)),
                      "convention": "from the bend layer's line, read as the bend's centre line, to the outline",
                      "location": _where(line), "xyz": [round(float(at[0]), 4), round(float(at[1]), 4), 0.0]})
    return items


# --- the report ---------------------------------------------------------------------------------------------


def _layer_intents(document: Any) -> tuple[dict[str, str], Any]:
    from cad.engine.export.dxf import layer_intent, layer_table_intents

    declared = layer_table_intents(document)
    return declared, lambda layer: declared.get(layer) or layer_intent(layer)


def _units(name: str, code: int, given: str | None) -> tuple[str, float, list[dict[str, Any]]]:
    """The unit the file is read in and its length in millimetres -- the one ``given`` (``--units``), else the
    one it declares (``$INSUNITS``) -- with what a shop should know of it: a file that declares none, a
    ``--units`` over the file's own. ``Unmeasured`` where neither says: no length would be a length."""
    declared = UNITS.get(code)
    if given is None:
        if declared is None:
            why = "is not set" if code == 0 else "names no length a cutter reads"
            raise Unmeasured("units_not_set", f"{name} declares no length unit ($INSUNITS {code} {why}), so nothing "
                                              "was measured: give --units (mm, cm, m, in or ft), the unit it was "
                                              "drawn in")
        return *declared, []
    factor = next(length for unit, length in UNITS.values() if unit == given)
    if declared is None:
        said = (f"the file declares no length unit ($INSUNITS {code}), and is read with --units {given}: a shop's "
                "software has to be told too")
    elif declared[0] != given:
        said = (f"the file declares {declared[0]} ($INSUNITS {code}), and is read with --units {given}: a shop's "
                "software reads the file's own")
    else:
        return given, factor, []
    return given, factor, [{"severity": "warning", "code": "units_not_set" if declared is None else "units_differ",
                            "message": said, "location": None,
                            "hint": "save the file with its unit set ($INSUNITS; R12 holds none: save a later "
                                    "version), or tell the shop the unit"}]


def _units_suspect(unit: str, extents: Any, options: dict[str, Any]) -> str | None:
    """Why the unit makes the drawing implausible, or None. A cut file's own two mistakes first, each read the
    other way: in millimetres a drawing under an inch; in inches one larger than the sheet (the one given,
    else the standard sheet). Then what every source is held to (``_common.units_doubt``): under a
    millimetre or over ten metres across. The rules still run in the unit the file is read in."""
    from cad._internal.dfm import _common
    from cad._internal.dfm import sheet as rules_side

    if extents is None or not len(extents):
        return None
    long, short = float(max(extents)), float(min(extents))
    if long <= 0:
        return None
    sheet = rules_side.sheet_size(options.get("sheet_size")) or rules_side.DEFAULT_SHEET
    if unit == "mm" and long < 25.4:
        return (f"read as millimetres the part is {long:.4g} x {short:.4g} mm; read as inches it is "
                f"{long * 25.4:.4g} x {short * 25.4:.4g} mm: if it was drawn in inches give --units in (and set "
                "$INSUNITS to 1)")
    if unit == "in" and (long > sheet[0] or short > sheet[1]):
        return (f"read as inches the part is {long:.4g} x {short:.4g} mm, larger than the {sheet[0]:.4g} x "
                f"{sheet[1]:.4g} mm sheet; read as millimetres it is {long / 25.4:.4g} x {short / 25.4:.4g} mm: if "
                "it was drawn in millimetres give --units mm (and set $INSUNITS to 4)")
    doubt = _common.units_doubt(math.hypot(long, short), f"the file is read in {unit} and its cut geometry is")
    return doubt["note"] if doubt["units_suspect"] else None


def _nothing_to_cut(name: str, read: dict[str, Any]) -> Unmeasured:
    """The file held no cut curve: what it did hold, so the reader knows why nothing was measured."""
    entities = sum(record["entities"] for record in read["layers"].values())
    said = []
    if not entities:
        said.append("its modelspace is empty")
    else:
        layers = ", ".join(f"{record['layer']} ({record['intent']}, {record['entities']})"
                           for record in sorted(read["layers"].values(), key=lambda r: r["layer"])[:6])
        said.append(f"its {entities} entit{'y' if entities == 1 else 'ies'} lie on layer(s) {layers}")
    if read["unread"]:
        first = read["unread"][0]
        more = f" and {len(read['unread']) - 1} more" if len(read["unread"]) > 1 else ""
        said.append(f"not read: {first['entity']} #{first['handle']} on layer {first['layer']}, {first['why']}{more}")
    if read["annotations"]:
        said.append(f"{len(read['annotations'])} annotation(s) on cut layers cut nothing")
    return Unmeasured("no_cut_geometry", f"{name} holds no cut geometry -- no line, arc, circle, polyline, ellipse "
                                         f"or spline was read on a cut layer -- so nothing was checked: "
                                         + "; ".join(said))


def measure(document_type: str, source: Any, process: str, options: dict[str, Any], candidates: bool) -> dict[str, Any]:
    """The cut-file report of the DXF ``source``: facts alone."""
    import ezdxf

    from cad.build123d._dfm_sheet import _outline_features
    from cad.engine.export.dxf import document_is_drawing, validate_drawing_document

    path = Path(str(source)).expanduser().resolve()
    try:
        document = ezdxf.readfile(str(path))
    except Exception as error:  # noqa: BLE001 - a file that does not read is the check's answer
        raise Unmeasured("document_unreadable", f"failed to read {path.name}: {error}") from None
    try:
        code = int(document.header.get("$INSUNITS", 0))
    except (TypeError, ValueError):
        code = 0
    unit, factor, findings = _units(path.name, code, options.get("units"))
    # the drawing check that bears on a cut: its zero-length entities. The rest are this check's own, read
    # exactly: open contours, curves cut twice (a duplicate is an overlap), and a file with dimensions in it is
    # measured as any other
    findings += [{"severity": found.severity, "code": found.code, "message": found.message, "location": None,
                  "hint": None} for found in validate_drawing_document(document) if found.code == "zero_length_entity"]
    _, intent = _layer_intents(document)
    is_drawing, evidence = document_is_drawing(document)
    read = _read(document, intent, factor)
    pieces: list[_Piece] = read["pieces"]
    layers: dict[str, dict[str, Any]] = read["layers"]
    if not pieces:
        raise _nothing_to_cut(path.name, read)
    # a bend line drawn twice is one bend
    bend_lines: list[_Piece] = _unique(read["bend_lines"])[0]
    report: dict[str, Any] = {"source": {"type": "dxf", "measured_as": "cut file", "document": path.name}}
    families: dict[str, list[dict[str, Any]]] = {name: [] for name in (
        "parts", "holes", "hole_spacing", "hole_to_bend", "flanges", "notches", "tabs", "webs", "gaps",
        "open_geometry", "joined_gaps", "overlaps", "self_intersections", "contour_crossings", "zero_area_loops",
        "annotations", "floating_interiors", "short_line_runs")}
    families["annotations"] = read["annotations"]
    failed: dict[str, str] = {}   # a family not measured, and why
    if read["unread"]:
        said = "; ".join(f"{item['entity']} #{item['handle']} on layer {item['layer']}: {item['why']}"
                         for item in read["unread"][:6])
        more = f"; and {len(read['unread']) - 6} more" if len(read["unread"]) > 6 else ""
        failed["cut_entities"] = (f"{len(read['unread'])} entit{'y' if len(read['unread']) == 1 else 'ies'} on a cut "
                                  f"layer not read, so not in any contour ({said}{more})")
    cut_layers = sorted({piece.layer for piece in pieces})
    all_points = np.vstack([piece.points for piece in pieces])
    extents = np.ptp(all_points, axis=0)
    report["cut_file"] = {
        "insunits": code, "unit": unit, "unit_from": "--units" if options.get("units") else "$INSUNITS",
        "mm_per_unit": factor,
        "extents_mm": [round(float(v), 4) for v in extents],
        "extents_min_mm": [round(float(v), 4) for v in all_points.min(axis=0)],
        "layers": sorted(layers.values(), key=lambda r: r["layer"]), "cut_layers": cut_layers,
        "cut_layer_count": len(cut_layers), "piece_count": len(pieces), "bend_line_count": len(bend_lines),
        "unread": read["unread"][:ITEM_CAP], "unread_count": len(read["unread"]),
        "is_drawing": bool(is_drawing), "drawing_evidence": evidence or None}
    # What a flat drawing does not hold: its rules judge nothing here, and the result says so (``rules``'
    # ``not_measured``); the bent part's check judges them.
    report["not_measured"] = {family: "a cut file is flat: it holds no bend, relief, hem or thickness to read"
                              for family in ("bends", "reliefs", "hems", "not_sheet")}
    report["scale"] = {"units_suspect": False, "note": f"lengths in {unit}, read as mm"}
    # an exact copy of a curve is cut twice (an overlap) but bounds nothing: the contours are chained without
    # it, so the outline it doubles is still the part's
    once, copies = _unique(pieces)
    chains, problems, families["joined_gaps"] = _chain(once)
    families["overlaps"] = copies + _overlaps(once)
    families["open_geometry"] = _unexplained(problems, families["overlaps"], pieces)
    loops: list[plane.Loop] = []
    for chain in chains:
        loop = _loop(chain)
        if len(loop.points) < 2:
            continue
        size = loop.length()
        crossing = plane.self_crossings(loop)
        if crossing is None:
            failed["self_intersections"] = (f"a contour of {len(loop.points)} segments ({_where(loop.source[0])}) has "
                                            f"over {plane.SELF_CROSSING_PAIRS} pairs of segments that may cross: "
                                            "past what this check seeks crossings in")
        elif crossing:
            source = loop.source[0]
            for point in crossing[:4]:
                families["self_intersections"].append({
                    "detail": f"crosses itself at {point[0]:.4g}, {point[1]:.4g}", "handles": loop.label,
                    "layer": getattr(source, "layer", None), "location": _where(source),
                    "xyz": [round(point[0], 4), round(point[1], 4), 0.0]})
            continue
        if abs(plane.area(loop)) <= max(1e-6, 1e-6 * size * size) or len(loop.points) < 3:
            first = chain[0][0]
            families["zero_area_loops"].append({"detail": f"{len(chain)} piece(s), {size:.4g} mm long, no area",
                                                "layer": first.layer, "handles": loop.label,
                                                "location": _where(first),
                                                "xyz": [round(float(loop.points[0][0]), 4),
                                                        round(float(loop.points[0][1]), 4), 0.0]})
            continue
        loops.append(loop)
    report["cut_file"]["contour_count"] = len(loops)
    if not loops:
        failed["parts"] = "no closed contour on a cut layer: no part to measure"
    handles = [loop.label for loop in loops]
    for loop in loops:
        families["short_line_runs"].extend(_short_runs(loop))
    lows = np.array([loop.bbox()[0] for loop in loops]).reshape(-1, 2)
    highs = np.array([loop.bbox()[1] for loop in loops]).reshape(-1, 2)
    for i in range(len(loops)):
        touching = np.nonzero((lows[i + 1:] <= highs[i] + 1e-9).all(axis=1) & (highs[i + 1:] >= lows[i] - 1e-9).all(axis=1))[0]
        for j in touching + i + 1:
            met = [("crosses", point) for point in plane.crossings(loops[i], loops[j], _SAME)[:2]]
            if not met:
                # two that meet without crossing (a hole tangent to the edge, two parts corner to corner) leave
                # no material, or no gap, between them
                gap, point, _ = plane.distance(loops[i], loops[j])
                met = [("touches", point)] if gap <= _SAME else []
            for verb, point in met:
                source = loops[i].source[0]
                families["contour_crossings"].append({
                    "kind": verb, "detail": f"#{','.join(handles[i])} {verb} #{','.join(handles[j])} at "
                                            f"{point[0]:.4g}, {point[1]:.4g}", "handles": handles[i] + handles[j],
                    "layer": getattr(source, "layer", None), "location": _where(source),
                    "xyz": [round(float(point[0]), 4), round(float(point[1]), 4), 0.0]})
    depth, parent = plane.nest(loops, _SAME)
    thickness = options.get("thickness")
    outlines = [i for i, level in enumerate(depth) if level % 2 == 0]
    held: dict[int, list[int]] = {}   # each outline's holes: the loops it holds directly
    for i, level in enumerate(depth):
        if level % 2 == 1 and parent[i] >= 0:
            held.setdefault(parent[i], []).append(i)
        if level >= 2 and level % 2 == 0:
            source = loops[i].source[0]
            families["floating_interiors"].append({
                "detail": f"#{','.join(handles[i])} lies inside a hole", "layer": getattr(source, "layer", None),
                "location": _where(source), "xyz": [round(float(v), 4) for v in (*loops[i].centroid(), 0.0)]})

    def locate(point: Any) -> tuple[str, list[float]]:
        """The entity nearest a point of the plane: the loops tried nearest box first."""
        p = np.asarray(point, dtype=float).reshape(2)
        gap = np.linalg.norm(np.maximum(0.0, np.maximum(lows - p, p - highs)), axis=1)
        best, where = math.inf, None
        for j in np.argsort(gap):
            if gap[j] >= best:
                break
            d, _ = plane._point_segment(p[None], loops[j].a, loops[j].b)
            k = int(np.argmin(d[0]))
            if d[0, k] < best:
                best, where = float(d[0, k]), loops[j].source[k]
        return (_where(where) if where is not None else "cut file"), [round(float(p[0]), 4), round(float(p[1]), 4), 0.0]

    middles = np.array([(line.points[0] + line.points[-1]) / 2 for line in bend_lines]).reshape(-1, 2)
    for o in outlines:
        mine = held.get(o, [])
        circle = loops[o].circle
        long, short, _ = (2 * circle[2], 2 * circle[2], 0.0) if circle else plane.min_rectangle(loops[o].points)
        source = loops[o].source[0]
        # the part's bend lines: those whose middle lies on it
        bends = [bend_lines[int(k)] for k in np.nonzero(plane.inside(middles, [loops[o]]))[0]] if len(middles) else []
        families["parts"].append({
            "name": f"contour #{','.join(handles[o][:3])}", "thickness_mm": thickness,
            "flat_length_mm": round(long, 4), "flat_width_mm": round(short, 4),
            "flat_area_mm2": round(abs(plane.area(loops[o])) - sum(abs(plane.area(loops[h])) for h in mine), 3),
            "hole_count": len(mine), "is_sheet": True, "bent": bool(bends), "bend_line_count": len(bends),
            "floating": depth[o] >= 2, "location": _where(source),
            "xyz": [round(float(v), 4) for v in (*loops[o].centroid(), 0.0)]})
        region = [loops[o]] + [loops[h] for h in mine]
        for loop in region:
            loop.label = "outer" if loop is loops[o] else "hole"
        features = _outline_features(None, region, thickness, locate)
        for name in ("notches", "tabs", "webs", "gaps"):
            families[name].extend(features[name])
        for line in bends:
            families["flanges"].extend(_flanges(line, loops[o], bends))
        records = []
        for h in mine:
            loop = loops[h]
            if loop.circle is not None:
                kind, size, length = "round", 2.0 * loop.circle[2], 2.0 * loop.circle[2]
            else:
                size, length, _ = plane.feret(loop.points)
                kind = "slot" if length > 1.2 * size and not loop.straight.all() else "cutout"
            edge = plane.distance(loop, loops[o])[0]
            source = loop.source[0]
            record = {"kind": kind, "size_mm": round(size, 4), "diameter_mm": round(size, 4) if kind == "round" else None,
                      "length_mm": round(length, 4), "edge_distance_mm": round(edge, 4), "in_bend": False,
                      "countersunk": False, "location": _where(source),
                      "xyz": [round(float(v), 4) for v in (*loop.centroid(), 0.0)]}
            records.append(record)
            families["holes"].append(record)
            # the nearest bend line that does not end at this cutout: one that ends on its edge (the cutout is the
            # bend's end, a window or a relief), or is drawn across a cutout wide enough to be a window
            near = [(plane.distance(loop, _line(line))[0], line) for line in bends]
            near = [(d, line) for d, line in near
                    if d > _JOIN or not (_ends_on(line, loop) or _window(line, loop, thickness))]
            if near:
                d, line = min(near, key=lambda found: found[0])
                record["in_bend"] = d <= _SAME
                families["hole_to_bend"].append({"bend": _where(line), "distance_centerline_mm": round(d, 4),
                                                 "location": record["location"], "xyz": record["xyz"],
                                                 "convention": "to the bend layer's line, read as the bend's "
                                                               "centre line"})
        pairs: dict[tuple[int, int], dict] = {}
        for k, found in enumerate(plane.nearest([loops[h] for h in mine])):
            if found is not None and "round" in (records[k]["kind"], records[found[1]]["kind"]):
                d, g = found  # (the bar between two cutouts is a web: ``_outline_features``)
                pairs.setdefault((min(k, g), max(k, g)), {
                    "distance_mm": round(d, 4), "location": records[k]["location"],
                    "other": records[g]["location"], "xyz": records[k]["xyz"]})
        families["hole_spacing"].extend(pairs.values())
    suspect = _units_suspect(unit, extents, options)
    if suspect:
        report["scale"].update(units_suspect=True, note=suspect)
    sort_keys = {"holes": "size_mm", "hole_spacing": "distance_mm", "hole_to_bend": "distance_centerline_mm",
                 "flanges": "length_centerline_mm", "notches": "width_mm", "tabs": "width_mm", "webs": "width_mm",
                 "gaps": "width_mm", "joined_gaps": "gap_mm"}
    for name, items in families.items():
        key = sort_keys.get(name)
        if key:
            items = sorted(items, key=lambda item: (item.get(key) is None, item.get(key) or 0.0),
                           reverse=name == "joined_gaps")
        report[name] = {"items": items[:ITEM_CAP], "count": len(items)}
    # what was not measured is said by its family (``_common.partial_findings``), never passed
    for name, why in failed.items():
        report[name] = {"error": why}
    report["findings"] = findings
    report["partial"], report["partial_sections"] = bool(failed), list(failed)
    return report
