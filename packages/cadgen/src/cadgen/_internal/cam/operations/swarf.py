"""``swarf``: cut a ruled wall with the side of the tool, its axis along the wall's rulings (lite, 5-axis).

Name the walls by ``faces``: planes (tilted or upright), cylinders, cones, and ruled lofts or extrusions (a B-spline
face straight in one direction). Along each wall the planner takes rulings, the straight lines from the wall's foot to
its top, every ``sample_mm`` (default 1 mm):

* a flat wall's rulings (a plane, or a B-spline face that is flat) run up the wall in parallel, the setup's tool
  direction laid onto the plane, clipped to the face's own outline (a trimmed or notched face is followed exactly);
* a curved ruled face's rulings are its straight parameter lines over the face's parameter range.

At each ruling the tool's axis lies along it (from the foot up), its side on the wall (the tip ``radius`` plus
``stock_to_leave_mm`` out along the wall's normal) and its end at the foot. Where the tilted end would dip below the
foot on the side away from the wall (a wall that overhangs), the tool is lifted along its axis just enough, leaving a
strip at the foot (reported). ``stepdown_mm`` splits a tall wall into passes from the top down; one pass by default.
Each pass runs climb (``direction``: ``climb`` or ``conventional``), approached from ``lead_mm`` off the wall, down
its axis from the clearance height, and left the same way.

Every placement is checked against a dense sample of the part's surface: rulings whose flutes would cut into
neighbouring geometry (an inside corner, a floor) are dropped from the pass, and the shank and holder are tested for
collisions (``holder_collision`` findings). The tilt from the setup's tool direction is capped by ``max_tilt_deg``
(default 60) and by the machine's rotary axes and ``rotary_limits_deg``: a wall beyond them is refused in a sentence.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, choice, read_number
from cadgen._internal.cam.operations.base import Operation

__all__ = ["SwarfOp", "rulings"]

RULED = ("plane", "cylinder", "cone", "bspline", "bezier", "extrusion")


def _unit(v):
    import numpy as np

    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n > 1e-12, n, 1.0)


def _flat_normal(ctx, info):
    """The face's normal when its tessellation is flat (a plane, or a B-spline that is one), else None."""
    import numpy as np

    if info.surface == "plane":
        return np.asarray(info.normal, dtype=float)
    vertices = np.asarray(ctx.part.vertices, dtype=float)
    tris = vertices[ctx.face_triangles(info.ref)]
    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    area = np.linalg.norm(normals, axis=1)
    if not len(area) or area.max() <= 0:
        return None
    normals = normals[area > 1e-12] / area[area > 1e-12, None]
    mean = normals.mean(axis=0)
    mean /= max(np.linalg.norm(mean), 1e-12)
    return mean if float((normals @ mean).min()) > 1.0 - 1e-8 else None


def _plane_rulings(ctx, info, up, sample: float, normal):
    """Rulings of a planar wall: (foot (N, 3), top (N, 3), normal (N, 3)), parallel, clipped to the face's outline."""
    import numpy as np
    import shapely

    n = np.asarray(normal, dtype=float)
    d = up - (up @ n) * n
    if np.linalg.norm(d) < 1e-6:
        raise CamJobError(f"{ctx.spec.where}.faces: {info.ref} faces the tool (a floor, not a wall); swarf cuts walls "
                          "with the side of the tool. Use face or pocket for floors")
    d = d / np.linalg.norm(d)
    e = np.cross(d, n)
    vertices = np.asarray(ctx.part.vertices, dtype=float)
    tris = vertices[ctx.face_triangles(info.ref)]
    origin = tris.reshape(-1, 3).mean(axis=0)
    q = np.stack([(tris - origin) @ e, (tris - origin) @ d], axis=-1)
    outline = shapely.union_all([shapely.Polygon(t) for t in q if abs(shapely.Polygon(t).area) > 1e-12])
    lo, hi = float(q[..., 0].min()), float(q[..., 0].max())
    count = max(2, int(math.ceil((hi - lo) / sample)) + 1)
    inset = min(1e-3, (hi - lo) / 10)
    feet, tops = [], []
    v_lo, v_hi = float(q[..., 1].min()) - 1.0, float(q[..., 1].max()) + 1.0
    for s in np.linspace(lo + inset, hi - inset, count):
        cut = outline.intersection(shapely.LineString([(s, v_lo), (s, v_hi)]))
        pieces = [g for g in getattr(cut, "geoms", [cut]) if g.length > 1e-6]
        if not pieces:
            continue
        piece = max(pieces, key=lambda g: g.length)
        ys = [c[1] for c in piece.coords]
        feet.append(origin + s * e + min(ys) * d)
        tops.append(origin + s * e + max(ys) * d)
    if not feet:
        raise CamJobError(f"{ctx.spec.where}.faces: {info.ref} has no wall to follow")
    feet, tops = np.asarray(feet), np.asarray(tops)
    return feet, tops, np.tile(n, (len(feet), 1))


def _surface_rulings(ctx, info, up, sample: float):
    """Rulings of a curved ruled face along its straight parameter direction."""
    import numpy as np
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.TopAbs import TopAbs_REVERSED

    face = ctx.part.ocp_face(info.ordinal)
    surface = BRepAdaptor_Surface(face)
    u0, u1, v0, v1 = BRepTools.UVBounds_s(face)
    if info.surface in ("cylinder", "cone", "extrusion"):
        straight = "v"
    elif surface.VDegree() == 1:
        straight = "v"
    elif surface.UDegree() == 1:
        straight = "u"
    else:
        raise CamJobError(f"{ctx.spec.where}.faces: {info.ref} curves both ways, so no straight line runs up it; swarf "
                          "follows ruled walls (planes, cylinders, cones, ruled lofts). Use surface_normal for it")
    a0, a1 = (u0, u1) if straight == "v" else (v0, v1)
    b0, b1 = (v0, v1) if straight == "v" else (u0, u1)

    def point(s, t):
        p = surface.Value(s, t) if straight == "v" else surface.Value(t, s)
        return np.array([p.X(), p.Y(), p.Z()])

    probe = np.array([point(s, b0) for s in np.linspace(a0, a1, 33)])
    length = float(np.linalg.norm(np.diff(probe, axis=0), axis=1).sum())
    count = max(2, int(math.ceil(length / sample)) + 1)
    feet, tops, normals = [], [], []
    reverse = face.Orientation() == TopAbs_REVERSED
    for s in np.linspace(a0, a1, count):
        p, q = point(s, b0), point(s, b1)
        mid = (b0 + b1) / 2
        pnt, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
        if straight == "v":
            surface.D1(s, mid, pnt, du, dv)
        else:
            surface.D1(mid, s, pnt, du, dv)
        normal = np.cross([du.X(), du.Y(), du.Z()], [dv.X(), dv.Y(), dv.Z()])
        if np.linalg.norm(normal) < 1e-12:
            continue
        normal = normal / np.linalg.norm(normal) * (-1.0 if reverse else 1.0)
        if (q - p) @ up < 0:
            p, q = q, p
        feet.append(p)
        tops.append(q)
        normals.append(normal)
    return np.asarray(feet), np.asarray(tops), np.asarray(normals)


def rulings(ctx, ref: str, up, sample: float):
    """A ruled wall's rulings, ordered along it: ``(foot (N, 3), top (N, 3), outward normal (N, 3))`` in part mm."""
    info = ctx.face(ref)
    if info.surface not in RULED:
        raise CamJobError(f"{ctx.spec.where}.faces: {ref} is a {info.surface}; swarf follows ruled walls ("
                          f"{', '.join(RULED)}). Use surface_normal for doubly curved faces")
    normal = _flat_normal(ctx, info)
    if normal is not None:
        return _plane_rulings(ctx, info, up, sample, normal)
    return _surface_rulings(ctx, info, up, sample)


class SwarfOp(Operation):
    name = "swarf"
    plain = "Swarf"
    family = "Multi-axis"
    machines = ("mill5",)
    status = "lite"
    limits = (
        "Each wall is cut on its own, along rulings sampled every sample_mm; corners between walls are not blended "
        "(an outside corner is left sharp by the two passes, an inside corner keeps what the tool's radius cannot "
        "reach).",
        "A curved wall is followed over its parameter range, so a trimmed curved face can be cut past its edges; the "
        "gouge test drops rulings whose flutes would cut the part, but check the path.",
        "The tool's side meets a twisted (non-developable) ruled wall only along its middle; the error grows with the "
        "twist and is not compensated.",
        "Where the tilted end would dip into the floor the tool is lifted, leaving a strip at the wall's foot.",
        "Moves are the tool tip in the part's frame with A/B/C tilting the tool (tool-centre-point style).",
    )
    keys = ("direction", "max_tilt_deg", "sample_mm", "lead_mm")
    common_keys = ("feed", "speed", "stepdown_mm", "stock_to_leave_mm")
    tool_types = ("flat", "bull")
    takes_faces = True
    feeds_kind = "finish"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        if not spec.faces:
            raise CamJobError(f"{spec.where}: a swarf names the walls it cuts (\"faces\": [\"#o1.f7\"]); "
                              "cadgen cam features lists them")
        extra = spec.extra
        return {
            "climb": choice(extra.get("direction", "climb"), ("climb", "conventional"), f"{spec.where}.direction")
            == "climb",
            "max_tilt_deg": read_number(extra, "max_tilt_deg", spec.where, default=60.0, maximum=90.0),
            "sample_mm": read_number(extra, "sample_mm", spec.where, default=1.0, minimum=0.05, maximum=20.0),
            "lead_mm": read_number(extra, "lead_mm", spec.where, default=2.0, minimum=0.0, maximum=100.0),
        }

    def plan(self, ctx, params):
        import numpy as np

        from cadgen._internal.cam.ir import FEED, RAPID
        from cadgen._internal.cam.multiaxis import (
            MoveList, PointCloud, holder_intrusion, intrusion_findings, rotary_axes, solve_abc, surface_points,
            tool_intrusion,
        )

        tool, wcs = ctx.tool, ctx.wcs
        r = tool.radius
        tol = ctx.tolerance_mm
        leave = ctx.spec.stock_to_leave_mm
        axes = rotary_axes(ctx.machine)
        setup = dict(wcs.rotary_deg)
        setup_abc = [setup.get(a, 0.0) for a in "abc"]
        up = np.asarray(wcs.tool_axis, dtype=float)
        feeds = ctx.feeds("finish")
        points, _ = surface_points(ctx.part.vertices, ctx.part.triangles, min(0.25, max(0.05, r / 6.0)))
        cloud = PointCloud(points, max(r, 1.0))
        gouge_tol = max(0.02, 2 * tol)
        clearance = ctx.heights.clearance

        runs = []                   # (tips (N, 3), axes (N, 3), normals (N, 3)) per pass, part mm
        dropped, worst_lift, worst_tilt = 0, 0.0, 0.0
        findings = []
        for ref in ctx.spec.faces:
            feet, tops, normals = rulings(ctx, ref, up, params["sample_mm"])
            dirs = tops - feet
            lengths = np.linalg.norm(dirs, axis=1)
            keep = lengths > 1e-6
            feet, tops, normals, dirs, lengths = feet[keep], tops[keep], normals[keep], dirs[keep], lengths[keep]
            if not len(feet):
                continue
            dirs = dirs / lengths[:, None]
            tilt = np.degrees(np.arccos(np.clip(dirs @ up, -1.0, 1.0)))
            if tilt.max() > params["max_tilt_deg"] + 1e-6:
                raise CamJobError(f"{ctx.spec.where}.faces: {ref} leans {tilt.max():.1f}° from the setup's tool "
                                  f"direction, more than max_tilt_deg {params['max_tilt_deg']:g}; raise max_tilt_deg "
                                  "(if the machine reaches it) or cut it from a tilted setup")
            worst_tilt = max(worst_tilt, float(tilt.max()))
            # Climb: the wall on the tool's right going along it, travel along n x d.
            travel = feet[-1] - feet[0]
            along = np.cross(normals[len(normals) // 2], dirs[len(dirs) // 2])
            if (travel @ along > 0) != params["climb"]:
                feet, tops, normals, dirs, lengths = feet[::-1], tops[::-1], normals[::-1], dirs[::-1], lengths[::-1]
            # Lift where the tilted end would dip below the foot on the far side of the wall.
            sin_tilt = np.sqrt(np.clip(1.0 - (dirs @ up) ** 2, 0.0, 1.0))
            lift = np.maximum(0.0, r * (sin_tilt - normals @ up)) / np.maximum(dirs @ up, 1e-3)
            worst_lift = max(worst_lift, float(lift.max()))
            base = feet + (r + leave) * normals + lift[:, None] * dirs
            # Rulings whose flutes would cut the part beside the wall are dropped.
            depth, _ = tool_intrusion(cloud, base, dirs, tool, tolerance=gouge_tol)
            good = depth <= 0
            dropped += int((~good).sum())
            if not good.any():
                findings.append({"ref": ref})
                continue
            count = max(1, int(math.ceil(lengths.max() / ctx.spec.stepdown_mm))) if ctx.spec.stepdown_mm else 1
            for j in range(count):
                offset = np.maximum(0.0, lengths - lift) * (1.0 - (j + 1) / count)
                tips = base + offset[:, None] * dirs
                # Contiguous good stretches are passes of their own.
                edges = np.flatnonzero(np.diff(np.r_[0, good.astype(int), 0]))
                for a, b in zip(edges[::2], edges[1::2]):
                    if b - a >= 1:
                        runs.append((tips[a:b], dirs[a:b], normals[a:b]))

        if not runs:
            raise CamJobError(f"{ctx.spec.where}: every ruling of {', '.join(ctx.spec.faces)} would cut into the part "
                              f"beside the wall with {tool.id} ({tool.plain}); use a smaller tool or name other walls")

        # The sequence in part coordinates: (kind, points (N, 3), tool axes (N, 3), feed).
        sequence = []

        def add(kind, pts, dirs, f=0.0):
            sequence.append((kind, np.asarray(pts, dtype=float).reshape(-1, 3),
                             np.asarray(dirs, dtype=float).reshape(-1, 3), f))

        def above(point, d):
            """``point`` moved up its axis ``d`` until it reaches the clearance height (WCS)."""
            zw = float(wcs.to_wcs([point])[0][2])
            dz = float(wcs.vectors_to_wcs([d])[0][2])
            return point + max(0.0, clearance - zw) / max(dz, 0.05) * d

        position = wcs.from_wcs([ctx.start])[0]
        axis_now = up.copy()
        for tips, dirs, normals in runs:
            start = tips[0] + params["lead_mm"] * normals[0]
            high = above(start, dirs[0])
            # Over the approach at the clearance height, tilt there, down the tool's axis, in, along, out, up.
            over = wcs.from_wcs([[*wcs.to_wcs([high])[0][:2], max(clearance, float(wcs.to_wcs([position])[0][2]))]])[0]
            add(RAPID, over, axis_now)
            add(RAPID, over, dirs[0])
            add(RAPID, high, dirs[0])
            near = start + min(2.0, float(np.linalg.norm(high - start))) * dirs[0]
            add(RAPID, near, dirs[0])
            add(FEED, start, dirs[0], feeds.plunge_mm_min)
            add(FEED, tips, dirs, feeds.feed_mm_min)
            end = tips[-1] + params["lead_mm"] * normals[-1]
            add(FEED, end, dirs[-1], feeds.feed_mm_min)
            position = above(end, dirs[-1])
            add(RAPID, position, dirs[-1])
            axis_now = dirs[-1]
        add(RAPID, position, up)

        all_dirs = np.vstack([d for _, _, d, _ in sequence])
        abc = solve_abc(all_dirs, ctx.machine, wcs=wcs, previous={a: setup.get(a, 0.0) for a in axes})
        if np.isnan(abc).any():
            raise CamJobError(f"{ctx.spec.where}: this mill5's rotary axes cannot tilt the tool along the rulings of "
                              f"{', '.join(ctx.spec.faces)} (check machine.rotary_limits_deg and the setup's "
                              "orientation)")
        moves = MoveList(ctx.start, setup_abc, axes, op=ctx.index)
        row = 0
        for kind, pts, _, f in sequence:
            moves.polyline(kind, wcs.to_wcs(pts), abc[row:row + len(pts)], f=f)
            row += len(pts)
        path = moves.build()

        # The shank and holder against the part, at every cutting placement.
        tips_all = np.vstack([t for t, _, _ in runs])
        dirs_all = np.vstack([d for _, d, _ in runs])
        depth, where = holder_intrusion(cloud, tips_all, dirs_all, tool, clearance=gouge_tol)
        found = intrusion_findings(ctx, self.summary(ctx, params), depth, where, check="holder_collision")
        if findings:
            found += [_skipped(ctx, self, [f["ref"] for f in findings])]
        if found:
            ctx.meta.setdefault("findings", []).extend(found)
        ctx.meta.update({"passes": len(runs), "max_tilt_deg": round(worst_tilt, 3), "stock_to_leave": leave})
        notes = []
        if dropped:
            ctx.meta["dropped_rulings"] = dropped
            notes.append(f"{dropped} ruling(s) skipped where the flutes would cut the part beside the wall")
        if worst_lift > tol:
            ctx.meta["foot_strip_mm"] = round(worst_lift, 3)
            notes.append(f"lifted up to {worst_lift:.2f} mm at the wall's foot so the tilted end clears the floor")
        if notes:
            ctx.meta["note"] = "; ".join(notes)
        return path


def _skipped(ctx, operation, refs) -> dict:
    from cadgen._internal.cam.checks.base import finding

    return finding("gouge", "warning", "swarf_skipped",
                   f"{operation.plain} skipped {', '.join(refs)}: every ruling would cut into the part beside it",
                   "use a smaller tool or cut those walls another way",
                   [{"setup": ctx.setup.id, "operation": ctx.index, "faces": list(refs)}])
