"""``contour`` (Profile): follow a shape's loops at the tool's radius, outside, inside or on them, level by level.

What it follows:

* ``faces``: a flat face square to the tool (facing +Z or -Z) names its outline and its holes (``loops``: ``all``,
  the default, ``outer`` or ``inner``); a wall (a plane square to XY, a cylinder or cone along Z) names the whole
  loop of the part's section it stands on, and the tool runs on the wall's air side;
* or a ``region``: ``{"polygon": [[x, y], ...], "bottom_z": z}`` in the setup's WCS.

``side``: ``outside`` (the tool's edge on the loop, outside the face or region), ``inside`` or ``on`` (the tool's
centre on the loop). A flat face's default is ``outside``, except a floor below the part's top (a pocket's or a
step's floor), which defaults to ``inside`` (finish its walls); a wall's side is its air side (``on`` is allowed).

How deep: down to ``bottom_z`` (WCS) when given; else a wall's foot, a floor's height (side inside), a face facing
-Z's height, a region's ``bottom_z``, or the part's bottom (an outline cut through); ``through_mm`` goes that much
below a through cut. ``stock_to_leave_mm`` is left on the walls, and on the floor unless the cut goes through.

How: levels from the stock top down by the step down (the last exactly at the bottom); each loop is cut through all
its levels before the next, holes before the outline that holds them, then the nearest. ``direction`` ``climb``
(default) or ``conventional``. Each level is entered by a ``ramp`` along the loop (default; ``ramp_angle_deg``,
default 3) or a ``plunge``; with ``lead_in_mm`` a tangent quarter-arc lead swings in from the air side instead (the
descent is then made at the lead's start), and ``lead_out_mm`` swings off the same way; a lead is shrunk, then left
out, where it would not stay on the air side or would swing into one of the setup's fixture boxes. A level starts
by dropping straight down only where the tool is in air (off the stock and clear of the fixtures). ``tabs``:
``{"count": 4, "width_mm": 5, "height_mm": 1.5}`` leaves that many bridges, evenly spaced, standing ``height_mm``
above the bottom of a through cut (default width 5 mm, height a third of the depth, at most 2 mm): a level under
their top rises straight onto each tab and comes down off its end by zig-zagging along the loop ahead at
``ramp_angle_deg``, never dropping straight into the material. ``finish_mm`` leaves that much on the walls for the
levels and takes it off at the full depth in ``finish_passes`` passes (default 1; equal shares); with no
``finish_mm``, ``finish_passes`` are spring passes at the final offset. A finish pass with no lead steps in sideways
from the roughed slot.

What the tool cannot reach (inside corners tighter than its radius, holes smaller than it) goes into
``meta["unreachable"]`` for the ``corner_radius`` check; a loop too small for the tool is skipped and noted. Refused,
as plan errors on the operation: every loop too small for the tool (``tool_too_large``), a bottom at or above the
stock top (``empty_operation``), and part material at a face's own height under the tool beside it (``gouge``).
"""

from __future__ import annotations

from cadgen._internal.cam.job_errors import CamJobError, PlanError, check_keys, choice, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["ContourOp"]


class ContourOp(Operation):
    name = "contour"
    plain = "Profile"
    family = "2.5D milling"
    machines = MILLS
    status = "full"
    keys = ("side", "direction", "loops", "bottom_z", "through_mm", "tabs", "lead_in_mm", "lead_out_mm",
            "finish_mm", "finish_passes", "entry", "ramp_angle_deg")
    common_keys = ("feed", "speed", "stepdown_mm", "stock_to_leave_mm")
    tool_types = ("flat", "bull", "ball")
    takes_faces = True
    takes_region = True
    feeds_kind = "slot"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        if not spec.faces and spec.region is None:
            raise CamJobError(f"{spec.where}: a contour needs the faces it follows (\"faces\": [\"#o1.f3\"]) or a "
                              "\"region\" ({\"polygon\": [[x, y], ...], \"bottom_z\": z})")
        if spec.faces and spec.region is not None:
            raise CamJobError(f"{spec.where}: give a contour faces or a region, not both")
        extra = spec.extra
        where = spec.where
        params = {
            "side": choice(extra["side"], ("outside", "inside", "on"), f"{where}.side") if "side" in extra else None,
            "climb": choice(extra.get("direction", "climb"), ("climb", "conventional"), f"{where}.direction") == "climb",
            "loops": choice(extra.get("loops", "all"), ("all", "outer", "inner"), f"{where}.loops"),
            "bottom_z": read_number(extra, "bottom_z", where, minimum=-1e6),
            "through_mm": read_number(extra, "through_mm", where, default=0.0, minimum=0.0),
            "lead_in_mm": read_number(extra, "lead_in_mm", where, default=0.0, minimum=0.0),
            "lead_out_mm": read_number(extra, "lead_out_mm", where, default=0.0, minimum=0.0),
            "finish_mm": read_number(extra, "finish_mm", where, default=0.0, minimum=0.0),
            "finish_passes": None,
            "entry": choice(extra.get("entry", "ramp"), ("ramp", "plunge"), f"{where}.entry"),
            "ramp_angle_deg": read_number(extra, "ramp_angle_deg", where, default=3.0, maximum=45.0),
            "tabs": None,
            "region": region_polygon(spec, where=where) if spec.region is not None else None,
        }
        if "finish_passes" in extra:
            count = extra["finish_passes"]
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 10:
                raise CamJobError(f"{where}.finish_passes must be a whole number from 0 to 10 (passes at the final "
                                  "depth)")
            if count == 0 and params["finish_mm"] > 0:
                raise CamJobError(f"{where}: finish_mm {params['finish_mm']:g} needs at least one finish pass to take "
                                  "it off; leave finish_passes out or give 1 or more")
            params["finish_passes"] = count
        if "tabs" in extra:
            tabs = extra["tabs"]
            if not isinstance(tabs, dict):
                raise CamJobError(f"{where}.tabs must be {{\"count\": 4, \"width_mm\": 5, \"height_mm\": 1.5}}")
            check_keys(tabs, ("count", "width_mm", "height_mm"), f"{where}.tabs")
            count = tabs.get("count")
            if isinstance(count, bool) or not isinstance(count, int) or count < 1:
                raise CamJobError(f"{where}.tabs.count must be a whole number of at least 1")
            params["tabs"] = {"count": count, "width_mm": read_number(tabs, "width_mm", f"{where}.tabs", default=5.0),
                              "height_mm": read_number(tabs, "height_mm", f"{where}.tabs")}
        return params

    # --- the loops -----------------------------------------------------------------------------------

    def _targets(self, ctx, params):
        from cadgen._internal.cam.operations._milling2d import Target, face_targets

        heights = ctx.heights
        if params["region"] is not None:
            polygon, bottom = params["region"]
            targets = [Target(polygon=polygon, side=params["side"] or "outside", kind="region",
                              bottom_z=bottom if bottom is not None else heights.part_bottom)]
        else:
            targets = face_targets(ctx, ctx.spec.faces, where=f"{ctx.spec.where}.faces")
        out, seen = [], set()
        for target in targets:
            given = params["side"]
            if target.kind == "wall":
                if given not in (None, "on", target.side):
                    raise CamJobError(f"{ctx.spec.where}.side: {target.ref} is a wall, and a contour along a wall runs "
                                      f"on its air side ({target.side} of its loop); leave \"side\" out or use on")
                side = given or target.side
                bottom = target.bottom_z
            elif target.kind == "region":
                side, bottom = target.side, target.bottom_z
            else:
                side = given or ("inside" if target.floor else "outside")
                if target.kind == "under":
                    bottom = target.z
                elif side == "inside":
                    bottom = target.z
                else:
                    bottom = heights.part_bottom
            if params["bottom_z"] is not None:
                bottom = params["bottom_z"]
            key = (side, round(target.polygon.area, 3), round(target.polygon.centroid.x, 3),
                   round(target.polygon.centroid.y, 3), round(bottom, 4))
            if key in seen:
                continue
            seen.add(key)
            target.side = side
            target.bottom_z = bottom
            out.append(target)
        return out

    def plan(self, ctx, params):
        import shapely

        from cadgen._internal.cam import geom2d
        from cadgen._internal.cam.operations._milling2d import unreachable_in

        tool = ctx.tool
        r = tool.radius
        tol = ctx.tolerance_mm
        heights = ctx.heights
        leave = ctx.spec.stock_to_leave_mm
        finish = params["finish_mm"]
        top = heights.stock_top
        stepdown = ctx.stepdown()
        rough_feeds = ctx.feeds(self.feeds_kind)
        finish_count = params["finish_passes"] if params["finish_passes"] is not None else (1 if finish > 0 else 0)
        finish_feeds = ctx.feeds("finish", stepover_mm=finish / finish_count) if finish > 0 else rough_feeds
        notes: list[str] = []
        unreachable: list[dict] = []
        passes = []
        for target in self._targets(ctx, params):
            base = target.polygon
            if params["loops"] == "outer":
                base = shapely.Polygon(base.exterior)
            # Material and air: where the tool removes material, for the corners it cannot reach.
            bottom = target.bottom_z
            if target.side == "inside":
                region = geom2d.offset(base, -leave, tolerance=tol) if leave else base
                unreachable_in(region, r, bottom, tol, unreachable)
            elif target.side == "outside" and params["loops"] != "inner":
                grown = geom2d.offset(base, leave, tolerance=tol) if leave else base
                air = base.buffer(3.0 * (r + leave + finish) + 2.0).difference(grown)
                unreachable_in(air, r, bottom, tol, unreachable)
            elif target.side == "outside":
                holes = shapely.union_all([shapely.Polygon(ring.coords) for ring in base.interiors])
                unreachable_in(geom2d.offset(holes, -leave, tolerance=tol) if leave else holes, r, bottom, tol,
                               unreachable)
            wanted = _loop_count(base, params["loops"])
            rough = _rings(base, target.side, r + leave + finish, params["loops"], tol)
            if len(rough) < wanted:
                notes.append(f"{wanted - len(rough)} loop(s) of {target.ref or 'the region'} are too small for "
                             f"{tool.id} and were not cut")
            # A flat face's outline cut outside or on it goes down to whatever material lies under the tool there
            # (a slot's floor under a blind mouth), else through; every other loop to its target's bottom.
            floors = target.kind == "flat" and target.side != "inside" and params["bottom_z"] is None
            # The finish passes at the final depth: finish_mm in equal shares, or spring passes at the final offset.
            sets = [("rough", 0, rough)]
            for j in range(1, finish_count + 1):
                sets.append(("finish", j, _rings(base, target.side, r + leave + finish * (1.0 - j / finish_count),
                                                 params["loops"], tol)))
            for kind, share, rings in sets:
                for ring, material_inside in rings:
                    floor = _floor_under(ctx, ring, base, target.z) if floors else target.bottom_z
                    through = floor is None or floor <= heights.part_bottom + 1e-6
                    if floor is None:
                        floor = heights.part_bottom
                    cut_bottom = floor - params["through_mm"] if through else floor + leave
                    if cut_bottom >= top - 1e-6:
                        raise PlanError("empty_operation", f"{ctx.spec.where}: the contour's bottom (Z "
                                        f"{cut_bottom:.3f}) is at or above the stock top in setup '{ctx.setup.id}', so "
                                        "it cuts nothing; give a lower bottom_z")
                    passes.append({"ring": ring, "material_inside": material_inside, "bottom": cut_bottom,
                                   "levels": _levels(top, cut_bottom, stepdown) if kind == "rough" else [cut_bottom],
                                   "finish": kind == "finish", "share": share,
                                   "tab_base": floor if through else None,
                                   "feeds": rough_feeds if kind == "rough" else finish_feeds})
        if not passes:
            raise PlanError("tool_too_large", f"{ctx.spec.where}: every loop is too small for {tool.id} ({tool.plain}) "
                            "to fit inside; use a smaller tool")
        b = ctx.builder()
        counts = {"ramp": 0, "plunge": 0, "air": 0, "lead": 0}
        rough_starts = []
        ordered = _order([p for p in passes if not p["finish"]], b.pos)
        for j in range(1, finish_count + 1):
            ordered += _order([p for p in passes if p["finish"] and p["share"] == j], b.pos)
        tabs_short = 0
        for p in ordered:
            short = self._cut(ctx, params, b, p, rough_starts, counts)
            tabs_short += short
        b.rapid(z=heights.clearance)
        if tabs_short:
            notes.append(f"{tabs_short} loop(s) are too short for {params['tabs']['count']} tabs and were cut "
                         "without them")
        ctx.meta.update({"loops": sum(1 for p in passes if not p["finish"]),
                         "levels": max(len(p["levels"]) for p in passes),
                         "entries": {k: v for k, v in counts.items() if v and k in ("ramp", "air", "lead")},
                         "unreachable": unreachable, "stock_to_leave": leave,
                         "bottom_z": round(min(p["bottom"] for p in passes), 4)})
        if finish > 0:
            ctx.meta["finish_mm"] = finish
        if finish_count:
            ctx.meta["finish_passes"] = finish_count
        if counts["plunge"]:
            ctx.meta["plunges"] = counts["plunge"]
        if counts.get("lead_dropped"):
            notes.append(f"{counts['lead_dropped']} lead(s) did not fit beside their loop and were left out")
        if notes:
            ctx.meta["note"] = "; ".join(notes)
        return b.build()

    def _cut(self, ctx, params, b, p, rough_starts, counts) -> int:
        """Cut one pass (a loop through its levels). Returns 1 when the loop was too short for its tabs."""
        import numpy as np
        import shapely

        from cadgen._internal.cam.operations._milling2d import (
            down_in_air, fixtures_clear, in_air as straight_down, lift_and_go, orient, ramp_along,
            rotate_to_nearest,
        )

        tool = ctx.tool
        r = tool.radius
        heights = ctx.heights
        climb = params["climb"]
        feeds = p["feeds"]
        ring = orient(p["ring"], material_inside=p["material_inside"], climb=climb)
        line = shapely.LineString(ring)
        tab_xy = []
        if p["finish"]:
            # Start and tab where the roughing pass of this loop did.
            near = [s for s in rough_starts if line.distance(shapely.Point(s["start"])) < params["finish_mm"] + 0.05]
            if near:
                ring = rotate_to_nearest(ring, near[0]["start"])
                tab_xy = [t for s in near for t in s["tabs"]]
            else:
                ring = rotate_to_nearest(ring, b.pos)
        else:
            ring = rotate_to_nearest(ring, b.pos)
        line = shapely.LineString(ring)
        total = float(line.length)
        tabs = params["tabs"]
        short = 0
        tab_top = None
        spans: list[tuple[float, float]] = []
        if tabs is not None and p["tab_base"] is not None:
            height = tabs["height_mm"]
            if height is None:
                height = min(2.0, (heights.stock_top - p["tab_base"]) / 3.0)
            tab_top = p["tab_base"] + height
            span = tabs["width_mm"] + tool.diameter_mm
            if not p["finish"]:
                if total <= tabs["count"] * span * 1.5:
                    short = 1
                    tab_top = None
                else:
                    centres = [(k + 0.5) * total / tabs["count"] for k in range(tabs["count"])]
                    tab_xy = [tuple(line.interpolate(c).coords[0]) for c in centres]
            if tab_top is not None and tab_xy:
                for xy in tab_xy:
                    c = float(line.project(shapely.Point(xy)))
                    spans.append((c - span / 2.0, c + span / 2.0))
            elif tab_top is not None:
                tab_top = None
        if not p["finish"]:
            rough_starts.append({"start": tuple(ring[0]), "tabs": tab_xy if tab_top is not None else []})
        start = ring[0]
        d0 = _direction(ring, 0)
        d1 = _direction(ring, -1)
        lowest = min(p["levels"])

        def clear_of_fixtures(geometry) -> bool:
            return fixtures_clear(ctx, geometry, lowest)

        lead_in_geom = _fit_lead(ring, p["material_inside"], start, d0, params["lead_in_mm"], climb, True, counts,
                                 clear_of_fixtures)
        lead_out_geom = _fit_lead(ring, p["material_inside"], start, d1, params["lead_out_mm"], climb, False, counts,
                                  clear_of_fixtures)
        # The ramp runs along the loop up to the first tab.
        ramp_path = ring
        if spans:
            free = min(s for s, _ in spans)
            if free > 1.0:
                from shapely.ops import substring

                ramp_path = np.asarray(substring(line, 0.0, free).coords)
            else:
                ramp_path = ring[:1]
        away = np.array([-d0[1], d0[0]]) if climb else np.array([d0[1], -d0[0]])
        z_prev = heights.stock_top
        for k, z in enumerate(p["levels"]):
            if lead_in_geom is not None:
                entry_xy = lead_in_geom[0]
            elif p["finish"]:
                entry_xy = (start[0] + away[0] * params["finish_mm"], start[1] + away[1] * params["finish_mm"])
            else:
                entry_xy = (start[0], start[1])
            if k == 0:
                lift_and_go(b, entry_xy, heights)
            else:
                b.feed(x=float(entry_xy[0]), y=float(entry_xy[1]), f=feeds.feed_mm_min)
            if straight_down(ctx, entry_xy, z):
                down_in_air(b, heights, z, f=feeds.plunge_mm_min)
                counts["air"] += 1
            elif lead_in_geom is not None or p["finish"]:
                if p["finish"] and lead_in_geom is None:
                    # Down the roughed slot beside the loop: air all the way.
                    b.feed(z=z, f=feeds.plunge_mm_min)
                else:
                    b.feed(z=z_prev, f=feeds.ramp_mm_min)
                    b.plunge(z=z, f=feeds.plunge_mm_min)
                    counts["plunge"] += 1
            else:
                b.feed(z=z_prev, f=feeds.ramp_mm_min)
                if params["entry"] == "ramp" and len(ramp_path) >= 2 and ramp_along(
                        b, ramp_path, z_prev, z, angle_deg=params["ramp_angle_deg"], f=feeds.ramp_mm_min):
                    counts["ramp"] += 1
                else:
                    b.plunge(z=z, f=feeds.plunge_mm_min)
                    counts["plunge"] += 1
            if lead_in_geom is not None:
                _, centre, clockwise = lead_in_geom
                b.arc(float(start[0]), float(start[1]), z, centre=(centre[0], centre[1], 0.0), clockwise=clockwise,
                      f=feeds.feed_mm_min)
                counts["lead"] += 1
            else:
                b.feed(x=float(start[0]), y=float(start[1]), z=z, f=feeds.feed_mm_min)
            points = np.column_stack([ring, np.full(len(ring), z)])
            if tab_top is not None and z < tab_top - 1e-9 and spans:
                points = _lift(points, spans, tab_top, params["ramp_angle_deg"])
            b.polyline(points[1:], f=feeds.feed_mm_min)
            if lead_out_geom is not None:
                end, centre, clockwise = lead_out_geom
                b.arc(float(end[0]), float(end[1]), z, centre=(centre[0], centre[1], 0.0), clockwise=clockwise,
                      f=feeds.feed_mm_min)
            z_prev = z
        b.rapid(z=heights.retract)
        return short


def _fit_lead(ring, material_inside: bool, point, direction, radius: float, climb: bool, entering: bool, counts,
              clear=None):
    """A lead arc (``linking.lead_arc``) of ``radius``, halved until it stays on the loop's air side (inside a hole's
    loop, outside an outline's) and ``clear(line)`` (the setup's fixtures) passes; None when no lead was asked for or
    none fits (counted in ``counts["lead_dropped"]``)."""
    import numpy as np
    import shapely

    from cadgen._internal.cam import linking

    if not radius:
        return None
    loop = shapely.Polygon(ring)
    for _ in range(4):
        start, centre, clockwise = linking.lead_arc(point, direction, radius=radius, material_on_right=climb,
                                                    entering=entering)
        a0 = np.arctan2(start[1] - centre[1], start[0] - centre[0])
        a1 = np.arctan2(point[1] - centre[1], point[0] - centre[0])
        sweep = (a1 - a0) % (2 * np.pi)
        if clockwise:
            sweep -= 2 * np.pi
        angles = a0 + sweep * np.linspace(0.0, 1.0, 9)[:-1]
        arc = shapely.points(centre[0] + radius * np.cos(angles), centre[1] + radius * np.sin(angles))
        inside = shapely.contains(loop.buffer(1e-6), arc) if not material_inside else ~shapely.intersects(
            loop.buffer(-1e-6), arc)
        if np.all(inside) and (clear is None or clear(shapely.LineString(
                np.vstack([shapely.get_coordinates(arc), [point[:2]]])))):
            return start, centre, clockwise
        radius /= 2.0
    counts["lead_dropped"] = counts.get("lead_dropped", 0) + 1
    return None


def _floor_under(ctx, ring, material, z_face: float):
    """The highest part surface under the tool's sweep along ``ring`` (on the air side of ``material``) below
    ``z_face``, WCS; None when nothing is under it (the cut goes through)."""
    import numpy as np
    import shapely

    r = ctx.tool.radius
    band = shapely.LineString(ring).buffer(max(1e-3, r - 0.05)).difference(material.buffer(-0.05))
    if band.is_empty:
        return None
    vertices, triangles = ctx.mesh
    tris = np.asarray(vertices)[np.asarray(triangles)]
    low = tris[:, :, 2].min(axis=1)
    x0, y0, x1, y1 = band.bounds
    keep = (low < z_face - 1e-3) & (tris[:, :, 0].max(axis=1) >= x0) & (tris[:, :, 0].min(axis=1) <= x1) & (
        tris[:, :, 1].max(axis=1) >= y0) & (tris[:, :, 1].min(axis=1) <= y1)
    tris = tris[keep]
    if not len(tris):
        return None
    e1, e2 = tris[:, 1, :2] - tris[:, 0, :2], tris[:, 2, :2] - tris[:, 0, :2]
    flat = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) > 1e-9
    tris = tris[flat]
    if not len(tris):
        return None
    closed = np.concatenate([tris[:, :, :2], tris[:, :1, :2]], axis=1)
    hit = shapely.intersects(band, shapely.polygons(closed))
    if not hit.any():
        return None
    top = float(tris[hit][:, :, 2].max())
    if top >= z_face - 1e-3:
        beside = ctx.spec.faces[0] if ctx.spec.faces else "the loop"
        raise PlanError("gouge", f"{ctx.spec.where}: part material at the face's own height lies under the tool beside "
                        f"{beside}, so cutting round it would cut the part; give bottom_z, or name a wall")
    return top


def _loop_count(polygon, loops: str) -> int:
    return {"all": 1 + len(polygon.interiors), "outer": 1, "inner": len(polygon.interiors)}[loops]


def _rings(polygon, side: str, distance: float, loops: str, tolerance: float) -> list:
    """The tool-centre rings round ``polygon`` at ``distance`` on ``side``, each ``(ring (N, 2), material inside)``."""
    import numpy as np

    from cadgen._internal.cam import geom2d

    if side == "outside":
        shape, outer_material = geom2d.offset(polygon, distance, tolerance=tolerance), True
    elif side == "inside":
        shape, outer_material = geom2d.offset(polygon, -distance, tolerance=tolerance), False
    else:
        shape, outer_material = polygon, True
    out = []
    for piece in geom2d.polygons_of(shape):
        if loops in ("all", "outer"):
            out.append((np.asarray(piece.exterior.coords)[:, :2], outer_material))
        if loops in ("all", "inner"):
            out.extend((np.asarray(ring.coords)[:, :2], not outer_material) for ring in piece.interiors)
    return out


def _levels(top: float, bottom: float, stepdown: float) -> list[float]:
    from cadgen._internal.cam.operations._milling2d import levels

    return levels(top, bottom, stepdown)


def _order(passes: list, start) -> list:
    """Holes before the outline that holds them, deepest nesting first; nearest first among equals."""
    import shapely

    from cadgen._internal.cam import linking

    if not passes:
        return []
    shapes = [shapely.Polygon(p["ring"]) for p in passes]
    depth = []
    for i, shape in enumerate(shapes):
        point = shape.representative_point() if shape.is_valid and shape.area > 0 else shapely.Point(passes[i]["ring"][0])
        depth.append(sum(1 for j, other in enumerate(shapes) if j != i and other.is_valid and other.contains(point)))
    out = []
    here = start
    for level in sorted(set(depth), reverse=True):
        group = [p for p, d in zip(passes, depth) if d == level]
        group = linking.order_nearest(group, here, key=lambda p: tuple(p["ring"][0]))
        out.extend(group)
        here = tuple(group[-1]["ring"][0])
    return out


def _direction(ring, index: int):
    """The unit direction of travel leaving vertex 0 (``index`` 0) or arriving at the last vertex (``index`` -1)."""
    import numpy as np

    ring = np.asarray(ring, dtype=float)
    if index == 0:
        for k in range(1, len(ring)):
            delta = ring[k] - ring[0]
            if np.hypot(*delta) > 1e-9:
                return delta / np.hypot(*delta)
    else:
        for k in range(len(ring) - 2, -1, -1):
            delta = ring[-1] - ring[k]
            if np.hypot(*delta) > 1e-9:
                return delta / np.hypot(*delta)
    return np.array([1.0, 0.0])


def _lift(points, spans, tab_top: float, angle_deg: float):
    """A closed path ((N, 3), first == last) lifted to ``tab_top`` over each ``(start, end)`` span of distance along
    it: straight up onto a tab at its start, and off its end by zig-zagging down along the path ahead at no more than
    ``angle_deg`` (:func:`~cadgen._internal.cam.linking.ramp_points`), back to the tab's end at depth, so the tab
    stays square and the tool never drops straight into the material beyond it."""
    import numpy as np

    from cadgen._internal.cam.linking import ramp_points

    seg = np.linalg.norm(np.diff(points[:, :2], axis=0), axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cumulative[-1])
    bounds = []
    for s, e in spans:
        s, e = max(0.0, s), min(total, e)
        if e > s:
            bounds.extend([s, e])
    distances = np.unique(np.concatenate([cumulative, bounds]))
    xyz = np.column_stack([np.interp(distances, cumulative, points[:, i]) for i in range(3)])
    inside = np.zeros(len(distances), dtype=bool)
    for s, e in spans:
        inside |= (distances >= s - 1e-9) & (distances <= e + 1e-9)
    out = []
    last = len(xyz) - 1
    for i, (point, lifted) in enumerate(zip(xyz, inside)):
        low = [point[0], point[1], point[2]]
        if not lifted:
            out.append(low)
            continue
        high = [point[0], point[1], max(point[2], tab_top)]
        if i > 0 and not inside[i - 1]:
            out.append(low)
        out.append(high)
        if i < last and not inside[i + 1]:
            # The ring ahead at depth, up to the next tab (round past the ring's end to the first one).
            following = [k for k in range(i + 1, len(xyz)) if inside[k]]
            ahead = xyz[i:following[0] + 1] if following else np.vstack(
                [xyz[i:], xyz[1:int(np.argmax(inside)) + 1]])
            out.extend([list(q) for q in ramp_points(ahead, high[2], angle_deg=angle_deg)] or [low])
    return np.asarray(out)
