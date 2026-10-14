"""``turn_drill``: a centre hole or a hole on the spindle axis, the part turning and the drill (or centre/spot
drill) held still in the tailstock or a turret, with an optional peck.

Own keys: ``depth_mm`` (below the material's face, to the drill's point), ``z_mm`` (the point's WCS height, instead
of a depth), ``peck_mm`` (peck so deep, then out to the R plane: G83; default no peck), ``chipbreak`` (peck by
backing off a little instead of coming out: G73; default false), ``dwell_s`` (at the bottom; a centre drill's
default 0.2 s), ``beyond_mm`` (a through bore: how far past the part's back end the drill's full diameter goes;
default 1 where the bar is long enough).

Without a depth, a centre (spot) drill goes in until its countersink is 0.8 of its diameter across, and a drill goes
as deep as the part's bore stays at least its diameter: through it (and ``beyond_mm`` past the part's end) for a
through bore, its point to the floor of a blind one. A drill wider than the bore it would make is refused. The cycle
is carried as a ``cycle`` event (a post may emit G81/G83/G73 on the axis) and as plain moves. Speed and feed are the
drill's (the milling table's), at a constant rpm, posted per revolution.
"""

from __future__ import annotations

import dataclasses
import math

from cadgen._internal.cam.job_errors import CamJobError, read_number
from cadgen._internal.cam.operations._turning import TurnOperation, lathe, note

__all__ = ["TurnDrillOp"]


class TurnDrillOp(TurnOperation):
    name = "turn_drill"
    plain = "Centre drill"
    keys = ("depth_mm", "z_mm", "peck_mm", "chipbreak", "dwell_s", "beyond_mm")
    common_keys = ("feed", "speed")
    tool_types = ("drill", "spot")
    feeds_kind = "drill"

    def parse(self, spec, ctx):
        params = super().parse(spec, ctx)
        extra, where = spec.extra, spec.where
        params.update(depth_mm=read_number(extra, "depth_mm", where), z_mm=read_number(extra, "z_mm", where,
                                                                                       minimum=-1e6),
                      peck_mm=read_number(extra, "peck_mm", where), chipbreak=self.flag(spec, "chipbreak", False),
                      dwell_s=read_number(extra, "dwell_s", where, minimum=0.0),
                      beyond_mm=read_number(extra, "beyond_mm", where, minimum=0.0))
        if params["depth_mm"] is not None and params["z_mm"] is not None:
            raise CamJobError(f"{where}: give depth_mm or z_mm, not both")
        if params["chipbreak"] and not params["peck_mm"]:
            raise CamJobError(f"{where}: chipbreak pecks: give peck_mm too")
        return params

    def plan(self, ctx, params):
        from cadgen._internal.cam.feeds import LATHE_MAX_RPM, for_op

        lt = lathe(ctx)
        tool = ctx.tool
        p = lt.profile
        r = tool.radius
        spot = tool.type == "spot"
        half = math.radians((tool.angle_deg or 90.0) / 2.0 if spot else tool.point_angle / 2.0)
        cone = r / math.tan(half)
        ctx.meta["lathe"] = {"role": "drill"}
        b = lt.builder()
        lt.begin(b)
        kind = "spot" if spot else "drill"
        speed = ctx.spec.speed
        if speed is None and ctx.machine.max_rpm is None:
            probe = for_op(ctx.material, tool, kind, ctx.machine)
            speed = min(probe.rpm, LATHE_MAX_RPM) if probe.rpm > LATHE_MAX_RPM else None
        feeds = for_op(ctx.material, tool, kind, ctx.machine, feed=ctx.spec.feed, speed=speed)
        feeds = dataclasses.replace(feeds, feed_mm_rev=round(feeds.feed_mm_min / max(feeds.rpm, 1.0), 5),
                                    max_rpm=ctx.machine.max_rpm or LATHE_MAX_RPM)
        ctx.chosen_feeds.append(feeds)
        face = lt.front(0.0, max(r, 0.01))
        if face is None:
            note(ctx, "there is no material on the axis to drill")
            lt.home(b)
            return b.build()
        if params["z_mm"] is not None:
            tip = params["z_mm"]
        elif params["depth_mm"] is not None:
            tip = face - params["depth_mm"]
        elif spot:
            tip = face - 0.4 * tool.diameter_mm / math.tan(half)
        else:
            tip = _bore_tip(ctx, lt, p, r, cone, params)
        if tip >= face - 1e-6:
            note(ctx, "the hole is already there: nothing to drill")
            lt.home(b)
            return b.build()
        r_plane = face + lt.approach
        f = feeds.feed_mm_min
        cycle_kind = "spot" if spot and not params["peck_mm"] else ("chipbreak" if params["chipbreak"] else
                                                                   "peck" if params["peck_mm"] else "drill")
        dwell = params["dwell_s"] if params["dwell_s"] is not None else (0.2 if spot else 0.0)
        b.rapid(x=0.0)
        b.rapid(z=r_plane)
        handle = b.begin_cycle(cycle=cycle_kind, holes=[[0.0, 0.0, round(face, 4)]], z_bottom=round(tip, 4),
                               r_plane=round(r_plane, 4), retract="r", initial_z=round(lt.z_clear, 4),
                               peck_mm=params["peck_mm"] or 0.0, dwell_s=dwell, feed=f)
        peck = params["peck_mm"]
        if peck:
            z = face
            while z > tip + 1e-9:
                z_next = max(tip, z - peck)
                b.feed(z=z_next, f=f)
                z = z_next
                if z <= tip + 1e-9:
                    break
                if params["chipbreak"]:
                    b.rapid(z=z + min(0.3, peck / 2))
                else:
                    b.rapid(z=r_plane)
                    b.rapid(z=z + 0.5)
        else:
            b.feed(z=tip, f=f)
        b.dwell(dwell)
        b.rapid(z=r_plane)
        b.end_cycle(handle)
        depth = face - tip
        ctx.meta.update({"bottom_z": round(tip, 4), "depth_mm": round(depth, 4),
                         "what": f"Ø{tool.diameter_mm:g} x {depth:.3g} deep"})
        lt.home(b)
        return b.build()


def _bore_tip(ctx, lt, p, r: float, cone: float, params) -> float:
    """A drill's point height for the part's bore: through it, or to the floor of a blind one."""
    import numpy as np

    entry = float(p.r_in(p.z_front - 1e-3)[0])
    if entry <= 0:
        raise CamJobError(f"{ctx.spec.where}: the part has no bore on its axis to drill; give depth_mm (a centre hole, "
                          "or a hole that is turned away later)")
    if entry < r - 1e-6:
        raise CamJobError(f"{ctx.spec.where}: {ctx.tool.id} (Ø{2 * r:g}) is wider than the bore it would make "
                          f"(Ø{2 * entry:.4g} at its mouth); use a drill no wider than the bore")
    bore = p.bore
    # Walk the bore from the front while it stays at least the drill's radius.
    floor = None
    for (x0, z0), (x1, z1) in zip(bore[:-1], bore[1:]):
        if not (x0 >= r - 1e-6 and x1 >= r - 1e-6):
            floor = z0 if abs(z0 - z1) < 1e-9 else z0 + (z1 - z0) * (x0 - r) / (x0 - x1) if x0 != x1 else z0
            break
    if floor is None:
        room = max(0.0, p.z_back - lt.bar_back)
        beyond = params["beyond_mm"] if params["beyond_mm"] is not None else min(1.0, room)
        return p.z_back - beyond - cone
    narrower = float(np.nanmax(p.r_in([floor - 1e-3])))
    if narrower > 0:
        note(ctx, f"the bore narrows to Ø{2 * narrower:.4g} at Z{floor:.4g}: the drill stops with its point there")
    return float(floor)
