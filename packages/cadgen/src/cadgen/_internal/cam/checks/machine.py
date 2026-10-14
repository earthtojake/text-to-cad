"""``machine``: an operation or setup needs an axis the machine does not have (a rotary move on a 3-axis mill)."""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding

__all__ = ["run"]


def run(ctx) -> list[dict]:
    out = []
    axes = ctx.job.machine.axes
    for plan in ctx.setups:
        needed = {axis.upper() for axis, _ in plan.wcs.rotary_deg}
        if plan.toolpath is not None:
            needed |= {axis.upper() for axis in plan.toolpath.rotary}
        missing = sorted(axis for axis in needed if axis not in axes)
        if missing:
            out.append(finding(
                "machine", "error", "machine_axes",
                f"Setup {plan.setup.id} needs the {', '.join(missing)} axis but the {ctx.job.machine.kind} has {axes}",
                "use a machine with those axes (mill4, mill5), or a fixed orientation", [{"setup": plan.setup.id,
                                                                                           "missing": missing}]))
    return out
