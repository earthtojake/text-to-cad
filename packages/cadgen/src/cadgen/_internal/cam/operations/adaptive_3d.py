"""``adaptive_3d`` (3D adaptive clear, lite): rough the stock down round the part's 3D shape in z levels at a capped
tool engagement, cutting only where material stands.

Keys: ``bottom_z`` (the lowest level, WCS; default the part's bottom, or the region's ``bottom_z``),
``ramp_angle_deg`` (helix entries, default 3), ``direction`` (``climb``, the default, or ``conventional``); and the
shared ``stepdown_mm`` (default twice the material's, within the flutes: deep and light), ``stepover`` (default 0.15
of the diameter, at most 0.5), ``stock_to_leave_mm`` and ``region`` (``{"polygon": [[x, y], ...], "bottom_z": z}``:
the tool centre kept inside it).

The levels are ``rough``'s: even step-downs from the stock top, plus every upward-facing flat of the part plus the
stock to leave, so flats are left exactly that thick. At each level the tool centre keeps its radius plus the stock to
leave off everything of the part above the level (its silhouette, :class:`~cadgen._internal.cam.milling3d.Silhouettes`)
and may go out into the air round the stock. The shared engine (:mod:`cadgen._internal.cam.operations._adaptive`)
clears that against the stock as it stands before the operation: what an earlier operation or setup cut is air, a
level with nothing left is skipped, an open side is come into from the air beside the stock and a closed cavity by a
helix, and the cleared area grows one stepover at a time, so the radial engagement never exceeds the stepover.

On slopes the levels leave steps up to the step-down tall (deeper than ``rough``'s): finish with ``parallel`` or
``waterline``, or rest machining. A bull tool is kept off the part by its full radius at every level (safe, a little
more material left on slopes). ``meta["air_fraction"]`` is the share of the cutting path that removes nothing.
"""

from __future__ import annotations

from cadgen._internal.cam.job_errors import PlanError
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations._adaptive import Clearing, check_stepover, default_stepdown
from cadgen._internal.cam.operations.base import Operation

__all__ = ["Adaptive3dOp"]


class Adaptive3dOp(Operation):
    name = "adaptive_3d"
    plain = "3D adaptive clear"
    family = "3D milling"
    machines = MILLS
    status = "lite"
    limits = (
        "Engagement is capped by growing the cleared area one stepover at a time, not by a true medial-axis "
        "adaptive solver: the radial step never exceeds the stepover, but a pass wrapping round a small cleared area "
        "cuts more per millimetre (up to about twice the stepover's worth on the first ring round an entry).",
        "No trochoidal slotting: a piece too narrow for a helix entry is entered by a ramp along its outline, cut "
        "at full width there.",
        "Z levels only: steps on slopes are left as tall as the step-down, with no finer intermediate levels.",
    )
    keys = ("bottom_z", "ramp_angle_deg", "direction")
    tool_types = ("flat", "bull")
    takes_region = True
    feeds_kind = "rough"

    def parse(self, spec, ctx):
        from cadgen._internal.cam.operations.rough import parse_rough

        super().parse(spec, ctx)
        check_stepover(spec, ctx.job.tool(spec.tool))
        return parse_rough(spec, spec.extra)

    def plan(self, ctx, params):
        from cadgen._internal.cam.milling3d import Silhouettes
        from cadgen._internal.cam.operations.pocket import _levels
        from cadgen._internal.cam.operations.rough import keep_off, lowest_level

        r = ctx.tool.radius
        leave = ctx.spec.stock_to_leave_mm
        top = ctx.heights.stock_top
        bottom = lowest_level(ctx, params)
        if bottom >= top - 1e-6:
            raise PlanError("empty_operation", f"{ctx.spec.where}: the lowest level (Z {bottom:.3f}) is at or above "
                            f"the stock top in setup '{ctx.setup.id}', so there is nothing to clear")
        clearing = Clearing(ctx, feeds_kind=self.feeds_kind, climb=params["climb"],
                            ramp_angle_deg=params["ramp_angle_deg"])
        stepdown = default_stepdown(ctx)
        # Out past the stock far enough that the tool's centre stands where its circle touches nothing.
        outer = ctx.stock_outline.buffer(r + 1.0 + clearing.stock_now.cell)
        vertices, triangles = ctx.mesh
        silhouettes = Silhouettes(vertices, triangles, ctx.sections)
        for z in _levels(ctx, top, bottom, stepdown, leave):
            area = outer.difference(keep_off(silhouettes, z, r, leave, ctx.tolerance_mm))
            if params["region"] is not None:
                area = area.intersection(params["region"][0])
            ctx.say(f"adaptive_3d level z {z:.3f}")
            clearing.level(area, z, part=ctx.sections.at(z), leave=leave)
        ctx.meta.update({"stock_to_leave": leave, "floor_z": round(bottom, 4),
                         "stepover_mm": round(clearing.stepover, 4), "stepdown_mm": round(stepdown, 4)})
        return clearing.finish(ctx.meta, nothing_left="the lowest level")
