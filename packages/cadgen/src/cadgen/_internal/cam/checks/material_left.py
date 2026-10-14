"""``material_left``: stock still standing above the part after every operation, beyond the stock to leave.

Which stock to leave: where the simulator knows the last operation that covered each place (the heightfield,
``tracks_ops``), that operation's, so a roughing's allowance is not excused where a finish ran after it; elsewhere
the smallest any operation leaves (a finish's 0 is not hidden behind a roughing's allowance). A simulator that
cannot read the part says so as a ``not_judged`` warning, never a silent pass.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding, xyz
from cadgen._internal.cam.job_errors import CamJobError

__all__ = ["run"]

#: Less than this is the grid's own noise along walls.
MIN_VOLUME_MM3 = 1.0


def run(ctx) -> list[dict]:
    if ctx.sim is None:
        return []
    leaves = {op.index: float(op.spec.stock_to_leave_mm) for op in ctx.ops}
    least = min(leaves.values(), default=0.0)
    extra = {"leave_by_op": leaves} if getattr(ctx.sim, "tracks_ops", False) else {}
    try:
        left = ctx.sim.material_left(ctx.part, stock_to_leave_mm=least, tolerance_mm=ctx.tolerance_mm, **extra)
    except CamJobError as exc:
        return [finding("material_left", "warning", "not_judged",
                        f"Material left was not judged: the simulated stock could not be compared with the part ({exc})",
                        "check the part against the program by hand", [{}])]
    if left is None or left.volume_mm3 < MIN_VOLUME_MM3:
        return []
    uniform = len(set(leaves.values())) <= 1
    words = (f" (stock to leave {least:g} mm)" if uniform and least else
             "" if uniform else " (beyond each place's last operation's stock to leave)")
    return [finding(
        "material_left", "warning", "material_left",
        f"Material left on the part: {left.volume_mm3:.0f} mm³ over {left.area_mm2:.0f} mm², up to {left.max_mm:.2f} mm "
        f"proud{words}",
        "add an operation (face, a smaller tool, rest machining) where it is, or accept it",
        [{"volume_mm3": round(left.volume_mm3, 2), "area_mm2": round(left.area_mm2, 2), "max_mm": round(left.max_mm, 3),
          "at": xyz(left.at) if left.at else None,
          "bounds_mm": [xyz(left.bounds_min), xyz(left.bounds_max)] if left.bounds_min else None}])]
