"""``prepared_hole``: a tap or an internal thread mill works a hole no earlier operation of the job made.

The stock starts solid where the part has a hole, so a tap needs its tap drill, and an internal thread mill its
bore, from an operation before it (in program order, across setups). The job may mean a hole made before it runs
(a casting, a blank from STEP, an earlier job): the warning (``assumes_prepared_hole``) says so, never a silent
pass. An earlier operation made the hole when its cutting moves reach three quarters of the way down the hole's
axis inside its radius; a spot drill's cone does not. From the parallel cam build.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding, xyz

__all__ = ["run"]


def _needs(ctx, op) -> list[tuple]:
    """``(top, bottom, radius)`` in part mm for every hole ``op`` threads."""
    import numpy as np

    plan = ctx.setup_plan(op.setup)
    holes = []
    if op.tool is not None and op.tool.type == "tap":
        for event in plan.toolpath.events:
            if event.kind == "cycle" and event.data.get("cycle") == "tap" and op.start <= event.at < op.end:
                for x, y, top in event.data.get("holes", ()):
                    holes.append(((x, y, top), (x, y, event.data["z_bottom"]), op.tool.diameter_mm / 2.0))
    for x, y, top, bottom, diameter in op.meta.get("needs_holes", ()) or ():
        holes.append(((x, y, top), (x, y, bottom), diameter / 2.0))
    out = []
    for top, bottom, radius in holes:
        a, b = plan.wcs.from_wcs(np.array([top, bottom], dtype=float))
        out.append((a, b, radius))
    return out


def _made(ctx, hole, before) -> bool:
    import numpy as np

    from cadgen._internal.cam.ir import DWELL, RAPID

    top, bottom, radius = hole
    axis = bottom - top
    length = float(np.linalg.norm(axis))
    if length <= 1e-9:
        return True
    axis = axis / length
    for op in before:
        plan = ctx.setup_plan(op.setup)
        if plan.toolpath is None or op.end <= op.start:
            continue
        samples = plan.toolpath.sample(max(ctx.tolerance_mm, 0.05), max_step_mm=max(0.5, radius))
        mask = (samples.op == op.index) & (samples.kind != RAPID) & (samples.kind != DWELL)
        if not mask.any():
            continue
        points = plan.wcs.from_wcs(samples.points[mask]) - top
        along = points @ axis
        off = np.linalg.norm(points - np.outer(along, axis), axis=1)
        inside = off < radius
        if inside.any() and float(along[inside].max()) >= 0.75 * length:
            return True
    return False


def run(ctx) -> list[dict]:
    out = []
    for op in ctx.ops:
        if "plan_error" in op.meta:
            continue
        before = [other for other in ctx.ops if other.index < op.index and other.tool is not None]
        missing = [hole for hole in _needs(ctx, op) if not _made(ctx, hole, before)]
        if not missing:
            continue
        what = "taps" if op.tool is not None and op.tool.type == "tap" else "threads"
        out.append(finding(
            "prepared_hole", "warning", "assumes_prepared_hole",
            f"operation {op.index + 1} ({op.summary}, setup {op.setup}) {what} {len(missing)} hole"
            f"{'s' if len(missing) != 1 else ''} no earlier operation makes",
            "the job assumes each hole is already there at its size (drilled, bored or milled before this job). Add "
            "the drilling first (the tap drill for a tap), or confirm with the user the hole is made before the job "
            "runs",
            [{"setup": op.setup, "operation": op.index, "at": xyz(top)} for top, _, _ in missing]))
    return out
