"""``fixture``: a move takes the tool into a fixture keep-out (a vise jaw, a clamp, a plate under the stock).

Each setup's fixtures are boxes in part coordinates: the job's own, and those its vise or plate was built into
(``workholding.py``). Every sampled position, rapids included, is tested with the tool as a cylinder of its radius
from the tip up its stickout, against each box: a point of the tool axis closer to the box than the radius is a hit.
Where the tool axis runs along a part axis (every fixed orientation) the tool stands on one side of its tip, so only
what of a box rises past the tip counts, and how far it rises bounds the depth: a tip resting on a plate touches it
and is no hit, one 0.5 mm into it is 0.5 mm in.

``assumed_fixture`` (info): a vise or plate the plan modelled with sizes the job does not state, each named with the
default used, to check against the real fixture.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding, xyz

__all__ = ["run"]


def _number(value) -> str:
    return f"{value:g}" if isinstance(value, (int, float)) else str(value)


def run(ctx) -> list[dict]:
    import numpy as np

    out = []
    for plan in ctx.setups:
        for entry in getattr(plan, "fixture_assumed", ()) or ():
            sizes = ", ".join(f"{key} {_number(value)}" for key, value in entry["assumed"].items())
            out.append(finding(
                "fixture", "info", "assumed_fixture",
                f"Setup {plan.setup.id}'s {entry['fixture']} is modelled with sizes the job does not state: {sizes}",
                f"the fixture check judged the cut against these; check them against the real {entry['type']} and "
                "state them in the setup's fixture",
                [{"setup": plan.setup.id, "fixture": entry["fixture"], "assumed": dict(entry["assumed"])}]))
        boxes = plan.setup.fixtures
        if not boxes or plan.toolpath is None or not len(plan.toolpath):
            continue
        # Every millimetre, coarser on a path too long to hold that many samples (the 3D gouge check's budget).
        from cadgen._internal.cam.checks._gouge3d import MAX_POINTS

        step = max(1.0, float(plan.toolpath.lengths().sum()) / MAX_POINTS)
        samples = plan.toolpath.sample(max(ctx.tolerance_mm, 0.05), max_step_mm=step)
        axis = np.asarray(plan.wcs.tool_axis)
        k = int(np.argmax(np.abs(axis)))
        # The part axis the tool runs along, and which way, when it runs along one.
        along = k if abs(abs(axis[k]) - 1.0) < 1e-9 else None
        up = float(np.sign(axis[k]))
        tips = plan.wcs.from_wcs(samples.points)
        tools = {op.index: op.tool for op in ctx.ops if op.setup == plan.setup.id}
        for b, box in enumerate(boxes):
            low, high = np.asarray(box.min_mm), np.asarray(box.max_mm)
            hits: dict[int, tuple[float, int]] = {}
            for op_index, tool in tools.items():
                if tool is None:
                    continue
                mask = samples.op == op_index
                if not mask.any():
                    continue
                points = tips[mask]
                lo = np.broadcast_to(low, points.shape).copy()
                hi = np.broadcast_to(high, points.shape).copy()
                rises = np.full(len(points), np.inf)
                if along is not None:
                    # Only what of the box is past the tip, on the tool's side of it.
                    if up > 0:
                        lo[:, along] = np.maximum(lo[:, along], points[:, along])
                        rises = high[along] - points[:, along]
                    else:
                        hi[:, along] = np.minimum(hi[:, along], points[:, along])
                        rises = points[:, along] - low[along]
                depth = np.full(len(points), -np.inf)
                for h in np.linspace(0.0, max(tool.stickout_mm, tool.radius), 8):
                    probe = points + axis * h
                    gap = np.linalg.norm(np.maximum(0.0, np.maximum(lo - probe, probe - hi)), axis=1)
                    depth = np.maximum(depth, tool.radius - gap)
                depth = np.minimum(depth, rises)
                worst = int(np.argmax(depth))
                if depth[worst] > 1e-6:
                    hits[op_index] = (float(depth[worst]), int(np.nonzero(mask)[0][worst]))
            for op_index, (deep, row) in hits.items():
                name = box.name or f"fixture {b + 1}"
                out.append(finding(
                    "fixture", "error", "fixture",
                    f"The tool runs into {name} in setup {plan.setup.id} ({deep:.2f} mm in)",
                    "move the fixture, keep the operation away from it (a smaller region), or raise the clearance",
                    [{"setup": plan.setup.id, "operation": op_index, "fixture": name, "depth_mm": round(deep, 3),
                      "at": xyz(tips[row])}]))
    return out
