"""``turn_rough``: rough the turned profile on the outside (``side: "od"``) or in a bore (``"id"``), in passes along Z.

Own keys: ``side`` (``od``, the default, or ``id``), ``doc_mm`` (radial depth of cut a pass; default the material's,
0.6 of it in a bore), ``retract_mm`` (how far each pass backs off at 45°; default 0.5), ``allowance_x_mm`` and
``allowance_z_mm`` (left for the finish pass, radial and axial; default ``stock_to_leave_mm``, else 0.2 and 0.1),
``beyond_mm`` (how far past the part's back end the profile is carried, so the part-off line is clean; default the
nose radius plus 0.5 where the bar is long enough), ``cleanup`` (one profile-following pass at the allowance after
the steps; default true), ``reach_mm`` (a boring bar: how far it stands inward of its nose; default half the bar's
``diameter_mm``, else 3), ``css_m_min``, ``feed_mm_rev``.

The passes run towards the chuck at levels ``doc_mm`` apart, from the stock as it stands (everything planned before
is simulated), each ending where the insert would touch the profile plus its allowance (the insert's nose radius,
its edges and its holder are kept off the part, so a back taper steeper than its end clearance is left alone), then
pull off at 45°. A bore needs a hole to start in (``turn_drill`` it first); its passes also stop short of material
the bar would run into. Regions only a plunge can reach (grooves, undercuts) are left for ``turn_groove`` and named in
the note. A profile that only steps out (od) or in (id) is also emitted as a G71 cycle a post may use.
"""

from __future__ import annotations

from cadgen._internal.cam.job_errors import CamJobError, read_number
from cadgen._internal.cam.operations._turning import (BIG, TURN_KEYS, TurnOperation, feed_path, first_hit, lathe,
                                                       levels, monotonic, note, profile_path, swept_by)

__all__ = ["TurnRoughOp"]


class TurnRoughOp(TurnOperation):
    name = "turn_rough"
    plain = "Rough turn"
    keys = ("side", "doc_mm", "retract_mm", "allowance_x_mm", "allowance_z_mm", "beyond_mm", "cleanup", "reach_mm",
            *TURN_KEYS)
    common_keys = ("feed", "speed", "stock_to_leave_mm")
    tool_types = ("turn",)
    feeds_kind = "turn_rough"

    def parse(self, spec, ctx):
        params = super().parse(spec, ctx)
        extra, where = spec.extra, spec.where
        leave = spec.stock_to_leave_mm
        params.update(
            side=self.side(spec),
            doc_mm=read_number(extra, "doc_mm", where),
            retract_mm=read_number(extra, "retract_mm", where, default=0.5),
            allowance_x_mm=read_number(extra, "allowance_x_mm", where, minimum=0.0, default=leave or 0.2),
            allowance_z_mm=read_number(extra, "allowance_z_mm", where, minimum=0.0, default=leave or 0.1),
            beyond_mm=read_number(extra, "beyond_mm", where, minimum=0.0),
            cleanup=self.flag(spec, "cleanup", True),
            reach_mm=read_number(extra, "reach_mm", where),
        )
        return params

    def plan(self, ctx, params):
        from cadgen._internal.cam.feeds import turn_depth_of_cut
        from cadgen._internal.cam.turn_profile import tool_shape

        lt = lathe(ctx)
        tool = ctx.tool
        side = params["side"]
        inside = side == "id"
        reach = params["reach_mm"] or (tool.diameter_mm / 2.0 if tool.diameter_mm else 3.0)
        shape_params = {"reach_mm": reach} if inside else {}
        role = "id" if inside else "od"
        shapes = tool_shape(tool, role, **shape_params)
        ctx.meta["lathe"] = {"role": role, **shape_params}
        ctx.meta["what"] = "OD" if not inside else "bore"
        p = lt.profile
        room = max(0.0, p.z_back - lt.bar_back)
        beyond = params["beyond_mm"] if params["beyond_mm"] is not None else min(tool.nose_radius_mm + 0.5, room)
        target = lt.target(beyond=beyond)
        ax, az = params["allowance_x_mm"], params["allowance_z_mm"]
        forbidden = lt.forbidden(target, shapes, allowance_x=ax, allowance_z=az)
        doc = params["doc_mm"] or turn_depth_of_cut(ctx.material, inside=inside)
        rr = params["retract_mm"]
        b = lt.builder()
        lt.begin(b)
        front = lt.front()
        if front is None:
            note(ctx, "there is no stock left to rough")
            lt.feeds("turn_rough", 2.0 * lt.bar_radius, params)
            lt.home(b)
            return b.build()
        z_start = front + lt.approach
        if not inside:
            top = lt.top()
            feeds = lt.feeds("turn_rough", 2.0 * top, params)
            passes, deepest = _od(lt, b, forbidden, top, z_start, doc, rr, feeds.feed_mm_min, params, ctx, p, beyond)
        else:
            hole = lt.hole(p.z_front - 0.5, p.z_front + 1e-6)
            need = reach + 2.0 * tool.nose_radius_mm
            if hole >= BIG or hole < need:
                raise CamJobError(f"{ctx.spec.where}: a bore rough needs a hole on the axis to start in, at least "
                                  f"Ø{2 * need:.3g} for {tool.id} (its bar reaches {reach:g} mm inward); add a "
                                  "turn_drill before it, or set reach_mm")
            feeds = lt.feeds("turn_rough", 2.0 * hole, params)
            passes, deepest = _id(lt, b, forbidden, hole, z_start, doc, rr, feeds.feed_mm_min, params, ctx, reach)
        ctx.meta.update({"passes": passes, "doc_mm": round(doc, 4), "stock_to_leave": max(ax, az),
                         "allowance_mm": [ax, az]})
        if deepest is not None:
            ctx.meta["bottom_z"] = round(deepest, 4)
        lt.home(b)
        return b.build()


def _level(b, lt, x: float, z_end: float, z_start: float, begin: float, rr: float, f: float, inside: bool) -> None:
    """One pass at radius ``x``: in front of the material, along Z to ``z_end``, then off at 45 degrees."""
    if b.pos[2] < begin:
        b.rapid(z=begin)
    b.rapid(x=x)
    if b.pos[2] > begin + 1e-9:
        b.rapid(z=begin)
    b.feed(z=z_end, f=f)
    b.feed(x=x - rr if inside else x + rr, z=z_end + rr, f=f)


def _od(lt, b, forbidden, top, z_start, doc, rr, f, params, ctx, profile, beyond):
    import shapely

    material = lt.material()
    x_start = top + lt.approach
    b.rapid(x=x_start)
    keep = lambda x, z: x <= top + 1e-6  # noqa: E731 - the profile only matters under the stock
    z_low = profile.z_back - beyond - 1.0
    # A profile that only steps outward (and back) is also a G71 the post may emit instead of these moves.
    finished = lt.forbidden(lt.target(beyond=beyond), _shapes(ctx, "od"))
    finished_path = profile_path(finished, side="od", z_high=finished.bounds[3], z_low=z_low, keep=keep,
                                 tolerance=ctx.tolerance_mm / 4.0)
    cycle = None
    if monotonic(finished_path, "od"):
        b.rapid(z=z_start)
        cycle = b.begin_cycle(cycle="turn_rough", external=True,
                              profile=[[round(x, 4), round(z, 4)] for x, z in finished_path],
                              depth_mm=doc, allowance_x_mm=params["allowance_x_mm"],
                              allowance_z_mm=params["allowance_z_mm"], retract_mm=rr, feed=f, x_start=x_start,
                              z_start=z_start)
    passes, deepest = 0, None
    clip = 2 * ctx.tool.nose_radius_mm + 2 * max(params["allowance_x_mm"], params["allowance_z_mm"]) + 0.1
    for x in levels(forbidden, start=top, far=0.0, doc=doc, z_start=z_start, front=z_start - lt.approach, clip=clip):
        z_end = first_hit(forbidden, x, z_start)
        band = shapely.intersection(material, shapely.box(x, z_end, BIG, z_start))
        if band.is_empty or band.area < 1e-3:
            continue
        _level(b, lt, x, z_end, z_start, min(z_start, float(band.bounds[3]) + lt.approach), rr, f, False)
        passes += 1
        deepest = z_end if deepest is None else min(deepest, z_end)
    path = profile_path(forbidden, side="od", z_high=forbidden.bounds[3], z_low=z_low, keep=keep,
                        tolerance=ctx.tolerance_mm / 4.0)
    if params["cleanup"] and len(path):
        if b.pos[2] < z_start:
            b.rapid(z=z_start)
        b.rapid(x=path[0][0])
        if b.pos[2] > z_start:
            b.rapid(z=z_start)
        feed_path(b, path, f)
        xl, zl = path[-1]
        b.feed(x=xl + rr, z=zl + rr, f=f)
        passes += 1
        deepest = zl if deepest is None else min(deepest, zl)
    b.rapid(x=x_start)
    if cycle is not None:
        b.rapid(z=z_start)
        b.end_cycle(cycle)
    _report_left(lt, ctx, path, "od", params)
    return passes, deepest


def _id(lt, b, forbidden, hole, z_start, doc, rr, f, params, ctx, reach):
    import numpy as np
    import shapely

    from cadgen._internal.cam.turn_profile import sweep

    material = lt.material()
    shapes = _shapes(ctx, "id", reach_mm=reach)
    r = ctx.tool.nose_radius_mm
    p = lt.profile
    inner = hole - 0.2                     # inside the hole: the bar's way in and out
    b.rapid(x=inner)
    passes, deepest = 0, None
    x_previous = hole
    widest = float(np.nanmax(p.bore[:, 0])) if len(p.bore) else hole
    clip = 2 * r + 2 * max(params["allowance_x_mm"], params["allowance_z_mm"]) + 0.1
    for x in levels(forbidden, start=hole, far=max(widest, hole), doc=doc, z_start=z_start,
                    front=z_start - lt.approach, clip=clip):
        z_end = first_hit(forbidden, x, z_start)
        # The bar (inward of the nose) must run in the hole cut so far: stop short of material ahead of it.
        strip = shapely.intersection(material, shapely.box(max(0.0, x - 2 * r - reach - 0.5), -BIG,
                                                           x_previous - 1e-3, z_start))
        if not strip.is_empty and strip.area > 1e-9:
            z_end = max(z_end, float(strip.bounds[3]) + 0.2)
        if z_end >= z_start - lt.approach - 1e-6:
            break
        band = shapely.intersection(material, shapely.box(x_previous - 1e-3, z_end, x, z_start))
        x_previous = x
        if band.is_empty or band.area < 1e-3:
            continue
        begin = min(z_start, float(band.bounds[3]) + lt.approach)
        _level(b, lt, x, z_end, z_start, begin, rr, f, True)
        # What this pass opened is open for the next one's bar.
        material = shapely.difference(material, sweep([(x, begin), (x, z_end), (x - rr, z_end + rr)], shapes))
        passes += 1
        deepest = z_end if deepest is None else min(deepest, z_end)
    if params["cleanup"]:
        # The bar must stay in what is open by now: the stock less what these passes cut.
        opened = shapely.difference(material, swept_by(b.build(), _shapes(ctx, "id", reach_mm=reach)))
        shapely.prepare(opened)

        def keep(x, z):
            # Inward of a pass's depth from the nose must be open already: the edge takes no more than a pass.
            inner = x - 2 * r - reach
            bar = shapely.box(max(0.0, inner - 0.5), z + 0.05, max(0.0, x - 2 * r - doc), z + BIG)
            return inner > -1e-6 and not shapely.intersects(opened, bar.buffer(-0.01))

        path = profile_path(forbidden, side="id", z_high=forbidden.bounds[3], z_low=p.z_back - 1.0, keep=keep,
                            tolerance=ctx.tolerance_mm / 4.0)
        if len(path):
            if b.pos[2] < z_start:
                b.rapid(z=z_start)
            b.rapid(x=path[0][0])
            if b.pos[2] > z_start:
                b.rapid(z=z_start)
            feed_path(b, path, f)
            xl, zl = path[-1]
            b.feed(x=xl - rr, z=zl + rr, f=f)
            passes += 1
            deepest = zl if deepest is None else min(deepest, zl)
    b.rapid(x=min(b.pos[0], inner))
    return passes, deepest


def _report_left(lt, ctx, path, side, params) -> None:
    from cadgen._internal.cam.operations._turning import unreached

    left = unreached(lt, path, _shapes(ctx, side), side=side,
                     allowance=max(params["allowance_x_mm"], params["allowance_z_mm"]))
    if left:
        where = ", ".join(f"Z{g.bounds[1]:.3g}..{g.bounds[3]:.3g}" for g in left[:4])
        note(ctx, f"{len(left)} groove{'s' if len(left) > 1 else ''} or undercut{'s' if len(left) > 1 else ''} "
             f"the insert cannot reach from the front {'are' if len(left) > 1 else 'is'} left ({where}): plunge "
             "them with turn_groove, or use a sharper insert")


def _shapes(ctx, role, **params):
    from cadgen._internal.cam.turn_profile import tool_shape

    return tool_shape(ctx.tool, role, **params)
