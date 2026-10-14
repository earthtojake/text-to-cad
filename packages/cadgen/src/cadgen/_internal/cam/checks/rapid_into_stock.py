"""``rapid_into_stock``: a rapid move passes through material that was not cut yet (the simulator's finding).

A move made with the spindle stopped is judged like a rapid (a tool that is not turning cuts nothing). A back bore's
stopped moves are its bar's neck passing down through the hole, under the part and back up: judged with the neck's
radius (``shank_diameter_mm`` / 2), so a hit there is the neck in uncut material (the hole not drilled through yet).
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding, xyz

__all__ = ["run"]


def run(ctx) -> list[dict]:
    out = []
    names = {op.index: op for op in ctx.ops}
    for setup_id, report in ctx.sim_reports.items():
        for hit in report.rapid_hits:
            op = names.get(hit["op"])
            what = op.summary if op is not None else f"operation {hit['op'] + 1}"
            item = {"setup": setup_id, "operation": hit["op"], "move": hit["move"], "count": hit["count"],
                    "depth_mm": hit["depth_mm"], "at": xyz(hit["at"])}
            if "neck_diameter_mm" in hit:
                item["neck_diameter_mm"] = hit["neck_diameter_mm"]
                out.append(finding(
                    "rapid_into_stock", "error", "rapid_into_stock",
                    f"The bar's Ø{hit['neck_diameter_mm']:g} mm neck crashes into the stock in {what}: going through "
                    f"the hole with the spindle stopped it dips {hit['depth_mm']:.2f} mm into uncut material",
                    "drill or bore the hole through in an earlier operation, so the bar passes through it; check "
                    "shift_mm and shift_xy keep the neck inside the hole", [item]))
                continue
            out.append(finding(
                "rapid_into_stock", "error", "rapid_into_stock",
                f"A rapid crashes into the stock in {what}: it dips {hit['depth_mm']:.2f} mm into uncut material",
                "raise the clearance or retract height (clearance_mm, retract_mm), or reorder the operations so the "
                "material is cut first", [item]))
    return out
