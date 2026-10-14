"""``face``: take the top of the stock down flat to the part's top (or a depth), in parallel passes.

Own keys: ``depth_mm`` (how far below the stock top to face; default: down to the part's top plus the stock to
leave), ``pattern`` (``zigzag``, the default, or ``one_way``: every pass the same direction, climb), ``angle_deg``
(the passes' direction in the WCS XY plane; 0 runs along X).

Facing the whole stock, the passes run past the stock's edges by the tool's radius plus 2 mm, so every pass starts and
ends in air (off the stock's footprint and clear of the setup's fixture boxes); zigzag passes step over in that air
and stay down. A ``region`` (``{"polygon": [[x, y], ...]}``, WCS) faces only there: the tool's centre stays inside the
region shrunk by 0.8 of its radius, so it hangs over the region's edge by a tenth of its diameter and no further (a
tool too wide for that is refused, ``tool_too_large``). Zigzag rows stay down across the turns; one-way rows lift
0.5 mm over the material, go back over the row just cut and ramp down onto the next. Wherever a row cannot start in
air the tool ramps down along it at 3 degrees, never a plunge (one only where a row has no length, counted in the
op's ``plunges``).

Step down defaults to the material's; stepover to 0.4 of the diameter for an end mill, 0.7 for a ``face_mill``.
Facing deeper than the part's top is refused (``too_deep``) when what the rows sweep at the floor meets the part;
nothing left to face (the stock top already at the floor) is ``empty_operation``.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import PlanError, choice, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["FaceOp"]

#: Default stepover, a fraction of the diameter: an end mill's corners cut the row's edges, so rows overlap more; a
#: face mill's inserts sweep most of its width.
_STEPOVER = 0.4
_STEPOVER_FACE_MILL = 0.7
#: How far a facing's tool hangs over the edge of a region, as a fraction of its radius (a tenth of its diameter).
_OVERHANG = 0.2
#: How high over the material a one-way facing in a region lifts to go back for its next row, mm.
_HOVER_MM = 0.5
#: The steepest a facing ramps into the material where it cannot start in air, degrees.
_RAMP_DEG = 3.0


class FaceOp(Operation):
    name = "face"
    plain = "Face"
    family = "2.5D milling"
    machines = MILLS
    status = "full"
    keys = ("depth_mm", "pattern", "angle_deg")
    tool_types = ("flat", "bull", "face_mill")
    takes_region = True
    feeds_kind = "face"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        extra = spec.extra
        params = {
            "depth_mm": read_number(extra, "depth_mm", spec.where),
            "pattern": choice(extra.get("pattern", "zigzag"), ("zigzag", "one_way"), f"{spec.where}.pattern"),
            "angle_deg": read_number(extra, "angle_deg", spec.where, default=0.0, minimum=-360.0, maximum=360.0),
            "region": None,
        }
        if spec.region is not None:
            params["region"] = region_polygon(spec, where=spec.where)[0]
        return params

    def plan(self, ctx, params):
        import numpy as np
        import shapely

        from cadgen._internal.cam import geom2d
        from cadgen._internal.cam.operations._milling2d import down_in_air, fixtures_clear, in_air

        tool = ctx.tool
        r = tool.radius
        tol = ctx.tolerance_mm
        heights = ctx.heights
        top = heights.stock_top
        leave = ctx.spec.stock_to_leave_mm
        bottom = top - params["depth_mm"] if params["depth_mm"] is not None else heights.part_top + leave
        if top - bottom <= 1e-6:
            raise PlanError("empty_operation", f"{ctx.spec.where}: the stock top (Z {top:.3f}) is already at the "
                            f"facing's floor (Z {bottom:.3f}) in setup '{ctx.setup.id}', so there is nothing to face; "
                            "drop the operation, or give depth_mm")
        stepover = ctx.stepover(_STEPOVER_FACE_MILL if tool.type == "face_mill" else _STEPOVER)
        feeds = ctx.feeds(self.feeds_kind, stepover_mm=stepover)
        levels = _levels(top, bottom, ctx.stepdown())
        user = params["region"]
        if user is not None:
            # The tool's centre stays inside the region shrunk by most of its radius: it hangs over the region's
            # edge by a tenth of its diameter and no further.
            centres = geom2d.offset(user, -(1.0 - _OVERHANG) * r, tolerance=tol)
            if centres.is_empty or centres.area < 1e-9:
                raise PlanError("tool_too_large", f"{ctx.spec.where}: {tool.id} ({tool.plain}) is too wide for the "
                                f"region: its centre cannot stay inside it with the tool hanging over its edge by at "
                                f"most {_OVERHANG * r:.3g} mm; use a smaller tool or a larger region")
        else:
            centres = ctx.stock_outline.buffer(r + 2.0, join_style="mitre")
        passes = self._passes(centres, params, r, stepover, region=user is not None)
        if bottom < heights.part_top - 1e-6:
            # Below the part's top: refuse when what the rows sweep at the floor meets the part.
            swept = shapely.union_all([shapely.LineString(c).buffer(r, quad_segs=16) for c in passes])
            heights_below = sorted({bottom, *[z for z in levels if z < heights.part_top], heights.part_top - 1e-3})
            part = shapely.union_all([ctx.sections.at(z) for z in heights_below if z >= bottom])
            hit = part.intersection(swept)
            if hit.area > 1e-6:
                where = hit.representative_point()
                raise PlanError("too_deep", f"{ctx.spec.where}: facing down to Z {bottom:.3f} cuts into the part (at "
                                f"X {where.x:.1f} Y {where.y:.1f}), whose top is at Z {heights.part_top:.3f}; face to "
                                "the part's top or above it (a smaller depth_mm), or keep the region off the part")
        b = ctx.builder()
        counts = {"air": 0, "ramp": 0, "plunge": 0}
        angle = _RAMP_DEG
        for li, z in enumerate(levels):
            above = top if li == 0 else levels[li - 1]
            for k, coords in enumerate(passes):
                start = (float(coords[0][0]), float(coords[0][1]))
                row = np.column_stack([coords, np.full(len(coords), z)])
                here = b.pos
                at_level = k > 0 and abs(here[2] - z) < 1e-9
                turn = shapely.LineString([here[:2], start]) if math.dist(here[:2], start) > 1e-9 else None
                if user is None:
                    if (params["pattern"] == "zigzag" and at_level and in_air(ctx, here[:2], z)
                            and in_air(ctx, start, z) and (turn is None or fixtures_clear(ctx, turn, z))):
                        # Zig-zag: step over to the next pass in the air beyond the stock's edge.
                        b.feed(x=start[0], y=start[1], f=feeds.feed_mm_min)
                    else:
                        _over(b, start, heights)
                        if in_air(ctx, start, z):
                            down_in_air(b, heights, z, f=feeds.plunge_mm_min)
                            counts["air"] += 1
                        else:
                            self._enter(b, row, above, angle, feeds, counts)
                elif params["pattern"] == "zigzag" and at_level and (
                        turn is None or turn.within(centres.buffer(tol))):
                    # Zig-zag in a region: stay down across the turn, which keeps inside the region.
                    b.feed(x=start[0], y=start[1], f=feeds.feed_mm_min)
                elif params["pattern"] == "one_way" and at_level and self._way_back(passes[k - 1], start, centres, tol):
                    # One way in a region: up just clear of the material, back over the row just cut, across to the
                    # next row's start, and ramp down onto it.
                    hover = min(above + _HOVER_MM, heights.retract)
                    back = passes[k - 1][0]
                    b.feed(z=hover, f=feeds.feed_mm_min)
                    b.feed(x=float(back[0]), y=float(back[1]), z=hover, f=feeds.feed_mm_min)
                    b.feed(x=start[0], y=start[1], z=hover, f=feeds.feed_mm_min)
                    self._enter(b, row, hover, angle, feeds, counts)
                else:
                    _over(b, start, heights)
                    if in_air(ctx, start, z):
                        down_in_air(b, heights, z, f=feeds.plunge_mm_min)
                        counts["air"] += 1
                    else:
                        if above + 1.0 < heights.retract:
                            # The column over the region down to the level above is faced already.
                            b.rapid(z=above + 1.0)
                        self._enter(b, row, above, angle, feeds, counts)
                b.polyline(row[1:], f=feeds.feed_mm_min)
        b.rapid(z=heights.clearance)
        ctx.meta.update({"levels": len(levels), "passes": len(passes), "bottom_z": round(bottom, 4),
                         "stepover_mm": round(stepover, 4), "stock_to_leave": leave,
                         "entries": {key: value for key, value in counts.items() if value and key != "plunge"}})
        if user is None:
            # The whole stock's top is now here: what a chamfer of the part's top edges reads (``faced_z``).
            ctx.meta["faced_z"] = round(bottom, 4)
        if counts["plunge"]:
            ctx.meta["plunges"] = counts["plunge"]
        return b.build()

    @staticmethod
    def _passes(centres, params, r: float, stepover: float, *, region: bool) -> list:
        """The rows ((N, 2) arrays, in cutting order and direction) across ``centres`` (where the tool's centre may
        go) at ``params``' angle: a region's from its lowest edge to its highest, the whole stock's from its edge to
        its edge, at most ``stepover`` apart."""
        import numpy as np
        import shapely
        from shapely import affinity

        angle = params["angle_deg"]
        origin = (0.0, 0.0)
        turned = affinity.rotate(centres, -angle, origin=origin)
        x0, y0, x1, y1 = turned.bounds
        if region:
            # Just inside the area's lowest and highest edge, so a row meets it as a line, not a point.
            first, last = (y0 + 1e-6, y1 - 1e-6) if y1 - y0 > 2e-6 else ((y0 + y1) / 2, (y0 + y1) / 2)
        else:
            first, last = y0 + r + 2.0, y1 - r - 2.0
        count = max(1, int(math.ceil((last - first) / stepover - 1e-9)) + 1)
        ys = [first] if count == 1 or last <= first else list(np.linspace(first, last, count))
        passes = []
        for k, y in enumerate(ys):
            line = shapely.LineString([(x0 - 1.0, y), (x1 + 1.0, y)]).intersection(turned)
            pieces = sorted((p for p in shapely.get_parts(line) if p.geom_type == "LineString" and p.length > 1e-6),
                            key=lambda p: p.bounds[0])
            if params["pattern"] == "zigzag" and k % 2 == 1:
                pieces = pieces[::-1]
            for piece in pieces:
                coords = np.asarray(piece.coords)
                forward = coords[0, 0] <= coords[-1, 0]
                if (params["pattern"] == "zigzag" and k % 2 == 1) == forward:
                    coords = coords[::-1]
                passes.append(np.asarray(affinity.rotate(shapely.LineString(coords), angle, origin=origin).coords))
        return passes

    @staticmethod
    def _way_back(previous, start, centres, tol: float) -> bool:
        """A one-way row's way back (over the row just cut to its start, then across to ``start``) keeps inside
        ``centres``."""
        import shapely

        back = shapely.LineString([tuple(previous[-1]), tuple(previous[0]), tuple(start)])
        return back.within(centres.buffer(tol))

    @staticmethod
    def _enter(b, row, z_from: float, angle: float, feeds, counts) -> None:
        """Into the material at the row's start from ``z_from`` (the material's top there, or over it): zig-zagging
        down along the row at ``angle`` (a plunge only when the row has no length to ramp along, counted)."""
        from cadgen._internal.cam.linking import ramp_points

        b.feed(z=z_from, f=feeds.ramp_mm_min)
        legs = ramp_points(row, z_from, angle_deg=angle)
        if legs:
            b.polyline(legs, f=feeds.ramp_mm_min)
            counts["ramp"] += 1
        else:
            b.plunge(z=float(row[0][2]), f=feeds.plunge_mm_min)
            counts["plunge"] += 1


def _over(b, xy, heights) -> None:
    """Up to the clearance plane (unless already over ``xy``), over ``xy``, down to the retract plane."""
    if b.pos[2] < heights.clearance - 1e-9 and math.dist(b.pos[:2], xy) > 1e-9:
        b.rapid(z=heights.clearance)
    b.rapid(x=xy[0], y=xy[1])
    if b.pos[2] > heights.retract + 1e-9:
        b.rapid(z=heights.retract)


def _levels(top: float, bottom: float, stepdown: float) -> list[float]:
    """Cut levels from just below ``top`` down to exactly ``bottom``, evenly split, none deeper than ``stepdown``."""
    from cadgen._internal.cam.job_errors import level_count

    count = level_count(top, bottom, stepdown)
    return [top - (top - bottom) * (k + 1) / count for k in range(count)]
