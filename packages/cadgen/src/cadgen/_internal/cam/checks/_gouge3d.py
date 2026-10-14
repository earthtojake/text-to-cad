"""The 3D half of ``gouge``: every feed point of a 3D milling operation against the drop-cutter.

A point of a cutting move (sampled along the path, arcs by chord) gouges when it sits lower than the drop-cutter
height of the tool inset by the tolerance at its XY: the real cutter there would cut more than the tolerance into
the part, measured along the surface's normal (so a pass brushing a vertical wall is not a gouge, and one cutting
into it is). The depth reported is that normal depth, read off a ladder of insets (to
half the tool's radius). The mesh is the part's own tessellation in the
setup's WCS, whatever the setup's tilt (the tool comes down its +Z). Called from :mod:`.gouge`.
"""

from __future__ import annotations

from cadgen._internal.cam.checks.base import finding, xyz

__all__ = ["FAMILIES_3D", "gouges_3d"]

FAMILIES_3D = ("3D milling",)
#: Feed points judged per operation at most; a longer path is sampled more coarsely.
MAX_POINTS = 1_500_000


def gouges_3d(ctx, tolerance: float) -> list[dict]:
    import numpy as np

    from cadgen._internal.cam.dropcutter import drop
    from cadgen._internal.cam.ir import RAPID

    out = []
    for op in ctx.ops:
        tool = op.tool
        if tool is None or tool.family != "mill" or op.operation.family not in FAMILIES_3D \
                or op.meta.get("no_gouge_check") or op.end <= op.start:
            continue
        plan = ctx.setup_plan(op.setup)
        piece = plan.toolpath.slice(op.start, op.end)
        cutting_moves = piece.moves["kind"] != RAPID
        length = float(piece.lengths()[cutting_moves].sum())
        step = max(min(0.25, tool.radius / 2.0), length / MAX_POINTS)
        samples = piece.sample(ctx.tolerance_mm, max_step_mm=step)
        cutting = samples.kind != RAPID
        cutting[0] = False
        points = samples.points[cutting]
        if not len(points):
            continue
        mesh = ctx.part.mesh_in(plan.wcs)
        allowed = drop(points[:, :2], tool, mesh, leave=-tolerance)
        bad = np.nonzero(points[:, 2] < allowed - 1e-9)[0]
        if not len(bad):
            continue
        # How deep, along the normal: the largest inset of a ladder (to half the radius) that still reaches each of
        # the worst few hundred points.
        vertical = allowed[bad] - points[bad, 2]
        judge = bad[np.argsort(-vertical)[:400]]
        depth = np.full(len(judge), tolerance)
        for inset in np.linspace(tolerance, tool.radius / 2.0, 33)[1:]:
            hit = points[judge, 2] < drop(points[judge, :2], tool, mesh, leave=-float(inset)) - 1e-9
            depth = np.where(hit, inset, depth)
        k = int(np.argmax(depth))
        worst = float(depth[k])
        deeper = worst >= tool.radius / 2.0 - 1e-9
        at = plan.wcs.from_wcs([points[judge[k]]])[0]
        count = len(bad)
        out.append(finding(
            "gouge", "error", "gouge_3d",
            f"{op.summary} cuts into the part: up to {worst:.2f} mm{'+' if deeper else ''} at {count} point"
            f"{'s' if count > 1 else ''}",
            "a 3D pass goes lower than the drop-cutter allows: this is a planning fault, or faces and a stock to leave "
            "the operation should not have; report it if the job is right",
            [{"setup": op.setup, "operation": op.index, "depth_mm": round(worst, 3), "count": count,
              "at": xyz(at)}]))
    return out
