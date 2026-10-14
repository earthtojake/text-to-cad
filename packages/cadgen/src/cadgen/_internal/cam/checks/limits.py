"""``limits``: a spindle speed or feed the machine clamped, one warning per tool and limit, saying what it does.

The feeds rules (:func:`cadgen._internal.cam.feeds.for_op`) report each clamp. What follows from it depends on
where the feed came from: under a spindle clamp a worked-out feed follows the slower spindle (the chip load is
kept, the cut is slower), but a feed the operation states is kept, so each tooth takes a bigger chip, and the
warning gives the feed that keeps the planned chip. Under a feed clamp each tooth takes a thinner chip than
planned, which rubs and wears the tool. A tap slows its spindle instead, so its feed stays rpm x pitch. Clamps of
one kind on one tool are one warning naming every operation (from the parallel cam build).
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding

__all__ = ["run"]


def _kind(note: str) -> str:
    """``tap`` (a tap or thread slowed its spindle to keep rpm x pitch), ``raised`` (a spindle sped up to the machine's
    slowest), ``spindle`` or ``feed``."""
    if note.startswith(("a tap ", "a thread ")):
        return "tap"
    if "raised to the machine's slowest" in note:
        return "raised"
    return "spindle" if "rpm" in note.split("clamped", 1)[0] else "feed"


def _description(kind: str, ops, tool, machine) -> str:
    if kind == "raised":
        return (f"the spindle turns no slower than the machine's min_rpm ({machine.min_rpm:g}), past the table's "
                "surface speed for this tool: the chip load is kept, so the feed is faster too. Check the tool maker's "
                "chart at this speed; a smaller tool wants more rpm")
    if kind == "tap":
        return ("the spindle was slowed so the feed stays rpm x pitch under the machine's max_feed_mm_min: the "
                "thread is right, the cut is slower")
    if kind == "feed":
        fewer = ("set a lower speed (rpm) on the operation, or use a tool with fewer flutes, to keep the planned chip "
                 "at this feed")
        return (f"the feed is held to the machine's max_feed_mm_min ({machine.max_feed_mm_min:g} mm/min), so each "
                f"tooth takes a thinner chip than planned, which rubs and wears the tool: {fewer}")
    stated = [op for op in ops if op.spec.feed is not None and op.feeds is not None and op.feeds.chipload_mm
              and tool.family == "mill" and getattr(op.feeds, "feed_mm_rev", None) is None]
    if not stated:
        return (f"the spindle is held to the machine's max_rpm ({machine.max_rpm:g}); the worked-out feed follows "
                "it, so the chip load is kept and the cut is slower than the table suggests. Usually fine: report "
                "it; a larger tool needs fewer rpm")
    parts = []
    for op in stated:
        # Hole makers' chip load is per revolution; a milling cutter's per tooth.
        teeth = 1 if tool.type in ("drill", "spot", "reamer", "boring", "tap") else max(1, tool.flutes)
        keep = op.feeds.chipload_mm * op.feeds.rpm * teeth
        parts.append(f"operation {op.index + 1} states feed {op.spec.feed:g} mm/min; {keep:.0f} mm/min keeps the "
                     "planned chip")
    return (f"the spindle is held to the machine's max_rpm ({machine.max_rpm:g}) but a feed the operation states is "
            f"kept, so each tooth takes a bigger chip: {'; '.join(parts)}. Lower the feed in step")


def run(ctx) -> list[dict]:
    machine = ctx.job.machine
    groups: dict[tuple, dict] = {}
    for op in ctx.ops:
        for note in getattr(op.feeds, "clamped", ()) or ():
            kind = _kind(note)
            key = (op.tool.id if op.tool is not None else None, kind)
            group = groups.setdefault(key, {"ops": [], "notes": []})
            if op not in group["ops"]:
                group["ops"].append(op)
            if note not in group["notes"]:
                group["notes"].append(note)
    out = []
    for (tool_id, kind), group in groups.items():
        ops = group["ops"]
        tool = ops[0].tool
        who = f"{tool.id} ({tool.plain})" if tool is not None else ops[0].summary
        names = ", ".join(str(op.index + 1) for op in ops)
        out.append(finding(
            "limits", "warning", "limits",
            f"{who}: {'; '.join(group['notes'])} (operation{'s' if len(ops) > 1 else ''} {names})",
            _description(kind, ops, tool, machine) if tool is not None else "the machine's limits held the cut back",
            [{"setup": op.setup, "operation": op.index, "tool": tool_id, "limit": kind} for op in ops]))
    return out
