"""``corner_radius``: an inside corner is tighter than the tool's radius, so material is left in it.

Planners that clear a region record what their tool cannot reach in their op ``meta["unreachable"]``: a list of
``{"area_mm2", "at": [x, y, z] WCS, "z": level}``. This check turns them into one warning per operation.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding, xyz

__all__ = ["run"]

#: Corners leaving less than this much area are within the tessellation's noise.
MIN_AREA_MM2 = 0.05


def run(ctx) -> list[dict]:
    out = []
    for op in ctx.ops:
        spots = [s for s in op.meta.get("unreachable", ()) if s["area_mm2"] >= MIN_AREA_MM2]
        if not spots or op.tool is None:
            continue
        plan = ctx.setup_plan(op.setup)
        items = []
        for spot in spots[:20]:
            at = plan.wcs.from_wcs([spot["at"]])[0]
            items.append({"setup": op.setup, "operation": op.index, "area_mm2": round(spot["area_mm2"], 3),
                          "at": xyz(at)})
        total = sum(s["area_mm2"] for s in spots)
        out.append(finding(
            "corner_radius", "warning", "corner_radius",
            f"Tool too big for {len(spots)} inside corner{'s' if len(spots) > 1 else ''} of {op.summary}: "
            f"{op.tool.id}'s {op.tool.radius:g} mm radius leaves {total:.2f} mm² of material there",
            "finish the corners with a smaller tool, or round the corners in the part to at least the tool's radius",
            items))
    return out
