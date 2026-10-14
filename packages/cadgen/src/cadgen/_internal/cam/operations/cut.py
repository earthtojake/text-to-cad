"""``cut``: cut parts out of a sheet on a laser, a plasma, a waterjet or a router.

What it cuts: every profile of the document, in the setup's WCS (look along Z: orientation ``+Z``, or ``-Z``
flipped). A DXF's closed profiles, or a STEP plate's outline: the plate's section, which must be the same at its top,
middle and bottom (a pocket, a step or a chamfer is refused in one sentence: mill it).

How it plans:

* **Kerf compensation.** Each outside profile is offset outward and each hole inward (the waste side) by half the
  cut: a beam's ``kerf_mm``, a router bit's radius. Corners the cut cannot reach (a hole's inside corners) are
  recorded for the ``corner_radius`` check; a hole narrower than the cut is not cut, and the op says so.
* **Order.** Inside first: every ring lying inside another (holes, and parts nested inside holes) is cut before it,
  then nearest-neighbour from where the head is.
* **Pierce points** sit on a straight run at least ``max(1 mm, 2 kerfs, the lead)`` from any corner, nearest the
  head; on a ring with no straight run, mid-way between corners; on a ring that is all curve, nearest the head.
* **Beam processes** (laser, plasma, waterjet): travel at the clearance height, rise or drop to the pierce height,
  beam on with the process's pierce dwell (``beam`` event, ``pierce_s``), down to the cut height, a lead-in (``arc``
  or ``line`` of ``lead_in_mm``) on the waste side, the ring, a lead-out (``lead_out_mm``), beam off. Leads shrink to
  a half and a quarter to stay clear of the parts, then fall back to a line, then to piercing on the profile.
  ``corner_slowdown`` (laser, plasma and waterjet) scales the feed by cos²(turn/2) (at least 0.3) within
  ``max(1 mm, 2 kerfs)`` of each sharp corner. ``tabs`` ``{"count", "width_mm"}`` leave microjoints on outside
  profiles: the beam goes off over each (``width + kerf`` of path) and re-pierces after it. A plasma's holes smaller
  than 1.5x the thickness are cut at 0.6x speed and flagged (``small_holes``: ``slow`` or ``warn``).
* **Router**: a flat end mill at the full width of its slot (``feeds`` slot), step-downs from the sheet top to
  ``breakthrough_mm`` below its bottom, each depth ramped into along the profile itself (``ramp_angle_deg``,
  forward and back over its first stretch, never across it; no leads), tabs on outside profiles by default
  (``tabs`` ``{"count", "width_mm", "height_mm"}``; count 0 for none) lifting the last depths over each tab.

The speed comes from ``feeds.cut_speed`` (process, material, sheet thickness, the machine's ``power_w``/``amps``/
``abrasive``, the op's waterjet ``quality``); a ``feed`` overrides it. The op's meta ``cut`` carries the numbers
(kerf, speed, pierces, leads fitted, tabs, corners slowed, small holes) and which parts fall free, which are held
by microjoints and which slugs drop (stock_sheet.analyse of its own path); ``note`` says what needs a look.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, check_keys, choice, read_number
from cadgen._internal.cam.operations.base import Operation

__all__ = ["CutOp"]

BEAMS = ("laser", "plasma", "waterjet")
_COMMON = ("direction", "tabs")
_BEAM_KEYS = ("lead_type", "lead_in_mm", "lead_out_mm", "pierce_s", "pierce_height_mm", "cut_height_mm",
              "corner_slowdown")
_KEYS_BY_KIND = {
    "laser": _COMMON + _BEAM_KEYS + ("power",),
    "plasma": _COMMON + _BEAM_KEYS + ("small_holes",),
    "waterjet": _COMMON + _BEAM_KEYS + ("quality",),
    "router": _COMMON + ("ramp_angle_deg", "breakthrough_mm"),
}
#: Per process: lead in and out (mm), cut and pierce heights over the sheet (mm).
_DEFAULTS = {
    "laser": {"lead_in_mm": 1.0, "lead_out_mm": 0.5, "cut_height_mm": 1.0, "pierce_height_mm": 2.0},
    "plasma": {"lead_in_mm": 4.0, "lead_out_mm": 2.0, "cut_height_mm": 1.5, "pierce_height_mm": 3.8},
    "waterjet": {"lead_in_mm": 2.0, "lead_out_mm": 1.0, "cut_height_mm": 2.0, "pierce_height_mm": 2.0},
}
SMALL_HOLE_RATIO = 1.5
SMALL_HOLE_FACTOR = 0.6


class CutOp(Operation):
    name = "cut"
    plain = "Cut out"
    family = "Cutting"
    machines = ("laser", "plasma", "waterjet", "router")
    status = "full"
    keys = tuple(sorted({key for keys in _KEYS_BY_KIND.values() for key in keys}))
    common_keys = ("feed", "speed", "stepdown_mm")
    tool_types = ("beam", "flat")
    feeds_kind = "slot"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        kind = ctx.job.machine.kind
        where = spec.where
        extra = spec.extra
        check_keys(extra, _KEYS_BY_KIND[kind], where, hint=f"a cut on a {kind}")
        tool = ctx.job.tool(spec.tool)
        if kind in BEAMS and tool.type != "beam":
            raise CamJobError(f"{where}: a {kind} cuts with a beam tool ({{\"type\": \"beam\", \"kerf_mm\": 0.2}}); "
                              f"{tool.id} is a {tool.type}")
        if kind == "router" and tool.type != "flat":
            raise CamJobError(f"{where}: a router cuts sheet with a flat end mill; {tool.id} is a {tool.type}")
        if kind in BEAMS and spec.stepdown_mm is not None:
            raise CamJobError(f"{where}: a {kind} cuts through in one pass; remove stepdown_mm")
        if kind in BEAMS and spec.speed is not None:
            raise CamJobError(f"{where}: a {kind} has no spindle; set the cutting speed with feed (mm/min)"
                              + (" and the beam with power (0..1)" if kind == "laser" else ""))
        if not isinstance(ctx.setup.orientation, str) or ctx.setup.orientation not in ("+Z", "-Z"):
            raise CamJobError(f"{where}: a sheet is cut from above; give setup '{ctx.setup.id}' the orientation +Z "
                              "(or -Z to cut it flipped)")
        params = {"kind": kind, "part_right": choice(extra.get("direction", "climb"), ("climb", "conventional"),
                                                     f"{where}.direction") == "climb"}
        params["tabs"] = _tabs(extra.get("tabs"), kind, f"{where}.tabs")
        if kind in BEAMS:
            defaults = _DEFAULTS[kind]
            params.update(
                lead_type=choice(extra.get("lead_type", "arc"), ("arc", "line", "none"), f"{where}.lead_type"),
                lead_in_mm=read_number(extra, "lead_in_mm", where, default=defaults["lead_in_mm"], minimum=0.0),
                lead_out_mm=read_number(extra, "lead_out_mm", where, default=defaults["lead_out_mm"], minimum=0.0),
                pierce_s=read_number(extra, "pierce_s", where, default=None, minimum=0.0),
                pierce_height_mm=read_number(extra, "pierce_height_mm", where, default=defaults["pierce_height_mm"],
                                             minimum=0.0),
                cut_height_mm=read_number(extra, "cut_height_mm", where, default=defaults["cut_height_mm"],
                                          minimum=0.0),
                power=read_number(extra, "power", where, default=1.0, maximum=1.0),
                small_holes=choice(extra.get("small_holes", "slow"), ("slow", "warn"), f"{where}.small_holes"),
            )
            corner = extra.get("corner_slowdown", True)
            if not isinstance(corner, bool):
                raise CamJobError(f"{where}.corner_slowdown must be true or false")
            params["corner_slowdown"] = corner
            quality = extra.get("quality", 3)
            if isinstance(quality, bool) or quality not in (1, 2, 3, 4, 5):
                raise CamJobError(f"{where}.quality is a waterjet's edge quality, a whole number from 1 (separation, "
                                  f"fastest) to 5 (finest), not {quality!r}")
            params["quality"] = int(quality)
        else:
            params.update(
                ramp_angle_deg=read_number(extra, "ramp_angle_deg", where, default=3.0, maximum=45.0),
                breakthrough_mm=read_number(extra, "breakthrough_mm", where, default=0.3, minimum=0.0, maximum=5.0),
            )
        return params

    def plan(self, ctx, params):
        from cadgen._internal.cam import cutting

        profiles = cutting.sheet_profiles(ctx, ctx.spec.where)
        if not profiles:
            raise CamJobError(f"{ctx.spec.where}: the part has no closed profile to cut")
        if params["kind"] == "router":
            return _plan_router(ctx, params, profiles)
        return _plan_beam(ctx, params, profiles)

    def summary(self, ctx, params):
        cut = ctx.meta.get("cut", {})
        count = cut.get("profiles")
        what = f" {count} profile{'s' if count != 1 else ''}" if count else ""
        name = f" ({ctx.spec.name})" if ctx.spec.name else ""
        speed = f" at {cut['speed_mm_min']:g} mm/min" if cut.get("speed_mm_min") and params["kind"] in BEAMS else ""
        return f"{self.plain}{name}{what} with {ctx.tool.id} {ctx.tool.plain}{speed}"


def _tabs(raw, kind: str, where: str) -> dict:
    """``{"count", "width_mm", "height_mm"}``; a router gets tabs by default (count from the outline), beams none."""
    if raw is None:
        return {"count": None if kind == "router" else 0, "width_mm": None, "height_mm": None}
    if not isinstance(raw, dict):
        raise CamJobError(f"{where} must be {{\"count\": 4, \"width_mm\": 0.5}}")
    allowed = ("count", "width_mm", "height_mm") if kind == "router" else ("count", "width_mm")
    check_keys(raw, allowed, where)
    count = raw.get("count", 4)
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 64:
        raise CamJobError(f"{where}.count must be a whole number from 0 to 64")
    return {"count": count, "width_mm": read_number(raw, "width_mm", where, default=None),
            "height_mm": read_number(raw, "height_mm", where, default=None)}


def _feeds(ctx, params, thickness: float):
    """The cutting speed (a Feeds row for the results) and its notes, for a beam process."""
    from cadgen._internal.cam.feeds import Feeds, cut_speed

    machine = ctx.machine
    choice_ = cut_speed(ctx.material, machine, thickness, quality=params["quality"])
    notes = list(choice_.notes)
    clamped = []
    if ctx.spec.feed is not None:
        speed, source = float(ctx.spec.feed), "job"
    elif choice_.speed_mm_min is None:
        raise CamJobError(f"{ctx.spec.where}: {choice_.why}")
    else:
        speed, source = choice_.speed_mm_min, "table"
    if machine.max_feed_mm_min is not None and speed > machine.max_feed_mm_min:
        clamped.append(f"cutting speed {speed:.0f} mm/min clamped to the machine's {machine.max_feed_mm_min:.0f} "
                       "mm/min")
        speed = float(machine.max_feed_mm_min)
    feeds = Feeds(rpm=None, feed_mm_min=speed, plunge_mm_min=speed, ramp_mm_min=speed, chipload_mm=None,
                  surface_m_min=None, clamped=tuple(clamped), source=source,
                  note=f"a starting point from {choice_.reference or 'the job'}: test-cut a coupon first")
    ctx.chosen_feeds.append(feeds)
    return feeds, notes, choice_


def _design_union(profiles):
    import shapely

    return shapely.union_all(profiles)


def _hole_size(ring) -> float:
    """A hole's size as the diameter of a circle of its area."""
    import shapely

    return 2.0 * math.sqrt(shapely.Polygon(ring.design).area / math.pi)


def _gaps(length: float, count: int, span: float, zones, slow: float) -> list[tuple[float, float]]:
    """Microjoint gaps along a ring started at its pierce point: evenly spaced, nudged off corners."""
    from cadgen._internal.cam.cutting import near_zone

    if count <= 0 or length <= count * span * 1.5 + 2.0:
        return []
    pitch = length / count
    gaps = []
    for k in range(count):
        centre = (k + 0.5) * pitch
        for shift in (0.0, 0.1, -0.1, 0.2, -0.2, 0.3, -0.3):
            c = centre + shift * pitch
            if not any(near_zone(c + d, zones, length, slow) for d in (-span / 2, 0.0, span / 2)):
                centre = c
                break
        gaps.append((max(0.5, centre - span / 2), min(length - 0.5, centre + span / 2)))
    return gaps


def _plan_beam(ctx, params, profiles):
    import shapely

    from cadgen._internal.cam import cutting, stock_sheet
    from cadgen._internal.cam.feeds import laser_source, pierce_seconds

    kind = params["kind"]
    tool = ctx.tool
    heights = ctx.heights
    tol = ctx.tolerance_mm
    kerf = tool.kerf_mm
    half = kerf / 2.0
    thickness = heights.stock_top - heights.stock_bottom
    feeds, notes, choice_ = _feeds(ctx, params, thickness)
    speed = feeds.feed_mm_min
    source = laser_source(ctx.material, ctx.machine) if kind == "laser" else ""
    if params["pierce_s"] is not None:
        pierce = params["pierce_s"]
    else:
        reference = choice_.speed_mm_min if kind == "waterjet" else None
        if kind == "waterjet" and reference:
            reference /= {1: 2.0, 2: 1.4, 3: 1.0, 4: 0.75, 5: 0.6}[params["quality"]]
        pierce = pierce_seconds(ctx.machine, thickness, reference_speed_mm_min=reference, source=source)
    rings, ring_notes = cutting.kerf_rings(profiles, half, tolerance=tol, part_right=params["part_right"])
    notes += ring_notes
    union = _design_union(profiles)
    lead_len = params["lead_in_mm"] if params["lead_type"] != "none" else 0.0
    window = max(1.0, 2.0 * kerf)
    clear = max(1.0, 2.0 * kerf, lead_len)
    small = []
    if kind == "plasma":
        for ring in rings:
            if ring.kind == "hole":
                size = _hole_size(ring)
                if size < SMALL_HOLE_RATIO * thickness:
                    small.append(size)
                    if params["small_holes"] == "slow":
                        ring.factor = SMALL_HOLE_FACTOR
        if small:
            action = (f"cut at {SMALL_HOLE_FACTOR:g}x speed" if params["small_holes"] == "slow"
                      else "cut at full speed")
            notes.append(f"{len(small)} hole{'s' if len(small) > 1 else ''} under {SMALL_HOLE_RATIO:g}x the "
                         f"{thickness:g} mm thickness (smallest Ø{min(small):.2g} mm), {action}: plasma holes this "
                         "small come out tapered and out of round; drill or ream them if they matter")
    ordered = cutting.order_rings(rings, ctx.start, clear_for=lambda ring: clear, window_for=lambda ring: window)
    top = heights.stock_top
    cut_z = top + params["cut_height_mm"]
    pierce_z = top + params["pierce_height_mm"]
    b = ctx.builder()
    count = {"pierces": 0, "leads_in": 0, "leads_out": 0, "lead_fallbacks": 0, "leads_shortened": 0, "corners": 0,
             "tabs": 0}
    breaks = []
    tabs = params["tabs"]
    tab_width = tabs["width_mm"] if tabs["width_mm"] is not None else max(0.3, 2.0 * kerf)
    slow_mm = max(1.0, 2.0 * kerf)
    zones_cache = {}

    def beam_on():
        b.event("beam", on=True, power=params["power"], pierce_s=pierce, process=kind)
        count["pierces"] += 1

    def travel_to(x, y):
        if b.pos[2] < heights.clearance - 1e-9:
            b.rapid(z=heights.clearance)
        b.rapid(x=x, y=y)
        b.rapid(z=pierce_z)

    for ring in ordered:
        coords = cutting.rotate_ring(ring.coords, ring.start_s)
        zones = cutting.corner_zones(coords, window=window)
        zones_cache[id(ring)] = zones
        start = coords[0]
        direction_in = coords[1] - coords[0]
        direction_out = coords[-1] - coords[-2]
        lead_kwargs = {"kind": params["lead_type"] if params["lead_type"] != "none" else "line",
                       "part_right": params["part_right"], "keep_off": union, "clearance": half - tol}
        lead = None
        if params["lead_type"] != "none" and params["lead_in_mm"] > 0:
            lead = cutting.lead_in(start, direction_in, length=params["lead_in_mm"], **lead_kwargs)
            if lead is None:
                count["lead_fallbacks"] += 1
            elif lead["size"] < params["lead_in_mm"] - 1e-9 or lead["kind"] != params["lead_type"]:
                count["leads_shortened"] += 1
        exit_ = None
        if params["lead_type"] != "none" and params["lead_out_mm"] > 0:
            exit_ = cutting.lead_out(start, direction_out, length=params["lead_out_mm"], **lead_kwargs)
        pierce_xy = lead["start"] if lead is not None else start
        travel_to(float(pierce_xy[0]), float(pierce_xy[1]))
        beam_on()
        b.plunge(z=cut_z, f=speed)
        f_ring = speed * ring.factor
        if lead is not None:
            count["leads_in"] += 1
            if lead["kind"] == "arc":
                c = lead["centre"]
                b.arc(float(start[0]), float(start[1]), cut_z, centre=(float(c[0]), float(c[1]), cut_z),
                      clockwise=lead["clockwise"], f=f_ring)
            else:
                b.feed(x=float(start[0]), y=float(start[1]), f=f_ring)
        gaps = []
        if ring.kind == "outside" and tabs["count"]:
            span = tab_width + kerf
            gaps = _gaps(ring.length, tabs["count"], span, zones, slow_mm)
            for lo, hi in gaps:
                mid = cutting.point_at(coords, (lo + hi) / 2.0)
                breaks.append([float(mid[0]), float(mid[1]), (hi - lo) / 2.0 + 0.05])
            count["tabs"] += len(gaps)
        runs = cutting.slow_segments(coords, zones if params["corner_slowdown"] else [], slow_mm=slow_mm, gaps=gaps)
        count["corners"] += len([z for z in zones if not z.get("whole")]) if params["corner_slowdown"] else 0
        for points, factor, cutting_on in runs:
            if cutting_on:
                for point in points[1:]:
                    b.feed(x=float(point[0]), y=float(point[1]), f=round(f_ring * factor, 1))
            else:
                b.event("beam", on=False)
                b.rapid(z=pierce_z)
                b.rapid(x=float(points[-1][0]), y=float(points[-1][1]))
                beam_on()
                b.plunge(z=cut_z, f=speed)
        if exit_ is not None:
            count["leads_out"] += 1
            if exit_["kind"] == "arc":
                c = exit_["centre"]
                end = exit_["start"]
                b.arc(float(end[0]), float(end[1]), cut_z, centre=(float(c[0]), float(c[1]), cut_z),
                      clockwise=exit_["clockwise"], f=f_ring)
            else:
                end = exit_["start"]
                b.feed(x=float(end[0]), y=float(end[1]), f=f_ring)
        b.event("beam", on=False)
        b.rapid(z=heights.clearance)
    path = b.build()
    if count["lead_fallbacks"]:
        many = count["lead_fallbacks"] > 1
        notes.append(f"{count['lead_fallbacks']} profile{'s' if many else ''} had no room for a lead-in on the waste "
                     f"side, so {'they are' if many else 'it is'} pierced on the profile itself: expect a pierce mark "
                     "on the part's edge there")
    # Which parts fall free, from this path's own kerf.
    sheet = ctx.stock_outline
    removed = stock_sheet.swept([run[:, :2] for run in stock_sheet.cutting_runs(path, tolerance=tol)], kerf)
    tab_shapes = [shapely.Point(x, y).buffer(r, quad_segs=8) for x, y, r in breaks]
    report = stock_sheet.analyse(sheet, removed, profiles, tolerance=tol, breaks=tab_shapes)
    if report["not_free"]:
        notes.append(f"{len(report['not_free'])} part{'s are' if len(report['not_free']) > 1 else ' is'} not cut free "
                     "of the sheet (check the profiles close and the parts are not closer than the kerf)")
    _crowded(profiles, half, notes)
    ctx.meta.update({
        "kerf_mm": kerf, "tab_breaks": breaks, "stock_to_leave": 0.0,
        "unreachable": cutting.unreachable(profiles, half, tolerance=tol, z=top - thickness / 2.0),
        "cut": {"process": kind, "kerf_mm": kerf, "thickness_mm": round(thickness, 4), "speed_mm_min": speed,
                "speed_from": choice_.reference if ctx.spec.feed is None else "the job's feed",
                "source": source or None, "pierce_s": pierce, "profiles": len(rings),
                "outsides": sum(1 for r in rings if r.kind == "outside"),
                "holes": sum(1 for r in rings if r.kind == "hole"), "pierces": count["pierces"],
                "leads_in": count["leads_in"], "leads_out": count["leads_out"], "lead_type": params["lead_type"],
                "leads_shortened": count["leads_shortened"],
                "corners_slowed": count["corners"], "tabs": count["tabs"], "small_holes": len(small),
                "parts": report["parts"], "parts_free": len(report["free"]), "parts_held": len(report["held"]),
                "parts_not_free": len(report["not_free"]), "slugs_drop": report["slugs"]},
    })
    if notes:
        ctx.meta["note"] = "; ".join(notes)
    return path


def _crowded(profiles, half: float, notes: list) -> None:
    """A note when two parts sit closer than the cut: each one's kerf takes material from the other."""
    import shapely

    if len(profiles) < 2:
        return
    grown = [shapely.Polygon(p.exterior).buffer(half * 0.999) for p in profiles]
    tree = shapely.STRtree(grown)
    close = 0
    for i, shape in enumerate(grown):
        for j in tree.query(shape, predicate="intersects"):
            j = int(j)
            if j > i and not shapely.Polygon(profiles[j].exterior).within(shapely.Polygon(profiles[i].exterior)) \
                    and not shapely.Polygon(profiles[i].exterior).within(shapely.Polygon(profiles[j].exterior)):
                close += 1
    if close:
        notes.append(f"{close} pair{'s' if close > 1 else ''} of parts sit closer than the {2 * half:g} mm cut, so "
                     "each kerf takes material from its neighbour; space them at least a kerf apart")


def _prefix(coords, length: float):
    """The first ``length`` mm of a path (at least its first point)."""
    import numpy as np

    from cadgen._internal.cam.cutting import point_at

    if length <= 0:
        return coords[:1]
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(coords, axis=0), axis=1))])
    k = int(np.searchsorted(cum, length))
    return np.vstack([coords[:k], [point_at(coords, length)]])


def _path_ramp(b, coords, z_from: float, z_to: float, *, angle_deg: float, f: float, limit: float) -> bool:
    """Ramp down along the profile itself (never across it), ending over its start at ``z_to``: round the whole
    profile in laps when it is shorter than the ramp and nothing (a tab) is in the way, else forward and back along
    its first ``limit`` mm at ``angle_deg``. False (nothing added) when there is less than 0.5 mm to ramp along."""
    import numpy as np

    depth = z_from - z_to
    if depth <= 1e-9:
        return True
    total = float(np.linalg.norm(np.diff(coords, axis=0), axis=1).sum())
    need = max(1.0, depth / math.tan(math.radians(angle_deg)))
    if limit >= total - 1e-9 and need >= total and total >= 0.5:
        # Nothing in the way and a short profile: spiral down round it, whole laps, ending over its start.
        laps = int(math.ceil(need / total - 1e-9))
        cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(coords, axis=0), axis=1))])
        b.feed(x=float(coords[0][0]), y=float(coords[0][1]), f=f)
        b.feed(z=z_from, f=f)
        for lap in range(laps):
            for k in range(1, len(coords)):
                b.feed(x=float(coords[k][0]), y=float(coords[k][1]),
                       z=z_from - depth * (lap * total + cum[k]) / (laps * total), f=f)
        return True
    run = min(limit, total, need)
    if run < 0.5:
        return False
    leg = _prefix(coords, run)
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(leg, axis=0), axis=1))])
    drop = run * math.tan(math.radians(angle_deg))
    b.feed(x=float(leg[0][0]), y=float(leg[0][1]), f=f)
    b.feed(z=z_from, f=f)
    z = z_from
    forward = True
    while z > z_to + 1e-9 or not forward:
        target = max(z_to, z - drop)
        order = range(1, len(leg)) if forward else range(len(leg) - 2, -1, -1)
        for k in order:
            share = cum[k] / run if forward else 1.0 - cum[k] / run
            b.feed(x=float(leg[k][0]), y=float(leg[k][1]), z=z + (target - z) * min(1.0, share), f=f)
        z = target
        forward = not forward
    return True


def _circle_of(coords, tolerance: float):
    """``(cx, cy, r, clockwise)`` when a closed ring is a circle within the tolerance, else None."""
    import numpy as np

    pts = np.asarray(coords, dtype=float)[:-1]
    if len(pts) < 8:
        return None
    # A least-squares circle (the vertices need not be evenly spread round it).
    design = np.column_stack([pts[:, 0], pts[:, 1], np.ones(len(pts))])
    solution, *_ = np.linalg.lstsq(design, -(pts[:, 0] ** 2 + pts[:, 1] ** 2), rcond=None)
    centre = np.array([-solution[0] / 2.0, -solution[1] / 2.0])
    radii = np.hypot(pts[:, 0] - centre[0], pts[:, 1] - centre[1])
    r = float(radii.mean())
    if r < 0.05 or float(np.abs(radii - r).max()) > max(2.0 * tolerance, 0.005):
        return None
    x, y = np.asarray(coords)[:, 0], np.asarray(coords)[:, 1]
    clockwise = float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])) < 0
    return float(centre[0]), float(centre[1]), r, clockwise


def _helix_level(b, circle, start, z_from: float, z_to: float, *, angle_deg: float, f_ramp: float,
                 f_cut: float) -> None:
    """From over ``start`` (on the circle) at or above ``z_from``: half-turn helical arcs down to ``z_to`` at the
    ramp angle, back to ``start``, then the full circle at ``z_to``."""
    cx, cy, r, clockwise = circle
    sx, sy = float(start[0]), float(start[1])
    a0 = math.atan2(sy - cy, sx - cx)
    b.feed(x=sx, y=sy, f=f_ramp)
    b.feed(z=z_from, f=f_ramp)
    pitch = max(1e-3, 2 * math.pi * r * math.tan(math.radians(angle_deg)))
    halves = max(1, int(math.ceil((z_from - z_to) / (pitch / 2.0) - 1e-9)))
    turn = -math.pi if clockwise else math.pi
    for half in range(halves):
        angle = a0 + turn * (half + 1)
        z = z_from - (z_from - z_to) * (half + 1) / halves
        b.arc(cx + r * math.cos(angle), cy + r * math.sin(angle), z, centre=(cx, cy, z), clockwise=clockwise, f=f_ramp)
    if halves % 2:
        b.arc(sx, sy, z_to, centre=(cx, cy, z_to), clockwise=clockwise, f=f_cut)
    b.arc(sx, sy, z_to, centre=(cx, cy, z_to), clockwise=clockwise, f=f_cut)


def _plan_router(ctx, params, profiles):
    import numpy as np

    from cadgen._internal.cam import cutting, linking

    tool = ctx.tool
    r = tool.radius
    heights = ctx.heights
    tol = ctx.tolerance_mm
    feeds = ctx.feeds("slot")
    top, bottom = heights.stock_top, heights.stock_bottom
    thickness = top - bottom
    floor = bottom - params["breakthrough_mm"]
    stepdown = ctx.stepdown()
    levels_count = max(1, int(math.ceil((top - floor) / stepdown - 1e-9)))
    levels = [top - (top - floor) * (k + 1) / levels_count for k in range(levels_count)]
    rings, notes = cutting.kerf_rings(profiles, r, tolerance=tol, part_right=params["part_right"])
    clear = max(1.0, r)
    ordered = cutting.order_rings(rings, ctx.start, clear_for=lambda ring: clear,
                                  window_for=lambda ring: max(1.0, tool.diameter_mm))
    tabs = params["tabs"]
    tab_height = tabs["height_mm"] if tabs["height_mm"] is not None else max(1.0, min(3.0, thickness / 3.0))
    tab_width = tabs["width_mm"] if tabs["width_mm"] is not None else max(4.0, tool.diameter_mm)
    tab_top = bottom + min(tab_height, thickness)
    b = ctx.builder()
    placed = 0
    skipped = 0
    plunges = 0
    for ring in ordered:
        coords = cutting.rotate_ring(ring.coords, ring.start_s)
        count = tabs["count"]
        if count is None:
            count = max(2, min(8, int(round(ring.length / 150.0)) + 2)) if ring.kind == "outside" else 0
        if ring.kind != "outside":
            count = 0
        linking.retract_and_move(b, float(coords[0][0]), float(coords[0][1]), heights)
        z_prev = top
        lifted = False
        circle = _circle_of(coords, tol) if not count else None
        for z in levels:
            if circle is not None:
                # A round profile: helical arcs down at the ramp angle, then the full circle at depth.
                _helix_level(b, circle, coords[0], z_prev, z, angle_deg=params["ramp_angle_deg"],
                             f_ramp=feeds.ramp_mm_min, f_cut=feeds.feed_mm_min)
                z_prev = z
                continue
            points = np.column_stack([coords, np.full(len(coords), z)])
            if count and z < tab_top - 1e-9:
                tabbed = linking.apply_tabs(points, tab_top=tab_top, count=count, width=tab_width,
                                            tool_diameter=tool.diameter_mm)
                lifted = lifted or len(tabbed) != len(points)
                points = tabbed
            limit = ring.length
            if count and z < tab_top - 1e-9:
                # Ramp only before the first tab, so the ramp's deep legs never cut through it.
                limit = ring.length / count / 2.0 - (tab_width + tool.diameter_mm) / 2.0 - 0.5
            if not _path_ramp(b, coords, z_prev, z, angle_deg=params["ramp_angle_deg"], f=feeds.ramp_mm_min,
                              limit=limit):
                b.feed(x=float(coords[0][0]), y=float(coords[0][1]), f=feeds.feed_mm_min)
                b.feed(z=z_prev, f=feeds.feed_mm_min)
                b.plunge(z=z, f=feeds.plunge_mm_min)
                plunges += 1
            b.polyline(points[1:], f=feeds.feed_mm_min)
            z_prev = z
        if count:
            if lifted:
                placed += count
            else:
                skipped += 1
        b.rapid(z=heights.clearance)
    if skipped:
        notes.append(f"tabs did not fit on {skipped} small part{'s' if skipped > 1 else ''}: "
                     f"{'they come' if skipped > 1 else 'it comes'} loose on the last pass; hold "
                     f"{'them' if skipped > 1 else 'it'} down or give a smaller tab width")
    if plunges:
        ctx.meta["plunges"] = plunges
    ctx.meta.update({
        "kerf_mm": tool.diameter_mm, "levels": len(levels), "stock_to_leave": 0.0,
        "unreachable": cutting.unreachable(profiles, r, tolerance=tol, z=top - thickness / 2.0),
        "cut": {"process": "router", "kerf_mm": tool.diameter_mm, "thickness_mm": round(thickness, 4),
                "profiles": len(rings), "outsides": sum(1 for x in rings if x.kind == "outside"),
                "holes": sum(1 for x in rings if x.kind == "hole"), "depths": len(levels),
                "stepdown_mm": round(stepdown, 4), "breakthrough_mm": params["breakthrough_mm"], "tabs": placed,
                "tab_height_mm": round(tab_top - bottom, 4), "tab_width_mm": tab_width},
    })
    if notes:
        ctx.meta["note"] = "; ".join(notes)
    return b.build()
