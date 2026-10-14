"""``gouge`` (2.5D): a cutting move takes the tool into the part beyond tolerance.

For the 2.5D milling and drilling families this compares every cutting sample with the part's sections above the
tool tip: at each height the tool's radius there (:meth:`Tool.radius_at`) must stay at least ``radius - tolerance``
from the material, and the tip must not sit inside it. A flat end mill is judged just above its tip (its radius is
the same all the way up). Any other cutter is judged at a ladder of heights from its tip up its flutes: densely
through its profile (a drill's or a spot drill's cone, a ball's or a bull nose's corner, where the radius grows) and
every millimetre above it, so a drill too big for its hole is caught by its body, not passed by its point. A tap is
judged as its core (the thread's minor diameter, ``d - 1.2269 P``): the thread form cuts the wall on purpose, the
core must not. Heights sit on a 0.05 mm grid (rounded up) and every millimetre, so a few hundred sections cover a
part. The 3D milling family gets the full check
against its drop-cutter (:mod:`._gouge3d`): every feed point on or over the drop-cutter height of the tool inset by the
tolerance.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding, xyz

__all__ = ["run", "FAMILIES"]

#: "Cutting" judges a router's sheet cut (its end mill); beams and wires are not mill tools and are skipped.
FAMILIES = ("2.5D milling", "Cutting")
GRID = 0.05
#: Above its profile a non-flat cutter is judged every this many millimetres up its flutes.
COARSE = 1.0
#: An external ISO thread's minor diameter is ``d - MINOR * P`` (a tap's core).
MINOR = 1.226869


def tap_core_radius(tool) -> float:
    """The radius of a tap's core, the part of it that is not thread form."""
    return max(0.0, tool.diameter_mm - MINOR * tool.pitch_mm) / 2.0


def _profile(tool):
    """``(radius at height h above the tip, the profile's top, the flutes' length)`` of what the check judges."""
    if tool.type == "tap":
        core = tap_core_radius(tool)
        return (lambda h: core if h >= 0 else 0.0), 0.0, tool.flute_length_mm
    if tool.type == "flat":
        return (lambda h: tool.radius if h >= 0 else 0.0), 0.0, 0.0
    # Where the radius stops growing: a cone's full diameter, a ball's or a corner's top.
    top = 0.0
    if tool.type in ("ball",):
        top = tool.radius
    elif tool.type == "bull":
        top = min(tool.corner_radius_mm, tool.radius)
    elif tool.type in ("vee", "chamfer", "engraver", "spot", "drill"):
        import math

        top = max(0.0, tool.radius - tool.tip_diameter_mm / 2.0) / math.tan(tool._half_angle())
    return tool.radius_at, top, max(tool.flute_length_mm, top)


def _ladder(profile_top: float, flutes: float) -> list[float]:
    """Heights over a tip's grid key to judge: dense (doubling from the grid) through the profile, its top, then
    every :data:`COARSE` mm to the flutes' end. Multiples of the grid, so sections are shared across samples."""
    import math

    steps = {GRID}
    h = GRID
    while h < profile_top:
        steps.add(h)
        h *= 2.0
    steps.add(math.ceil(profile_top / GRID) * GRID if profile_top > 0 else GRID)
    h = COARSE
    while h <= flutes + 1e-9:
        steps.add(h)
        h += COARSE
    if flutes > GRID:
        steps.add(math.floor(flutes / GRID) * GRID)
    return sorted(round(v, 6) for v in steps if v <= max(flutes, GRID) + 1e-9)


def run(ctx) -> list[dict]:
    import numpy as np
    import shapely

    from cadgen._internal.cam.ir import RAPID

    out = []
    tol = max(0.02, 2.0 * getattr(ctx.part, "deflection_mm", 0.01), 2.0 * ctx.tolerance_mm)
    from cadgen._internal.cam.checks._gouge3d import MAX_POINTS, gouges_3d

    out.extend(gouges_3d(ctx, tol))
    for op in ctx.ops:
        tool = op.tool
        if tool is None or tool.family != "mill" or op.operation.family not in FAMILIES or op.meta.get("no_gouge_check"):
            continue
        plan = ctx.setup_plan(op.setup)
        if plan.sections is None:
            continue
        if op.end <= op.start:
            continue
        piece = plan.toolpath.slice(op.start, op.end)
        # Every quarter millimetre (half the radius for a big tool), coarser on a path too long to hold that many
        # samples (a tiny tool across a big plate), as the 3D gouge check does.
        length = float(piece.lengths()[piece.moves["kind"] != RAPID].sum())
        samples = piece.sample(ctx.tolerance_mm, max_step_mm=max(0.25, tool.radius / 2.0, length / MAX_POINTS))
        cutting = (samples.kind != RAPID)
        cutting[0] = False
        points = samples.points[cutting]
        if not len(points):
            continue
        top = plan.sections.top
        radius_at, profile_top, flutes = _profile(tool)
        heights = _ladder(profile_top, flutes)
        keys = np.ceil((points[:, 2] + 1e-3) / GRID) * GRID
        worst, at, count = 0.0, None, 0
        bad_any = np.zeros(len(points), dtype=bool)
        for key in np.unique(keys):
            if key > top:
                continue
            members = np.nonzero(keys == key)[0]
            group = points[members]
            for offset in heights:
                level = round(float(key) + offset - GRID, 6)
                if level > top:
                    break
                material = plan.sections.at(level)
                if material.is_empty:
                    continue
                # The cutter's radius at the section's height over each tip (a cone's is smaller near its tip).
                radii = np.array([radius_at(float(h)) for h in level - group[:, 2]])
                distance = shapely.distance(shapely.points(group[:, :2]), material)
                depth = radii - distance
                bad = depth > tol
                if bad.any():
                    bad_any[members[bad]] = True
                    k = int(np.argmax(depth))
                    if depth[k] > worst:
                        worst, at = float(depth[k]), group[k]
        count = int(bad_any.sum())
        if count:
            point = plan.wcs.from_wcs([at])[0]
            out.append(finding(
                "gouge", "error", "gouge_2d",
                f"{op.summary} cuts into the part: up to {worst:.2f} mm too deep at {count} point"
                f"{'s' if count > 1 else ''}",
                "this is a planning fault or a face the operation should not reach: check the faces and the stock to "
                "leave, and report it if the job is right", [{"setup": op.setup, "operation": op.index,
                                                              "depth_mm": round(worst, 3), "count": count,
                                                              "at": xyz(point)}]))
    # Lathe operations: the tool's shape swept through the half-plane against the part's turned section.
    from cadgen._internal.cam.checks._turning import gouges

    out.extend(gouges(ctx))
    return out
