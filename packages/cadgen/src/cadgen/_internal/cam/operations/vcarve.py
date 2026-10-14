"""``vcarve`` (V-carve): carve closed shapes with a V-bit along their medial axis, the cone's edge on the outline.

What it carves, one of:

* ``dxf``: a DXF's closed profiles (path relative to the job file, else to the part; or absolute), even-odd filled
  (a letter's counter is a hole), placed with the DXF's origin at ``origin_mm`` ``[x, y]`` in the setup's WCS (default
  ``[0, 0]``); its ``$INSUNITS`` are honoured, open curves that close nothing and annotation are skipped and counted
  in the note (:func:`~cadgen._internal.cam.part.read_dxf_drawing`);
* ``faces``: flat faces facing the tool: each face's own area (its outline and holes), carved from its height;
* ``region``: ``{"polygon": [[x, y], ...]}``: the polygon.

How: the shape's medial axis (the centres of the largest circles inside it) is read from a Voronoi diagram of its
outline sampled every :data:`SPACING_MM` (finer in a small shape, coarser on a very long outline), pruned of the
branches a wider circle beside them already covers, and run on into the convex corners it points at. Along it the
tool's tip goes ``(distance to the outline - tip radius) / tan(half angle)`` below ``surface_z`` (default: the named
face's height, else the part's top): the cone's edge just touches the outline, so the walls come out as sharp Vs
and a narrow stroke is shallow, a wide one deep. ``max_depth_mm`` caps it: where the shape is wider than the cone
at that depth, the V-bit also runs the outline inset ``tip radius + max_depth x tan(half angle)`` at that depth
(the walls' foot), and the flat bottom inside is left for a separate clearing operation (a ``pocket`` with a flat
tool on that inset region): this operation has one tool. ``stepdown_mm`` (optional; default one pass) carves in
levels no deeper than it each.

Entries: every run starts where the tool already is, or comes straight down onto a point at the surface (the
axis runs out into the shape's corners at the surface) or onto one this carve already cut at least as deep, nearest
first; a run with no such end (a ring's axis, a round end's) is entered by zig-zagging down along itself from the
surface (or from as deep as it is already cut there), never below the carve, no steeper than the cone's flank; a
round shape, whose axis is one point, is entered by a spiral in to it along the cone. So the tip never meets
material steeper than its own cone's side. The surface must be clear: a carve of the part's top under uncut
stock is refused (``unreachable``; face it first).

Refused, as plan errors: no closed shape, or every shape too small to carve (``empty_operation``); every shape
narrower than the tool's tip (``tool_too_large``); a shape wider than the cone is tall with no ``max_depth_mm``
(``tool_too_small``); a ``max_depth_mm`` deeper than the cone, or a carve past the flutes (``too_deep``). The facts:
``shapes``, ``runs``, ``levels``, ``length_mm``, ``max_depth_mm``, ``entries``, and with a flat bottom
``flat_bottom_z``, ``flat_inset_mm`` and ``flat_area_mm2``.

The part as modelled has no carving, so this cuts into it by design: the ``gouge`` check does not judge it.
"""

from __future__ import annotations

import math
from pathlib import Path

from cadgen._internal.cam.job_errors import CamJobError, PlanError, number_list, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["VCarveOp", "medial_axis"]

#: How far apart the outline is sampled for the medial axis (mm): finer in a shape whose widest circle is under five
#: of these, coarser past :data:`MAX_SAMPLES` points on one shape.
SPACING_MM = 0.1
MAX_SAMPLES = 20_000
#: The longest step along a carved run (mm): its depth is read from the outline at least this often.
STEP_MM = 0.2


class VCarveOp(Operation):
    name = "vcarve"
    plain = "V-carve"
    family = "2.5D milling"
    machines = MILLS
    status = "lite"
    limits = (
        "a shape wider than the cone at max_depth_mm keeps a flat bottom the V-bit does not clear (the V-bit cuts its "
        "walls and their foot): clear it with a pocket and a flat tool on the outline inset by the facts' "
        "flat_inset_mm, down to flat_bottom_z (a DXF shape's inset needs its outline as a region)",
        "the medial axis is read from the outline sampled every 0.1 mm (finer in small shapes, coarser on outlines "
        "over 2 m): the depth at each point is exact for where the point is, the axis within about that spacing",
    )
    keys = ("dxf", "origin_mm", "max_depth_mm", "surface_z")
    common_keys = ("feed", "speed", "stepdown_mm")
    tool_types = ("vee", "engraver", "chamfer")
    takes_faces = True
    takes_region = True
    feeds_kind = "engrave"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        extra = spec.extra
        where = spec.where
        given = sum(1 for present in (bool(spec.faces), spec.region is not None, "dxf" in extra) if present)
        if given != 1:
            raise CamJobError(f"{where}: a vcarve needs one of \"dxf\" (a drawing's closed profiles), \"faces\" (flat "
                              "faces facing the tool) or \"region\" ({\"polygon\": [[x, y], ...]})")
        if "dxf" in extra and (not isinstance(extra["dxf"], str) or not extra["dxf"].strip()):
            raise CamJobError(f"{where}.dxf must be the DXF's path, relative to the job file or the part")
        if "origin_mm" in extra and "dxf" not in extra:
            raise CamJobError(f"{where}.origin_mm places a DXF; remove it, or give \"dxf\"")
        region = None
        if spec.region is not None:
            region = region_polygon(spec, where=where)
            if region[1] is not None:
                raise CamJobError(f"{where}.region.bottom_z: a vcarve's depth comes from the cone and the shape's "
                                  "width; remove bottom_z (cap the depth with max_depth_mm, and give the surface with "
                                  "surface_z)")
        return {
            "dxf": extra.get("dxf"),
            "origin_mm": number_list(extra["origin_mm"], f"{where}.origin_mm", length=2) if "origin_mm" in extra
            else (0.0, 0.0),
            "max_depth_mm": read_number(extra, "max_depth_mm", where),
            "surface_z": read_number(extra, "surface_z", where, minimum=-1e6),
            "region": None if region is None else region[0],
            "base_dir": ctx.job.base_dir,
        }

    def _shapes(self, ctx, params):
        """([(polygon, surface z)], notes): what is carved, each from its own surface."""
        from cadgen._internal.cam import geom2d

        notes = []
        given_z = params["surface_z"]
        if params["dxf"] is not None:
            from shapely import affinity

            from cadgen._internal.cam.part import read_dxf_drawing, skipped_words

            path = Path(params["dxf"]).expanduser()
            if not path.is_absolute():
                bases = [params["base_dir"]] if params["base_dir"] is not None else []
                bases.append(Path(ctx.part.document).resolve().parent)
                path = next((base / path for base in bases if (base / path).is_file()), bases[0] / path)
            if not path.is_file():
                raise CamJobError(f"{ctx.spec.where}.dxf: no DXF at {path}; give its path relative to the job file or "
                                  "the part")
            polygons, skipped = read_dxf_drawing(path, tolerance_mm=ctx.tolerance_mm)
            if skipped:
                notes.append(skipped_words(path.name, skipped))
            ox, oy = params["origin_mm"]
            polygons = [affinity.translate(p, ox, oy) for p in polygons]
            if not polygons:
                raise PlanError("empty_operation", f"{ctx.spec.where}.dxf: {path.name} has no closed profile to carve "
                                "(a V-carve fills closed shapes: close the outlines, or engrave open curves with an "
                                "engrave)")
            z = given_z if given_z is not None else ctx.heights.part_top
            return [(p, z) for p in polygons], notes
        if params["region"] is not None:
            return [(params["region"], given_z if given_z is not None else ctx.heights.part_top)], notes
        from cadgen._internal.cam.operations.engrave import _flat_face

        shapes = []
        for ref in ctx.spec.faces:
            z, footprint = _flat_face(ctx, ref)
            shapes.extend((polygon, given_z if given_z is not None else z) for polygon in geom2d.polygons_of(footprint))
        return shapes, notes

    def plan(self, ctx, params):
        import numpy as np

        from cadgen._internal.cam import geom2d
        from cadgen._internal.cam.operations._milling2d import levels, lift_and_go

        tool = ctx.tool
        heights = ctx.heights
        tol = ctx.tolerance_mm
        where = ctx.spec.where
        half = math.radians((tool.angle_deg or 90.0) / 2.0)
        tan = math.tan(half)
        tip = tool.tip_diameter_mm / 2.0
        cone_height = (tool.radius - tip) / tan
        cap = params["max_depth_mm"]
        shapes, notes = self._shapes(ctx, params)
        for _, surface in shapes:
            _check_faced(ctx, surface)

        carved, small = [], 0
        for polygon, surface in shapes:
            axis = medial_axis(polygon, tolerance=tol)
            widest = max(float(chain[:, 2].max()) for chain in axis)
            if widest - tip <= tol:
                small += 1
                continue
            carved.append((polygon, surface, axis, widest))
        if not carved:
            if tip > tol:
                raise PlanError("tool_too_large", f"{where}: every shape is narrower than {tool.id}'s "
                                f"{tool.tip_diameter_mm:g} mm tip, so the V-bit carves nothing; use a V-bit with a "
                                "finer tip, or engrave the outlines")
            raise PlanError("empty_operation", f"{where}: every shape is too small to carve (under "
                            f"{2 * (tip + tol):.2g} mm across)")
        if small:
            notes.append(f"{small} shape(s) narrower than {tool.id}'s tip are not carved")

        deepest = max((widest - tip) / tan for _, _, _, widest in carved)
        reach = deepest if cap is None else min(cap, deepest)
        if reach > cone_height + tol:
            if cap is not None and cap > cone_height + tol:
                raise PlanError("too_deep", f"{where}.max_depth_mm: {cap:g} mm is deeper than {tool.id}'s cone "
                                f"({cone_height:.3g} mm from its tip to its full {tool.diameter_mm:g} mm), so the "
                                f"shank would cut the walls; give max_depth_mm up to {cone_height:.3g}")
            raise PlanError("tool_too_small", f"{where}: the widest shape needs a {deepest:.3g} mm deep carve, and "
                            f"{tool.id}'s cone is {tool.diameter_mm:g} mm across at {cone_height:.3g} mm deep; give "
                            f"max_depth_mm up to {cone_height:.3g} (the flat bottom left for a pocket), or use a wider "
                            "V-bit")
        if reach > tool.flute_length_mm + tol:
            raise PlanError("too_deep", f"{where}: the carve is {reach:.3g} mm deep, past {tool.id}'s "
                            f"{tool.flute_length_mm:g} mm flutes; give max_depth_mm up to {tool.flute_length_mm:g}")

        # Each shape's runs: the axis at the cone's depth (capped), and, where the cap leaves a flat bottom, the
        # inset outline at the cap.
        step = ctx.spec.stepdown_mm
        work = []                 # (shape index, surface, runs [(N, 3) arrays at their full depth], levels)
        flat_area, flat_z = 0.0, None
        slack = tol / 10.0        # how far the cone may stray past the outline between two points of a run, across
        for index, (polygon, surface, axis, widest) in enumerate(carved):
            boundary = polygon.boundary
            runs = []
            for chain in axis:
                xy = chain[:, :2] if len(chain) > 1 else _spiral(polygon, chain[0, :2], tip, tan, tol)
                runs.append(_carve(boundary, _densify(xy, STEP_MM), surface, tip, tan, cap, slack))
            if cap is not None and (widest - tip) / tan > cap + tol:
                inset = tip + cap * tan
                flat = geom2d.offset(polygon, -inset, tolerance=tol)
                for ring in geom2d.rings(flat):
                    runs.append(_carve(boundary, _densify(ring[:, :2], STEP_MM), surface, tip, tan, cap, slack))
                floor = geom2d.offset(polygon, -cap * tan, tolerance=tol)
                flat_area += float(floor.area)
                flat_z = surface - cap if flat_z is None else min(flat_z, surface - cap)
            bottom = float(min(run[:, 2].min() for run in runs))
            cut_levels = levels(surface, bottom, step) if step is not None else [bottom]
            work.append((index, surface, runs, cut_levels))

        feeds = ctx.feeds(self.feeds_kind)
        flank = math.degrees(math.atan(1.0 / tan))
        b = ctx.builder()
        cut: dict = {}            # (shape, x, y) -> the deepest z this carve has cut there
        entries = {"joined": 0, "surface": 0, "cut": 0, "ramp": 0}
        count, length, plunges = 0, 0.0, 0
        for k in range(max(len(item[3]) for item in work)):
            pending = []
            for index, surface, runs, cut_levels in work:
                if k >= len(cut_levels):
                    continue
                previous = surface if k == 0 else cut_levels[k - 1]
                for run in runs:
                    pending.extend((index, surface, piece) for piece in _deeper(run, previous, cut_levels[k]))
            while pending:
                index, surface, run, closed, how = _nearest(pending, b.pos, cut, tol)
                if how != "joined":
                    if b.pos[2] < heights.retract:
                        b.rapid(z=heights.retract)
                    lift_and_go(b, run[0], heights)
                    top = cut.get(_key(index, run[0]))
                    if how == "ramp":
                        top = surface if top is None else top
                        b.feed(z=max(top, float(run[0, 2])), f=feeds.plunge_mm_min)
                        points = _ramp(run, top, flank)
                        if points:
                            b.polyline(np.asarray(points), f=feeds.ramp_mm_min)
                        else:
                            b.plunge(z=float(run[0, 2]), f=feeds.plunge_mm_min)
                            plunges += 1
                    else:
                        b.feed(z=float(run[0, 2]), f=feeds.plunge_mm_min)
                entries[how] += 1
                b.polyline(run[1:], f=feeds.feed_mm_min)
                count += 1
                length += float(np.linalg.norm(np.diff(run, axis=0), axis=1).sum())
                for point in run:
                    key = _key(index, point)
                    cut[key] = min(float(point[2]), cut.get(key, math.inf))
        b.rapid(z=heights.retract)
        b.rapid(z=heights.clearance)

        depth_reached = max(surface - float(min(run[:, 2].min() for run in runs)) for _, surface, runs, _ in work)
        words = [f"V-carves {len(carved)} shape(s) up to {depth_reached:.3g} mm deep with the {tool.plain}, the cone's "
                 "edge on the outline, into the modelled surface (not judged by the gouge check)"]
        level = "warning" if notes else "info"
        if flat_z is not None:
            words.append(f"the flat bottom at Z {flat_z:.4g} ({flat_area:.3g} mm², inside the outline inset "
                         f"{cap * tan:.3g} mm) is left for a separate clearing operation: a pocket with a flat tool "
                         f"on that inset region down to Z {flat_z:.4g}")
            level = "warning"
        if plunges:
            ctx.meta["plunges"] = plunges
        ctx.meta.update({
            "shapes": len(carved), "runs": count, "levels": max(len(item[3]) for item in work),
            "length_mm": round(length, 2), "max_depth_mm": round(depth_reached, 4),
            "entries": {key: value for key, value in entries.items() if value},
            "no_gouge_check": True, "note_level": level, "note": "; ".join(words + notes),
        })
        if flat_z is not None:
            ctx.meta.update({"flat_bottom_z": round(flat_z, 4), "flat_inset_mm": round(cap * tan, 4),
                             "flat_area_mm2": round(flat_area, 3)})
        return b.build()


def _check_faced(ctx, surface: float) -> None:
    """Refuse a carve of the part's top while stock still stands over it: its entries come down onto the surface.
    Clear when the stock's top is at or under the surface, or an earlier ``face`` in this setup took the whole stock
    down to it (its ``faced_z``). A face below the part's top is the job's to have cleared (a pocket before it)."""
    heights = ctx.heights
    tol = ctx.tolerance_mm
    if heights.stock_top <= surface + tol or surface < heights.part_top - tol:
        return
    faced = [op.meta["faced_z"] for _, path in ctx.history for op in path.ops
             if op.setup == ctx.setup.id and op.op == "face" and op.meta.get("faced_z") is not None]
    if faced and min(faced) <= surface + tol:
        return
    raise PlanError("unreachable", f"{ctx.spec.where}: the V-carve starts from the surface at Z {surface:.3f}, and the "
                    f"stock still stands {heights.stock_top - surface:.3g} mm over it; face the stock first (a face of "
                    "the whole stock before this operation, in the same setup), or give surface_z at the stock's top")


def _depth(boundary, xy, tip: float, tan: float, cap: float | None):
    """How deep the tip goes at each point so the cone's edge touches ``boundary``: ``(distance - tip) / tan``, at
    least 0, at most ``cap``."""
    import numpy as np
    import shapely

    distance = shapely.distance(shapely.points(np.asarray(xy, dtype=float)), boundary)
    depth = np.maximum(0.0, (distance - tip) / tan)
    return depth if cap is None else np.minimum(depth, cap)


def _carve(boundary, xy, surface: float, tip: float, tan: float, cap: float | None, slack: float):
    """The run over ``xy`` (N, 2) as (N', 3) at the cone's depth, with points added where a straight move between
    two would take the cone more than ``slack`` (mm, across) past the outline: the depth is not straight between
    points (it kinks where the tip's flat meets the outline, and bends round a corner of it)."""
    import numpy as np

    xy = np.asarray(xy, dtype=float)
    depth = _depth(boundary, xy, tip, tan, cap)
    for _ in range(12):
        middle = 0.5 * (xy[:-1] + xy[1:])
        allowed = _depth(boundary, middle, tip, tan, cap)
        over = (0.5 * (depth[:-1] + depth[1:]) - allowed) * tan > slack
        if not over.any():
            break
        at = np.nonzero(over)[0] + 1
        xy = np.insert(xy, at, middle[over], axis=0)
        depth = np.insert(depth, at, allowed[over])
    return np.column_stack([xy, surface - depth])


def _densify(xy, step: float):
    """``xy`` (N, 2) with points added so no step is longer than ``step``."""
    import numpy as np

    xy = np.asarray(xy, dtype=float)
    out = [xy[:1]]
    for a, b in zip(xy[:-1], xy[1:]):
        n = max(1, int(math.ceil(float(np.hypot(*(b - a))) / step - 1e-9)))
        t = (np.arange(1, n + 1) / n)[:, None]
        out.append(a + (b - a) * t)
    return np.vstack(out)


def _spiral(polygon, centre, tip: float, tan: float, tol: float):
    """A round shape's carve (its axis one point): two turns spiralling in to ``centre`` from where the cone first
    touches the outline, so it comes down along the cone instead of plunging. Just the centre when that is within
    ``tol`` of the surface."""
    import numpy as np
    import shapely
    from shapely.ops import nearest_points

    start = float(polygon.boundary.distance(shapely.Point(centre))) - tip
    if start / tan <= tol:
        return np.asarray([centre], dtype=float)
    near = nearest_points(shapely.Point(centre), polygon.boundary)[1]
    a0 = math.atan2(near.y - centre[1], near.x - centre[0])
    turns = 2
    count = turns * max(24, int(math.ceil(2 * math.pi * start / STEP_MM)))
    f = np.arange(count + 1) / count
    rho = start * (1.0 - f)
    angle = a0 + 2 * math.pi * turns * f
    return np.column_stack([centre[0] + rho * np.cos(angle), centre[1] + rho * np.sin(angle)])


def _deeper(run, previous: float, level: float) -> list:
    """The pieces of ``run`` ((N, 3) at full depth) still to cut between ``previous`` (the level above) and
    ``level``: its stretches deeper than ``previous``, each with the point either side (already cut at its own
    depth), held no deeper than ``level``. ``[(piece, closed)]``; a closed run deeper than ``previous`` all round is
    one closed piece."""
    import numpy as np

    closed = len(run) > 2 and float(np.hypot(*(run[0, :2] - run[-1, :2]))) < 1e-9
    deep = run[:, 2] < previous - 1e-9
    if not deep.any():
        return []
    if closed:
        if deep.all():
            return [(np.column_stack([run[:, :2], np.maximum(run[:, 2], level)]), True)]
        body = run[:-1]
        k = int(np.argmax(body[:, 2]))             # start where it is shallowest, so no stretch wraps round
        run = np.vstack([body[k:], body[:k], body[k:k + 1]])
        deep = run[:, 2] < previous - 1e-9
    pieces = []
    i, n = 0, len(run)
    while i < n:
        if not deep[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and deep[j + 1]:
            j += 1
        lo, hi = max(i - 1, 0), min(j + 1, n - 1)
        piece = run[lo:hi + 1]
        pieces.append((np.column_stack([piece[:, :2], np.maximum(piece[:, 2], level)]), False))
        i = j + 1
    return pieces


def _key(index: int, point) -> tuple:
    return (index, round(float(point[0]), 6), round(float(point[1]), 6))


def _nearest(pending: list, here, cut: dict, tol: float):
    """Take the next run from ``pending`` (``(shape, surface, (run, closed))``): one starting where the tool is,
    else the nearest that starts open (at the surface, or where this carve has cut at least as deep), else the
    nearest, to be ramped into. An open run may be cut from either end, a closed one from its point nearest the
    tool. ``(shape, surface, run, closed, how)``, how one of joined, surface, cut, ramp."""
    import numpy as np

    from cadgen._internal.cam.operations._milling2d import rotate_to_nearest

    best = None
    for i, (index, surface, (run, closed)) in enumerate(pending):
        if closed:
            ring = rotate_to_nearest(run, here[:2])
            options = [ring]
        else:
            options = [run, run[::-1]]
        for path in options:
            start = path[0]
            gap = float(np.hypot(start[0] - here[0], start[1] - here[1]))
            if gap < 1e-6 and abs(float(start[2]) - here[2]) < 1e-6:
                rank, how = 0, "joined"
            elif float(start[2]) >= surface - tol:
                rank, how = 1, "surface"
            elif cut.get(_key(index, start), math.inf) <= float(start[2]) + 1e-9:
                rank, how = 1, "cut"
            else:
                rank, how = 2, "ramp"
            candidate = (rank, gap, i)
            if best is None or candidate < best[0]:
                best = (candidate, path, how)
    (_, _, i), path, how = best
    index, surface, (_, closed) = pending.pop(i)
    return index, surface, path, closed, how


def _ramp(run, top: float, flank_deg: float) -> list:
    """Down from ``top`` over the run's start to the start itself, back and forth along the run, never below it, no
    steeper than the cone's flank (:func:`~cadgen._internal.cam.linking.ramp_points`)."""
    from cadgen._internal.cam.linking import ramp_points

    return ramp_points(run, top, angle_deg=flank_deg)


def medial_axis(polygon, *, tolerance: float = 0.01, spacing: float = SPACING_MM) -> list:
    """The medial axis of a shapely Polygon (holes allowed) as chains, each an (N, 3) array of ``x, y, r`` (``r`` the
    distance to the outline there); one chain of one point (the shape's pole) when nothing is left of it (a circle).

    The outline is sampled every ``spacing`` (finer when the widest circle is under five of it, coarser past
    :data:`MAX_SAMPLES` points); the Voronoi edges wholly inside the shape are its axis. Edges shorter than a
    hundredth of the spacing are merged (sampled outlines put many Voronoi vertices on one point), branches whose
    every circle lies within ``tolerance`` inside the circle where they join are pruned (they carve nothing that
    circle does not), and a branch ending within a few samples of a convex corner runs on into it."""
    import numpy as np
    import shapely
    from shapely.ops import polylabel

    pole = polylabel(polygon, tolerance=max(tolerance, 1e-4))
    widest = float(polygon.boundary.distance(pole))
    perimeter = float(polygon.boundary.length)
    spacing = max(min(spacing, widest / 5.0), perimeter / MAX_SAMPLES, 1e-3)
    rings = [np.asarray(polygon.exterior.coords)[:, :2]] + [np.asarray(r.coords)[:, :2] for r in polygon.interiors]
    samples = []
    for ring in rings:
        for a, b in zip(ring[:-1], ring[1:]):
            n = max(1, int(math.ceil(float(np.hypot(*(b - a))) / spacing - 1e-9)))
            samples.append(a + (b - a) * (np.arange(n) / n)[:, None])
    points = np.unique(np.round(np.vstack(samples), 9), axis=0)
    single = [np.asarray([[pole.x, pole.y, widest]])]
    if len(points) < 3:
        return single
    edges = shapely.get_parts(shapely.voronoi_polygons(shapely.multipoints(points), only_edges=True))
    shapely.prepare(polygon)
    edges = edges[shapely.contains(polygon, edges)]
    if not len(edges):
        return single
    ends = shapely.get_coordinates(edges).reshape(-1, 2, 2)                       # (E, 2, 2): two-point edges
    # Nodes: endpoints on a fine grid, then edges shorter than a hundredth of the spacing merged (union-find).
    grid = spacing / 1000.0
    flat = np.round(ends.reshape(-1, 2) / grid).astype(np.int64)
    _, ids = np.unique(flat, axis=0, return_inverse=True)
    ids = ids.reshape(-1, 2)
    parent = list(range(int(ids.max()) + 1))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    lengths = np.hypot(*(ends[:, 1] - ends[:, 0]).T)
    for (a, b), length in zip(ids, lengths):
        if length < spacing / 100.0:
            ra, rb = find(int(a)), find(int(b))
            if ra != rb:
                parent[rb] = ra
    roots = np.asarray([find(i) for i in range(len(parent))])
    position: dict = {}
    for (a, b), (pa, pb) in zip(ids, ends):
        position.setdefault(int(roots[a]), pa)
        position.setdefault(int(roots[b]), pb)
    graph: dict = {}
    for a, b in ids:
        ra, rb = int(roots[a]), int(roots[b])
        if ra != rb:
            graph.setdefault(ra, set()).add(rb)
            graph.setdefault(rb, set()).add(ra)
    if not graph:
        return single
    nodes = sorted(graph)
    radius = dict(zip(nodes, shapely.distance(shapely.points(np.asarray([position[n] for n in nodes])),
                                              polygon.boundary).tolist()))

    def covered(group, centre) -> bool:
        """Every circle of ``group`` (nodes) within ``tolerance`` inside the circle at ``centre``."""
        xy = np.asarray([position[p] for p in group])
        r = np.asarray([radius[p] for p in group])
        return bool(np.all(r + np.hypot(*(xy - position[centre]).T) <= radius[centre] + tolerance))

    # Peel the leaves: a leaf whose circle (and every circle peeled into it) lies inside its neighbour's goes into it.
    absorbed: dict = {node: [] for node in graph}
    leaves = [node for node in nodes if len(graph[node]) == 1]
    while leaves:
        leaf = leaves.pop()
        if len(graph.get(leaf, ())) != 1:
            continue
        (near,) = graph[leaf]
        group = absorbed[leaf] + [leaf]
        if not covered(group, near):
            continue
        graph[near].discard(leaf)
        del graph[leaf]
        absorbed[near].extend(group)
        if len(graph[near]) == 1:
            leaves.append(near)
    graph = {node: near for node, near in graph.items() if near}
    if not graph:
        return single
    best = max(graph, key=lambda n: radius[n])
    if covered(list(graph), best):
        return single
    # A branch that ends next to a convex corner runs on into it (the corner is at the surface).
    corners = np.vstack([ring[:-1] for ring in rings])
    out = []
    for chain in _chains(graph):
        xy = [position[n] for n in chain]
        r = [radius[n] for n in chain]
        if chain[0] != chain[-1]:
            for at_end in (False, True):
                node = chain[-1] if at_end else chain[0]
                if len(graph[node]) != 1 or radius[node] > 2 * spacing:
                    continue
                gaps = np.hypot(*(corners - position[node]).T)
                k = int(np.argmin(gaps))
                if gaps[k] <= 3 * spacing and polygon.covers(shapely.LineString([position[node], corners[k]])):
                    if at_end:
                        xy.append(corners[k])
                        r.append(0.0)
                    else:
                        xy.insert(0, corners[k])
                        r.insert(0, 0.0)
        out.append(np.column_stack([np.asarray(xy, dtype=float), np.asarray(r, dtype=float)]))
    return out


def _chains(graph: dict) -> list:
    """The graph's edges as node chains between nodes that are not simple links (ends and junctions); a loop of
    simple links on its own is one chain that ends where it starts."""
    used: set = set()
    chains = []

    def walk(start, nxt):
        chain = [start, nxt]
        used.add(frozenset((start, nxt)))
        while len(graph[chain[-1]]) == 2 and chain[-1] != start:
            ahead = [n for n in graph[chain[-1]] if frozenset((chain[-1], n)) not in used]
            if not ahead:
                break
            used.add(frozenset((chain[-1], ahead[0])))
            chain.append(ahead[0])
        return chain

    for start in sorted(n for n, near in graph.items() if len(near) != 2):
        for nxt in sorted(graph[start]):
            if frozenset((start, nxt)) not in used:
                chains.append(walk(start, nxt))
    for start in sorted(graph):
        for nxt in sorted(graph[start]):
            if frozenset((start, nxt)) not in used:
                chains.append(walk(start, nxt))
    return chains
