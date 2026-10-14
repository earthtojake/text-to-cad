"""The lathe's stock simulator: the bar's half-section (radius, axial) as an exact 2D region, cut by each tool's shape.

A turned part is the same at every angle, so the stock is the region of the half-plane through the spindle axis
that still holds material: shapely ``(x, y)`` = ``(radius, t)``, ``t`` the part coordinate along the bar's axis (so
a part flipped for its second setup is simulated in the same frame). It starts as the bar's rectangle.

:meth:`LatheSim.cut` walks one setup's toolpath in program order. Each operation's tool is its shape from
:func:`~cadgen._internal.cam.turn_profile.tool_shape` (the role and its numbers ride in the op's ``meta["lathe"]``):
a run of cutting moves removes the region the shape sweeps (convex hulls of each piece, exact up to the chord of
arcs), a rapid is tested, never cut: a rapid whose tool overlaps material by more than 0.05 mm is a hit. Thread
passes are not stamped (a thread's helical groove is not a body of revolution; the part's thread is drawn as the
toolpath only). Once a part-off blade reaches the centre, the bar behind the cut is dropped: the part goes on to the
next setup alone. Removed volume is Pappus's (2 pi x the section's area x its centroid radius).

:meth:`material_left` compares the stock with the part's turned profile (the max-radius envelope from
:mod:`~cadgen._internal.cam.turn_profile`) in the last setup, ignoring the bar behind the part (towards the chuck):
material proud of it beyond the stock to leave is left, with its volume, section area, how proud and where.
:meth:`mesh` revolves the region into a closed triangle mesh in part coordinates. shapely and numpy at import.
"""

from __future__ import annotations

import math

import numpy as np
import shapely

from cadgen._internal.cam.ir import DWELL, RAPID
from cadgen._internal.cam.stock import MaterialLeft, SimReport

__all__ = ["LatheSim", "role_of"]

#: How far a rapid may overlap material before it is a hit (mm).
RAPID_TOLERANCE = 0.05
_FAR = 1e5


def role_of(tool, meta: dict | None = None) -> tuple[str, dict]:
    """The tool's role for its shape (``meta["lathe"]`` from the planner, else from the tool's type)."""
    lathe = dict((meta or {}).get("lathe") or {})
    role = lathe.pop("role", None)
    if role is None:
        role = {"turn": "od", "groove": "groove", "partoff": "partoff", "thread": "thread"}.get(
            tool.type, "drill" if tool.family == "mill" else "od")
    return role, lathe


def pappus(region) -> float:
    """The volume a half-section region sweeps about its x = 0 axis (mm^3)."""
    if region is None or region.is_empty or region.area <= 0:
        return 0.0
    return float(2.0 * math.pi * region.area * region.centroid.x)


class LatheSim:
    kind = "lathe"

    def __init__(self, stock, part=None, *, cell_mm: float = 0.5, tolerance_mm: float = 0.01):
        self.stock = stock
        self.part = part
        self.tolerance = float(tolerance_mm)
        self.wcs = None
        self.material = None
        cylinder = stock.cylinder if stock.kind == "cylinder" else None
        if cylinder:
            self.w = "xyz".index(cylinder["axis"])
            self.centre = np.asarray(cylinder["center"], dtype=float)
            self.material = shapely.box(0.0, float(cylinder["start"]), float(cylinder["radius"]),
                                        float(cylinder["end"]))

    # --- frames --------------------------------------------------------------------------------------

    def _frame(self, wcs):
        """``(s, c)`` with ``t = s * z + c`` for this setup, or a reason it cannot be simulated."""
        if self.material is None:
            return "a lathe simulates bar stock (a cylinder) only"
        axis = np.zeros(3)
        axis[self.w] = 1.0
        o = np.asarray(wcs.from_wcs([[0.0, 0.0, 0.0]])[0])
        z1 = np.asarray(wcs.from_wcs([[0.0, 0.0, 1.0]])[0]) - o
        if abs(abs(float(z1 @ axis)) - 1.0) > 1e-6:
            return "this setup does not spin about the bar's axis"
        v = o - self.centre
        if float(np.linalg.norm(v - axis * float(v @ axis))) > 1e-3:
            return "this setup's work zero is off the bar's axis"
        return float(np.sign(z1 @ axis)), float(o[self.w])

    def supports(self, wcs) -> str | None:
        frame = self._frame(wcs)
        return frame if isinstance(frame, str) else None

    def _to_sim(self, points, frame):
        s, c = frame
        points = np.asarray(points, dtype=float)
        return np.column_stack([points[:, 0], s * points[:, 2] + c])

    def _shapes(self, tool, role, params, frame):
        from cadgen._internal.cam.turn_profile import tool_shape

        s, _ = frame
        out = []
        for shape in tool_shape(tool, role, **params):
            shape = np.asarray(shape, dtype=float).copy()
            shape[:, 1] *= s
            out.append(shape)
        return out

    # --- cutting -------------------------------------------------------------------------------------

    def cut(self, toolpath, tools: dict, wcs) -> SimReport:
        report = SimReport(setup=wcs.setup_id)
        frame = self._frame(wcs)
        if isinstance(frame, str):
            report.skipped = frame
            return report
        self.wcs = wcs
        half = shapely.box(0.0, -_FAR, _FAR, _FAR)
        chord = max(self.tolerance, 0.005)
        for op in toolpath.ops:
            tool = tools.get(op.tool) if op.tool else None
            if tool is None or op.end <= op.start:
                continue
            role, params = role_of(tool, op.meta)
            shapes = self._shapes(tool, role, params, frame)
            stamp = not role.startswith("thread")
            piece = toolpath.slice(op.start, op.end)
            samples = piece.sample(chord)
            points = self._to_sim(samples.points, frame)
            kinds = samples.kind
            before = self.material
            face_t = self._face(points, kinds, role, tool, frame)
            hits = []
            run: list[int] = []
            # A thread's passes cut a helical groove the half-section cannot hold: they are not stamped, and its own
            # rapids are judged against the stock less the region those passes sweep.
            spared = None if stamp else _cut_runs(points, kinds, shapes)

            def flush(run):
                if len(run) < 2 or not stamp:
                    return
                swept = shapely.intersection(_sweep(points[run], shapes), half)
                if not swept.is_empty:
                    self.material = shapely.difference(self.material, swept)

            for i in range(1, len(points)):
                kind = int(kinds[i])
                if kind == DWELL:
                    continue
                if kind == RAPID:
                    flush(run)
                    run = []
                    if np.allclose(points[i - 1], points[i]):
                        continue
                    hit = self._rapid_hit(points[i - 1:i + 1], shapes, spared)
                    if hit is not None:
                        hits.append((i, hit))
                else:
                    if not run:
                        run = [i - 1]
                    run.append(i)
            flush(run)
            if role == "partoff":
                self._part_off(points, kinds, tool, frame)
            report.removed_mm3_by_op[op.index] = round(pappus(before) - pappus(self.material), 3)
            if hits:
                i, (depth, at) = max(hits, key=lambda h: h[1][0])
                report.rapid_hits.append({"op": op.index, "move": int(op.start + samples.move[i]),
                                          "at": self._part_point(at, frame), "depth_mm": round(depth, 3),
                                          "count": len(hits)})
            if role == "drill" and face_t is not None:
                tips = points[kinds != RAPID]
                if len(tips):
                    s, _ = frame
                    k = int(np.argmin(s * tips[:, 1]))
                    depth = float(s * (face_t - tips[k, 1]))
                    if depth > 0:
                        report.depth_by_op[op.index] = {"depth_mm": round(depth, 3),
                                                        "at": self._part_point(tips[k], frame)}
        return report

    def _part_off(self, points, kinds, tool, frame) -> None:
        """Once the blade is through, the bar on the chuck side stays in the machine and the part goes on (to the
        next setup, or the parts bin): keep only the material in front of the cut."""
        s, _ = frame
        cuts = points[kinds != RAPID]
        if not len(cuts) or float(cuts[:, 0].min()) > 0.05:
            return                                             # not through to the centre: still one piece
        # The middle of the kerf (the blade's controlled point is its chuck-side corner).
        t = cuts[int(np.argmin(cuts[:, 0])), 1] + s * tool.width_mm / 2.0
        front = shapely.box(0.0, t, _FAR, _FAR) if s > 0 else shapely.box(0.0, -_FAR, _FAR, t)
        kept = [g for g in shapely.get_parts(shapely.intersection(self.material, front))
                if g.geom_type == "Polygon" and g.area > 1e-9]
        if kept:
            self.material = shapely.union_all(kept)

    def _face(self, points, kinds, role, tool, frame):
        """Where the material in front of a drill starts (t), before it cuts."""
        if role != "drill":
            return None
        s, _ = frame
        band = shapely.intersection(self.material, shapely.box(0.0, -_FAR, max(tool.radius, 0.01), _FAR))
        if band.is_empty:
            return None
        lo, hi = band.bounds[1], band.bounds[3]
        return hi if s > 0 else lo

    def _rapid_hit(self, segment, shapes, spared=None):
        swept = _sweep(segment, shapes)
        material = self.material if spared is None else shapely.difference(self.material, spared)
        overlap = shapely.intersection(swept, material)
        if overlap.is_empty or overlap.area < 1e-9:
            return None
        coords = shapely.get_coordinates(overlap)
        inside = shapely.contains_xy(material, coords[:, 0], coords[:, 1])
        if not inside.any():
            # The overlap's corners all sit on the material's boundary: measure its thickness instead.
            depth = overlap.area / max(overlap.length / 2.0, 1e-9)
            at = np.asarray(overlap.representative_point().coords[0])
        else:
            distance = shapely.distance(shapely.points(coords[inside]), material.boundary)
            k = int(np.argmax(distance))
            depth, at = float(distance[k]), coords[inside][k]
        if depth <= RAPID_TOLERANCE:
            return None
        return depth, at

    def _part_point(self, point, frame):
        s, c = frame
        x, t = float(point[0]), float(point[1])
        return [round(v, 4) + 0.0 for v in self.wcs.from_wcs([[x, 0.0, (t - c) / s]])[0]]

    # --- results -------------------------------------------------------------------------------------

    def volume(self) -> float:
        if self.material is None:
            return float(self.stock.volume_mm3)
        return pappus(self.material)

    def target(self, part, wcs, *, tolerance_mm: float):
        """The part's turned section in this simulator's frame, with the bar behind it (towards the chuck)."""
        from cadgen._internal.cam.turn_profile import read_profile

        frame = self._frame(wcs)
        if isinstance(frame, str):
            return None
        s, c = frame
        profile = read_profile(part, wcs, tolerance_mm=tolerance_mm)
        behind = shapely.box(0.0, -_FAR, _FAR, profile.z_back)
        region = shapely.union(profile.region, behind)
        return shapely.affinity.affine_transform(region, [1.0, 0.0, 0.0, s, 0.0, c])

    def material_left(self, part, *, stock_to_leave_mm: float, tolerance_mm: float) -> MaterialLeft | None:
        if self.material is None or self.wcs is None or part is None:
            return None
        # A part whose turned section cannot be read raises (CamJobError): the material_left check says so.
        target = self.target(part, self.wcs, tolerance_mm=tolerance_mm)
        if target is None:
            return None
        slack = stock_to_leave_mm + max(0.02, 2.0 * tolerance_mm)
        left = shapely.difference(self.material, target.buffer(slack, quad_segs=8))
        pieces = [p for p in shapely.get_parts(left) if p.area > 1e-6]
        if not pieces:
            return None
        left = shapely.union_all(pieces)
        # How proud: the farthest point of its edge from the part (measured along the edge, not just its corners).
        coords = shapely.get_coordinates(shapely.segmentize(left, 0.05))
        distance = shapely.distance(shapely.points(coords), target)
        k = int(np.argmax(distance))
        frame = self._frame(self.wcs)
        low, high = left.bounds[:2], left.bounds[2:]
        corners = [self._part_point(low, frame), self._part_point(high, frame)]
        return MaterialLeft(volume_mm3=pappus(left), area_mm2=float(left.area), max_mm=float(distance[k]),
                            at=tuple(self._part_point(coords[k], frame)),
                            bounds_min=tuple(np.minimum(*corners)), bounds_max=tuple(np.maximum(*corners)))

    def mesh(self):
        if self.material is None or self.material.is_empty:
            return self.stock.vertices, self.stock.triangles
        region = self.material.simplify(max(self.tolerance / 2.0, 0.005), preserve_topology=True)
        return revolve(region, self.w, self.centre, segments=_segments(region))


def _cut_runs(points, kinds, shapes):
    """The region the cutting runs of sampled ``points`` sweep."""
    pieces, run = [], []
    for i in range(1, len(points)):
        kind = int(kinds[i])
        if kind == DWELL:
            continue
        if kind == RAPID:
            if len(run) > 1:
                pieces.append(_sweep(points[run], shapes))
            run = []
            continue
        if not run:
            run = [i - 1]
        run.append(i)
    if len(run) > 1:
        pieces.append(_sweep(points[run], shapes))
    return shapely.union_all(pieces) if pieces else shapely.Polygon()


def _sweep(points, shapes):
    from cadgen._internal.cam.turn_profile import sweep

    return sweep(points, shapes)


def _segments(region) -> int:
    edges = len(shapely.get_coordinates(region))
    segments = 72
    while segments > 24 and edges * segments * 2 > 600_000:
        segments -= 12
    return segments


def revolve(region, w: int, centre, *, segments: int = 72):
    """A closed triangle mesh (part mm) of a half-section region (x = radius, y = the coordinate along axis ``w``)
    turned once about the axis through ``centre``."""
    others = [i for i in range(3) if i != w]
    angles = np.linspace(0.0, 2.0 * math.pi, segments, endpoint=False)
    cos, sin = np.cos(angles), np.sin(angles)
    vertices, triangles = [], []
    offset = 0
    for polygon in shapely.get_parts(region):
        if polygon.geom_type != "Polygon" or polygon.is_empty:
            continue
        polygon = shapely.geometry.polygon.orient(polygon, 1.0)
        for ring in (polygon.exterior, *polygon.interiors):
            coords = np.asarray(ring.coords)[:-1]
            n = len(coords)
            if n < 3:
                continue
            ring_v = np.zeros((n, segments, 3))
            ring_v[:, :, w] = coords[:, 1:2]
            ring_v[:, :, others[0]] = centre[others[0]] + coords[:, 0:1] * cos[None, :]
            ring_v[:, :, others[1]] = centre[others[1]] + coords[:, 0:1] * sin[None, :]
            index = np.arange(n * segments).reshape(n, segments) + offset
            a, b = index, np.roll(index, -1, axis=0)
            a1, b1 = np.roll(a, -1, axis=1), np.roll(b, -1, axis=1)
            tris = np.concatenate([np.stack([a, b, b1], -1).reshape(-1, 3), np.stack([a, b1, a1], -1).reshape(-1, 3)])
            vertices.append(ring_v.reshape(-1, 3))
            triangles.append(tris)
            offset += n * segments
    if not vertices:
        return np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64)
    v = np.vstack(vertices)
    t = np.vstack(triangles).astype(np.int64)
    p = v[t]
    area = np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    t = t[area > 1e-12]
    p = v[t]
    signed = float(np.einsum("ij,ij->i", p[:, 0], np.cross(p[:, 1], p[:, 2])).sum())
    if signed < 0:
        t = t[:, [0, 2, 1]]
    return v, t
