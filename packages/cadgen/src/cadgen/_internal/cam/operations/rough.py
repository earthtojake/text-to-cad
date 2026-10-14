"""``rough``: clear the stock down round the part's 3D shape in z levels, leaving ``stock_to_leave_mm`` for finishing.

Keys: ``bottom_z`` (the lowest level, WCS; default the part's bottom), ``ramp_angle_deg`` (entry ramps and helices,
default 3), ``direction`` (``climb``, the default, or ``conventional``); and the shared ``stepdown_mm`` (default the
material's), ``stepover`` (default 0.4 of the diameter), ``stock_to_leave_mm`` and ``region``
(``{"polygon": [[x, y], ...], "bottom_z": z}``: the tool centre kept inside it).

How it plans, level by level from the stock top down (even step-downs, plus every upward-facing flat of the part plus
the stock to leave, so flats are left exactly that thick):

* the part's silhouette above the level less the stock to leave (every bit of material higher than that, seen from
  the tool), grown by the tool's radius plus the stock to leave, is where the tool centre must not go; the region
  to clear is the stock (grown so the tool can start in the air outside it) minus that;
* a piece of that region that reaches the open air outside the stock is cleared from the outside in, in passes at a
  constant distance from the part (the stepover apart, the last one along the part), each starting in the air where
  it can, else fed in sideways at its level from the air through what is already cut, else ramped in along itself;
  a closed piece (a cavity) is cleared from the inside out like a pocket, entered by a helix (else a ramp
  along the first pass, else a plunge);
* between passes the tool stays down where the way is already cut, otherwise lifts just over the level above (or
  to the retract plane) and comes back down by a ramp.

On slopes the levels leave steps up to the step-down tall; finish them with ``parallel`` or ``waterline``, or rest
machining. A ball or bull tool is kept off the part by its full radius at every level (safe, a little more material
left on slopes).
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, choice, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["RoughOp", "keep_off", "lowest_level", "plan_rough"]


class RoughOp(Operation):
    name = "rough"
    plain = "3D rough"
    family = "3D milling"
    machines = MILLS
    status = "full"
    keys = ("bottom_z", "ramp_angle_deg", "direction")
    tool_types = ("flat", "bull", "ball")
    takes_region = True
    feeds_kind = "rough"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        return parse_rough(spec, spec.extra)

    def plan(self, ctx, params):
        return plan_rough(ctx, params)


def parse_rough(spec, extra) -> dict:
    params = {
        "bottom_z": read_number(extra, "bottom_z", spec.where, minimum=-1e6) if "bottom_z" in extra else None,
        "ramp_angle_deg": read_number(extra, "ramp_angle_deg", spec.where, default=3.0, maximum=45.0),
        "climb": choice(extra.get("direction", "climb"), ("climb", "conventional"), f"{spec.where}.direction")
        == "climb",
        "region": None,
    }
    if spec.region is not None:
        params["region"] = region_polygon(spec, where=spec.where)
    return params


def lowest_level(ctx, params) -> float:
    """The lowest level a z-level rough goes to: ``bottom_z``, else its region's, else the part's bottom (or the
    stock's, when that is higher)."""
    heights = ctx.heights
    region_bottom = params["region"][1] if params["region"] is not None else None
    if params["bottom_z"] is not None:
        return params["bottom_z"]
    return region_bottom if region_bottom is not None else max(heights.part_bottom, heights.stock_bottom)


def keep_off(silhouettes, z: float, radius: float, leave: float, tolerance: float):
    """Where a tool's centre may not go at level ``z``: everything of the part above it less the stock to leave, seen
    from the tool, grown by the radius plus the stock to leave."""
    import shapely

    from cadgen._internal.cam import geom2d

    material = silhouettes.above(z - leave)
    if material.is_empty:
        return shapely.Polygon()
    return geom2d.offset(material, radius + leave, tolerance=tolerance, radius=radius + leave)


def plan_rough(ctx, params, *, limit=None):
    """The rough toolpath; ``limit`` (a shapely area, WCS) keeps the tool centre inside it (rest machining)."""
    import numpy as np
    import shapely

    from cadgen._internal.cam import geom2d, linking
    from cadgen._internal.cam.milling3d import Silhouettes
    from cadgen._internal.cam.operations.pocket import _levels, _rings_inside_out, _travel

    tool = ctx.tool
    r = tool.radius
    tol = ctx.tolerance_mm
    heights = ctx.heights
    leave = ctx.spec.stock_to_leave_mm
    top = heights.stock_top
    user_region = params["region"][0] if params["region"] is not None else None
    bottom = lowest_level(ctx, params)
    if bottom >= top - 1e-6:
        raise CamJobError(f"{ctx.spec.where}: the rough's lowest level is at or above the stock top in setup "
                          f"'{ctx.setup.id}'; nothing to clear")
    stepover = ctx.stepover(0.4)
    if stepover >= 2 * r:
        raise CamJobError(f"{ctx.spec.where}: a stepover of {stepover:g} mm leaves ridges with a {tool.diameter_mm:g} mm "
                          "tool; make it less than the diameter")
    feeds = ctx.feeds("rough", stepover_mm=stepover)
    stepdown = ctx.stepdown()
    levels = _levels(ctx, top, bottom, stepdown, leave)
    stock = ctx.stock_outline
    outer = stock.buffer(r + 0.5)
    air_edge = stock.buffer(r + 0.05)
    zone = stock.buffer(r + 0.1)
    vertices, triangles = ctx.mesh
    silhouettes = Silhouettes(vertices, triangles, ctx.sections)
    b = ctx.builder()
    entries: dict[str, int] = {}
    previous_area = None
    z_prev = top
    cut_levels = 0
    for z in levels:
        kept_off = keep_off(silhouettes, z, r, leave, tol)
        region = outer.difference(kept_off)
        if user_region is not None:
            region = region.intersection(user_region)
        if limit is not None:
            region = region.intersection(limit)
        pieces = [p for p in geom2d.polygons_of(region) if p.area > 1e-4 and p.intersects(zone)]
        ctx.say(f"rough level z {z:.3f}: {len(pieces)} piece(s)")
        if not pieces:
            z_prev = z
            previous_area = region
            continue
        cut_levels += 1
        pieces = linking.order_nearest(pieces, b.pos, key=lambda p: (p.centroid.x, p.centroid.y))
        for piece in pieces:
            open_piece = not stock.buffer(r + 0.25).contains(piece)
            if open_piece:
                curves = _outside_in(piece, kept_off, stepover, tol, params["climb"], zone)
            else:
                curves = [(c, True) for c in _rings_inside_out(piece, stepover, tol, params["climb"])]
            if not curves:
                continue
            # Offsets of a tessellated silhouette carry every vertex: within half the tolerance is plenty.
            curves = [(_thin(c, tol / 2.0), closed) for c, closed in curves]
            for k, (coords, closed) in enumerate(curves):
                start = (float(coords[0][0]), float(coords[0][1]))
                in_air = not air_edge.contains(shapely.Point(start))
                here = b.pos
                link = shapely.LineString([here[:2], start]) if math.dist(here[:2], start) > 1e-9 else None
                down_here = abs(here[2] - z) < 1e-9
                if k and down_here and (link is None or _clear_link(link, piece, air_edge, kept_off, coords)):
                    b.feed(x=start[0], y=start[1], z=z, f=feeds.feed_mm_min)
                elif in_air:
                    _over(b, start, heights, previous_area, z_prev, link)
                    b.rapid(z=z)
                    entries["air"] = entries.get("air", 0) + 1
                elif open_piece and (side := _side_entry(start, piece, air_edge, kept_off, coords)) is not None:
                    # From the air beside the stock, straight in at the level through what is already cut.
                    _over(b, side, heights, previous_area, z_prev,
                          shapely.LineString([here[:2], side]) if math.dist(here[:2], side) > 1e-9 else None)
                    b.rapid(z=z)
                    b.feed(x=start[0], y=start[1], z=z, f=feeds.feed_mm_min)
                    entries["side"] = entries.get("side", 0) + 1
                else:
                    cleared_above = previous_area is not None and previous_area.contains(shapely.Point(start))
                    z_from = z_prev if cleared_above else top
                    if k and down_here and link is not None and previous_area is not None and \
                            link.within(previous_area.buffer(1e-6)) and cleared_above:
                        b.rapid(z=min(heights.retract, z_prev + 1.0))
                        b.rapid(x=start[0], y=start[1])
                    else:
                        _travel(b, start, z_from, heights, previous_area, z_prev)
                    kind = enter(b, piece if (closed and not open_piece and k == 0) else None, start, z_from, z,
                                 tool_radius=r, angle_deg=params["ramp_angle_deg"], f=feeds.ramp_mm_min,
                                 plunge_f=feeds.plunge_mm_min, path=coords, clockwise=not params["climb"])
                    entries[kind] = entries.get(kind, 0) + 1
                points = np.column_stack([coords, np.full(len(coords), z)])
                b.polyline(points[1:], f=feeds.feed_mm_min)
            b.rapid(z=min(heights.retract, z + 1.0))
        previous_area = region
        z_prev = z
    b.rapid(z=heights.clearance)
    ctx.meta.update({"levels": cut_levels, "entries": {k: v for k, v in entries.items() if v},
                     "stock_to_leave": leave, "floor_z": round(bottom, 4)})
    if entries.get("plunge"):
        ctx.meta["plunges"] = entries["plunge"]
    return b.build()


def enter(b, region, start, z_from: float, z_to: float, *, tool_radius: float, angle_deg: float, f: float,
          plunge_f: float, path, clockwise: bool) -> str:
    """Into the material at ``start`` from ``z_from`` down to ``z_to``: a helix inside ``region`` when one of at least
    a quarter of the tool's radius fits there, else a ramp that zig-zags along ``path`` itself (never cutting across
    its bends), else a plunge. The tool ends at ``start`` at ``z_to``."""
    import shapely

    from cadgen._internal.cam import linking

    if z_from - z_to <= 1e-9:
        b.feed(x=start[0], y=start[1], z=z_to, f=f)
        return "none"
    if region is not None:
        for share in (0.75, 0.5, 0.25):
            radius = share * tool_radius
            centre = shapely.Point(start[0] - radius, start[1])
            if region.buffer(-radius * 1.01).contains(centre):
                linking.helix(b, (centre.x, centre.y), radius, z_from, z_to, angle_deg=angle_deg, f=f,
                              clockwise=clockwise)
                b.feed(x=start[0], y=start[1], z=z_to, f=f)
                return "helix"
    if path is not None and ramp_along(b, path, z_from, z_to, angle_deg=angle_deg, f=f):
        return "ramp"
    b.feed(x=start[0], y=start[1], f=f)
    b.feed(z=z_from, f=f)
    b.plunge(z=z_to, f=plunge_f)
    return "plunge"


def ramp_along(b, path, z_from: float, z_to: float, *, angle_deg: float, f: float) -> bool:
    """Zig-zag down along the first stretch of ``path`` ((N, 2)) itself, forward and back, from ``z_from`` to
    ``z_to`` at ``angle_deg``; ends at the path's first point at ``z_to``. False (nothing added) when the path is
    shorter than half a millimetre."""
    import numpy as np

    points = np.asarray(path, dtype=float)[:, :2]
    if len(points) < 2:
        return False
    lengths = np.hypot(*np.diff(points, axis=0).T)
    cumulative = np.concatenate([[0.0], np.cumsum(lengths)])
    total = float(cumulative[-1])
    slope = math.tan(math.radians(angle_deg))
    run = min(total, max(1.0, (z_from - z_to) / slope))
    if run < 0.5:
        return False
    k = int(np.searchsorted(cumulative, run, side="left"))
    k = max(1, min(k, len(points) - 1))
    t = (run - cumulative[k - 1]) / max(lengths[k - 1], 1e-12)
    end = points[k - 1] + (points[k] - points[k - 1]) * t
    stretch = np.vstack([points[:k], end[None, :]])
    s = np.concatenate([cumulative[:k], [run]])
    b.feed(x=float(stretch[0, 0]), y=float(stretch[0, 1]), f=f)
    b.feed(z=z_from, f=f)
    z = z_from
    forward = True
    per_leg = run * slope
    while z > z_to + 1e-9:
        z_end = max(z_to, z - per_leg)
        if forward:
            seq, fraction = stretch[1:], s[1:] / run
        else:
            seq, fraction = stretch[-2::-1], (run - s[-2::-1]) / run
        heights = z + (z_end - z) * fraction
        b.polyline(np.column_stack([seq, heights]), f=f)
        z = z_end
        forward = not forward
    if not forward:
        back = stretch[-2::-1]
        b.polyline(np.column_stack([back, np.full(len(back), z_to)]), f=f)
    return True


def _over(b, start, heights, previous_area, z_prev, link) -> None:
    """To over ``start`` (a point in the air beside the stock): just over the level above when the way is cleared
    there, else by the retract plane."""
    if link is not None and previous_area is not None and link.within(previous_area.buffer(1e-6)):
        if b.pos[2] < z_prev + 1.0:
            b.rapid(z=min(heights.retract, z_prev + 1.0))
        b.rapid(x=start[0], y=start[1])
        return
    if b.pos[2] < heights.retract - 1e-9:
        b.rapid(z=heights.retract)
    b.rapid(x=start[0], y=start[1])


def _thin(coords, tolerance: float):
    """A pass with the points it does not need within ``tolerance`` left out (its ends kept)."""
    import numpy as np
    import shapely

    coords = np.asarray(coords, dtype=float)
    if len(coords) < 4:
        return coords
    thinned = np.asarray(shapely.simplify(shapely.LineString(coords), tolerance, preserve_topology=False).coords)
    return thinned if len(thinned) >= 2 else coords


def _side_entry(start, piece, air_edge, keep_off, coords):
    """The nearest point in the air beside the stock from which a straight feed at the level reaches ``start``
    through what this level has already cut, or None."""
    import shapely

    boundary = air_edge.exterior if air_edge.geom_type == "Polygon" else air_edge.boundary
    point = shapely.Point(start)
    outside = boundary.interpolate(boundary.project(point))
    # A hair further out, so the tool starts clear of the stock.
    dx, dy = outside.x - start[0], outside.y - start[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return None
    side = (outside.x + dx / length * 0.05, outside.y + dy / length * 0.05)
    link = shapely.LineString([side, start])
    return side if _clear_link(link, piece, air_edge, keep_off, coords) else None


def _clear_link(link, piece, air_edge, keep_off, coords) -> bool:
    """A link at the cutting level stays down only through what this level has already cut: within the piece and no
    nearer the part than the pass it goes to, or out in the air."""
    import shapely

    if not link.within(piece.buffer(1e-6).union(link.difference(air_edge).buffer(1e-6))):
        return False
    if keep_off.is_empty:
        return True
    target = shapely.distance(shapely.Point(coords[0]), keep_off)
    return link.distance(keep_off) >= target - 1e-6


def _outside_in(piece, keep_off, stepover: float, tolerance: float, climb: bool, zone):
    """The passes that clear an open piece from the outside in: curves at a constant distance from the part's
    keep-off (or, above the part, from the piece's own edge), farthest first, clipped to where the tool meets the
    stock; each an (N, 2) array oriented for climb with the material on its right, and whether it is closed."""
    import numpy as np
    import shapely

    from cadgen._internal.cam import geom2d

    target = piece.intersection(zone)
    if target.is_empty:
        return []
    shapes = []
    if keep_off.is_empty or not piece.buffer(1e-3).intersects(keep_off):
        k = 1
        while True:
            inner = geom2d.offset(piece, -k * stepover, tolerance=tolerance)
            if inner.is_empty or inner.area < 1e-6 or k > 4000:
                break
            shapes.append(inner)
            k += 1
    else:
        boundary = shapely.get_coordinates(piece.exterior)
        sample = np.vstack([boundary] + [shapely.get_coordinates(ring) for ring in piece.interiors])
        far = float(np.max(shapely.distance(shapely.points(sample), keep_off)))
        count = int(math.ceil(far / stepover))
        for k in range(count, -1, -1):
            shapes.append(geom2d.offset(keep_off, k * stepover, tolerance=tolerance) if k else keep_off)
    out = []
    for shape in shapes:
        for ring in geom2d.rings(shape, climb=not climb):
            line = shapely.LineString(ring)
            inside = line.intersection(target)
            if inside.is_empty:
                continue
            if inside.equals(line) or line.within(target.buffer(1e-9)):
                out.append((np.asarray(ring), True))
                continue
            # Restart the ring outside the target so its pieces do not wrap round its start.
            outside = np.nonzero(~shapely.contains_xy(target, ring[:, 0], ring[:, 1]))[0]
            if len(outside):
                k = int(outside[0])
                ring = np.vstack([ring[k:-1], ring[:k + 1]])
                line = shapely.LineString(ring)
                inside = line.intersection(target)
            for part in shapely.get_parts(shapely.line_merge(inside) if inside.geom_type == "MultiLineString"
                                          else inside):
                if part.geom_type != "LineString" or part.length < 1e-3:
                    continue
                coords = np.asarray(part.coords)[:, :2]
                if line.project(shapely.Point(coords[0])) > line.project(shapely.Point(coords[-1])):
                    coords = coords[::-1]
                out.append((coords, False))
    return out
