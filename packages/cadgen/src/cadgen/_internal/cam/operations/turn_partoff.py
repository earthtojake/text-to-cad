"""``turn_partoff``: cut the finished part off the bar with a part-off blade, plunging at the part's back end.

Own keys: ``z_mm`` (the part's side of the cut, WCS; default the part's back end), ``x_end_mm`` (where the blade
stops; default a hair past the centre, or just inside a bore that runs through), ``peck_mm`` (back off every so deep
to break the chip; default none), ``slow_diameter_mm`` (below this diameter the feed drops, as the part gets ready
to fall and the blade nears the centre; default a quarter of the bar, at least 3 mm), ``slow_factor`` (that feed's
share; default 0.5), ``css_m_min``, ``feed_mm_rev``.

The blade's controlled point is its tip corner on the chuck side, so it cuts from ``z_mm - width_mm`` to ``z_mm``: the
part keeps its length. It feeds in from just outside the stock, then backs straight out radially (the part is off).
"""

from __future__ import annotations

from cadgen._internal.cam.job_errors import CamJobError, read_number
from cadgen._internal.cam.operations._turning import TURN_KEYS, TurnOperation, lathe, note

__all__ = ["TurnPartoffOp"]


class TurnPartoffOp(TurnOperation):
    name = "turn_partoff"
    plain = "Part off"
    keys = ("z_mm", "x_end_mm", "peck_mm", "slow_diameter_mm", "slow_factor", *TURN_KEYS)
    common_keys = ("feed", "speed")
    tool_types = ("partoff", "groove")
    feeds_kind = "partoff"

    def parse(self, spec, ctx):
        params = super().parse(spec, ctx)
        extra, where = spec.extra, spec.where
        params.update(z_mm=read_number(extra, "z_mm", where, minimum=-1e6),
                      x_end_mm=read_number(extra, "x_end_mm", where, minimum=-1e6),
                      peck_mm=read_number(extra, "peck_mm", where),
                      slow_diameter_mm=read_number(extra, "slow_diameter_mm", where, minimum=0.0),
                      slow_factor=read_number(extra, "slow_factor", where, default=0.5, maximum=1.0))
        return params

    def plan(self, ctx, params):
        lt = lathe(ctx)
        tool = ctx.tool
        p = lt.profile
        width = tool.width_mm
        z_part = params["z_mm"] if params["z_mm"] is not None else p.z_back
        z_blade = z_part - width
        ctx.meta["lathe"] = {"role": "partoff"}
        ctx.meta["what"] = f"at Z{z_part:.4g}"
        if z_blade < lt.bar_back - 1e-6:
            raise CamJobError(f"{ctx.spec.where}: the bar ends at Z{lt.bar_back:.4g}, so a {width:g} mm blade has no "
                              f"room to part off at Z{z_part:.4g}; give a longer stock.length_mm (the part plus the "
                              "blade plus what the chuck holds)")
        if z_part > p.z_back + 1e-6:
            note(ctx, f"parts off at Z{z_part:.4g}, inside the part (its back end is at Z{p.z_back:.4g})")
        b = lt.builder()
        lt.begin(b)
        top = lt.top(z_blade, z_part) or lt.bar_radius
        feeds = lt.feeds("partoff", 2.0 * top, params)
        f = feeds.feed_mm_min
        hole = lt.hole(z_blade, z_part)
        if params["x_end_mm"] is not None:
            x_end = params["x_end_mm"]
        elif 0.0 < hole < top:
            x_end = max(0.0, hole - 0.3)
        else:
            x_end = -0.2
        slow = (params["slow_diameter_mm"] if params["slow_diameter_mm"] is not None
                else max(3.0, 0.5 * lt.bar_radius)) / 2.0
        x_start = top + lt.approach
        x_travel = (lt.top(z_blade) or top) + lt.approach
        b.rapid(x=x_travel)
        b.rapid(z=z_blade)
        b.rapid(x=x_start)
        x = x_start
        stops = [v for v in (max(slow, x_end), x_end) if v < x - 1e-9]
        peck = params["peck_mm"]
        for k, stop in enumerate(stops):
            rate = f if k == 0 and stop > x_end + 1e-9 else f * params["slow_factor"]
            while peck and x - peck > stop + 1e-9:
                x -= peck
                b.feed(x=x, f=rate)
                b.rapid(x=x + min(0.5, peck))
                b.feed(x=x, f=rate)
            b.feed(x=stop, f=rate)
            x = stop
        b.rapid(x=x_travel)
        ctx.meta.update({"bottom_z": round(z_blade, 4), "x_end": round(x_end, 4)})
        lt.home(b)
        return b.build()
