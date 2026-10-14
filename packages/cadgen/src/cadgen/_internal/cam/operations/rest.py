"""``rest``: rest machining: a ``rough``, ``parallel`` or ``waterline`` kept to where material is still left.

Keys: ``of`` (``rough``, ``parallel`` or ``waterline``: the operation to run there; required),
``from_tool_diameter_mm`` (optional: judge what is left by a bigger tool of this diameter, the same type as this
operation's, having finished everywhere, instead of by the simulated stock), and the chosen operation's own keys
(``rough``: ``bottom_z``, ``ramp_angle_deg``, ``direction``; ``parallel``: ``angle_deg``, ``pattern``,
``min_slope_deg``, ``max_slope_deg``; ``waterline``: ``min_slope_deg``, ``max_slope_deg``, ``direction``); and the
shared keys as that operation reads them (``faces`` or ``region`` for parallel and waterline, ``region`` for rough).

Where material is left: by default, the stock as it stands before this operation (every earlier operation replayed
on the heightfield simulator) standing more than ``stock_to_leave_mm`` plus 0.05 mm (or twice the tolerance) over
the part; with ``from_tool_diameter_mm``, what that bigger tool's cutter could not reach. That area, cleaned of
single-cell specks along walls and grown by this tool's radius, is where the tool centre may go; the chosen
operation plans inside it.
"""

from __future__ import annotations

from cadgen._internal.cam.job_errors import CamJobError, choice, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation

__all__ = ["RestOp"]

_INNER = {"rough": ("bottom_z", "ramp_angle_deg", "direction"),
          "parallel": ("angle_deg", "pattern", "min_slope_deg", "max_slope_deg"),
          "waterline": ("min_slope_deg", "max_slope_deg", "direction")}


class RestOp(Operation):
    name = "rest"
    plain = "Rest machining"
    family = "3D milling"
    machines = MILLS
    status = "full"
    keys = ("of", "from_tool_diameter_mm", "bottom_z", "ramp_angle_deg", "direction", "angle_deg", "pattern",
            "min_slope_deg", "max_slope_deg")
    tool_types = ("flat", "ball", "bull")
    takes_faces = True
    takes_region = True
    feeds_kind = "finish"

    def shared_keys(self, spec):
        # The shared keys as the chosen operation reads them: a parallel has no step down.
        if spec.extra.get("of") == "parallel":
            return tuple(key for key in self.common_keys if key != "stepdown_mm")
        return self.common_keys

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        extra = spec.extra
        if "of" not in extra:
            raise CamJobError(f"{spec.where}: a rest needs \"of\", the operation to run where material is left: "
                              f"{', '.join(_INNER)}")
        of = choice(extra["of"], tuple(_INNER), f"{spec.where}.of")
        inner = {key: value for key, value in extra.items() if key not in ("of", "from_tool_diameter_mm")}
        for key in inner:
            if key not in _INNER[of]:
                raise CamJobError(f"{spec.where}: '{key}' is not a key of a {of}; a rest of {of} takes "
                                  f"{', '.join(('of', 'from_tool_diameter_mm') + _INNER[of])}")
        tool = ctx.job.tool(spec.tool)
        reference = read_number(extra, "from_tool_diameter_mm", spec.where)
        if reference is not None and reference <= tool.diameter_mm:
            raise CamJobError(f"{spec.where}.from_tool_diameter_mm ({reference:g}) must be more than {tool.id}'s "
                              f"diameter ({tool.diameter_mm:g}): it is the bigger tool that went before")
        if of == "rough":
            from cadgen._internal.cam.operations.rough import parse_rough

            if spec.faces:
                raise CamJobError(f"{spec.where}: a rest of rough takes no faces; give a region or nothing")
            params = parse_rough(spec, inner)
        elif of == "parallel":
            from cadgen._internal.cam.operations.parallel import parse_parallel

            params = parse_parallel(spec, inner)
        else:
            from cadgen._internal.cam.operations.waterline import parse_waterline

            params = parse_waterline(spec, inner)
        return {"of": of, "reference_mm": reference, "inner": params}

    def summary(self, ctx, params) -> str:
        return super().summary(ctx, params).replace(self.plain, f"{self.plain} ({params['of']})", 1)

    def plan(self, ctx, params):
        import dataclasses

        from cadgen._internal.cam import geom2d
        from cadgen._internal.cam.milling3d import StockNow, boundary, reference_rest_area

        tool = ctx.tool
        r = tool.radius
        leave = ctx.spec.stock_to_leave_mm
        threshold = leave + max(0.05, 2.0 * ctx.tolerance_mm)
        inner = params["inner"]
        area = boundary(ctx, inner.get("region") if params["of"] != "rough" else
                        (inner["region"][0] if inner["region"] is not None else None), grow=r)
        if params["reference_mm"] is not None:
            reference = dataclasses.replace(tool, diameter_mm=params["reference_mm"],
                                            corner_radius_mm=min(tool.corner_radius_mm, params["reference_mm"] / 2))
            spacing = min(0.25, max(0.05, r / 4.0))
            left = reference_rest_area(ctx, reference, area, leave=leave, threshold=threshold, spacing=spacing)
            source = f"a {params['reference_mm']:g} mm tool"
        else:
            stock = StockNow(ctx)
            left = stock.rest_area(threshold=threshold)
            spacing = stock.cell
            source = "the simulated stock"
            if left is None:
                ctx.meta["adapted"] = [{"step": "rest", "words": f"setup '{ctx.setup.id}' is not a top or bottom "
                                        "setup, so the stock is not simulated there: the rest runs everywhere"}]
                left = area
        limit = geom2d.offset(left, r + spacing, tolerance=ctx.tolerance_mm) if not left.is_empty else left
        ctx.meta["rest_area_mm2"] = round(float(left.area), 2)
        ctx.meta["rest_from"] = source
        if limit.is_empty:
            ctx.meta["note"] = f"nothing left to cut: {source} leaves no more than {threshold:g} mm anywhere"
            return ctx.builder().build()
        if params["of"] == "rough":
            from cadgen._internal.cam.operations.rough import plan_rough

            return plan_rough(ctx, inner, limit=limit)
        if params["of"] == "parallel":
            from cadgen._internal.cam.operations.parallel import plan_parallel

            return plan_parallel(ctx, inner, limit=limit)
        from cadgen._internal.cam.operations.waterline import plan_waterline

        return plan_waterline(ctx, inner, limit=limit)
