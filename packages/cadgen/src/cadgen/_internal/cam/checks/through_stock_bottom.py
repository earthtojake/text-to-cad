"""``through_stock_bottom``: a cut goes below the stock's bottom (a through drill's point, a profile's breakthrough).

Whatever stands under the stock there (the vise's parallels, the table, a spoilboard) is cut too unless the job
allows for it, so the user must know where. One warning per operation, at its lowest point; not said where the
same cut already runs into a fixture box (``fixture`` says that). Mills and routers only: a lathe's bar has no
bottom, and a laser, plasma or waterjet cuts through by nature. From the parallel cam build.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding, xyz

__all__ = ["run"]

_MACHINES = ("mill", "mill4", "mill5", "router")


def run(ctx) -> list[dict]:
    import numpy as np

    from cadgen._internal.cam.ir import DWELL, RAPID

    if ctx.job.machine.kind not in _MACHINES:
        return []
    tol = max(0.01, ctx.tolerance_mm)
    out = []
    for op in ctx.ops:
        if op.tool is None or op.operation.family == "Multi-axis" or "plan_error" in op.meta:
            continue
        plan = ctx.setup_plan(op.setup)
        moves = plan.toolpath.moves[op.start:op.end]
        cutting = moves[(moves["kind"] != RAPID) & (moves["kind"] != DWELL)] if len(moves) else moves
        if not len(cutting):
            continue
        k = int(np.argmin(cutting["z"]))
        depth = float(plan.heights.stock_bottom - cutting["z"][k])
        if depth <= tol:
            continue
        at = plan.wcs.from_wcs([[cutting["x"][k], cutting["y"][k], cutting["z"][k]]])[0]
        out.append(finding(
            "through_stock_bottom", "warning", "through_stock_bottom",
            f"operation {op.index + 1} ({op.summary}, setup {op.setup}) cuts {depth:.2f} mm below the stock's bottom",
            "whatever is under the stock there is cut too: put a spoilboard or sacrificial plate under it, or a gap "
            "between the parallels, and tell the user where",
            [{"setup": op.setup, "operation": op.index, "depth_mm": round(depth, 3), "at": xyz(at)}]))
    return out
