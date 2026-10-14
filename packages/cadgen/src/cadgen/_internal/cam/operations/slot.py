"""``slot`` (Slot): cut a slot along its centreline, level by level, entering each level by a ramp.

What it cuts, one of:

* ``path``: ``{"points": [[x, y], ...], "bottom_z": z}``, the centreline in the setup's WCS (open; closed when its
  last point is its first), any shape;
* ``faces``: a slot's flat floor facing the tool, a straight slot (a stadium or a rectangle): its centreline runs
  along the floor's long axis, its width is the floor's short side and its bottom the floor;
* ``region``: ``{"polygon": [[x, y], ...], "bottom_z": z}``, a straight slot's outline, read the same way.

The slot is as wide as ``width_mm`` (a path's default: the tool's diameter; a face's or a region's: its own width).
A tool wider than the slot is refused. Wider than the tool, each level cuts the centreline, then widens the slot in
loops round it, a stepover at a time (default 0.4 of the diameter), the last on the slot's wall, oriented for
``direction`` (``climb`` or ``conventional``).

Levels run from the stock top down by the step down (a full-width slot; the material's default) to the bottom
(plus ``stock_to_leave_mm`` on the floor and walls). Each level is entered by a ``ramp`` (default) zig-zagging along
the centreline at ``ramp_angle_deg`` (default 3), or a ``plunge``; an open slot is cut back and forth, so each
level ramps in where the last one ended. Square ends of a rectangular slot keep the tool's radius in their corners
(the ``corner_radius`` check reports it). The centreline is cut at the tool's full width at every level: its length
times the levels is ``meta["full_slot_mm"]``. A tool wider than the slot is refused (``tool_too_large``), and a floor
at or above the stock top (``empty_operation``).
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, PlanError, check_keys, choice, number_list, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["SlotOp"]


class SlotOp(Operation):
    name = "slot"
    plain = "Slot"
    family = "2.5D milling"
    machines = MILLS
    status = "full"
    keys = ("path", "width_mm", "entry", "ramp_angle_deg", "direction")
    tool_types = ("flat", "bull", "ball")
    takes_faces = True
    takes_region = True
    feeds_kind = "slot"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        extra = spec.extra
        where = spec.where
        given = sum(1 for present in (bool(spec.faces), spec.region is not None, "path" in extra) if present)
        if given != 1:
            raise CamJobError(f"{where}: a slot needs one of \"path\" ({{\"points\": [[x, y], ...], \"bottom_z\": z}}, "
                              "its centreline), \"faces\" (its floor) or \"region\" (its outline)")
        params = {
            "width_mm": read_number(extra, "width_mm", where),
            "entry": choice(extra.get("entry", "ramp"), ("ramp", "plunge"), f"{where}.entry"),
            "ramp_angle_deg": read_number(extra, "ramp_angle_deg", where, default=3.0, maximum=45.0),
            "climb": choice(extra.get("direction", "climb"), ("climb", "conventional"), f"{where}.direction") == "climb",
            "path": None,
            "region": None,
        }
        tool = ctx.job.tool(spec.tool)
        if params["width_mm"] is not None and params["width_mm"] < tool.diameter_mm - 1e-6:
            raise CamJobError(f"{where}.width_mm ({params['width_mm']:g}) is narrower than {tool.id}'s "
                              f"{tool.diameter_mm:g} mm; use a smaller tool or a wider slot")
        if "path" in extra:
            raw = extra["path"]
            if not isinstance(raw, dict):
                raise CamJobError(f"{where}.path must be {{\"points\": [[x, y], ...], \"bottom_z\": z}} in the setup's WCS")
            check_keys(raw, ("points", "bottom_z"), f"{where}.path")
            points = raw.get("points")
            if not isinstance(points, list) or len(points) < 2:
                raise CamJobError(f"{where}.path.points needs at least two [x, y] points")
            coords = [number_list(p, f"{where}.path.points[{i}]", length=2) for i, p in enumerate(points)]
            if "bottom_z" not in raw:
                raise CamJobError(f"{where}.path needs \"bottom_z\", the slot's floor height in the setup's WCS")
            bottom = read_number(raw, "bottom_z", f"{where}.path", minimum=-1e6)
            if sum(math.dist(a, b) for a, b in zip(coords, coords[1:])) < 1e-6:
                raise CamJobError(f"{where}.path.points are all one point; a slot needs a length (drill or bore a hole)")
            params["path"] = (coords, bottom)
        if spec.region is not None:
            params["region"] = region_polygon(spec, where=where)
            if params["region"][1] is None:
                raise CamJobError(f"{where}.region needs \"bottom_z\", the slot's floor height in the setup's WCS")
        return params

    def _centreline(self, ctx, polygon, what: str):
        """A straight slot's centreline (2 points) and width, from its outline."""
        import numpy as np
        import shapely

        rect = polygon.minimum_rotated_rectangle
        corners = np.asarray(rect.exterior.coords)[:4]
        sides = [corners[(k + 1) % 4] - corners[k] for k in range(2)]
        lengths = [float(np.hypot(*s)) for s in sides]
        long_k = int(np.argmax(lengths))
        length, width = lengths[long_k], lengths[1 - long_k]
        if length < width * 1.05:
            raise CamJobError(f"{ctx.spec.where}: {what} is about as wide as it is long, not a slot; use pocket or "
                              "helix_bore")
        axis = sides[long_k] / length
        centre = np.asarray(rect.centroid.coords[0])
        half = (length - width) / 2.0
        ends = np.array([centre - axis * half, centre + axis * half])
        line = shapely.LineString(ends)
        stadium = line.buffer(width / 2.0)
        box = line.buffer(width / 2.0, cap_style="square")
        fit = min(polygon.symmetric_difference(stadium).area, polygon.symmetric_difference(box).area)
        if fit > 0.05 * polygon.area:
            raise CamJobError(f"{ctx.spec.where}: {what} is not a straight slot (a stadium or a rectangle); give its "
                              "centreline as \"path\"")
        return ends, width

    def plan(self, ctx, params):
        import numpy as np
        import shapely

        from cadgen._internal.cam import geom2d
        from cadgen._internal.cam.operations._milling2d import levels, unreachable_in

        tool = ctx.tool
        r = tool.radius
        tol = ctx.tolerance_mm
        heights = ctx.heights
        leave = ctx.spec.stock_to_leave_mm
        outline = None
        if params["path"] is not None:
            coords, bottom = params["path"]
            centre = np.asarray(coords, dtype=float)
            width = params["width_mm"] or tool.diameter_mm
        else:
            if params["region"] is not None:
                outline, bottom = params["region"]
                what = "the region"
            else:
                if len(ctx.spec.faces) != 1:
                    raise CamJobError(f"{ctx.spec.where}.faces: name one slot floor per slot operation")
                bottom, outline = ctx.floor(ctx.spec.faces[0])
                outline = geom2d.polygons_of(outline)[0] if outline.geom_type != "Polygon" else outline
                what = ctx.spec.faces[0]
            centre, width = self._centreline(ctx, outline, what)
            if params["width_mm"] is not None:
                width = params["width_mm"]
        if tool.diameter_mm > width + max(2 * tol, 0.02):
            raise PlanError("tool_too_large", f"{ctx.spec.where}: {tool.id} ({tool.plain}) is wider than the {width:g} "
                            "mm slot; use a tool no wider than the slot")
        closed = len(centre) > 2 and math.dist(centre[0], centre[-1]) < 1e-6
        floor = bottom + leave
        top = heights.stock_top
        if floor >= top - 1e-6:
            raise PlanError("empty_operation", f"{ctx.spec.where}: the slot's floor (Z {floor:.3f}) is at or above the "
                            f"stock top in setup '{ctx.setup.id}', so there is nothing to cut")
        stepover = ctx.stepover(0.4)
        slot_feeds = ctx.feeds(self.feeds_kind)
        side_feeds = ctx.feeds("rough", stepover_mm=stepover)
        cut_levels = levels(top, floor, ctx.stepdown())
        reach = width / 2.0 - r - leave
        offsets = []
        if reach > max(tol, 1e-3):
            count = max(1, int(math.ceil(reach / stepover - 1e-9)))
            offsets = [reach * (k + 1) / count for k in range(count)]
        line = shapely.LineString(centre)
        # Where the tool's centre has been at a level once it is cut: back there is a free way between levels.
        cut = geom2d.offset(line, offsets[-1], tolerance=tol) if offsets else line.buffer(1e-3)
        unreachable: list[dict] = []
        if outline is not None:
            region = geom2d.offset(outline, -leave, tolerance=tol) if leave else outline
            unreachable_in(region, r, floor, tol, unreachable)
        b = ctx.builder()
        entries = {"ramp": 0, "plunge": 0}
        path = centre
        z_prev = top
        from cadgen._internal.cam.operations._milling2d import lift_and_go, link, ramp_along

        for k, z in enumerate(cut_levels):
            if k == 0:
                lift_and_go(b, path[0], heights)
            elif not closed:
                # Back and forth: this level starts where the tool is nearer.
                ends = (path[0], path[-1])
                if math.dist(b.pos[:2], ends[1]) < math.dist(b.pos[:2], ends[0]):
                    path = path[::-1]
                link(b, path[0], z_prev, clear=cut, heights=heights, f=slot_feeds.feed_mm_min)
            else:
                link(b, path[0], z_prev, clear=cut, heights=heights, f=slot_feeds.feed_mm_min)
            b.feed(z=z_prev, f=slot_feeds.ramp_mm_min)
            if params["entry"] == "ramp" and ramp_along(b, path, z_prev, z, angle_deg=params["ramp_angle_deg"],
                                                         f=slot_feeds.ramp_mm_min):
                entries["ramp"] += 1
            else:
                b.plunge(z=z, f=slot_feeds.plunge_mm_min)
                entries["plunge"] += 1
            b.polyline(np.column_stack([path[1:], np.full(len(path) - 1, z)]), f=slot_feeds.feed_mm_min)
            for offset in offsets:
                band = geom2d.offset(line, offset, tolerance=tol)
                inside = band.buffer(1e-6)
                for ring in geom2d.rings(band, climb=params["climb"]):
                    start = _nearest(ring, b.pos)
                    ring = np.vstack([ring[:-1][start:], ring[:-1][:start], ring[start:start + 1]])
                    step = shapely.LineString([b.pos[:2], ring[0]])
                    if abs(b.pos[2] - z) < 1e-9 and step.within(inside):
                        # Across the slot cut so far, stepping at most a stepover into the wall.
                        b.feed(x=float(ring[0][0]), y=float(ring[0][1]), f=side_feeds.ramp_mm_min)
                    else:
                        link(b, ring[0], z, clear=None, heights=heights, f=side_feeds.feed_mm_min)
                    b.polyline(np.column_stack([ring[1:], np.full(len(ring) - 1, z)]), f=side_feeds.feed_mm_min)
            z_prev = z
        b.rapid(z=heights.clearance)
        ctx.meta.update({"levels": len(cut_levels), "entries": {k: v for k, v in entries.items() if v},
                         "width_mm": round(width, 4), "length_mm": round(float(line.length), 4),
                         "passes": 1 + len(offsets), "floor_z": round(floor, 4), "stock_to_leave": leave,
                         "full_slot_mm": round(float(line.length) * len(cut_levels), 3),
                         "unreachable": unreachable})
        if entries["plunge"]:
            ctx.meta["plunges"] = entries["plunge"]
        return b.build()


def _nearest(ring, position) -> int:
    import numpy as np

    ring = np.asarray(ring)[:-1]
    return int(np.argmin(np.hypot(ring[:, 0] - position[0], ring[:, 1] - position[1])))
