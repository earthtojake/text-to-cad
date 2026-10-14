"""``travel``: a setup's toolpath spans more than the machine's travel on an axis.

Where the work offset sits on the machine is the operator's; what the program can be sure of is its own span. The
span of every move (rapids included) on X, Y and Z is compared with ``machine.travel_mm`` (a lathe: X as diameter
and Z). No travel in the job, no check.

Rotary axes: every A, B, C position the moves carry is compared with ``machine.rotary_limits_deg`` (multi-axis).
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding

__all__ = ["run"]


def run(ctx) -> list[dict]:
    travel = ctx.job.machine.travel_mm
    if not travel:
        return _rotary(ctx)
    out = _rotary(ctx)
    lathe = ctx.job.machine.kind == "lathe"
    for plan in ctx.setups:
        path = plan.toolpath
        if path is None or not len(path):
            continue
        samples = path.sample(max(ctx.tolerance_mm, 0.05))
        points = samples.points
        span = points.max(axis=0) - points.min(axis=0)
        axes = (("X", 2 * float(points[:, 0].max()), travel[0]), ("Z", float(span[2]), travel[1])) if lathe and len(travel) == 2 \
            else tuple(zip("XYZ", (float(v) for v in span), travel))
        for name, needed, available in axes:
            if needed > available + 1e-6:
                out.append(finding(
                    "travel", "error", "travel",
                    f"Setup {plan.setup.id} needs {needed:.1f} mm of {name} travel; the machine has {available:g} mm",
                    "split the job into more setups, use a bigger machine, or check travel_mm",
                    [{"setup": plan.setup.id, "axis": name, "needed_mm": round(needed, 3), "travel_mm": available}]))
    return out


def _rotary(ctx) -> list[dict]:
    """Moves whose A, B or C position is outside ``machine.rotary_limits_deg``: one finding per setup and axis."""
    limits = ctx.job.machine.rotary_limits_deg
    if not limits:
        return []
    out = []
    for plan in ctx.setups:
        path = plan.toolpath
        if path is None or not len(path) or not path.rotary:
            continue
        for axis in path.rotary:
            if axis not in limits:
                continue
            low, high = limits[axis]
            values = path.moves[axis]
            bad = (values < low - 1e-6) | (values > high + 1e-6)
            if not bad.any():
                continue
            k = int(bad.nonzero()[0][0])
            ops = sorted({int(op) for op in path.moves["op"][bad] if op >= 0})
            worst = float(values[bad][abs(values[bad] - (low + high) / 2.0).argmax()])
            out.append(finding(
                "travel", "error", "rotary_travel",
                f"Setup {plan.setup.id} turns {axis.upper()} to {worst:.1f}°; the machine's {axis.upper()} range is "
                f"{low:g}..{high:g}°",
                "tilt less (max_tilt_deg), name fewer faces, or set rotary_limits_deg to the machine's real range",
                [{"setup": plan.setup.id, "axis": axis.upper(), "move": k, "value_deg": round(worst, 3),
                  "limits_deg": [low, high], **({"operation": ops[0]} if ops else {})}]))
    return out
