"""``full_slot``: an operation cuts at the tool's full width for more than five of its diameters.

A full-width cut loads the tool hardest and packs the chips in: on a small tool or in a hard material it breaks
tools. The length is the operation's own fact (``meta["full_slot_mm"]``: the stretches of a pocket's links from one
ring to the next that run into material the level has not cut yet, and its first ring after an entry; an adaptive
clear's rings round pieces too narrow for a helix; a slot's centreline times its levels); a ``slot`` operation is
meant to cut full width, so it is not judged. From the parallel cam build.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding

__all__ = ["DIAMETERS", "run"]

#: Past this many tool diameters of full-width cutting in one operation, it is said.
DIAMETERS = 5.0


def run(ctx) -> list[dict]:
    out = []
    for op in ctx.ops:
        length = op.meta.get("full_slot_mm")
        if op.tool is None or op.operation.name == "slot" or not isinstance(length, (int, float)):
            continue
        if length <= DIAMETERS * op.tool.diameter_mm:
            continue
        out.append(finding(
            "full_slot", "warning", "full_slot",
            f"operation {op.index + 1} ({op.summary}, setup {op.setup}) cuts {length:.0f} mm at {op.tool.id}'s full "
            f"width ({length / op.tool.diameter_mm:.0f} diameters)",
            "a full-width cut loads the tool hardest and packs the chips in: a smaller stepdown_mm or a lower feed is "
            "gentler; say it when the tool is small or the material hard",
            [{"setup": op.setup, "operation": op.index, "full_slot_mm": round(float(length), 1)}]))
    return out
