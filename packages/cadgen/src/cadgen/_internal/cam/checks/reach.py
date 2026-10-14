"""``reach``: the cut goes deeper than the tool's flutes (the shank rubs the walls) or its stickout (the holder hits).

The depth is the simulator's: the deepest the tool tip sat below material within reach of its side (the walls next
to the tool, not the stock top far away), per operation, so a stepped pocket is judged step by step. A setup the
simulator skipped falls back to the setup's stock top minus the operation's lowest cutting move (conservative).
A holder wider than the cut is judged by ``holder_collision``, not here.

A length the job did not state (``Tool.assumed``: the catalogue flute length, the stickout worked from it) is not one
the plan can judge against: a cut past it is a ``not_judged`` warning that names the assumed length and asks for the
real one, never an error on a guess nor a silent pass.

A back bore (``drill``'s ``back_bore`` cycle) is judged from its plan, not from a depth: its head cuts upward from
under the part, so the counterbore's depth is not bounded by the head's flutes (the head rises through it), and the
bar's neck in the hole above the head is there by design (the planner fits the head, the neck and the shift to the
hole and the counterbore). What reach judges is the holder: the bar must stick out far enough that, with the head
down at the R plane under the part, the holder is still over the stock's top (``reach_holder``).
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import assumed_lengths, finding, xyz

__all__ = ["run"]


def _fallback_depth(ctx, op) -> tuple[float, list | None]:
    import numpy as np

    from cadgen._internal.cam.ir import RAPID

    plan = ctx.setup_plan(op.setup)
    path = plan.toolpath
    rows = path.moves[(path.moves["op"] == op.index) & (path.moves["kind"] != RAPID)]
    if not len(rows):
        return 0.0, None
    k = int(np.argmin(rows["z"]))
    point = plan.wcs.from_wcs([[rows["x"][k], rows["y"][k], rows["z"][k]]])[0]
    return float(plan.heights.stock_top - rows["z"][k]), list(point)


def _back_bore(ctx, op, tol: float) -> list[dict]:
    """A back bore's holder against the stock's top, with the head at its lowest (the R plane under the part)."""
    import numpy as np

    tool = op.tool
    plan = ctx.setup_plan(op.setup)
    rows = plan.toolpath.moves[op.start:op.end]
    if not len(rows):
        return []
    k = int(np.argmin(rows["z"]))
    depth = float(plan.heights.stock_top - rows["z"][k])
    if depth <= tool.stickout_mm + tol:
        return []
    at = plan.wcs.from_wcs([[rows["x"][k], rows["y"][k], rows["z"][k]]])[0]
    item = {"setup": op.setup, "operation": op.index, "depth_mm": round(depth, 3),
            "flute_length_mm": tool.flute_length_mm, "stickout_mm": tool.stickout_mm, "at": xyz(at)}
    if assumed_lengths(tool, ("stickout_mm",)):
        return [_not_judged(op, tool, depth, "stickout_mm", item)]
    return [finding(
        "reach", "error", "reach_holder",
        f"Bar too short for this back bore: {op.summary or op.spec.op} takes {tool.id}'s head {depth:.1f} mm under "
        f"the stock's top but {tool.id} ({tool.plain}) sticks out only {tool.stickout_mm:g} mm, so the holder hits",
        "use a longer bar or more stickout (stickout_mm): the head goes down through the hole to under the part",
        [item])]


def _not_judged(op, tool, depth: float, key: str, item: dict) -> dict:
    """A cut deeper than a length the job did not state: the plan cannot say whether it reaches."""
    word = "flutes" if key == "flute_length_mm" else "stickout"
    return finding(
        "reach", "warning", "not_judged",
        f"Reach not judged: {op.summary or op.spec.op} goes {depth:.1f} mm deep, past {tool.id}'s assumed {word} of "
        f"{getattr(tool, key):g} mm (the job gives no {key})",
        f"state {tool.id}'s real flute_length_mm and stickout_mm and plan again: with them reach is judged", [item])


def run(ctx) -> list[dict]:
    out = []
    tol = max(0.05, ctx.tolerance_mm)
    for op in ctx.ops:
        tool = op.tool
        if tool is None or tool.family != "mill":
            continue
        if op.meta.get("cycle") == "back_bore":
            out.extend(_back_bore(ctx, op, tol))
            continue
        report = ctx.sim_reports.get(op.setup)
        entry = report.depth_by_op.get(op.index) if report is not None else None
        if entry is not None:
            depth, at = entry["depth_mm"], entry["at"]
        else:
            depth, at = _fallback_depth(ctx, op)
        if depth <= tool.flute_length_mm + tol:
            continue
        item = {"setup": op.setup, "operation": op.index, "depth_mm": round(depth, 3),
                "flute_length_mm": tool.flute_length_mm, "stickout_mm": tool.stickout_mm,
                "at": xyz(at) if at is not None else None}
        # Each finding stands on the length it is judged by: a stated one judges, a guessed one cannot.
        past_holder = depth > tool.stickout_mm + tol
        if past_holder and not assumed_lengths(tool, ("stickout_mm",)):
            out.append(finding(
                "reach", "error", "reach_holder",
                f"Tool too short for this cut: {op.summary or op.spec.op} goes {depth:.1f} mm deep but {tool.id} "
                f"({tool.plain}) sticks out only {tool.stickout_mm:g} mm, so the holder hits",
                "use a longer tool or more stickout (stickout_mm), or cut less deep from this side", [item]))
        elif assumed_lengths(tool, ("flute_length_mm",)):
            out.append(_not_judged(op, tool, depth, "stickout_mm" if past_holder else "flute_length_mm", item))
        else:
            out.append(finding(
                "reach", "error", "reach_flutes",
                f"Tool flutes too short for this cut: {op.summary or op.spec.op} goes {depth:.1f} mm deep but "
                f"{tool.id}'s flutes are {tool.flute_length_mm:g} mm long, so the shank rubs the walls",
                "use a tool with longer flutes (flute_length_mm), or machine the rest from the other side", [item]))
    return out
