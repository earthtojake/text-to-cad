"""``long_stickout``: an end mill standing out of its holder more than four times its diameter.

A cutter that long bends away from the cut and chatters: the walls come out tapered and rough, and a small one
breaks. One warning per tool, naming every operation that runs it. Drills, taps and reamers are left out: a drill
of ten diameters is normal, and it cuts along its axis. From the parallel cam build.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import assumed_lengths, finding

__all__ = ["RATIO", "run"]

#: Past this many diameters out of the holder, an end mill deflects and chatters.
RATIO = 4.0
_MILLING = ("flat", "ball", "bull", "thread_mill", "engraver", "vee", "chamfer", "slot")


def run(ctx) -> list[dict]:
    out = []
    by_tool: dict[str, list] = {}
    for op in ctx.ops:
        if op.tool is not None and op.tool.type in _MILLING:
            by_tool.setdefault(op.tool.id, []).append(op)
    for ops in by_tool.values():
        tool = ops[0].tool
        ratio = tool.stickout_mm / max(tool.diameter_mm, 1e-9)
        if ratio <= RATIO + 1e-9:
            continue
        names = ", ".join(str(op.index + 1) for op in ops)
        guessed = bool(assumed_lengths(tool, ("stickout_mm",)))
        out.append(finding(
            "long_stickout", "warning", "long_stickout",
            f"{tool.id} ({tool.plain}) sticks out {tool.stickout_mm:g} mm{' (assumed)' if guessed else ''}, "
            f"{ratio:.1f} times its diameter: expect it to deflect and chatter "
            f"(operation{'s' if len(ops) > 1 else ''} {names})",
            ("the job gives no stickout_mm, so this one is the catalogue's guess: ask for the real one (the length "
             "out of the holder, flutes included) and plan again. " if guessed else "") +
            f"Past {RATIO:g} diameters an end mill bends away from the cut: hold it shorter, or take lighter cuts (a "
            "smaller stepdown_mm and stepover)",
            [{"setup": op.setup, "operation": op.index, "tool": tool.id, "stickout_mm": tool.stickout_mm,
              "diameter_mm": tool.diameter_mm} for op in ops]))
    return out
