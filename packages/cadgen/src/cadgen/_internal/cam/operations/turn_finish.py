"""``turn_finish``: one pass along the finished profile, outside (``side: "od"``) or in a bore (``"id"``).

Own keys: ``side`` (``od``, the default, or ``id``), ``face`` (od: start with a pass across the front face from the
centre, or from the bore; default false), ``spring_passes`` (the same pass again, to take out tool spring; default
0), ``beyond_mm`` (how far past the part's back end the profile is carried; default the nose radius plus 0.5 where
the bar is long enough), ``reach_mm`` (a boring bar: how far it stands inward of its nose; default half the bar's
``diameter_mm``, else 3), ``css_m_min``, ``feed_mm_rev``. ``stock_to_leave_mm`` leaves that much all round.

The path is the edge of the region the tool's controlled point may not enter (the part grown by the reflected
insert: nose radius, edges and holder), so it is compensated for the nose radius in the path itself (post it with
G40) and never lets the insert's edges rub a back taper steeper than their clearance; what the insert cannot reach
is left and named in the note. A bore's pass stops where the bar would run into material it has not cleared.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, read_number
from cadgen._internal.cam.operations._turning import (BIG, TURN_KEYS, TurnOperation, feed_path, lathe, note,
                                                       profile_path, unreached)

__all__ = ["TurnFinishOp"]


class TurnFinishOp(TurnOperation):
    name = "turn_finish"
    plain = "Finish turn"
    keys = ("side", "face", "spring_passes", "beyond_mm", "reach_mm", *TURN_KEYS)
    common_keys = ("feed", "speed", "stock_to_leave_mm")
    tool_types = ("turn",)
    feeds_kind = "turn_finish"

    def parse(self, spec, ctx):
        params = super().parse(spec, ctx)
        extra, where = spec.extra, spec.where
        spring = extra.get("spring_passes", 0)
        if isinstance(spring, bool) or not isinstance(spring, int) or not 0 <= spring <= 5:
            raise CamJobError(f"{where}.spring_passes must be a whole number from 0 to 5")
        params.update(side=self.side(spec), face=self.flag(spec, "face", False), spring_passes=spring,
                      beyond_mm=read_number(extra, "beyond_mm", where, minimum=0.0),
                      reach_mm=read_number(extra, "reach_mm", where))
        if params["face"] and params["side"] == "id":
            raise CamJobError(f"{where}: face is for an outside finish; remove it or set side to \"od\"")
        return params

    def plan(self, ctx, params):
        import shapely

        from cadgen._internal.cam.turn_profile import sweep, tool_shape

        lt = lathe(ctx)
        tool = ctx.tool
        r = tool.nose_radius_mm
        inside = params["side"] == "id"
        reach = params["reach_mm"] or (tool.diameter_mm / 2.0 if tool.diameter_mm else 3.0)
        role = "id" if inside else "od"
        shape_params = {"reach_mm": reach} if inside else {}
        shapes = tool_shape(tool, role, **shape_params)
        ctx.meta["lathe"] = {"role": role, **shape_params}
        ctx.meta["what"] = "bore" if inside else "OD"
        p = lt.profile
        leave = ctx.spec.stock_to_leave_mm
        room = max(0.0, p.z_back - lt.bar_back)
        beyond = params["beyond_mm"] if params["beyond_mm"] is not None else min(r + 0.5, room)
        forbidden = lt.forbidden(lt.target(beyond=beyond), shapes, allowance_x=leave, allowance_z=leave)
        material = lt.material()
        b = lt.builder()
        lt.begin(b)
        front = lt.front()
        top = lt.top()
        z_start = (front if front is not None else p.z_front) + lt.approach
        rr = 0.5
        if not inside:
            feeds = lt.feeds("turn_finish", 2.0 * (top or p.r_max), params)
            limit = (top or p.r_max) + 1e-6
            path = profile_path(forbidden, side="od", z_high=forbidden.bounds[3], z_low=p.z_back - beyond - 1.0,
                                keep=lambda x, z: x <= limit, tolerance=ctx.tolerance_mm / 4.0)
            x_out = (top or p.r_max) + lt.approach
            b.rapid(x=x_out)
        else:
            hole = lt.hole(p.z_front - 0.5, p.z_front + 1e-6)
            if hole >= BIG or hole < reach + 2 * r:
                raise CamJobError(f"{ctx.spec.where}: a bore finish needs the bore open to at least "
                                  f"Ø{2 * (reach + 2 * r):.3g} for {tool.id}'s bar; rough it first (turn_rough side "
                                  "id) or set reach_mm")
            feeds = lt.feeds("turn_finish", 2.0 * hole, params)
            prepared = material
            shapely.prepare(prepared)

            def keep(x, z):
                # Inward of the finishing cut (1 mm, or four times the stock left) must be open already.
                inner = x - 2 * r - reach
                bar = shapely.box(max(0.0, inner - 0.5), z + 0.05, max(0.0, x - 2 * r - max(1.0, 4.0 * leave)),
                                  z + BIG)
                return inner > -1e-6 and not shapely.intersects(prepared, bar.buffer(-0.01))

            path = profile_path(forbidden, side="id", z_high=forbidden.bounds[3], z_low=p.z_back - beyond - 1.0,
                                keep=keep, tolerance=ctx.tolerance_mm / 4.0)
            x_out = hole - 0.2
            b.rapid(x=x_out)
        f = feeds.feed_mm_min
        if not len(path):
            note(ctx, "the profile is not under the stock: nothing to finish")
            lt.home(b)
            return b.build()
        lead = []
        if params["face"]:
            bore = float(p.r_in(p.z_front - 1e-3)[0])
            x_face = -r if bore <= 0 else max(0.0, bore - 2 * r)
            lead = [(x_face, path[0][1])]
        passes = 1 + params["spring_passes"]
        for _ in range(passes):
            first = lead[0] if lead else path[0]
            if b.pos[2] < z_start:
                b.rapid(z=z_start)
            b.rapid(x=first[0])
            if b.pos[2] > z_start:
                b.rapid(z=z_start)
            b.feed(z=first[1], f=f)
            feed_path(b, [*lead, *path], f)
            xl, zl = path[-1]
            b.feed(x=xl - rr if inside else xl + rr, z=zl + rr, f=f)
            b.rapid(x=x_out if not inside else min(b.pos[0], x_out))
        # A finish that takes a heavy cut is a job without a rough.
        cut = shapely.intersection(sweep(path, shapes), material)
        if not cut.is_empty:
            line = shapely.LineString(path)
            coords = shapely.get_coordinates(shapely.segmentize(cut, 0.1))
            heaviest = float(shapely.distance(shapely.points(coords), line).max()) if len(coords) else 0.0
            if heaviest > max(1.0, 4.0 * leave):
                note(ctx, f"the finish takes up to {heaviest:.2g} mm in one pass where the stock was not roughed to "
                     "the profile: rough it first (turn_rough), with an insert that reaches there")
        left = unreached(lt, path, shapes, side=role, allowance=leave)
        if left:
            where = ", ".join(f"Z{g.bounds[1]:.3g}..{g.bounds[3]:.3g}" for g in left[:4])
            note(ctx, f"{len(left)} groove{'s' if len(left) > 1 else ''} or undercut{'s' if len(left) > 1 else ''} the "
                 f"insert cannot reach {'are' if len(left) > 1 else 'is'} left ({where}): plunge them with "
                 "turn_groove, or use a sharper insert")
        ctx.meta.update({"passes": passes, "bottom_z": round(float(min(z for _, z in path)), 4),
                         "stock_to_leave": leave, "length_mm": round(float(math.fsum(
                             math.dist(a, c) for a, c in zip(path[:-1], path[1:]))), 3)})
        lt.home(b)
        return b.build()
