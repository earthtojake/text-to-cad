"""``scallop`` (lite): finish in rings a constant stepover apart, offset in from the boundary and dropped onto the part.

Keys: ``direction`` (``climb``, the default, or ``conventional``: which way round the rings run); and the shared
``stepover`` (default 0.1 of the diameter), ``stock_to_leave_mm``, ``faces`` (the tool centre stays over those faces'
footprint) or ``region`` (``{"polygon": [[x, y], ...]}``, WCS). Without faces or a region the rings cover the part's
whole silhouette.

How it plans: the boundary is offset inward by the stepover again and again (in the XY plane, as seen from the tool);
each ring is sampled, dropped onto the part with the stock to leave and refined like ``parallel`` (midpoints where
the drop-cutter surface strays from a straight move by more than half the tolerance), cut from the outside in, and
joined to the next ring by a short feed along the surface where it is near.
"""

from __future__ import annotations

from cadgen._internal.cam.job_errors import CamJobError, choice
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["ScallopOp"]


class ScallopOp(Operation):
    name = "scallop"
    plain = "Scallop"
    family = "3D milling"
    machines = MILLS
    status = "lite"
    limits = (
        "The stepover is constant in the part's plan view, not along the surface: on a slope the real distance "
        "between passes grows by 1/cos(slope), so steep walls get a coarser finish; pair it with waterline there.",
        "Rings are offsets of the boundary's outline, not of the 3D surface, so the finish is even only where the "
        "surface's shape follows the boundary's.",
    )
    keys = ("direction",)
    common_keys = ("feed", "speed", "stepover", "stepover_mm", "stock_to_leave_mm")
    tool_types = ("ball", "bull", "flat")
    takes_faces = True
    takes_region = True
    feeds_kind = "finish"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        if spec.faces and spec.region is not None:
            raise CamJobError(f"{spec.where}: give a scallop faces or a region, not both")
        return {
            "climb": choice(spec.extra.get("direction", "climb"), ("climb", "conventional"),
                            f"{spec.where}.direction") == "climb",
            "region": region_polygon(spec, where=spec.where)[0] if spec.region is not None else None,
        }

    def plan(self, ctx, params):
        import numpy as np

        from cadgen._internal.cam import fit, geom2d
        from cadgen._internal.cam.milling3d import Linker, StockNow, boundary, drape, drop_mesh, simplify
        from cadgen._internal.cam.operations.parallel import densify

        tool = ctx.tool
        r = tool.radius
        leave = ctx.spec.stock_to_leave_mm
        tol = max(0.002, ctx.tolerance_mm)
        heights = ctx.heights
        floor = heights.part_bottom
        stepover = ctx.stepover(0.1)
        feeds = ctx.feeds("finish", stepover_mm=stepover)
        area = boundary(ctx, params["region"])
        b = ctx.builder()
        if area.is_empty or area.area < 1e-6:
            ctx.meta["note"] = "nothing to cut: the boundary is empty"
            return b.build()
        rings = []
        k = 0
        while True:
            shape = area if k == 0 else geom2d.offset(area, -k * stepover, tolerance=tol)
            if shape.is_empty or shape.area < 1e-6 or k > 20000:
                break
            # Material inside each ring (outside-in): climb runs it clockwise, as round an island.
            rings.extend(geom2d.rings(shape, climb=not params["climb"]))
            k += 1
        length = sum(float(np.hypot(*np.diff(ring, axis=0).T).sum()) for ring in rings)
        spacing, steps = fit.sample_spacing(length, min(1.0, max(0.05, r / 2.0)), fit.Budget(), dims=1,
                                            what="scallop rings")
        ctx.meta["adapted"] = steps
        mesh = drop_mesh(ctx)
        draped = drape([densify(ring, spacing) for ring in rings], tool, mesh, leave=leave, floor=floor,
                       tolerance=tol / 2.0)
        link = Linker(ctx, b, mesh, leave=leave, floor=floor, feeds=feeds, hop=max(2.5 * stepover, tool.diameter_mm),
                      stock_now=StockNow(ctx))
        for points in draped:
            points = simplify(points, tol / 2.0)
            # Start each ring at its point nearest the tool.
            here = np.asarray(b.pos[:2])
            j = int(np.argmin(np.hypot(points[:-1, 0] - here[0], points[:-1, 1] - here[1])))
            points = np.vstack([points[j:-1], points[:j + 1]])
            link.to(points[0])
            b.polyline(points[1:], f=feeds.feed_mm_min)
        link.finish()
        ctx.meta.update({"passes": len(draped), "stock_to_leave": leave,
                         "links": {"hops": link.hops, "retracts": link.retracts}})
        return b.build()
