"""``pocket``: clear a pocket down to its floors by offsetting its outline inward, level by level.

Name the pocket by its floor faces (``faces``: flat faces facing the tool; naming the deepest floor of a stepped
pocket clears the steps above it too) or by a ``region`` (``{"polygon": [[x, y], ...], "bottom_z": z}``, WCS).

How it plans, at each level from the stock top down (step down, plus every upward-facing flat of the part in
between, so steps and floors are reached exactly):

* the region to clear is the empty space at that height (the stock's outline minus the part's section grown by the
  stock to leave) that holds a named floor; above the part's top it is the pocket's mouth, so the stock above the
  pocket is cleared and the rest of the top is left to ``face``;
* the tool centre stays inside that region shrunk by the tool's radius; rings offset inward by the stepover are cut
  from the innermost out, the last one along the walls, oriented for climb (``direction``: ``climb`` or
  ``conventional``); islands are walked round the same way;
* each region at each level is entered by a helix (``entry``: ``helix``, the default, ``ramp`` or ``plunge``) at
  ``ramp_angle_deg`` (default 3), falling back to a ramp along the first ring, then to a plunge (counted in the
  op's meta);
* moves between rings stay down when the straight link lies inside the region, else lift to the retract plane and
  come down again (fed down where that level is cut already round the ring's start, else entered as a level is);
* what the tool cuts at its full width goes into ``meta["full_slot_mm"]`` for the ``full_slot`` check: each link's
  stretch at depth outside what that level has cut so far, and the first ring after a ramp or plunge entry.

``finish_mm`` leaves that much on the walls for the levels and takes it off in one ring round each wall at the final
depth, entered from the area just cleared there (dropped in over the cleared column and stepped across), never from
the top. ``finish_floor_mm`` leaves that much on the floor for a last level of its own, cleared at the walls' final
offset (its outer ring finishes the walls too).

What the tool's radius cannot reach (inside corners, gaps narrower than the tool) is recorded per floor level in
``meta["unreachable"]`` for the ``corner_radius`` check. Refused, as plan errors on the operation: a floor at or above
the stock top (``empty_operation``), a level the part fills (``too_deep``), and a level the tool does not fit in at
all (``tool_too_large``: it could never reach the floor), rather than a pocket silently cut short.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, PlanError, choice, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["PocketOp"]


class PocketOp(Operation):
    name = "pocket"
    plain = "Pocket"
    family = "2.5D milling"
    machines = MILLS
    status = "full"
    keys = ("entry", "ramp_angle_deg", "direction", "finish_mm", "finish_floor_mm")
    tool_types = ("flat", "bull", "ball")
    takes_faces = True
    takes_region = True
    feeds_kind = "rough"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        if not spec.faces and spec.region is None:
            raise CamJobError(f"{spec.where}: a pocket needs its floor faces (\"faces\": [\"#o1.f12\"]) or a "
                              "\"region\" ({\"polygon\": [[x, y], ...], \"bottom_z\": z})")
        if spec.faces and spec.region is not None:
            raise CamJobError(f"{spec.where}: give a pocket faces or a region, not both")
        extra = spec.extra
        params = {
            "entry": choice(extra.get("entry", "helix"), ("helix", "ramp", "plunge"), f"{spec.where}.entry"),
            "ramp_angle_deg": read_number(extra, "ramp_angle_deg", spec.where, default=3.0, maximum=45.0),
            "climb": choice(extra.get("direction", "climb"), ("climb", "conventional"), f"{spec.where}.direction")
            == "climb",
            "finish_mm": read_number(extra, "finish_mm", spec.where, default=0.0, minimum=0.0),
            "finish_floor_mm": read_number(extra, "finish_floor_mm", spec.where, default=0.0, minimum=0.0),
            "region": None,
        }
        if spec.region is not None:
            params["region"] = region_polygon(spec, where=spec.where)
            if params["region"][1] is None:
                raise CamJobError(f"{spec.where}.region needs \"bottom_z\", the pocket's floor height in the setup's WCS")
        return params

    def plan(self, ctx, params):
        import numpy as np
        import shapely

        from cadgen._internal.cam import geom2d, linking

        tool = ctx.tool
        r = tool.radius
        tol = ctx.tolerance_mm
        heights = ctx.heights
        leave = ctx.spec.stock_to_leave_mm
        sections = ctx.sections
        stock = ctx.stock_outline
        if params["region"] is not None:
            polygon, bottom_z = params["region"]
            floors = [(bottom_z, polygon)]
        else:
            floors = [ctx.floor(ref) for ref in ctx.spec.faces]
        bottom = min(z for z, _ in floors) + leave
        top = heights.stock_top
        if bottom >= top - 1e-6:
            raise PlanError("empty_operation", f"{ctx.spec.where}: the pocket's floor (Z {bottom:.3f}) is at or above "
                            f"the stock top in setup '{ctx.setup.id}', so there is nothing to clear")
        finish, finish_floor = params["finish_mm"], params["finish_floor_mm"]
        rough_bottom = bottom + finish_floor
        if rough_bottom >= top - 1e-6:
            raise PlanError("empty_operation", f"{ctx.spec.where}: finish_floor_mm {finish_floor:g} leaves nothing "
                            f"for the roughing levels above the floor at Z {bottom:.3f}; give a smaller "
                            "finish_floor_mm")
        stepover = ctx.stepover(0.4)
        feeds = ctx.feeds(self.feeds_kind, stepover_mm=stepover)
        stepdown = ctx.stepdown()
        # (height, how far the tool's centre keeps off the walls) per level: the roughing levels leave finish_mm on
        # the walls; finish_floor_mm leaves that on the floor for a last level of its own, whose outer ring finishes
        # the walls too.
        levels = [(z, r + finish) for z in _levels(ctx, top, rough_bottom, stepdown, leave)]
        if finish_floor > 0:
            levels.append((bottom, r))
        mouth_z = min(heights.part_top, top) - 1e-3
        seeds = [shapely.Polygon(p.exterior).buffer(-min(0.05, r / 4)) if not p.is_empty else p for _, p in floors]
        seeds = [s if not s.is_empty else p for s, (_, p) in zip(seeds, floors)]
        b = ctx.builder()
        entries = {"helix": 0, "ramp": 0, "plunge": 0, "none": 0}
        unreachable = []
        previous_area = None
        z_prev = top
        full_slot = 0.0
        for index, (z, distance) in enumerate(levels):
            if params["region"] is not None:
                polygon, _ = params["region"]
                material = sections.at(min(z, mouth_z)) if z < heights.part_top else shapely.Polygon()
                region = polygon.difference(geom2d.offset(material, leave, tolerance=tol) if leave else material)
            else:
                material = sections.at(min(z, mouth_z))
                grown = geom2d.offset(material, leave, tolerance=tol) if leave > 0 else material
                empty = stock.difference(grown)
                region = shapely.union_all([piece for piece in geom2d.polygons_of(empty)
                                            if any(piece.intersects(seed) for seed in seeds)])
            if region.is_empty or region.area < 1e-6:
                raise PlanError("too_deep", f"{ctx.spec.where}: the part fills the pocket at Z {z:.3f} in setup "
                                f"'{ctx.setup.id}'; pocketing it would cut into the part")
            reach = geom2d.offset(region, -r, tolerance=tol, radius=r)
            if reach.is_empty or reach.area < 1e-9:
                raise PlanError("tool_too_large", f"{ctx.spec.where}: {tool.id} ({tool.plain}) does not fit in the "
                                f"pocket at Z {z:.3f} (narrower than the tool there), so it cannot clear it down to "
                                f"its floor at Z {bottom:.3f}; use a smaller tool")
            area = reach if distance <= r + 1e-12 else geom2d.offset(region, -distance, tolerance=tol, radius=r)
            if area.is_empty or area.area < 1e-9:
                raise PlanError("tool_too_large", f"{ctx.spec.where}: {tool.id} ({tool.plain}) with finish_mm "
                                f"{finish:g} left on the walls does not fit in the pocket at Z {z:.3f}; use a smaller "
                                "tool or a smaller finish_mm")
            # What the radius cannot reach, once per spot (the same corner at every level is one corner).
            reached = geom2d.offset(reach, r, tolerance=tol)
            for piece in geom2d.polygons_of(region.difference(reached).buffer(-1e-4).buffer(1e-4)):
                if piece.area > 1e-3:
                    c = piece.representative_point()
                    same = next((u for u in unreachable if math.hypot(u["at"][0] - c.x, u["at"][1] - c.y) < 0.5), None)
                    if same is None:
                        unreachable.append({"area_mm2": float(piece.area), "at": [c.x, c.y, z], "z": z})
                    elif piece.area > same["area_mm2"]:
                        same.update(area_mm2=float(piece.area), at=[c.x, c.y, z], z=z)
            pieces = geom2d.polygons_of(area)
            ctx.say(f"pocket level z {z:.3f}: region {region.area:.1f} mm², {len(pieces)} piece(s)")
            pieces = linking.order_nearest(pieces, b.pos, key=lambda p: (p.centroid.x, p.centroid.y))
            for piece in pieces:
                rings = _rings_inside_out(piece, stepover, tol, params["climb"])
                if not rings:
                    continue
                first = rings[0]
                start = _nearest_vertex(first, b.pos)
                ring = _rotate_to(first, start)
                # Over the start: stay low when the way there is open at this level, else go round by the retract plane.
                cleared_above = previous_area is not None and previous_area.contains(shapely.Point(start))
                z_from = z_prev if cleared_above else top
                _travel(b, start, z_from, heights, previous_area, z_prev)
                kind = linking.entry(
                    b, piece if params["entry"] == "helix" else None, start, z_from, z,
                    tool_radius=r, angle_deg=params["ramp_angle_deg"], f=feeds.ramp_mm_min,
                    plunge_f=feeds.plunge_mm_min, path=ring if params["entry"] != "plunge" else None,
                    clockwise=not params["climb"])
                entries[kind] = entries.get(kind, 0) + 1
                # Where the tool has cut at this level so far (tool space): a link's stretch outside it is cut at the
                # tool's full width.
                swept = []
                if kind in ("ramp", "plunge"):
                    full_slot += float(shapely.LineString(ring).length)
                for k, coords in enumerate(rings):
                    if k:
                        start = _nearest_vertex(coords, b.pos)
                        coords = _rotate_to(coords, start)
                        link = shapely.LineString([b.pos[:2], start])
                        done = shapely.union_all(swept) if swept else shapely.Polygon()
                        if link.length > 1e-9 and not link.within(piece.buffer(1e-6)):
                            # Round an island or a narrows: up to the retract plane, over, and back down (to 1 mm
                            # over this level's material where the column above is cleared); fed straight down where
                            # this level is cut already round the start, else entered as a level is.
                            cleared_above = previous_area is not None and previous_area.contains(shapely.Point(start))
                            _travel(b, start, z_prev if cleared_above else top, heights, previous_area, z_prev)
                            if done.contains(shapely.Point(start).buffer(r * 0.999)):
                                b.feed(z=z, f=feeds.plunge_mm_min)
                            else:
                                kind = linking.entry(
                                    b, piece if params["entry"] == "helix" else None, start,
                                    z_prev if cleared_above else top, z, tool_radius=r,
                                    angle_deg=params["ramp_angle_deg"], f=feeds.ramp_mm_min,
                                    plunge_f=feeds.plunge_mm_min, path=coords if params["entry"] != "plunge" else None,
                                    clockwise=not params["climb"])
                                entries[kind] = entries.get(kind, 0) + 1
                        else:
                            # A link at depth from one ring to the next: where it leaves what this level has cut so
                            # far, the tool cuts its full width.
                            full_slot += float(link.difference(done).length) if swept else float(link.length)
                            b.feed(x=start[0], y=start[1], z=z, f=feeds.feed_mm_min)
                    points = np.column_stack([coords, np.full(len(coords), z)])
                    b.polyline(points[1:], f=feeds.feed_mm_min)
                    swept.append(shapely.LineString(coords).buffer(r, quad_segs=8))
                b.rapid(z=min(heights.retract, z + 1.0))
            if finish > 0 and finish_floor == 0 and index == len(levels) - 1:
                # The wall stock the levels left: one ring round each wall at the floor, entered from the area just
                # cleared at this depth (dropped in from the level above and stepped across), never from the top.
                self._finish_walls(ctx, params, b, reach, area, z, z_prev, previous_area, feeds, entries)
            previous_area = area
            z_prev = z
        b.rapid(z=heights.clearance)
        ctx.meta.update({"levels": len(levels), "entries": {k: v for k, v in entries.items() if v},
                         "unreachable": unreachable, "stock_to_leave": leave, "floor_z": round(bottom, 4),
                         "full_slot_mm": round(full_slot, 3)})
        if finish > 0:
            ctx.meta["finish_mm"] = finish
        if finish_floor > 0:
            ctx.meta["finish_floor_mm"] = finish_floor
        if entries.get("plunge"):
            ctx.meta["plunges"] = entries["plunge"]
        return b.build()


    @staticmethod
    def _finish_walls(ctx, params, b, walls, cleared, z, z_prev, previous_area, feeds, entries) -> None:
        """One ring round each piece of ``walls`` (where the tool's centre runs to finish the walls) at ``z``: from
        the nearest point of ``cleared`` (the area the roughing at this depth cleared), reached by the retract plane
        and a drop over the cleared column, then a step across onto the ring; a piece with no cleared area beside it
        is entered as a level is."""
        import numpy as np
        import shapely
        from shapely.ops import nearest_points

        from cadgen._internal.cam import geom2d, linking

        heights = ctx.heights
        tool = ctx.tool
        for piece in geom2d.polygons_of(walls):
            for ring in geom2d.rings(piece, climb=params["climb"]):
                start = _nearest_vertex(ring, b.pos)
                ring = _rotate_to(ring, start)
                landing = None
                if not cleared.is_empty:
                    q = nearest_points(cleared, shapely.Point(start))[0]
                    step = shapely.LineString([(q.x, q.y), start])
                    if step.length < 1e-9 or step.within(piece.buffer(1e-6)):
                        landing = (float(q.x), float(q.y))
                if landing is not None:
                    _travel(b, landing, z_prev, heights, previous_area, z_prev)
                    b.feed(z=z, f=feeds.plunge_mm_min)
                    b.feed(x=start[0], y=start[1], z=z, f=feeds.feed_mm_min)
                else:
                    _travel(b, start, heights.stock_top, heights, None, z_prev)
                    kind = linking.entry(b, piece, start, heights.stock_top, z, tool_radius=tool.radius,
                                         angle_deg=params["ramp_angle_deg"], f=feeds.ramp_mm_min,
                                         plunge_f=feeds.plunge_mm_min, path=ring, clockwise=not params["climb"])
                    entries[kind] = entries.get(kind, 0) + 1
                b.polyline(np.column_stack([ring[1:], np.full(len(ring) - 1, z)]), f=feeds.feed_mm_min)
                b.rapid(z=min(heights.retract, z + 1.0))


def _levels(ctx, top: float, bottom: float, stepdown: float, leave: float) -> list[float]:
    """Even step-downs from the top to the floor, plus every upward-facing flat of the part between them."""
    import numpy as np

    from cadgen._internal.cam.job_errors import level_count

    count = level_count(top, bottom, stepdown)
    levels = {round(top - (top - bottom) * (k + 1) / count, 6) for k in range(count)}
    for info in ctx.part.faces.values():
        if info.surface != "plane" or info.normal is None:
            continue
        normal = ctx.wcs.vectors_to_wcs([info.normal])[0]
        if normal[2] < 1.0 - 1e-6:
            continue
        z = float(ctx.wcs.to_wcs([info.center_mm])[0][2]) + leave
        if bottom - 1e-6 <= z < top - 1e-6:
            levels.add(round(z, 6))
    ordered = sorted(levels, reverse=True)
    # Merge levels closer than a hundredth of a millimetre.
    out = []
    for z in ordered:
        if not out or out[-1] - z > 0.01:
            out.append(z)
    if abs(out[-1] - bottom) > 1e-6:
        out.append(bottom)
    return [float(z) for z in np.asarray(out)]


def _rings_inside_out(piece, stepover: float, tolerance: float, climb: bool):
    """The rings that clear ``piece`` (where the tool centre may go): offsets by the stepover, innermost first,
    each as an (N, 2) closed array oriented for climb or conventional."""
    from cadgen._internal.cam import geom2d

    offsets = [piece]
    while True:
        inner = geom2d.offset(offsets[-1], -stepover, tolerance=tolerance)
        if inner.is_empty or inner.area < 1e-6:
            break
        offsets.append(inner)
        if len(offsets) > 2000:
            break
    rings = []
    for shape in reversed(offsets):
        rings.extend(geom2d.rings(shape, climb=climb))
    return rings


def _nearest_vertex(ring, position):
    import numpy as np

    ring = np.asarray(ring)
    k = int(np.argmin(np.hypot(ring[:-1, 0] - position[0], ring[:-1, 1] - position[1])))
    return (float(ring[k, 0]), float(ring[k, 1]))


def _rotate_to(ring, start):
    """A closed ring re-started at its vertex ``start``."""
    import numpy as np

    ring = np.asarray(ring)[:-1]
    k = int(np.argmin(np.hypot(ring[:, 0] - start[0], ring[:, 1] - start[1])))
    turned = np.vstack([ring[k:], ring[:k]])
    return np.vstack([turned, turned[:1]])


def _travel(b, start, z_from, heights, previous_area, z_prev) -> None:
    """To over ``start``: by the clearance plane, then down to the retract plane, then (when the column below is
    already cleared) down to 1 mm over the material."""
    if b.pos[2] < heights.retract - 1e-9:
        b.rapid(z=heights.retract)
    if (b.pos[0], b.pos[1]) != start:
        if b.pos[2] < heights.clearance - 1e-9:
            b.rapid(z=heights.clearance)
        b.rapid(x=start[0], y=start[1])
    b.rapid(z=heights.retract)
    if z_from + 1.0 < heights.retract:
        b.rapid(z=z_from + 1.0)
