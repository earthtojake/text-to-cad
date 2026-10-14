"""Soundness of a planned toolpath, measured independently of the planner that made it.

* :func:`bad_descents`: every move down into material steeper than the operation's ramp angle. A descent (a rapid, a
  plunge, a feed or a helix's arc whose end is lower than its start) that drops more than ``tan(angle)`` per
  millimetre across must end where the tool's whole circle is in air: above the material's top (the stock top), off
  the stock's footprint (the stock projected down the tool axis), or in stock an earlier cut already took away (swept
  by an earlier move of the setup, at that height or lower, by its own tool), and never on a fixture box standing
  above that height. A ``PLUNGE`` into material is sound only where the operation says it plunged (its
  ``meta["plunges"]`` counts them; the run warns of each). ``excuse`` may pass a descent for a reason of its own; the
  suites write each one out with its reason.
* :func:`rapids_below`: the rapids that move sideways with either end under the retract plane (straight down onto a
  height the planner knows is clear, or straight up, are not counted).
* :func:`rapids_down_beside_stock`: the rapids down beside the stock to under 1 mm over its top: the last
  millimetre is fed.

Reads only the IR (:mod:`cadgen._internal.cam.ir`): the setup's toolpath, its op ranges, the setup's heights, fixtures
and WCS, and the stock.
"""

from __future__ import annotations

import math

__all__ = ["bad_descents", "fixture_boxes", "rapids_below", "stock_outline"]

#: How much of the tool's circle may stand in uncut stock before a descent is into material, mm²: buffered circles and
#: sweeps are polygons, and their slivers are not material.
AREA_MM2 = 1e-3


def stock_outline(setup_plan, stock):
    """The stock's silhouette on the setup's XY plane (WCS), as the planners see it."""
    import shapely

    points = setup_plan.wcs.to_wcs(stock.vertices)[:, :2]
    return shapely.MultiPoint(points).convex_hull


def fixture_boxes(setup_plan) -> list:
    """The setup's fixture keep-outs in its WCS: ``(footprint polygon, z_low, z_high)`` per box."""
    import numpy as np
    import shapely

    out = []
    for box in setup_plan.setup.fixtures:
        low, high = np.asarray(box.min_mm, dtype=float), np.asarray(box.max_mm, dtype=float)
        corners = np.array([[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])
        wcs = setup_plan.wcs.to_wcs(corners)
        out.append((shapely.MultiPoint(wcs[:, :2]).convex_hull, float(wcs[:, 2].min()), float(wcs[:, 2].max())))
    return out


def _op(ops, index):
    return next(op for op in ops if op.index == index)


def bad_descents(setup_plan, ops, index: int, *, stock, angle_deg: float | None = None, excuse=None,
                 tolerance: float = 0.01) -> list[str]:
    """The descents of operation ``index`` (in ``setup_plan``'s toolpath; ``ops`` the run's op plans) that go into
    material too steeply (see the module docstring). ``angle_deg`` defaults to the op's ``ramp_angle_deg``, else 3.
    ``excuse(op, start, end, kind)`` returns the reason a descent into material is sound (it is passed) or None; a
    suite writes each reason out. One line per offending move; empty when sound."""
    import numpy as np
    import shapely

    from cadgen._internal.cam.ir import ARC_CCW, ARC_CW, DWELL, PLUNGE, RAPID

    tp = setup_plan.toolpath
    rng = next(o for o in tp.ops if o.index == index)
    op = _op(ops, index)
    if angle_deg is None:
        params = op.params if isinstance(op.params, dict) else {}
        angle_deg = params.get("ramp_angle_deg") or 3.0
    slope = math.tan(math.radians(angle_deg)) * (1 + 1e-3)
    r = op.tool.radius
    outline = stock_outline(setup_plan, stock)
    stock_top = setup_plan.heights.stock_top
    boxes = fixture_boxes(setup_plan)
    radius_of = {o.index: o.tool.radius for o in ops if o.setup == setup_plan.setup.id and o.tool is not None}

    samples = tp.sample(0.005)
    points, kinds, moves = samples.points, samples.kind, samples.move
    move_op = tp.moves["op"]
    positions = tp.positions()
    # Every cut segment before the op, with its tool's radius: (a (3,), b (3,), radius).
    segments: list[tuple] = []
    cache: list[tuple] = []         # the same, flattened to rows of 7 numbers

    def add_cuts(lo: int, hi: int) -> None:
        """The sampled segments of moves ``[lo, hi)`` that cut (not rapids or dwells)."""
        first = int(np.searchsorted(moves, lo, side="left"))
        last = int(np.searchsorted(moves, hi, side="left"))
        for i in range(max(first, 1), last):
            if kinds[i] in (RAPID, DWELL):
                continue
            radius = radius_of.get(int(move_op[moves[i]]))
            if radius is not None:
                segments.append((points[i - 1], points[i], radius))

    add_cuts(0, rng.start)

    def where(p) -> str | None:
        """None when the tool's circle at ``p`` is in air or already cut; else what it meets."""
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        here = shapely.Point(x, y)
        for footprint, _, high in boxes:
            if high > z + tolerance and footprint.distance(here) < r - tolerance:
                return "a fixture"
        if z >= stock_top - 1e-9:
            return None
        left = here.buffer(r - tolerance, quad_segs=32).intersection(outline)
        if left.area < AREA_MM2:
            return None
        near = []
        if segments:
            if len(cache) < len(segments):
                cache.extend((*a, *b, radius) for a, b, radius in segments[len(cache):])
            seg = np.asarray(cache, dtype=float)
            a, b, radius = seg[:, 0:3].copy(), seg[:, 3:6].copy(), seg[:, 6]
            # Only what a cut swept with its tip at ``z`` or lower took the stock away at ``z``: a segment crossing
            # that height counts from where it crosses it down.
            low = np.minimum(a[:, 2], b[:, 2]) <= z + 1e-6
            dz = np.where(np.abs(b[:, 2] - a[:, 2]) > 1e-12, b[:, 2] - a[:, 2], 1.0)
            cross = np.clip((z - a[:, 2]) / dz, 0.0, 1.0)[:, None]
            at = a + (b - a) * cross
            a = np.where((a[:, 2] > z + 1e-6)[:, None], at, a)
            b = np.where((b[:, 2] > z + 1e-6)[:, None], at, b)
            ab = b[:, :2] - a[:, :2]
            span = np.maximum((ab * ab).sum(axis=1), 1e-18)
            t = np.clip(((np.array([x, y]) - a[:, :2]) * ab).sum(axis=1) / span, 0.0, 1.0)
            gap = np.hypot(*(a[:, :2] + ab * t[:, None] - np.array([x, y])).T)
            keep = low & (gap <= r + radius)
            for s in np.nonzero(keep)[0]:
                line = (shapely.LineString([a[s, :2], b[s, :2]]) if span[s] > 1e-12 else shapely.Point(a[s, :2]))
                near.append(line.buffer(float(radius[s]), quad_segs=32))
        if near:
            left = left.difference(shapely.union_all(near))
        return None if left.area < AREA_MM2 else f"material ({left.area:.3g} mm² of the tool's circle uncut)"

    problems = []
    plunged = 0
    for m in range(rng.start, rng.end):
        kind = int(tp.moves["kind"][m])
        start, end = positions[m], positions[m + 1]
        drop = float(start[2] - end[2])
        if kind in (ARC_CW, ARC_CCW):
            _, radius, sweep, _, _ = tp._arc_geometry(m, start)
            across = abs(sweep) * radius
        else:
            across = float(math.hypot(end[0] - start[0], end[1] - start[1]))
        if drop > 1e-9 and (kind == RAPID or drop > slope * across):
            met = where(end)
            if met is not None and not (excuse is not None and excuse(op, tuple(start), tuple(end), kind)):
                if kind == PLUNGE and met.startswith("material"):
                    plunged += 1
                else:
                    word = ("rapid", "feed", "plunge", "arc", "arc", "dwell")[kind]
                    problems.append(f"{op.spec.op} move {m - rng.start}: {word} down to ({end[0]:.3f}, {end[1]:.3f}, "
                                    f"{end[2]:.3f}) from z {start[2]:.3f} goes into {met}")
        add_cuts(m, m + 1)
    if plunged > int(op.meta.get("plunges", 0)):
        problems.append(f"{op.spec.op}: {plunged} plunge(s) into material, but meta['plunges'] says "
                        f"{op.meta.get('plunges', 0)}")
    return problems


def rapids_below(setup_plan, index: int) -> list[int]:
    """The moves of operation ``index`` (counted from its first) that rapid sideways with either end under the setup's
    retract plane."""
    from cadgen._internal.cam.ir import RAPID

    tp = setup_plan.toolpath
    rng = next(o for o in tp.ops if o.index == index)
    positions = tp.positions()
    retract = setup_plan.heights.retract
    found = []
    for m in range(rng.start, rng.end):
        if int(tp.moves["kind"][m]) != RAPID:
            continue
        a, b = positions[m], positions[m + 1]
        if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6 and min(a[2], b[2]) < retract - 1e-6:
            found.append(m - rng.start)
    return found


def rapids_down_beside_stock(setup_plan, index: int, stock) -> list[int]:
    """The moves of operation ``index`` (counted from its first) that rapid down beside the stock to under 1 mm over
    its top: that descent is fed, so a stock bigger than the job says is met at a feed. (Down into a floor the job
    cut, inside the stock's outline, the planner knows the height.)"""
    import shapely

    from cadgen._internal.cam.ir import RAPID

    tp = setup_plan.toolpath
    rng = next(o for o in tp.ops if o.index == index)
    positions = tp.positions()
    near = setup_plan.heights.stock_top + 1.0
    outline = stock_outline(setup_plan, stock)
    return [m - rng.start for m in range(rng.start, rng.end)
            if int(tp.moves["kind"][m]) == RAPID and positions[m + 1][2] < positions[m][2] - 1e-9
            and positions[m + 1][2] < near - 1e-6
            and not outline.contains(shapely.Point(positions[m + 1][0], positions[m + 1][1]))]
