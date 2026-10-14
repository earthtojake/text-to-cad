"""``wire_edm`` (lite): a two-axis wire cut of a sheet or plate's profiles, with skims, a hold and a constant taper.

What it cuts: the same profiles as ``cut`` (a DXF's, or a STEP plate's outline: prismatic along the setup's Z),
``profiles`` ``all`` (default), ``holes`` (a die: keep the plate, cut the openings) or ``outside`` (a punch).

How it plans each profile (holes first, then nearest-neighbour):

* **Offsets.** The finish offset is the wire's radius plus the spark gap (``spark_gap_mm``, 0.03); the rough cut runs
  further out by the stock the skims take (``skims`` 0-3, default 1; ``skim_stock_mm`` one number per skim, default
  0.04 / 0.06+0.02 / 0.08+0.03+0.01), each skim closer, the last at the finish offset. All on the waste side.
* **Start hole.** A hole starts from ``start_point`` ([x, y], WCS) when it lies inside it, else from the point of the
  opening farthest from its walls; an outside profile from ``start_point`` when it lies outside the part, else from a
  point ``lead_in_mm`` (3) off the profile, in the waste. The approach is a straight cut to an entry point on a
  straight run away from corners (or the nearest point of the profile when the straight way would cross the part).
* **Passes.** Rough from the entry round the profile, skims back and forth over the same stretch (alternating
  direction, each a short step across the kerf from the last), the feed rising per skim (feeds.wire_speeds).
* **Hold.** With ``hold_mm`` (default 2 with skims, else 0) the last ``hold_mm`` before the entry is left uncut by
  every pass, so the slug (or the part) stays put; a stop asks the operator to secure it, then the hold is cut in
  one pass at the finish offset and the wire is cut.
* **Taper** (``taper_deg``, constant): the profile is exact at the top of the work and the wire leans into the part
  by the thickness x tan(taper) at the bottom (a die's relief, a punch's draft); negative leans the other way.

**The IR's U and V.** A tapered wire EDM toolpath stores the wire's lean in each move's ``a`` and ``b`` columns: where
the wire passes the top of the work relative to the bottom (mm, ``top - bottom``); its ``rotary`` stays empty so mill
posts never write them. The ``beam`` events carry each pass as a whole (``process`` ``wire_edm``, ``taper_deg``
signed for the direction of travel: positive leans the wire's top to the left of travel, the G51 side, so a forward
pass carries the op's taper and a reversed skim its negative; ``thickness_mm``, ``offset_mm``, ``offset_side``
``left``/``right`` of travel, ``pass``): an on at each start hole and at each skim and hold, an off when the wire
is cut. The ``wire_edm`` post writes G51/G52 A from them, or U V words. Z stays at the top of the work (the
program plane). A ``comment`` names each start hole and each skim; a ``stop`` precedes each hold cut.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, choice, number_list, read_number
from cadgen._internal.cam.operations.base import Operation

__all__ = ["WireEdmOp"]

_SKIM_STOCK = {0: (), 1: (0.04,), 2: (0.06, 0.02), 3: (0.08, 0.03, 0.01)}


class WireEdmOp(Operation):
    name = "wire_edm"
    plain = "Wire cut"
    family = "Cutting"
    machines = ("wire_edm",)
    status = "lite"
    limits = (
        "Two-axis contours with one constant taper, carried as U/V offsets: no variable taper and no different top "
        "and bottom profiles.",
        "In a taper cut each segment leans by its own normal; how a sharp corner is tapered is left to the "
        "controller.",
        "The hold is cut once at the finish offset after a stop to secure the slug; it is not skimmed.",
        "Start holes are placed, not made: drill or EDM-drill them before the cut.",
        "Speeds are a generic removal rate per material for a 0.25 mm brass wire; the machine's own technology "
        "tables set the real ones.",
    )
    keys = ("start_point", "profiles", "spark_gap_mm", "skims", "skim_stock_mm", "hold_mm", "taper_deg", "lead_in_mm")
    common_keys = ("feed",)
    tool_types = ("wire",)
    feeds_kind = "finish"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        where, extra = spec.where, spec.extra
        if not isinstance(ctx.setup.orientation, str) or ctx.setup.orientation not in ("+Z", "-Z"):
            raise CamJobError(f"{where}: a wire runs along the setup's Z; give setup '{ctx.setup.id}' the orientation "
                              "+Z (or -Z)")
        skims = extra.get("skims", 1)
        if isinstance(skims, bool) or skims not in (0, 1, 2, 3):
            raise CamJobError(f"{where}.skims is the number of skim passes after the rough cut, 0 to 3, not {skims!r}")
        if "skim_stock_mm" in extra:
            stock = number_list(extra["skim_stock_mm"], f"{where}.skim_stock_mm", length=max(1, skims), positive=True)
            if skims == 0:
                raise CamJobError(f"{where}.skim_stock_mm needs skims; give skims, or remove skim_stock_mm")
        else:
            stock = _SKIM_STOCK[skims]
        start = None
        if "start_point" in extra:
            start = number_list(extra["start_point"], f"{where}.start_point", length=2)
        return {
            "profiles": choice(extra.get("profiles", "all"), ("all", "holes", "outside"), f"{where}.profiles"),
            "gap": read_number(extra, "spark_gap_mm", where, default=0.03, minimum=0.0, maximum=0.5),
            "skims": skims, "skim_stock": tuple(stock),
            "hold_mm": read_number(extra, "hold_mm", where, default=2.0 if skims else 0.0, minimum=0.0),
            "taper_deg": read_number(extra, "taper_deg", where, default=0.0, minimum=-30.0, maximum=30.0),
            "lead_in_mm": read_number(extra, "lead_in_mm", where, default=3.0),
            "start_point": start,
        }

    def plan(self, ctx, params):
        return _plan(ctx, params)

    def summary(self, ctx, params):
        cut = ctx.meta.get("cut", {})
        count = cut.get("profiles", 0)
        skims = params["skims"]
        taper = f", taper {params['taper_deg']:g}°" if params["taper_deg"] else ""
        name = f" ({ctx.spec.name})" if ctx.spec.name else ""
        return (f"{self.plain}{name} {count} profile{'s' if count != 1 else ''} with {ctx.tool.id} {ctx.tool.plain}, "
                f"rough + {skims} skim{'s' if skims != 1 else ''}{taper}")


def _match(rings, ring):
    """The ring among ``rings`` of the same profile and kind that overlaps ``ring`` most (its offset sibling)."""
    best, area = None, 0.0
    for other in rings:
        if other.part != ring.part or other.kind != ring.kind:
            continue
        a = other.region.intersection(ring.region).area
        if a > area:
            best, area = other, a
    return best


def _normals(coords):
    """(N - 1, 2) unit normals pointing from each segment to the part (rings are oriented part-right)."""
    import numpy as np

    d = np.diff(coords, axis=0)
    length = np.linalg.norm(d, axis=1)
    length[length == 0] = 1.0
    d = d / length[:, None]
    return np.column_stack([d[:, 1], -d[:, 0]])


def _span(coords, s0: float, s1: float):
    """The ring's points from arc length ``s0`` to ``s1`` (``s0 < s1`` within one lap from the ring's start), with the
    index of the segment each step runs along."""
    import numpy as np

    from cadgen._internal.cam.cutting import point_at

    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(coords, axis=0), axis=1))])
    inner = [k for k in range(1, len(coords) - 1) if s0 + 1e-9 < cum[k] < s1 - 1e-9]
    points = [point_at(coords, s0)] + [coords[k] for k in inner] + [coords[-1] if s1 >= cum[-1] - 1e-9 else
                                                                     point_at(coords, s1)]
    seg = []
    for a, b in zip([s0] + [cum[k] for k in inner], [cum[k] for k in inner] + [s1]):
        mid = (a + b) / 2.0
        seg.append(int(min(len(coords) - 2, max(0, np.searchsorted(cum, mid) - 1))))
    return np.asarray(points), seg


def _plan(ctx, params):
    import numpy as np
    import shapely
    from shapely.ops import polylabel

    from cadgen._internal.cam import cutting, stock_sheet
    from cadgen._internal.cam.feeds import Feeds, wire_speeds
    from cadgen._internal.cam.ir import FEED, RAPID

    tool = ctx.tool
    heights = ctx.heights
    tol = ctx.tolerance_mm
    where = ctx.spec.where
    top = heights.stock_top
    thickness = top - heights.stock_bottom
    profiles = cutting.sheet_profiles(ctx, where)
    if not profiles:
        raise CamJobError(f"{where}: the part has no closed profile to cut")
    passes = 1 + params["skims"]
    speeds = wire_speeds(ctx.material, thickness, passes)
    if ctx.spec.feed is not None:
        from cadgen._internal.cam.feeds import WIRE_SKIM_FACTORS

        speeds = [float(ctx.spec.feed)] + [float(ctx.spec.feed) * WIRE_SKIM_FACTORS[k] for k in range(passes - 1)]
    elif speeds is None:
        raise CamJobError(f"{where}: the wire table has no removal rate for {ctx.material.name}; give the cut a feed "
                          "(mm/min of the rough cut)")
    clamped = []
    if ctx.machine.max_feed_mm_min is not None and max(speeds) > ctx.machine.max_feed_mm_min:
        clamped.append(f"wire feeds clamped to the machine's {ctx.machine.max_feed_mm_min:.0f} mm/min")
        speeds = [min(v, ctx.machine.max_feed_mm_min) for v in speeds]
    ctx.chosen_feeds.append(Feeds(rpm=None, feed_mm_min=speeds[0], plunge_mm_min=speeds[0], ramp_mm_min=speeds[0],
                                  chipload_mm=None, surface_m_min=None, clamped=tuple(clamped),
                                  source="job" if ctx.spec.feed is not None else "table",
                                  note="a starting point: the machine's technology tables set the real feeds"))
    finish = tool.radius + params["gap"]
    stock = params["skim_stock"]
    offsets = [finish + sum(stock[k:]) for k in range(passes)]
    notes: list[str] = []
    ring_sets = []
    for k, offset in enumerate(offsets):
        rings, ring_notes = cutting.kerf_rings(profiles, offset, tolerance=tol, part_right=True,
                                               which=params["profiles"])
        if k == 0:
            notes += ring_notes
        ring_sets.append(rings)
    rough = ring_sets[0]
    if not rough:
        raise CamJobError(f"{where}: nothing to cut with profiles '{params['profiles']}'")
    union = shapely.union_all(profiles)
    clear = max(1.0, 4.0 * offsets[0])
    window = max(0.5, 4.0 * offsets[0])
    ordered = cutting.order_rings(rough, ctx.start, clear_for=lambda r: clear, window_for=lambda r: window)
    lean = thickness * math.tan(math.radians(params["taper_deg"]))
    user = shapely.Point(params["start_point"]) if params["start_point"] is not None else None
    b = ctx.builder()
    uv: list[tuple[float, float]] = []

    def move(kind, x=None, y=None, z=None, f=0.0, w=(0.0, 0.0)):
        before = b.count
        if kind == RAPID:
            b.rapid(x=x, y=y, z=z)
        else:
            b.feed(x=x, y=y, z=z, f=f)
        uv.extend([w] * (b.count - before))

    def walk(coords, s0, s1, f, *, reverse=False):
        points, segs = _span(coords, s0, s1)
        normals = _normals(coords)
        if reverse:
            points, segs = points[::-1], segs[::-1]
        for point, seg in zip(points[1:], segs):
            n = normals[seg]
            move(FEED, float(point[0]), float(point[1]), f=f, w=(float(-lean * n[0]), float(-lean * n[1])))

    def wire_on(label, offset: float, *, reverse: bool) -> None:
        # Signed for the way the wire travels, as posts read it: positive leans the wire's top to the left of
        # travel (G51). Rings run part-right, so a forward pass leans the op's way and a reversed skim the other.
        b.event("beam", on=True, process="wire_edm", power=1.0, pierce_s=0.0,
                taper_deg=-params["taper_deg"] if reverse else params["taper_deg"], thickness_mm=round(thickness, 4),
                offset_mm=round(offset, 4), offset_side="right" if reverse else "left", **{"pass": label})

    starts = []
    holds = 0
    for ring in ordered:
        coords = ring.coords
        if ring.kind == "hole":
            hole_region = shapely.Polygon(ring.design)
            if user is not None and hole_region.contains(user):
                start = np.array([user.x, user.y])
            else:
                label = polylabel(ring.region, max(tol, 0.01))
                start = np.array([label.x, label.y])
            entry_s, _ = cutting.pierce_at(coords, ring.zones, start, clear=clear)
        else:
            if user is not None and not shapely.Polygon(ring.design).buffer(offsets[0]).contains(user):
                start = np.array([user.x, user.y])
                entry_s, _ = cutting.pierce_at(coords, ring.zones, start, clear=clear)
            else:
                entry_s = ring.start_s
                p = cutting.point_at(coords, entry_s)
                rotated = cutting.rotate_ring(coords, entry_s)
                d = rotated[1] - rotated[0]
                d = d / (np.linalg.norm(d) or 1.0)
                start = p + np.array([-d[1], d[0]]) * params["lead_in_mm"]
        entry = cutting.point_at(coords, entry_s)
        approach = shapely.LineString([start, entry])
        if shapely.distance(approach, union) < offsets[0] - tol - 1e-6:
            entry_s = float(shapely.LineString(coords).project(shapely.Point(start)))
            entry = cutting.point_at(coords, entry_s)
        coords = cutting.rotate_ring(coords, entry_s)
        length = float(np.linalg.norm(np.diff(coords, axis=0), axis=1).sum())
        hold = params["hold_mm"] if params["hold_mm"] < length / 2.0 else 0.0
        if params["hold_mm"] and not hold:
            notes.append(f"a profile {length:.1f} mm round is too short to hold {params['hold_mm']:g} mm; it is cut "
                         "without a hold")
        cut_to = length - hold
        hold_point = cutting.point_at(coords, cut_to)
        starts.append([round(float(start[0]), 4), round(float(start[1]), 4)])
        # To the start hole, thread, approach.
        if b.pos[2] < heights.clearance - 1e-9:
            move(RAPID, z=heights.clearance)
        move(RAPID, x=float(start[0]), y=float(start[1]))
        move(RAPID, z=top)
        b.event("comment", text=f"Thread the wire at the start hole X{start[0]:.3f} Y{start[1]:.3f}")
        wire_on(0, offsets[0], reverse=False)
        move(FEED, float(entry[0]), float(entry[1]), f=speeds[0])
        # Rough, then the skims back and forth over the same stretch.
        walk(coords, 0.0, cut_to if hold else length, speeds[0])
        at_far = bool(hold)
        coords_last, a_last, length_last = coords, cut_to, length
        for k in range(1, passes):
            sibling = _match(ring_sets[k], ring)
            if sibling is None:
                notes.append(f"skim {k} found no profile at its offset (the hole closed up); it is skipped")
                continue
            line = shapely.LineString(sibling.coords)
            e_k = float(line.project(shapely.Point(entry)))
            ring_k = cutting.rotate_ring(sibling.coords, e_k)
            length_k = float(np.linalg.norm(np.diff(ring_k, axis=0), axis=1).sum())
            a_k = float(shapely.LineString(ring_k).project(shapely.Point(hold_point))) if hold else length_k
            if hold and a_k < length_k / 2.0:
                a_k = length_k - hold
            reverse = (k % 2 == 1) if hold else False
            b.event("comment", text=f"Skim {k} of {passes - 1}: offset {offsets[k]:.4f} mm, {speeds[k]:g} mm/min")
            wire_on(k, offsets[k], reverse=reverse)
            begin = cutting.point_at(ring_k, a_k if reverse else 0.0)
            move(FEED, float(begin[0]), float(begin[1]), f=speeds[k])
            walk(ring_k, 0.0, a_k, speeds[k], reverse=reverse)
            at_far = not reverse if hold else False
            coords_last, a_last, length_last = ring_k, a_k, length_k
        if hold:
            holds += 1
            b.event("stop", optional=False, message="Secure the slug (or the part): the next cut frees it")
            if passes > 1:
                # The hold is cut at the finish offset, from wherever the last skim ended.
                ring_f = coords_last
                wire_on("hold", offsets[-1], reverse=not at_far)
                walk(ring_f, a_last, length_last, speeds[0], reverse=not at_far)
            else:
                walk(coords, cut_to, length, speeds[0])
        b.event("beam", on=False, process="wire_edm")
    if any(r.kind == "outside" for r in rough) and passes > 1 and not params["hold_mm"]:
        notes.append("an outside profile is skimmed with no hold: the part drops when the rough cut closes, so its "
                     "skims cut air. Give hold_mm")
    move(RAPID, z=heights.clearance)
    path = b.build()
    assert len(uv) == len(path.moves), (len(uv), len(path.moves))
    if params["taper_deg"]:
        path.moves["a"] = [u for u, _ in uv]
        path.moves["b"] = [v for _, v in uv]
    removed = stock_sheet.swept([run[:, :2] for run in stock_sheet.cutting_runs(path, tolerance=tol)], 2 * finish)
    # What the cut frees: whole parts, or (cutting only the outsides) their outlines, or (a die) the plate's openings.
    if params["profiles"] == "outside":
        design = [shapely.Polygon(p.exterior) for p in profiles]
    elif params["profiles"] == "holes":
        openings = shapely.union_all([shapely.Polygon(ring) for p in profiles for ring in p.interiors])
        design = [shapely.difference(ctx.stock_outline, openings)]
    else:
        design = profiles
    report = stock_sheet.analyse(ctx.stock_outline, removed, design, tolerance=tol)
    ctx.meta.update({
        "kerf_mm": 2 * finish, "passes": passes, "stock_to_leave": 0.0, "sheet_cuts": params["profiles"],
        "unreachable": cutting.unreachable(profiles, finish, tolerance=tol, z=top - thickness / 2.0),
        "cut": {"process": "wire_edm", "wire_mm": tool.diameter_mm, "spark_gap_mm": params["gap"],
                "offsets_mm": [round(o, 4) for o in offsets], "feeds_mm_min": [round(v, 2) for v in speeds],
                "thickness_mm": round(thickness, 4), "profiles": len(rough), "start_holes": starts,
                "hold_mm": params["hold_mm"], "holds": holds, "taper_deg": params["taper_deg"],
                "uv_mm": round(abs(lean), 4), "parts": report["parts"], "parts_free": len(report["free"]),
                "parts_not_free": len(report["not_free"]), "slugs_drop": report["slugs"]},
    })
    if report["not_free"]:
        notes.append(f"{len(report['not_free'])} part(s) are not cut free; check the profiles close")
    if notes:
        ctx.meta["note"] = "; ".join(notes)
    return path
