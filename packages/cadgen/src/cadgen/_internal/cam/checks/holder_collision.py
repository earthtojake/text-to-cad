"""``holder_collision``: the shank or the holder, above the flutes, touches the part or the stock.

The tool above its flutes is two cylinders on its axis: the shank (``shank_diameter_mm``, default the tool's
diameter) from the top of the flutes (``flute_length_mm`` over the tip) to the holder, and the holder
(``holder_diameter_mm``, when the job gives one) from ``stickout_mm`` over the tip up. Each is wider than the flutes
or it is not judged here (a shank no wider than the cutter rubs only where the cutter itself is too short: that is
``reach``).

* **Part**: at every point of every cutting move (sampled along the path), a cylinder hits the part when the
  drop-cutter height of a flat cutter of its radius (inset by the tolerance) stands over the cylinder's bottom. Every
  milling operation in every setup is judged (the part's mesh in the setup's WCS).
* **Stock**: for top and bottom setups the stock is simulated again on a heightfield, operation by operation, and
  before each one its cylinders are checked against the stock as it stands then (the highest stock within the
  cylinder's radius over its bottom by more than 0.05 mm). Only operations with a cylinder wider than the cutter
  cost this replay. An operation in a setup the replay cannot cut (a side or tilted setup, or a job whose stock is
  not a heightfield) is not judged against the stock and says so: a ``not_judged`` note per setup, unless the run
  already warned that the whole setup went unsimulated.

One error per operation and cylinder, with the worst overlap and where. A cylinder placed by a length the job did
not state (``Tool.assumed``: a defaulted flute length, shank or stickout) is not a collision the plan can stand
behind: its hit is a ``not_judged`` warning naming the assumed length, as ``reach`` does.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.checks.base import assumed_lengths, finding, xyz

__all__ = ["run"]

#: Points judged per operation at most; a longer path is sampled more coarsely.
MAX_POINTS = 600_000
#: Stock within this of a cylinder is a near miss, not a hit (the heightfield's own noise).
STOCK_TOLERANCE = 0.05


def _cylinders(tool):
    """``(name, radius, bottom over the tip)`` of the parts above the flutes wider than the cutter."""
    out = []
    holder = tool.holder
    if holder.shank_diameter_mm / 2.0 > tool.radius + 1e-9:
        out.append(("shank", holder.shank_diameter_mm / 2.0, tool.flute_length_mm))
    if holder.holder_diameter_mm and holder.holder_diameter_mm / 2.0 > tool.radius + 1e-9:
        out.append(("holder", holder.holder_diameter_mm / 2.0, holder.stickout_mm))
    return out


def _points(plan, op, step_floor: float):
    import numpy as np

    from cadgen._internal.cam.ir import RAPID

    piece = plan.toolpath.slice(op.start, op.end)
    length = float(piece.lengths()[piece.moves["kind"] != RAPID].sum())
    step = max(step_floor, length / MAX_POINTS)
    samples = piece.sample(0.05, max_step_mm=step)
    cutting = samples.kind != RAPID
    cutting[0] = False
    return samples.points[cutting] if len(samples.points) else np.zeros((0, 3))


def run(ctx) -> list[dict]:
    import numpy as np

    from cadgen._internal.cam.dropcutter import Cutter, drop

    out = []
    tol = max(0.02, 2.0 * getattr(ctx.part, "deflection_mm", 0.01), 2.0 * ctx.tolerance_mm)
    judged = [op for op in ctx.ops if op.tool is not None and op.tool.family == "mill" and op.end > op.start
              and _cylinders(op.tool)]
    if not judged:
        return out
    cache = {}
    for op in judged:
        plan = ctx.setup_plan(op.setup)
        points = _points(plan, op, max(0.25, min(2.0, op.tool.radius)))
        cache[op.index] = points
        if not len(points):
            continue
        mesh = ctx.part.mesh_in(plan.wcs)
        for name, radius, bottom in _cylinders(op.tool):
            reach = drop(points[:, :2], Cutter("flat", radius), mesh, leave=-tol)
            overlap = reach - (points[:, 2] + bottom)
            bad = overlap > 1e-9
            if bad.any():
                k = int(np.argmax(overlap))
                out.append(_finding(op, name, "part", float(overlap[k] + tol), int(bad.sum()),
                                    plan.wcs.from_wcs([points[k]])[0], radius))
    out.extend(_against_stock(ctx, judged, cache))
    return out


#: The tool lengths each cylinder stands on: a hit judged on a length the job did not state is ``not_judged``.
_LENGTHS = {"shank": ("flute_length_mm", "shank_diameter_mm"), "holder": ("stickout_mm",)}


def _finding(op, name, what, depth, count, at, radius):
    tool = op.tool
    word = "shank" if name == "shank" else "holder"
    fix = ("use a tool whose flutes reach (flute_length_mm), a slimmer shank, or cut this from another setup"
           if name == "shank" else "use more stickout (stickout_mm), a slimmer holder (holder_diameter_mm), or cut "
           "this from another setup")
    items = [{"setup": op.setup, "operation": op.index, "depth_mm": round(depth, 3), "count": count, "at": xyz(at),
              "diameter_mm": round(2 * radius, 4)}]
    guessed = assumed_lengths(tool, _LENGTHS[word])
    if guessed:
        # The cylinder stands where a length the job left out puts it: not a collision the plan can stand behind.
        return finding(
            "holder_collision", "warning", "not_judged",
            f"Not judged: {tool.id}'s {word} may touch the {what} in {op.summary}; with the assumed "
            f"{' and '.join(f'{key} {getattr(tool, key):g}' for key in guessed)} it goes {depth:.2f} mm in",
            f"the job does not give {tool.id}'s {' or '.join(guessed)}: state the real one(s) and plan again; "
            f"if it still hits, {fix}", items)
    return finding(
        "holder_collision", "error", f"{word}_{what}",
        f"The {word} hits the {what} in {op.summary}: {tool.id}'s Ø{2 * radius:g} mm {word} goes {depth:.2f} mm into "
        f"it at {count} point{'s' if count > 1 else ''}", fix, items)


def _against_stock(ctx, judged, cache) -> list[dict]:
    """Replay the stock on a heightfield and check each judged operation's cylinders before it cuts."""
    import numpy as np

    from cadgen._internal.cam.stock_heightfield import HeightfieldSim

    sim = getattr(ctx, "sim", None)
    if sim is None:
        return []
    if not hasattr(sim, "top"):
        return _not_judged(ctx, judged, {plan.setup.id for plan in ctx.setups},
                           "the stock replay is a heightfield and this job's stock is not")
    tools = {tool.id: tool for tool in ctx.job.tools}
    wanted = {op.index for op in judged}
    replay = HeightfieldSim(ctx.stock, ctx.part, cell_mm=max(float(sim.cell), 0.25),
                            tolerance_mm=max(0.01, ctx.tolerance_mm))
    out = []
    unreplayed = set()
    reports = getattr(ctx, "sim_reports", {}) or {}
    for plan in ctx.setups:
        if replay.supports(plan.wcs):
            unreplayed.add(plan.setup.id)
            continue
        report = reports.get(plan.setup.id)
        if report is not None and report.skipped:
            # The run did not simulate this setup and its warning says the shank and holder were judged against the
            # part only there: replaying it here would cost what the simulator declined (a micro tool's path over a
            # big plate) to judge what the run already said it does not.
            continue
        direction = 1 if plan.wcs.tool_axis[2] > 0 else -1
        path = plan.toolpath
        for op_range in path.ops:
            op = next((o for o in judged if o.index == op_range.index), None)
            if op is not None and op.index in wanted and len(cache.get(op.index, ())):
                points = plan.wcs.from_wcs(cache[op.index])
                for name, radius, bottom in _cylinders(op.tool):
                    surface = _dilated(replay, radius, direction)
                    i = np.floor((points[:, 0] - replay.x0) / replay.cell).astype(np.int64)
                    j = np.floor((points[:, 1] - replay.y0) / replay.cell).astype(np.int64)
                    inside = (i >= 0) & (i < replay.nx) & (j >= 0) & (j < replay.ny)
                    if not inside.any():
                        continue
                    stock = surface[np.clip(i, 0, replay.nx - 1), np.clip(j, 0, replay.ny - 1)]
                    base = points[:, 2] + direction * bottom
                    overlap = np.where(inside & np.isfinite(stock), direction * (stock - base), -np.inf)
                    bad = overlap > STOCK_TOLERANCE
                    if bad.any():
                        k = int(np.argmax(overlap))
                        out.append(_finding(op, name, "stock", float(overlap[k]), int(bad.sum()), points[k], radius))
            tool = tools.get(op_range.tool) if op_range.tool else None
            if tool is not None and tool.family == "mill" and op_range.end > op_range.start:
                piece = path.slice(op_range.start, op_range.end)
                piece = type(piece)(piece.moves, piece.events, [op_range.shifted(-op_range.start)],
                                    start=piece.start, rotary=piece.rotary, lathe=piece.lathe)
                replay.cut(piece, tools, plan.wcs)
    return out + _not_judged(ctx, judged, unreplayed, "the stock replay covers top and bottom setups only")


def _not_judged(ctx, judged, setups, why: str) -> list[dict]:
    """One note per setup whose judged operations' shank or holder went unchecked against the stock; none where the
    run already warns that the setup was not simulated at all."""
    reports = getattr(ctx, "sim_reports", {}) or {}
    out = []
    for setup_id in sorted(setups):
        report = reports.get(setup_id)
        ops = [op for op in judged if op.setup == setup_id]
        if not ops or (report is not None and report.skipped):
            continue
        out.append(finding(
            "holder_collision", "info", "not_judged",
            f"Setup '{setup_id}': the shank and holder above the flutes were checked against the part, not the stock "
            f"({why})", "check the holder's clearance over the stock by hand on those operations",
            [{"setup": setup_id, "operation": op.index} for op in ops]))
    return out


def _dilated(sim, radius: float, direction: int):
    """The stock's face toward the tool, each cell the extreme within ``radius`` (part z)."""
    import numpy as np

    exists = sim.top > sim.bottom + 1e-9
    surface = np.where(exists, sim.top if direction > 0 else sim.bottom, -np.inf if direction > 0 else np.inf)
    k = int(math.ceil(radius / sim.cell))
    out = surface.copy()
    pick = np.maximum if direction > 0 else np.minimum
    nx, ny = surface.shape
    for di in range(-k, k + 1):
        for dj in range(-k, k + 1):
            if math.hypot(max(0, abs(di) - 1), max(0, abs(dj) - 1)) * sim.cell > radius:
                continue
            src = surface[max(0, di):nx + min(0, di), max(0, dj):ny + min(0, dj)]
            view = out[max(0, -di):nx + min(0, -di), max(0, -dj):ny + min(0, -dj)]
            view[...] = pick(view, src)
    return out
