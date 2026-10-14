"""``turn_groove``: plunge grooves with a grooving blade, outside (``side: "od"``) or in a bore (``"id"``).

A groove is a stretch of the profile lower (od) or wider (id) than the part on both sides of it, so a turning insert
cannot reach it from the front: relief grooves, ring grooves, undercuts. Which grooves: the ones holding the named
``faces`` (its floor or a wall), the ones at ``z_mm`` (a WCS height or a list), else every groove on that side.

Own keys: ``side`` (``od``, the default, or ``id``), ``z_mm``, ``allowance_mm`` (left on the floor and walls for a
finish; default ``stock_to_leave_mm``), ``peck_mm`` (break the chip every so deep; default none), ``dwell_s`` (at the
bottom of each plunge; default two revolutions), ``css_m_min``, ``feed_mm_rev``.

Each groove is plunged from its front wall back, the blade ``width_mm`` wide and each plunge overlapping the last by
a fifth of it, so a groove wider than the blade takes several plunges and its walls are cut exactly where they are.
Each plunge goes as deep as the blade's tip (its corner radii included) can go over the floor beneath it, so a
shaped floor is followed in steps. The tool's controlled point is the blade's tip corner on the chuck side (-Z). A
groove narrower than the blade is refused.
"""

from __future__ import annotations

import dataclasses
import math

from cadgen._internal.cam.job_errors import CamJobError, read_number
from cadgen._internal.cam.operations._turning import BIG, TURN_KEYS, TurnOperation, lathe

__all__ = ["TurnGrooveOp", "find_grooves"]

_HAIR = 1e-3


class TurnGrooveOp(TurnOperation):
    name = "turn_groove"
    plain = "Groove"
    keys = ("side", "z_mm", "allowance_mm", "peck_mm", "dwell_s", *TURN_KEYS)
    common_keys = ("feed", "speed", "stock_to_leave_mm")
    tool_types = ("groove",)
    takes_faces = True
    feeds_kind = "groove"

    def parse(self, spec, ctx):
        params = super().parse(spec, ctx)
        extra, where = spec.extra, spec.where
        params.update(side=self.side(spec), z_mm=self.z_list(spec, "z_mm"),
                      allowance_mm=read_number(extra, "allowance_mm", where, minimum=0.0,
                                               default=spec.stock_to_leave_mm),
                      peck_mm=read_number(extra, "peck_mm", where),
                      dwell_s=read_number(extra, "dwell_s", where, minimum=0.0))
        return params

    def plan(self, ctx, params):
        import shapely

        from cadgen._internal.cam.turn_profile import tool_shape

        lt = lathe(ctx)
        tool = ctx.tool
        width = tool.width_mm
        inside = params["side"] == "id"
        p = lt.profile
        grooves = find_grooves(p, side=params["side"])
        chosen = _choose(ctx, lt, grooves, params)
        if not chosen:
            where = "in the bore" if inside else "on the outside"
            raise CamJobError(f"{ctx.spec.where}: the part has no groove {where} (a stretch lower than the profile on "
                              "both sides of it); turn_rough and turn_finish cut the rest")
        b = lt.builder()
        lt.begin(b)
        feeds = lt.feeds("groove", 2.0 * max(g[2] for g in chosen), params)
        f = feeds.feed_mm_min
        dwell = params["dwell_s"] if params["dwell_s"] is not None else round(120.0 / max(feeds.rpm, 1.0), 3)
        leave = params["allowance_mm"]
        plunges = 0
        cut: list = []
        reach = 0.0
        if inside:
            hole = min(lt.hole(z_low, z_high) for z_low, z_high, _ in chosen)
            deepest = max(float(max(p.r_in([z_low + 1e-3, z_high - 1e-3]))) for z_low, z_high, _ in chosen)
            reach = deepest - hole + 1.0
            if hole >= BIG or reach > hole:
                raise CamJobError(f"{ctx.spec.where}: the bore (Ø{2 * hole:.3g} open) is too small for a groove "
                                  f"{deepest - hole:.2g} mm deep in it; open the bore first or groove from outside")
        role = "groove_id" if inside else "groove"
        shape_params = {"reach_mm": round(reach, 4)} if inside else {}
        ctx.meta["lathe"] = {"role": role, **shape_params}
        # Depths are probed with the blade a hair narrower (1 µm a side), so a blade exactly as wide as its groove
        # still finds the floor between the walls.
        narrow = tool_shape(dataclasses.replace(tool, width_mm=width - 2 * _HAIR), role, **shape_params)
        forbidden = lt.forbidden(lt.target(beyond=0.0), narrow, allowance_x=leave, allowance_z=leave)
        for z_low, z_high, lip in chosen:
            span = z_high - z_low - 2 * leave
            if span < width - 1e-6:
                raise CamJobError(f"{ctx.spec.where}: the groove at Z{z_low:g}..{z_high:g} is {z_high - z_low:g} mm "
                                  f"wide, narrower than {tool.id}'s {width:g} mm blade; use a narrower grooving tool")
            count = 1 if span <= width + 1e-9 else int(math.ceil((span - width) / (0.8 * width))) + 1
            first, last = z_high - leave - width, z_low + leave
            positions = [first] if count == 1 else [first + (last - first) * k / (count - 1) for k in range(count)]
            if not inside:
                over = lt.top(z_low + 1e-6, z_high - 1e-6) or lip
                x_start = over + lt.approach
                x_travel = (lt.top(z_low - 1e-3) or over) + lt.approach
                b.rapid(x=x_travel)
            else:
                x_start = max(0.0, lt.hole(z_low, z_high) - 0.5)
                x_travel = x_start
                b.rapid(x=x_travel)
            for z in positions:
                bottom = _depth(forbidden, z + _HAIR, inside, lip)
                b.rapid(z=z)
                b.rapid(x=x_start)
                _plunge(b, x_start, bottom, f, params["peck_mm"], dwell, inside)
                b.rapid(x=x_start)
                plunges += 1
            cut.append([round(z_low, 4), round(z_high, 4)])
            b.rapid(x=x_travel)
            if inside:
                b.rapid(z=lt.z_clear)
        ctx.meta.update({"grooves": cut, "passes": plunges, "dwell_s": dwell})
        ctx.meta["what"] = ", ".join(f"Z{a:g}..{c:g}" for a, c in cut[:3]) + (f" and {len(cut) - 3} more"
                                                                                if len(cut) > 3 else "")
        lt.home(b)
        return b.build()


def _depth(forbidden, z: float, inside: bool, lip: float) -> float:
    """How far the blade's tip can plunge at ``z`` (its chuck-side edge): the first point of ``forbidden`` from the
    lip's side."""
    import shapely

    if not inside:
        line = shapely.LineString([(lip + BIG / 1e3, z), (-BIG, z)])
        hit = shapely.intersection(line, forbidden)
        return float(hit.bounds[2]) if not hit.is_empty else 0.0
    line = shapely.LineString([(0.0, z), (BIG, z)])
    hit = shapely.intersection(line, forbidden)
    return float(hit.bounds[0]) if not hit.is_empty else lip


def _plunge(b, x_start: float, bottom: float, f: float, peck: float | None, dwell: float, inside: bool) -> None:
    sign = 1.0 if inside else -1.0
    if peck:
        depth = abs(bottom - x_start)
        done = 0.0
        while done + peck < depth - 1e-9:
            done += peck
            b.feed(x=x_start + sign * done, f=f)
            b.rapid(x=x_start + sign * max(0.0, done - min(0.3, peck)))
            b.feed(x=x_start + sign * done, f=f)
    b.feed(x=bottom, f=f)
    b.dwell(dwell)


def find_grooves(profile, *, side: str = "od") -> list[tuple[float, float, float]]:
    """``(z_low, z_high, lip radius)`` of every groove on a side of a turned profile, front first: a stretch lower
    (od) or wider (id) than the profile on both sides of it."""
    import numpy as np

    curve = profile.od if side == "od" else profile.bore
    z_front, z_back = profile.z_front, profile.z_back
    step = 0.01
    zs = np.arange(z_front - step / 2, z_back, -step)
    radius = profile.r_out(zs) if side == "od" else profile.r_in(zs)
    if side == "od":
        ahead = np.maximum.accumulate(radius)
        behind = np.maximum.accumulate(radius[::-1])[::-1]
        lip = np.minimum(ahead, behind)
        well = radius < lip - 0.01
    else:
        open_ = radius > 1e-6
        r = np.where(open_, radius, 0.0)
        ahead = np.minimum.accumulate(np.where(open_, r, np.inf))
        behind = np.minimum.accumulate(np.where(open_, r, 0.0)[::-1])[::-1]
        lip = np.maximum(ahead, behind)
        well = open_ & (r > lip + 0.01) & np.isfinite(ahead)
    out = []
    edges = np.flatnonzero(np.diff(np.concatenate([[0], well.astype(int), [0]])))
    knots = np.unique(curve[:, 1])
    for start, end in zip(edges[0::2], edges[1::2]):
        high, low = zs[start] + step / 2, zs[end - 1] - step / 2
        # Snap the ends to the profile's own corners.
        high = float(knots[np.argmin(np.abs(knots - high))]) if np.min(np.abs(knots - high)) <= step else float(high)
        low = float(knots[np.argmin(np.abs(knots - low))]) if np.min(np.abs(knots - low)) <= step else float(low)
        out.append((low, high, float(lip[start])))
    return out


def _choose(ctx, lt, grooves, params):
    import numpy as np

    wanted = []
    if ctx.spec.faces:
        for ref in ctx.spec.faces:
            info = ctx.face(ref)
            if info.bounds is None:
                continue
            corners = np.array([[x, y, z] for x in (info.bounds[0][0], info.bounds[1][0])
                                for y in (info.bounds[0][1], info.bounds[1][1])
                                for z in (info.bounds[0][2], info.bounds[1][2])])
            zs = ctx.wcs.to_wcs(corners)[:, 2]
            low, high = float(zs.min()), float(zs.max())
            hits = [g for g in grooves if g[0] - 1e-3 <= high and low <= g[1] + 1e-3]
            if not hits:
                raise CamJobError(f"{ctx.spec.where}.faces: {ref} is not in a groove (Z{low:.4g}..{high:.4g}); the "
                                  f"grooves are {_listed(grooves)}")
            wanted += [g for g in hits if g not in wanted]
    for z in params["z_mm"]:
        hits = [g for g in grooves if g[0] - 1e-3 <= z <= g[1] + 1e-3]
        if not hits:
            raise CamJobError(f"{ctx.spec.where}.z_mm: there is no groove at Z{z:g}; the grooves are "
                              f"{_listed(grooves)}")
        wanted += [g for g in hits if g not in wanted]
    if not ctx.spec.faces and not params["z_mm"]:
        wanted = list(grooves)
    return sorted(wanted, key=lambda g: -g[1])


def _listed(grooves) -> str:
    return ", ".join(f"Z{a:.4g}..{b:.4g}" for a, b, _ in grooves) or "none"
