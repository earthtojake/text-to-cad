"""Sheet-cutting geometry the ``cut`` and ``wire_edm`` operations share: profiles, offsets, order, pierces, leads.

* :func:`sheet_profiles` reads what a job cuts as shapely polygons in the setup's WCS (one per part, its holes as
  interiors): a DXF's profiles, or a STEP plate's outline (its section, the same at the top, the middle and the bottom
  of the plate; a part that is not prismatic along the setup's Z is refused in one sentence).
* :func:`kerf_rings` offsets every profile to its waste side: an outside profile outward, a hole inward, each by the
  offset (half the kerf, a router bit's radius, the wire's radius plus its spark gap), oriented so the part is on the
  right of travel (``part_right``; clockwise outsides, counter-clockwise holes) or the left.
* :func:`order_rings` cuts inside first (every ring that lies inside another, holes and parts nested in holes, before
  it) and otherwise nearest-neighbour from where the tool is, choosing each ring's pierce point as it goes.
* :func:`corner_zones` finds the sharp corners of a ring (the turning within a short window of path, so a kerf-wide
  round join counts as the sharp corner it is); :func:`pierce_at` picks a pierce point on a straight run away from
  them; :func:`slow_segments` splits a ring into runs with a feed factor (corner slowdown) and gaps (microjoints).
* :func:`lead_in` and :func:`lead_out` are an arc or a line on the waste side that keep the kerf off the part,
  shrinking until they fit.

All in WCS mm, rings as (N, 2) closed numpy arrays. Stdlib at import; numpy and shapely inside.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from cadgen._internal.cam.job_errors import CamJobError

__all__ = ["Ring", "corner_zones", "kerf_rings", "lead_in", "lead_out", "near_zone", "order_rings", "pierce_at",
           "point_at", "rotate_ring", "sheet_profiles", "slow_segments", "unreachable"]

#: A corner is where the path turns more than this within the corner window.
CORNER_DEG = 30.0


@dataclass
class Ring:
    """One closed path to cut: ``coords`` (N, 2) closed, oriented; ``kind`` ``outside`` or ``hole``; ``part`` the
    index of the profile it belongs to; ``region`` the polygon the ring bounds (waste inside it for a hole, the part
    and its kerf for an outside); ``design`` the design ring it was offset from."""

    coords: Any
    kind: str
    part: int
    region: Any
    design: Any
    zones: list = field(default_factory=list)
    #: Arc length of the chosen pierce point, set by :func:`order_rings`.
    start_s: float = 0.0
    #: Plasma's small-hole rule and the like: a feed factor for the whole ring.
    factor: float = 1.0
    notes: list = field(default_factory=list)

    @property
    def length(self) -> float:
        import numpy as np

        return float(np.linalg.norm(np.diff(self.coords, axis=0), axis=1).sum())


# --- what to cut ---------------------------------------------------------------------------------------------

def _to_wcs_2d(polygon, wcs):
    import numpy as np
    import shapely

    def move(xy):
        xy = np.asarray(xy, dtype=float)
        return wcs.to_wcs(np.column_stack([xy, np.zeros(len(xy))]))[:, :2]

    out = shapely.transform(polygon, move)
    return out if out.is_valid else out.buffer(0)


def sheet_profiles(ctx, where: str) -> list:
    """The polygons a cutting op cuts, in the setup's WCS: a DXF's profiles, or a prismatic STEP plate's outline."""
    import shapely

    from cadgen._internal.cam.geom2d import polygons_of

    wcs = ctx.wcs
    axis = wcs.tool_axis
    if abs(abs(axis[2]) - 1.0) > 1e-9:
        raise CamJobError(f"{where}: a sheet is cut from above; give the setup orientation +Z (or -Z to cut it "
                          "flipped)")
    if ctx.part.kind == "dxf":
        return [p for p in (_to_wcs_2d(profile, wcs) for profile in ctx.part.profiles) if p.area > 1e-9]
    heights = ctx.heights
    bottom, top = heights.part_bottom, heights.part_top
    thickness = top - bottom
    if thickness <= 1e-6:
        raise CamJobError(f"{where}: the part has no thickness along the setup's Z; cut a flat plate")
    eps = min(0.05, 0.02 * thickness)
    middle = ctx.sections.at(bottom + thickness / 2.0)
    if middle.is_empty:
        raise CamJobError(f"{where}: the part has no material halfway up its thickness; cut a flat plate")
    allowance = max(0.02, 4.0 * ctx.tolerance_mm) * max(1.0, middle.length)
    for z, word in ((bottom + eps, "bottom"), (top - eps, "top")):
        other = ctx.sections.at(z)
        differ = shapely.symmetric_difference(middle, other).area
        if differ > allowance:
            raise CamJobError(
                f"{where}: the part is not a flat plate seen from setup '{ctx.setup.id}': its outline at the {word} "
                f"differs from its middle by {differ:.1f} mm² (a pocket, a step, a chamfer or a slope); a sheet cut "
                "makes straight through-walls only. Mill it, or cut a DXF of the outline")
    return polygons_of(middle)


# --- offsets -------------------------------------------------------------------------------------------------

def _orient(coords, clockwise: bool):
    import numpy as np

    coords = np.asarray(coords, dtype=float)
    x, y = coords[:, 0], coords[:, 1]
    area = 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))
    if (area < 0) != clockwise:
        coords = coords[::-1].copy()
    return coords


def kerf_rings(profiles, offset: float, *, tolerance: float, part_right: bool = True,
               which: str = "all") -> tuple[list[Ring], list[str]]:
    """Every profile's rings offset to the waste side by ``offset``, oriented; and plain notes (a hole too small
    for the offset, one that splits in two)."""
    import numpy as np
    import shapely
    from shapely.ops import polylabel

    from cadgen._internal.cam.geom2d import offset as grow, polygons_of

    rings: list[Ring] = []
    notes: list[str] = []
    for index, polygon in enumerate(profiles):
        if which in ("all", "outside"):
            design = shapely.Polygon(polygon.exterior)
            grown = polygons_of(grow(design, offset, tolerance=tolerance, radius=max(offset, 1e-3)))
            for piece in grown:
                coords = _orient(np.asarray(piece.exterior.coords)[:, :2], clockwise=part_right)
                rings.append(Ring(coords, "outside", index, shapely.Polygon(piece.exterior), polygon.exterior))
        if which in ("all", "holes"):
            for interior in polygon.interiors:
                hole = shapely.Polygon(interior)
                shrunk = polygons_of(grow(hole, -offset, tolerance=tolerance, radius=max(offset, 1e-3)))
                c = hole.representative_point()
                if not shrunk:
                    # A hole exactly as wide as the cut (a slot for the bit, a hole for the drill-size beam): cut it
                    # a hair oversize along its middle rather than not at all.
                    hair = max(tolerance, 0.005)
                    shrunk = polygons_of(grow(hole, -(offset - hair), tolerance=tolerance, radius=max(offset, 1e-3)))
                    if shrunk:
                        notes.append(f"a hole at ({c.x:.1f}, {c.y:.1f}) is as narrow as the {2 * offset:.3g} mm cut: "
                                     f"it is cut along its middle, up to {hair:g} mm oversize a side")
                if not shrunk:
                    width = 2.0 * shapely.distance(polylabel(hole, tolerance), hole.exterior)
                    notes.append(f"a hole {width:.3g} mm across at ({c.x:.1f}, {c.y:.1f}) is narrower than the "
                                 f"{2 * offset:.3g} mm cut and is not cut")
                    continue
                if len(shrunk) > 1:
                    notes.append(f"a hole at ({c.x:.1f}, {c.y:.1f}) narrows below the {2 * offset:.3g} mm cut and is "
                                 f"cut as {len(shrunk)} pieces; the waist between them stays")
                for piece in shrunk:
                    coords = _orient(np.asarray(piece.exterior.coords)[:, :2], clockwise=not part_right)
                    rings.append(Ring(coords, "hole", index, shapely.Polygon(piece.exterior), interior))
    return rings, notes


def unreachable(profiles, radius: float, *, tolerance: float, z: float) -> list[dict]:
    """What a cut of ``radius`` cannot take out of the profiles' inside corners (hole corners, the outline's
    notches): the part's closing minus the part, one entry per spot, for the ``corner_radius`` check."""
    import shapely

    from cadgen._internal.cam.geom2d import offset as grow, polygons_of

    out = []
    if radius <= 1e-6:
        return out
    # A hair under the radius: a slot exactly the cut's width is cut along its middle (kerf_rings), not left.
    reach = max(radius - max(tolerance, 0.005), radius / 2.0)
    for polygon in profiles:
        closed = grow(grow(polygon, reach, tolerance=tolerance), -reach, tolerance=tolerance)
        left = shapely.difference(closed, polygon.buffer(1e-6))
        # Opened by the tolerance: slivers thinner than it are the offsets' own polygon noise.
        hair = max(tolerance, 0.005)
        for piece in polygons_of(left.buffer(-hair).buffer(hair)):
            if piece.area > 0.01:
                c = piece.representative_point()
                out.append({"area_mm2": float(piece.area), "at": [c.x, c.y, z], "z": z})
    return out


# --- corners, pierces, slowdowns -------------------------------------------------------------------------------

def _arclength(coords):
    import numpy as np

    seg = np.linalg.norm(np.diff(coords, axis=0), axis=1)
    return np.concatenate([[0.0], np.cumsum(seg)]), seg


def corner_zones(coords, *, window: float, angle_deg: float = CORNER_DEG) -> list[dict]:
    """The sharp corners of a closed ring: runs of vertices where the path turns more than ``angle_deg`` within
    ``window`` mm of path. Each zone: ``lo``, ``hi`` (arc lengths of its first and last vertex), ``at`` (its sharpest
    vertex's arc length) and ``turn_deg`` (the turning within the window there)."""
    import numpy as np

    coords = np.asarray(coords, dtype=float)
    pts = coords[:-1]
    n = len(pts)
    if n < 3:
        return []
    s, seg = _arclength(coords)
    total = float(s[-1])
    edges = np.diff(coords, axis=0)
    heading = np.arctan2(edges[:, 1], edges[:, 0])
    turn = np.abs((heading - np.roll(heading, 1) + math.pi) % (2 * math.pi) - math.pi)   # turn at vertex i
    sv = s[:-1]
    # Windowed turning, cyclic: vertices within window/2 of each vertex.
    s3 = np.concatenate([sv - total, sv, sv + total])
    t3 = np.concatenate([turn, turn, turn])
    c3 = np.concatenate([[0.0], np.cumsum(t3)])
    lo = np.searchsorted(s3, sv - window / 2.0, side="left")
    hi = np.searchsorted(s3, sv + window / 2.0, side="right")
    windowed = c3[hi] - c3[lo]
    sharp = windowed >= math.radians(angle_deg)
    if not sharp.any():
        return []
    # Sharp vertices a short edge apart are one corner (a round join's vertices); a long edge splits corners.
    joined = sharp & np.roll(sharp, -1) & (seg <= window)       # vertex i joins vertex i + 1
    if joined.all():
        k = int(np.argmax(turn))
        return [{"lo": 0.0, "hi": total, "at": float(sv[k]), "turn_deg": float(min(180.0, math.degrees(windowed[k]))),
                 "whole": True}]
    zones = []
    for start in range(n):
        if not sharp[start] or joined[start - 1]:
            continue
        idx = [start]
        j = start
        while joined[j]:
            j = (j + 1) % n
            idx.append(j)
        k = max(idx, key=lambda i: windowed[i])
        lo_s = float(sv[idx[0]])
        hi_s = float(sv[idx[-1]])
        if hi_s < lo_s:
            hi_s += total
        zones.append({"lo": lo_s, "hi": hi_s, "at": float(sv[k]),
                      "turn_deg": float(min(180.0, math.degrees(sum(turn[i] for i in idx)))), "whole": False})
    return zones


def near_zone(s: float, zones, total: float, clear: float) -> bool:
    for zone in zones:
        if zone.get("whole"):
            return True
        lo, hi = zone["lo"] - clear, zone["hi"] + clear
        for shift in (-total, 0.0, total):
            if lo <= s + shift <= hi:
                return True
    return False


def pierce_at(coords, zones, position, *, clear: float) -> tuple[float, float]:
    """``(arc length, distance)`` of a pierce point on the ring: on a straight edge at least ``clear`` from every
    corner zone, nearest ``position``; else the middle of the longest corner-free stretch; else (a ring that is all
    corner, like a small hole) the point nearest ``position``."""
    import numpy as np

    coords = np.asarray(coords, dtype=float)
    s, seg = _arclength(coords)
    total = float(s[-1])
    p = np.asarray(position[:2], dtype=float)
    best = None
    for i in np.nonzero(seg >= 2.0 * clear)[0]:
        a, b = coords[i], coords[i + 1]
        d = b - a
        t = float(np.clip(np.dot(p - a, d) / max(float(np.dot(d, d)), 1e-12), clear / seg[i], 1 - clear / seg[i]))
        sp = float(s[i] + t * seg[i])
        if near_zone(sp, zones, total, clear):
            # Try the edge's middle before giving the edge up.
            sp = float(s[i] + seg[i] / 2.0)
            if near_zone(sp, zones, total, clear):
                continue
            t = 0.5
        q = a + d * t
        dist = float(np.hypot(*(q - p)))
        if best is None or dist < best[1]:
            best = (sp, dist)
    if best is not None:
        return best
    real = [z for z in zones if not z.get("whole")]
    if real:
        ordered = sorted(real, key=lambda z: z["lo"])
        gaps = []
        for k, zone in enumerate(ordered):
            nxt = ordered[(k + 1) % len(ordered)]
            start, end = zone["hi"], nxt["lo"] + (total if k == len(ordered) - 1 else 0.0)
            if end > start:
                gaps.append((end - start, (start + end) / 2.0 % total))
        if gaps:
            length, sp = max(gaps)
            q = point_at(coords, sp)
            return sp, float(np.hypot(*(q - p)))
    import shapely

    ring = shapely.LineString(coords)
    sp = float(ring.project(shapely.Point(p)))
    q = point_at(coords, sp)
    return sp, float(np.hypot(*(q - p)))


def point_at(coords, s: float):
    import numpy as np

    cum, _ = _arclength(coords)
    s = s % cum[-1] if cum[-1] > 0 else 0.0
    return np.array([np.interp(s, cum, coords[:, 0]), np.interp(s, cum, coords[:, 1])])


def rotate_ring(coords, s: float):
    """The closed ring re-started at arc length ``s`` (a point inserted there)."""
    import numpy as np

    coords = np.asarray(coords, dtype=float)
    cum, _ = _arclength(coords)
    total = float(cum[-1])
    s = s % total
    k = int(np.searchsorted(cum, s, side="right")) - 1
    k = max(0, min(k, len(coords) - 2))
    q = point_at(coords, s)
    body = coords[:-1]
    after = body[k + 1:]
    before = body[:k + 1]
    out = np.vstack([[q], after, before, [q]])
    keep = np.concatenate([[True], np.linalg.norm(np.diff(out, axis=0), axis=1) > 1e-9])
    out = out[keep]
    if np.linalg.norm(out[-1] - q) > 1e-9:
        out = np.vstack([out, [q]])
    return out


def slow_segments(coords, zones, *, slow_mm: float, min_factor: float = 0.3, gaps=()) -> list[tuple]:
    """A ring (already started at its pierce point) as runs ``(points (M, 2), factor, cutting)``: ``factor`` the
    feed scale (``cos²(turn / 2)`` within ``slow_mm`` of each corner zone, at least ``min_factor``), ``cutting`` false
    over the microjoint ``gaps`` (``(s0, s1)`` arc lengths, the beam off)."""
    import numpy as np

    coords = np.asarray(coords, dtype=float)
    cum, _ = _arclength(coords)
    total = float(cum[-1])
    windows = []
    for zone in zones:
        factor = max(min_factor, math.cos(math.radians(zone["turn_deg"]) / 2.0) ** 2)
        if zone.get("whole"):
            windows.append((-1.0, total + 1.0, factor))
            continue
        for shift in (-total, 0.0, total):
            lo, hi = zone["lo"] - slow_mm + shift, zone["hi"] + slow_mm + shift
            if hi >= 0 and lo <= total:
                windows.append((max(0.0, lo), min(total, hi), factor))
    marks = set(cum.tolist())
    for lo, hi, _ in windows:
        marks.update(v for v in (lo, hi) if 0 < v < total)
    for lo, hi in gaps:
        marks.update(v for v in (lo, hi) if 0 < v < total)
    s = np.array(sorted(marks))
    points = np.column_stack([np.interp(s, cum, coords[:, 0]), np.interp(s, cum, coords[:, 1])])
    mids = (s[:-1] + s[1:]) / 2.0
    factors = np.ones(len(mids))
    for lo, hi, factor in windows:
        inside = (mids >= lo) & (mids <= hi)
        factors[inside] = np.minimum(factors[inside], factor)
    cutting = np.ones(len(mids), dtype=bool)
    for lo, hi in gaps:
        cutting[(mids > lo) & (mids < hi)] = False
    runs = []
    start = 0
    for i in range(1, len(mids) + 1):
        if i == len(mids) or cutting[i] != cutting[start] or factors[i] != factors[start]:
            runs.append((points[start:i + 1], float(factors[start]), bool(cutting[start])))
            start = i
    return runs


# --- order -----------------------------------------------------------------------------------------------------

def order_rings(rings: list[Ring], start, *, clear_for, window_for) -> list[Ring]:
    """Inside first, then nearest: a ring is ready once every ring lying inside it is cut; of the ready ones the one
    whose pierce point is nearest the tool goes next. Sets each ring's ``zones`` and ``start_s``."""
    import shapely

    for ring in rings:
        ring.zones = corner_zones(ring.coords, window=window_for(ring))
    inside: dict[int, set[int]] = {i: set() for i in range(len(rings))}
    tree = shapely.STRtree([ring.region for ring in rings])
    for i, ring in enumerate(rings):
        probe = shapely.Point(ring.coords[0])
        for j in tree.query(probe, predicate="within"):
            j = int(j)
            if j != i and rings[j].region.area > ring.region.area and rings[j].region.contains(probe):
                inside[j].add(i)
    done: set[int] = set()
    out: list[Ring] = []
    here = (float(start[0]), float(start[1]))
    while len(out) < len(rings):
        ready = [i for i in range(len(rings)) if i not in done and inside[i] <= done]
        best = None
        for i in ready:
            s, dist = pierce_at(rings[i].coords, rings[i].zones, here, clear=clear_for(rings[i]))
            if best is None or dist < best[2] - 1e-9:
                best = (i, s, dist)
        i, s, _ = best
        rings[i].start_s = s
        done.add(i)
        out.append(rings[i])
        q = point_at(rings[i].coords, s)
        here = (float(q[0]), float(q[1]))
    return out


# --- leads ----------------------------------------------------------------------------------------------------

def _arc_points(start, centre, end, clockwise: bool, steps: int = 16):
    import numpy as np

    a0 = math.atan2(start[1] - centre[1], start[0] - centre[0])
    a1 = math.atan2(end[1] - centre[1], end[0] - centre[0])
    sweep = a1 - a0
    if clockwise:
        while sweep > 0:
            sweep -= 2 * math.pi
    else:
        while sweep < 0:
            sweep += 2 * math.pi
    r = math.hypot(start[0] - centre[0], start[1] - centre[1])
    angles = a0 + sweep * np.linspace(0.0, 1.0, steps + 1)
    return np.column_stack([centre[0] + r * np.cos(angles), centre[1] + r * np.sin(angles)])


def _clear_of(points, keep_off, distance: float) -> bool:
    import shapely

    if keep_off is None or keep_off.is_empty:
        return True
    line = shapely.LineString(points)
    return shapely.distance(line, keep_off) >= distance - 1e-6


def _lead(point, direction, *, length: float, kind: str, part_right: bool, keep_off, clearance: float,
          entering: bool) -> dict | None:
    import numpy as np

    from cadgen._internal.cam.linking import lead_arc

    d = np.asarray(direction, dtype=float)
    d = d / (np.linalg.norm(d) or 1.0)
    away = np.array([-d[1], d[0]]) if part_right else np.array([d[1], -d[0]])
    p = np.asarray(point, dtype=float)
    for size in (length, length / 2.0, length / 4.0):
        if size < 0.05:
            break
        kinds = ("arc", "line") if kind == "arc" else ("line",)
        for shape in kinds:
            if shape == "arc":
                start, centre, clockwise = lead_arc(p, d, radius=size, material_on_right=part_right, entering=entering)
                points = _arc_points(start, centre, p, clockwise) if entering else _arc_points(p, centre, start,
                                                                                               clockwise)
                lead = {"kind": "arc", "start": np.asarray(start), "centre": np.asarray(centre),
                        "clockwise": clockwise, "points": points, "size": size}
            else:
                far = p + away * size
                points = np.vstack([far, p]) if entering else np.vstack([p, far])
                lead = {"kind": "line", "start": far, "points": points, "size": size}
            if _clear_of(points, keep_off, clearance):
                return lead
    return None


def lead_in(point, direction, **kwargs) -> dict | None:
    """A lead into ``point`` along ``direction`` from the waste side (an arc, else a line; shrinking to a quarter
    of ``length``) whose path keeps ``clearance`` from ``keep_off`` (the parts); None when none fits. The dict has
    ``kind``, ``start`` (where to pierce), ``points`` (start .. point), and for an arc ``centre``/``clockwise``."""
    return _lead(point, direction, entering=True, **kwargs)


def lead_out(point, direction, **kwargs) -> dict | None:
    """The lead away from ``point`` (the ring's end) into the waste; ``points`` run point .. end."""
    return _lead(point, direction, entering=False, **kwargs)
