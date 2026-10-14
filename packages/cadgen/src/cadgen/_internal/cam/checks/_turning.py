"""The turning half of ``gouge``: a lathe operation's tool, swept along its cutting moves, against the part's turned
section.

Each turning operation's tool is its shape from :func:`~cadgen._internal.cam.turn_profile.tool_shape` (the role in
the op's ``meta["lathe"]``: the insert with its nose radius, edges and holder, the blade, the drill), swept through
every cutting move in the setup's half-plane, and compared with the part's turned section (its max-radius envelope,
:func:`~cadgen._internal.cam.turn_profile.read_profile`): any overlap deeper than the tolerance is a gouge, measured as
how far inside the section the tool reaches. A thread is not judged (it cuts below the modelled major diameter on
purpose). A part whose turned section cannot be read is not judged and says so (a ``not_judged`` warning). Called
from ``gouge.run``.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding, xyz
from cadgen._internal.cam.job_errors import CamJobError

__all__ = ["gouges"]


def gouges(ctx) -> list[dict]:
    if ctx.job.machine.kind != "lathe":
        return []
    import numpy as np
    import shapely

    from cadgen._internal.cam.stock_lathe import role_of
    from cadgen._internal.cam.turn_profile import read_profile, tool_shape

    out = []
    tol = max(0.02, 2.0 * getattr(ctx.part, "deflection_mm", 0.01), 2.0 * ctx.tolerance_mm)
    for op in ctx.ops:
        if op.tool is None or op.operation.family != "Turning" or op.end <= op.start:
            continue
        role, params = role_of(op.tool, op.meta)
        if role.startswith("thread"):
            continue
        plan = ctx.setup_plan(op.setup)
        try:
            section = read_profile(ctx.part, plan.wcs, tolerance_mm=ctx.tolerance_mm).region
        except CamJobError as exc:
            # Said, never passed in silence; anything but a reading the lathe refuses is a fault and propagates.
            out.append(finding(
                "gouge", "warning", "not_judged",
                f"{op.summary} was not judged for gouges: the part's turned section could not be read ({exc})",
                "check the cut against the part by hand, or report it", [{"setup": op.setup, "operation": op.index}]))
            continue
        shapes = tool_shape(op.tool, role, **params)
        piece = plan.toolpath.slice(op.start, op.end)
        swept = _swept(piece, shapes, ctx.tolerance_mm)
        inside = shapely.intersection(swept, section.buffer(-tol))
        if inside.is_empty or inside.area < 1e-6:
            continue
        # The deepest point is on the overlap's edge (the tool's surface inside the part): measured along it.
        coords = shapely.get_coordinates(shapely.segmentize(inside, max(0.02, tol)))
        coords = coords[shapely.contains_xy(section, coords[:, 0], coords[:, 1])]
        depth = shapely.distance(shapely.points(coords), section.boundary)
        k = int(np.argmax(depth))
        at = plan.wcs.from_wcs([[coords[k, 0], 0.0, coords[k, 1]]])[0]
        out.append(finding(
            "gouge", "error", "gouge_turning",
            f"{op.summary} cuts into the part: up to {float(depth[k]):.2f} mm into its turned section",
            "a z_mm or x_end_mm the operation was given reaches into the part, or this is a planning fault: check the "
            "operation's keys and report it if the job is right",
            [{"setup": op.setup, "operation": op.index, "depth_mm": round(float(depth[k]), 3),
              "area_mm2": round(float(inside.area), 4), "at": xyz(at)}]))
    return out


def _swept(toolpath, shapes, tolerance: float):
    import shapely

    from cadgen._internal.cam.ir import DWELL, RAPID
    from cadgen._internal.cam.turn_profile import sweep

    samples = toolpath.sample(max(tolerance, 0.005))
    points = samples.points[:, [0, 2]]
    pieces, run = [], []
    for i in range(1, len(points)):
        kind = int(samples.kind[i])
        if kind == DWELL:
            continue
        if kind == RAPID:
            if len(run) > 1:
                pieces.append(sweep(points[run], shapes))
            run = []
            continue
        if not run:
            run = [i - 1]
        run.append(i)
    if len(run) > 1:
        pieces.append(sweep(points[run], shapes))
    return shapely.union_all(pieces) if pieces else shapely.Polygon()
