"""A sheet's cut file (a DXF), checked with ezdxf, build123d's own DXF library (``cad._internal.dfm.sheet``).

The file is read as a cutter reads it: its units (``$INSUNITS``, never assumed: an unset or unknown code is
reported and every size rule is withheld), each layer's intent by its name and its layer table
(``cad.engine.export.dxf.layer_intent``: cut, bend, engrave or reference), and the drawing checks every
export runs (``validate_drawing_document``: units, duplicates, zero-length entities, an empty or
dimensioned drawing), whose findings are kept.

The cut layers' curves are split into pieces (a line, an arc, a sampled spline or ellipse; a polyline's
segments and bulges each a piece) and chained end to end into closed contours. What does not close is open
geometry, located by layer, entity handle and the dangling end. Pieces lying on one another (collinear
lines overlapping, concentric arcs of one radius overlapping, a line along a polyline's segment) are cut
twice; a contour crossing itself or another leaves a sliver; a loop enclosing no area is a doubled-back
line; a run of many short lines turning a little at a time is a curve drawn as chords; text, dimensions,
hatches and points on a cut layer do not cut.

The closed contours are nested (an outline, its holes, an island in a hole: a piece that falls out) and
measured in the plane with ``cad._internal.meshops_sheet``, as the flat pattern of a bent part is
(``_dfm_sheet``): each part's size, holes (diameter, slot width), hole-to-edge and hole-to-hole distances
(edge to edge), notches, tabs, the narrowest web of material and the narrowest gap; a bend layer's lines
give each hole's distance to the bend line (the bend's centre line).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from cad._internal import meshops_sheet as plane
from cad._internal.dfm import Unmeasured

__all__ = ["measure"]

#: $INSUNITS codes and their length in millimetres (the others a cutter does not read as lengths).
UNITS = {1: ("in", 25.4), 2: ("ft", 304.8), 4: ("mm", 1.0), 5: ("cm", 10.0), 6: ("m", 1000.0),
         8: ("microinch", 25.4e-6), 9: ("mil", 0.0254), 10: ("yd", 914.4), 13: ("micron", 1e-3),
         14: ("dm", 100.0)}
_ANNOTATIONS = frozenset({"TEXT", "MTEXT", "DIMENSION", "ARC_DIMENSION", "LEADER", "MULTILEADER", "HATCH",
                          "MLEADER", "INSERT", "ATTRIB", "ATTDEF", "IMAGE", "WIPEOUT", "TOLERANCE", "POINT",
                          "SOLID", "TRACE", "MESH", "3DFACE", "REGION", "VIEWPORT"})
_CURVES = frozenset({"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "ELLIPSE", "SPLINE"})
ITEM_CAP = 300
_JOIN = 1e-4          # mm: two ends this close are one point
_CHAIN_DEGREE_FLAG = 2


@dataclass
class _Piece:
    kind: str                 # "line", "arc" or "curve"
    points: np.ndarray        # (n, 2) in mm, n >= 2
    handle: str
    layer: str
    entity: str
    closed: bool = False      # a whole circle, a closed polyline, a closed spline or a full ellipse
    centre: tuple[float, float] | None = None
    radius: float | None = None
    start: float = 0.0        # an arc's start angle and signed sweep, radians
    sweep: float = 0.0

    def ends(self) -> tuple[np.ndarray, np.ndarray]:
        return self.points[0], self.points[-1]


def _where(piece: _Piece, point: Any = None) -> str:
    return f"layer {piece.layer}, {piece.entity} #{piece.handle}"


def _arc_piece(centre: Any, radius: float, start: float, sweep: float, handle: str, layer: str, entity: str,
               factor: float, closed: bool = False) -> _Piece:
    c = (float(centre[0]) * factor, float(centre[1]) * factor)
    r = float(radius) * factor
    points = plane.arc_points(c, r, start, sweep)
    return _Piece("arc", points, handle, layer, entity, closed, c, r, start, sweep)


def _pieces(entity: Any, layer: str, factor: float) -> list[_Piece]:
    """An entity's pieces, in millimetres."""
    kind = entity.dxftype()
    handle = str(entity.dxf.handle)
    if kind == "LINE":
        s, e = entity.dxf.start, entity.dxf.end
        return [_Piece("line", np.array([[s[0], s[1]], [e[0], e[1]]], dtype=float) * factor, handle, layer, kind)]
    if kind == "CIRCLE":
        return [_arc_piece(entity.dxf.center, entity.dxf.radius, 0.0, 2 * math.pi, handle, layer, kind, factor,
                           closed=True)]
    if kind == "ARC":
        start = math.radians(float(entity.dxf.start_angle))
        end = math.radians(float(entity.dxf.end_angle))
        sweep = (end - start) % (2 * math.pi) or 2 * math.pi
        return [_arc_piece(entity.dxf.center, entity.dxf.radius, start, sweep, handle, layer, kind, factor,
                           closed=sweep >= 2 * math.pi - 1e-12)]
    if kind in ("LWPOLYLINE", "POLYLINE"):
        return _polyline(entity, kind, handle, layer, factor)
    if kind in ("ELLIPSE", "SPLINE"):
        try:
            points = np.array([(p[0], p[1]) for p in entity.flattening(plane.CHORD_MM / max(factor, 1e-12))],
                              dtype=float) * factor
        except Exception:  # noqa: BLE001 - a curve ezdxf cannot flatten has no pieces to cut
            return []
        if len(points) < 2:
            return []
        closed = bool(np.linalg.norm(points[0] - points[-1]) <= _JOIN)
        return [_Piece("curve", points, handle, layer, kind, closed)]
    return []


def _polyline(entity: Any, kind: str, handle: str, layer: str, factor: float) -> list[_Piece]:
    if kind == "LWPOLYLINE":
        vertices = [(float(x), float(y), float(b)) for x, y, *_, b in entity.get_points("xyseb")]
        closed = bool(entity.closed)
    else:
        if getattr(entity, "is_2d_polyline", True) is False:
            return []
        vertices = [(float(v.dxf.location[0]), float(v.dxf.location[1]), float(v.dxf.get("bulge", 0.0)))
                    for v in entity.vertices]
        closed = bool(entity.is_closed)
    if len(vertices) < 2:
        return []
    pieces = []
    count = len(vertices) if closed else len(vertices) - 1
    for i in range(count):
        x0, y0, bulge = vertices[i]
        x1, y1, _ = vertices[(i + 1) % len(vertices)]
        if abs(x1 - x0) < 1e-15 and abs(y1 - y0) < 1e-15:
            continue
        if abs(bulge) < 1e-12:
            pieces.append(_Piece("line", np.array([[x0, y0], [x1, y1]]) * factor, handle, layer, kind))
            continue
        sweep = 4.0 * math.atan(bulge)
        chord = math.hypot(x1 - x0, y1 - y0)
        radius = chord / (2.0 * abs(math.sin(sweep / 2)))
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = (x1 - x0) / chord, (y1 - y0) / chord
        offset = radius * math.cos(sweep / 2) * (1 if bulge > 0 else -1)
        cx, cy = mx - dy * offset, my + dx * offset
        start = math.atan2(y0 - cy, x0 - cx)
        pieces.append(_arc_piece((cx, cy), radius, start, sweep, handle, layer, kind, factor))
    return pieces


# --- chaining -----------------------------------------------------------------------------------------------


def _cluster(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Each point's cluster number: points within ``tolerance`` (chained) are one."""
    n = len(points)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = np.argsort(points[:, 0])
    for k, i in enumerate(order):
        for j in order[k + 1:]:
            if points[j, 0] - points[i, 0] > tolerance:
                break
            if abs(points[j, 1] - points[i, 1]) <= tolerance:
                a, b = find(int(i)), find(int(j))
                if a != b:
                    parent[b] = a
    roots = [find(i) for i in range(n)]
    numbers = {root: k for k, root in enumerate(dict.fromkeys(roots))}
    return np.array([numbers[root] for root in roots])


def _chain(pieces: list[_Piece]) -> tuple[list[list[tuple[_Piece, bool]]], list[dict[str, Any]]]:
    """The pieces chained into closed loops (each a list of (piece, reversed)), and the open geometry: one
    item per dangling end or branching point, located by layer and handle."""
    loops: list[list[tuple[_Piece, bool]]] = [[(piece, False)] for piece in pieces if piece.closed]
    open_pieces = [piece for piece in pieces if not piece.closed]
    problems: list[dict[str, Any]] = []
    if not open_pieces:
        return loops, problems
    ends = np.array([point for piece in open_pieces for point in piece.ends()])
    nodes = _cluster(ends, _JOIN)
    incident: dict[int, list[tuple[int, int]]] = {}
    for index in range(len(open_pieces)):
        for side in (0, 1):
            incident.setdefault(int(nodes[2 * index + side]), []).append((index, side))
    used = [False] * len(open_pieces)
    for node, touching in sorted(incident.items()):
        if len(touching) == 2:
            continue
        index, side = touching[0]
        piece = open_pieces[index]
        point = ends[2 * index + side]
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
    return loops, problems


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


def _overlaps(pieces: list[_Piece], tolerance: float = 1e-4) -> list[dict[str, Any]]:
    """Pieces lying on one another over a length: collinear lines overlapping, concentric arcs of one radius
    overlapping in angle, a line along a polyline's straight segment."""
    found = []
    lines = [p for p in pieces if p.kind == "line"]
    arcs = [p for p in pieces if p.kind == "arc"]
    if lines:
        a = np.array([p.points[0] for p in lines])
        b = np.array([p.points[-1] for p in lines])
        d = b - a
        length = np.linalg.norm(d, axis=1)
        u = d / np.maximum(length, 1e-300)[:, None]
        for i in range(len(lines)):
            # lines j > i parallel to i and on its line
            cross_dir = np.abs(u[i + 1:, 0] * u[i, 1] - u[i + 1:, 1] * u[i, 0])
            rel_a = a[i + 1:] - a[i]
            off_a = np.abs(rel_a[:, 0] * u[i, 1] - rel_a[:, 1] * u[i, 0])
            rel_b = b[i + 1:] - a[i]
            off_b = np.abs(rel_b[:, 0] * u[i, 1] - rel_b[:, 1] * u[i, 0])
            candidates = np.nonzero((cross_dir < 1e-7) & (off_a < tolerance) & (off_b < tolerance))[0]
            for k in candidates:
                j = i + 1 + int(k)
                s0, s1 = sorted((float(rel_a[k] @ u[i]), float(rel_b[k] @ u[i])))
                overlap = min(s1, length[i]) - max(s0, 0.0)
                if overlap > tolerance:
                    found.append(_overlap_item(lines[i], lines[j], overlap, a[i] + u[i] * (max(s0, 0.0) + overlap / 2)))
    for i, first in enumerate(arcs):
        for second in arcs[i + 1:]:
            if math.hypot(first.centre[0] - second.centre[0], first.centre[1] - second.centre[1]) > tolerance \
                    or abs(first.radius - second.radius) > tolerance:
                continue
            overlap = _angular_overlap(first, second) * first.radius
            if overlap > tolerance:
                found.append(_overlap_item(first, second, overlap, first.points[len(first.points) // 2]))
    return found


def _unique(pieces: list[_Piece]) -> list[_Piece]:
    """The pieces less exact copies of another entity's (the same kind through the same points, either way)."""
    kept: list[_Piece] = []
    seen: dict[tuple[Any, ...], str] = {}
    for piece in pieces:
        if not piece.closed:
            grid = [tuple(point) for point in np.round(piece.points / (10 * _JOIN)).astype(np.int64).tolist()]
            key = (piece.kind, *min(grid, grid[::-1]))
            if seen.get(key, piece.handle) != piece.handle:
                continue  # another entity's copy (one entity doubling back on itself is a zero-area loop)
            seen.setdefault(key, piece.handle)
        kept.append(piece)
    return kept


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
            if any(_off(point, piece) <= 10 * _JOIN for handle in others for piece in by_handle.get(handle, ())):
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
    """Runs of short straight segments turning a little, the same way, at each joint: a curve as chords."""
    pts = loop.points
    n = len(pts)
    if n < least_count + 2:
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
        if count >= least_count:
            source = loop.source[i]
            found.append({"segments": int(count), "length_mm": round(float(length[i:j + 1].sum()), 4),
                          "detail": f"{count} lines under {short:.3g} mm each", "layer": getattr(source, "layer", None),
                          "handles": sorted({getattr(loop.source[k], "handle", "") for k in range(i, j + 1)})[:12],
                          "location": _where(source) if source is not None else None,
                          "xyz": [round(float(pts[i][0]), 4), round(float(pts[i][1]), 4), 0.0]})
        i = j + 1
    return found


# --- the report ---------------------------------------------------------------------------------------------


def _layer_intents(document: Any) -> tuple[dict[str, str], Any]:
    from cad.engine.export.dxf import layer_intent, layer_table_intents

    declared = layer_table_intents(document)
    return declared, lambda layer: declared.get(layer) or layer_intent(layer)


def _units_suspect(code: int, extents: Any, holes: list[float], options: dict[str, Any]) -> str | None:
    """Why the declared unit makes the part implausible, read the other way, or None: in millimetres a part
    under an inch, every hole under the given thickness or a part under the set's smallest; in inches a part
    larger than the set's sheet. The rules still run in the declared unit."""
    from cad._internal.dfm import sheet as rules_side

    if code not in (1, 4) or extents is None or not len(extents):
        return None
    long, short = float(max(extents)), float(min(extents))
    if long <= 0:
        return None
    rules = str(options.get("rules") or "generic")
    thickness = options.get("thickness")
    if code == 4:
        least = rules_side.SMALLEST_PART.get(rules)
        small_holes = bool(holes) and thickness is not None and max(holes) < float(thickness)
        if not (long < 25.4 or small_holes or (least is not None and (long < least[0] or short < least[1]))):
            return None
        hole = f" (a {min(holes):.4g} mm hole)" if holes else ""
        return (f"read as millimetres the part is {long:.4g} x {short:.4g} mm{hole}; read as inches it is "
                f"{long * 25.4:.4g} x {short * 25.4:.4g} mm: if it was drawn in inches set $INSUNITS to 1")
    sheet = rules_side.sheet_size(options.get("sheet_size")) or rules_side.SHEETS.get(
        rules, rules_side.SHEETS["generic"])[0]
    if long <= sheet[0] and short <= sheet[1]:
        return None
    return (f"read as inches the part is {long:.4g} x {short:.4g} mm, larger than the {sheet[0]:.4g} x "
            f"{sheet[1]:.4g} mm sheet; read as millimetres it is {long / 25.4:.4g} x {short / 25.4:.4g} mm: if it "
            "was drawn in millimetres set $INSUNITS to 4")


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
    findings = [{"severity": found.severity, "code": found.code, "message": found.message, "location": None,
                 "hint": None} for found in validate_drawing_document(document) if found.code != "open_cut_profile"]
    try:
        code = int(document.header.get("$INSUNITS", 0))
    except (TypeError, ValueError):
        code = 0
    unit, factor = UNITS.get(code, (None, 1.0))
    unknown = unit is None
    _, intent = _layer_intents(document)
    is_drawing, evidence = document_is_drawing(document)
    report: dict[str, Any] = {"source": {"type": "dxf", "measured_as": "cut file", "document": path.name}}
    families: dict[str, list[dict[str, Any]]] = {name: [] for name in (
        "parts", "holes", "hole_spacing", "hole_to_bend", "notches", "tabs", "webs", "gaps", "open_geometry",
        "overlaps", "self_intersections", "contour_crossings", "zero_area_loops", "annotations",
        "floating_interiors", "short_line_runs")}
    pieces: list[_Piece] = []
    bend_lines: list[_Piece] = []
    layers: dict[str, dict[str, Any]] = {}
    for entity in document.modelspace():
        kind = entity.dxftype()
        layer = str(getattr(entity.dxf, "layer", "0") or "0")
        role = intent(layer)
        record = layers.setdefault(layer, {"layer": layer, "intent": role, "entities": 0})
        record["entities"] += 1
        if kind in _ANNOTATIONS:
            if role == "cut":
                where = getattr(entity.dxf, "insert", None) or getattr(entity.dxf, "location", None)
                families["annotations"].append({
                    "kind": kind, "detail": f"{kind} #{entity.dxf.handle}", "layer": layer,
                    "location": f"layer {layer}, {kind} #{entity.dxf.handle}",
                    "xyz": [round(float(where[0]) * factor, 4), round(float(where[1]) * factor, 4), 0.0]
                    if where is not None else None})
            continue
        if kind not in _CURVES:
            continue
        found = _pieces(entity, layer, factor)
        if role == "cut":
            pieces.extend(found)
        elif role == "bend":
            bend_lines.extend(piece for piece in found if piece.kind == "line")
    cut_layers = sorted(layer for layer, record in layers.items() if record["intent"] == "cut" and
                        any(piece.layer == layer for piece in pieces))
    all_points = np.vstack([piece.points for piece in pieces]) if pieces else np.zeros((0, 2))
    extents = (np.ptp(all_points, axis=0) if len(all_points) else np.zeros(2))
    report["cut_file"] = {
        "insunits": code, "unit": unit or f"unknown ($INSUNITS {code})", "mm_per_unit": factor,
        "extents_mm": [round(float(v), 4) for v in extents],
        "extents_min_mm": [round(float(v), 4) for v in (all_points.min(axis=0) if len(all_points) else np.zeros(2))],
        "layers": sorted(layers.values(), key=lambda r: r["layer"]), "cut_layers": cut_layers,
        "cut_layer_count": len(cut_layers), "piece_count": len(pieces), "bend_line_count": len(bend_lines),
        "is_drawing": bool(is_drawing), "drawing_evidence": evidence or None}
    report["scale"] = {"units_unknown": unknown, "units_suspect": unknown,
                       "note": (f"$INSUNITS is {code}: the file's units are not set, so no size is compared with a "
                                "rule; save it in mm or inches") if unknown else f"lengths in {unit}, read as mm"}
    if is_drawing:
        report["cut_file"]["contour_count"] = 0
        for name, items in families.items():
            report[name] = {"items": [], "count": 0}
        report["findings"] = findings
        report["partial"], report["partial_sections"] = False, []
        return report
    # an exact copy of a curve is cut twice (overlaps says so) but bounds nothing: the contours are chained
    # without it, so the outline it doubles is still the part's
    chains, problems = _chain(_unique(pieces))
    families["overlaps"] = _overlaps(pieces)
    families["open_geometry"] = _unexplained(problems, families["overlaps"], pieces)
    loops: list[plane.Loop] = []
    for chain in chains:
        loop = _loop(chain)
        if len(loop.points) < 2:
            continue
        size = loop.length()
        crossing = plane.self_crossings(loop)
        if crossing:
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
    for loop in loops:
        families["short_line_runs"].extend(_short_runs(loop))
    boxes = [loop.bbox() for loop in loops]
    for i in range(len(loops)):
        for j in range(i + 1, len(loops)):
            (lo1, hi1), (lo2, hi2) = boxes[i], boxes[j]
            if np.any(lo1 > hi2 + 1e-9) or np.any(lo2 > hi1 + 1e-9):
                continue
            for point in plane.crossings(loops[i], loops[j])[:2]:
                source = loops[i].source[0]
                families["contour_crossings"].append({
                    "detail": f"#{','.join(loops[i].label)} crosses #{','.join(loops[j].label)} at "
                              f"{point[0]:.4g}, {point[1]:.4g}", "handles": loops[i].label + loops[j].label,
                    "layer": getattr(source, "layer", None), "location": _where(source),
                    "xyz": [round(point[0], 4), round(point[1], 4), 0.0]})
    depth = plane.nest(loops)
    thickness = options.get("thickness")
    for loop, level in zip(loops, depth):
        loop.label = {"handles": loop.label, "depth": level}
    outlines = [i for i, level in enumerate(depth) if level % 2 == 0]
    holes = [i for i, level in enumerate(depth) if level % 2 == 1]
    for i, level in enumerate(depth):
        if level >= 2 and level % 2 == 0:
            source = loops[i].source[0]
            families["floating_interiors"].append({
                "detail": f"#{','.join(loops[i].label['handles'])} lies inside a hole", "layer": getattr(source, "layer", None),
                "location": _where(source), "xyz": [round(float(v), 4) for v in (*loops[i].centroid(), 0.0)]})

    def locate(point: Any) -> tuple[str, list[float]]:
        p = np.asarray(point, dtype=float).reshape(1, 2)
        best, where = math.inf, None
        for loop in loops:
            d, _ = plane._point_segment(p, loop.a, loop.b)
            k = int(np.argmin(d[0]))
            if d[0, k] < best:
                best, where = float(d[0, k]), loop.source[k]
        return (_where(where) if where is not None else "cut file"), [round(float(p[0, 0]), 4),
                                                                       round(float(p[0, 1]), 4), 0.0]

    # each outline and the holes directly inside it
    parent: dict[int, int] = {}
    for h in holes:
        holders = [o for o in outlines if depth[o] == depth[h] - 1 and
                   plane.inside(loops[h].points[:1], [loops[o]])[0]]
        if holders:
            parent[h] = min(holders, key=lambda o: abs(plane.area(loops[o])))
    for o in outlines:
        mine = [h for h in holes if parent.get(h) == o]
        circle = loops[o].circle
        long, short, _ = (2 * circle[2], 2 * circle[2], 0.0) if circle else plane.min_rectangle(loops[o].points)
        source = loops[o].source[0]
        families["parts"].append({
            "name": f"contour #{','.join(loops[o].label['handles'][:3])}", "thickness_mm": thickness,
            "flat_length_mm": round(long, 4), "flat_width_mm": round(short, 4),
            "flat_area_mm2": round(abs(plane.area(loops[o])) - sum(abs(plane.area(loops[h])) for h in mine), 3),
            "hole_count": len(mine), "is_sheet": True, "floating": depth[o] >= 2,
            "location": _where(source), "xyz": [round(float(v), 4) for v in (*loops[o].centroid(), 0.0)]})
        region = [loops[o]] + [loops[h] for h in mine]
        for loop in region:
            loop.label = "outer" if loop is loops[o] else "hole"
        features = _outline_features(None, region, thickness, locate)
        for name in ("notches", "tabs", "webs", "gaps"):
            families[name].extend(features[name])
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
            records.append((h, record))
            families["holes"].append(record)
            if bend_lines:
                nearest = min(bend_lines, key=lambda line: plane.segments_distance(
                    loop.a, loop.b, line.points[:1], line.points[1:])[0])
                d = plane.segments_distance(loop.a, loop.b, nearest.points[:1], nearest.points[1:])[0]
                families["hole_to_bend"].append({"bend": _where(nearest), "distance_centerline_mm": round(d, 4),
                                                 "location": record["location"], "xyz": record["xyz"],
                                                 "convention": "to the bend layer's line, read as the bend's "
                                                               "centre line"})
        pairs: dict[tuple[int, int], dict] = {}
        for h, record in records:
            others = [(plane.distance(loops[h], loops[g])[0], g, other) for g, other in records if g != h]
            if others:
                d, g, other = min(others, key=lambda found: found[0])
                key = (min(h, g), max(h, g))
                pairs.setdefault(key, {"distance_mm": round(d, 4), "location": record["location"],
                                       "other": other["location"], "xyz": record["xyz"]})
        families["hole_spacing"].extend(pairs.values())
    suspect = _units_suspect(code, extents, [item["size_mm"] for item in families["holes"]], options)
    if suspect:
        report["scale"].update(units_suspect=True, note=suspect)
    sort_keys = {"holes": "size_mm", "hole_spacing": "distance_mm", "hole_to_bend": "distance_centerline_mm",
                 "notches": "width_mm", "tabs": "width_mm", "webs": "width_mm", "gaps": "width_mm"}
    for name, items in families.items():
        key = sort_keys.get(name)
        if key:
            items = sorted(items, key=lambda item: (item.get(key) is None, item.get(key) or 0.0))
        report[name] = {"items": items[:ITEM_CAP], "count": len(items)}
    report["bent"] = bool(bend_lines)
    report["findings"] = findings
    report["partial"], report["partial_sections"] = False, []
    return report
