"""``circular`` (Circular): clear a round pocket from its centre out, or a round boss from outside in, level by level.

What it cuts, one of:

* ``faces``: round hole walls (a round pocket, blind or through: any face of it names the whole of it, ``cadgen cam
  features`` lists them) or the outside of round bosses (cylinders standing along the setup's Z), each read off the
  part (:func:`~cadgen._internal.cam.operations._milling2d.hole_targets`). ``boss`` (true or false) says which the
  job means and is refused when a face is the other kind; left out, each face says;
* ``region``: ``{"polygon": [[x, y], ...], "bottom_z": z}`` (WCS): a pocket is the largest circle inside the polygon,
  a boss (``boss: true``) the smallest circle round it.

Depth: down to the pocket's bottom (a through pocket ``through_mm`` past it, default 0) or the boss's foot, or to
``bottom_z`` (WCS) when given; ``bottom_z`` under a blind pocket's bottom or a boss's foot is refused (``too_deep``).
``stock_to_leave_mm`` is left on the wall and the floor. Levels run from the top of the material over the feature
(the stock top when it opens on the part's top) down by the step down (the material's default).

A pocket: each level is entered by a helix at the centre (``linking.helix``, half the tool's radius, no steeper than
``ramp_angle_deg``, default 3), then spirals out to the wall in tangent half circles about points on one line (true
arcs, posted as G2/G3), a stepover (default 0.4 of the diameter) per turn, then cuts one whole finishing circle on
the wall. The feed is the table's at the cutting edge: inside a circle the tool's centre runs a smaller circle than
its edge, so its feed is scaled by the centre's radius over the edge's (``rho / (rho + r)``), never under a quarter.
A tool within a tenth of its radius of the pocket's size is refused (``tool_too_large``: drill or bore it).

A boss: each level starts on an outer ring and spirals in to the boss's wall, a stepover per turn, then cuts one
whole finishing circle on it. ``clear_mm`` is how far out from the boss's wall the material is cleared (at least the
tool's diameter is); left out, it clears out to the stock's edge (the outer ring off the stock, so the tool comes
down in air), or, when the part stands nearer, up to the part beside it. Where the outer ring is in the stock, the
tool goes down along it on a helix at ``ramp_angle_deg`` and cuts one whole circle there before spiralling in. A
``clear_mm`` that reaches the part beside the boss is refused (``unreachable``); so is a boss with less room round it
than the tool's diameter (``tool_too_large``).

``direction``: ``climb`` (default: counter-clockwise inside a pocket, clockwise round a boss) or ``conventional``.

``helix_bore`` bores a hole to size with circles at its wall (and, wider than twice the tool, more circles inside
it); ``circular`` is for a round pocket wider than that, cleared by one spiral per level, and for bosses.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, PlanError, choice, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["CircularOp"]

#: The least share of the feed the tool's centre runs at round an internal arc (a small circle in a big tool).
_ARC_FEED_FLOOR = 0.25
#: A pocket must be wider than the tool by at least this much of its radius (on each side), else drill or bore it.
_SNUG = 0.1
#: How far past the stock's edge (mm, beyond the tool's radius) a boss's default outer ring runs, so the tool comes
#: down in air (``in_air`` wants half a millimetre).
_OFF_STOCK_MM = 1.0


class CircularOp(Operation):
    name = "circular"
    plain = "Circular"
    family = "2.5D milling"
    machines = MILLS
    status = "full"
    keys = ("boss", "clear_mm", "bottom_z", "through_mm", "ramp_angle_deg", "direction")
    tool_types = ("flat", "bull")
    takes_faces = True
    takes_region = True
    feeds_kind = "rough"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        extra = spec.extra
        where = spec.where
        if bool(spec.faces) == (spec.region is not None):
            raise CamJobError(f"{where}: a circular needs the round pocket's or boss's walls (\"faces\": [\"#o1.f8\"]) "
                              "or a \"region\" ({\"polygon\": [[x, y], ...], \"bottom_z\": z}), one of them")
        boss = extra.get("boss")
        if boss is not None and not isinstance(boss, bool):
            raise CamJobError(f"{where}.boss must be true (clear round a boss) or false (clear a round pocket), not "
                              f"{boss!r}")
        params = {
            "boss": boss,
            "clear_mm": read_number(extra, "clear_mm", where),
            "bottom_z": read_number(extra, "bottom_z", where, minimum=-1e6),
            "through_mm": read_number(extra, "through_mm", where, default=0.0, minimum=0.0),
            "ramp_angle_deg": read_number(extra, "ramp_angle_deg", where, default=3.0, maximum=45.0),
            "climb": choice(extra.get("direction", "climb"), ("climb", "conventional"), f"{where}.direction") == "climb",
            "region": region_polygon(spec, where=where) if spec.region is not None else None,
        }
        if params["clear_mm"] is not None and boss is False:
            raise CamJobError(f"{where}.clear_mm is how far round a boss to clear; a round pocket has none (remove it, "
                              "or set boss true)")
        if params["region"] is not None and params["clear_mm"] is not None and not boss:
            raise CamJobError(f"{where}.clear_mm is how far round a boss to clear; a region is a round pocket unless "
                              "boss is true")
        if params["region"] is not None and params["region"][1] is None and params["bottom_z"] is None:
            raise CamJobError(f"{where}.region needs \"bottom_z\", the {'boss' if boss else 'pocket'}'s floor height "
                              "in the setup's WCS")
        return params

    # --- what it cuts ------------------------------------------------------------------------------------

    def _targets(self, ctx, params) -> list[dict]:
        """``{ref, centre, radius, top_z, bottom_z, boss, through, region}`` per round pocket or boss, WCS."""
        import shapely

        from cadgen._internal.cam.operations._milling2d import hole_targets

        where = ctx.spec.where
        heights = ctx.heights
        given = params["bottom_z"]
        if params["region"] is not None:
            polygon, bottom = params["region"]
            bottom = given if given is not None else bottom
            if params["boss"]:
                centre = shapely.minimum_bounding_circle(polygon).centroid
                cx, cy, radius = centre.x, centre.y, float(shapely.minimum_bounding_radius(polygon))
            else:
                line = shapely.maximum_inscribed_circle(polygon, ctx.tolerance_mm / 4.0)
                (cx, cy), edge = line.coords[0], line.coords[1]
                radius = math.dist((cx, cy), edge)
            return [{"ref": "the region", "centre": (float(cx), float(cy)), "radius": radius,
                     "top_z": heights.part_top, "bottom_z": bottom, "boss": bool(params["boss"]),
                     "through": bottom <= heights.part_bottom + 1e-6, "region": True}]
        out = []
        for target in hole_targets(ctx, ctx.spec.faces, where=f"{where}.faces", bosses_ok=True):
            if target.hole and params["boss"]:
                raise CamJobError(f"{where}.boss: {target.ref} is a hole's wall, not a boss; leave boss out (or false) "
                                  "to clear it as a round pocket, or name the outside of a boss")
            if not target.hole and params["boss"] is False:
                raise CamJobError(f"{where}.boss: {target.ref} is the outside of a round boss, not a pocket; leave boss "
                                  "out (or true) to clear round it, or name a pocket's wall")
            if target.hole and params["clear_mm"] is not None:
                raise CamJobError(f"{where}.clear_mm is how far round a boss to clear; {target.ref} is a round pocket's "
                                  "wall (remove clear_mm)")
            bottom = target.bottom_z
            if given is not None:
                deepest = None if target.hole and target.through else target.bottom_z
                if deepest is not None and given < deepest - 1e-6:
                    what = "bottom" if target.hole else "foot"
                    raise PlanError("too_deep", f"{where}.bottom_z: Z {given:g} is under the {what} of "
                                    f"{target.ref} (Z {deepest:.3f}), so the cut would go into the part under it; give "
                                    f"bottom_z {deepest:.3f} or higher, or leave it out")
                bottom = given
            out.append({"ref": target.ref, "centre": target.centre, "radius": target.diameter_mm / 2.0,
                        "top_z": target.top_z, "bottom_z": bottom, "boss": not target.hole,
                        "through": bottom <= heights.part_bottom + 1e-6, "region": False})
        return out

    def _material(self, ctx, low: float, high: float, keep_out):
        """The part's material between heights ``low`` and ``high`` (WCS) outside ``keep_out`` (a shapely
        polygon), as pieces with any area."""
        import shapely

        from cadgen._internal.cam import geom2d
        from cadgen._internal.cam.operations._edges import material_heights

        pieces = []
        for h in material_heights(ctx, low, high):
            for piece in geom2d.polygons_of(ctx.sections.at(h).difference(keep_out)):
                if piece.area > 1e-2:
                    pieces.append(piece)
        return shapely.union_all(pieces) if pieces else None

    # --- the plan ----------------------------------------------------------------------------------------

    def plan(self, ctx, params):
        from cadgen._internal.cam import linking
        from cadgen._internal.cam.operations._milling2d import levels

        tool = ctx.tool
        heights = ctx.heights
        leave = ctx.spec.stock_to_leave_mm
        stepover = ctx.stepover(0.4)
        if stepover > tool.diameter_mm + 1e-9:
            raise CamJobError(f"{ctx.spec.where}: a {stepover:g} mm stepover is wider than {tool.id}'s "
                              f"{tool.diameter_mm:g} mm, so it leaves rings of material between the turns; give a "
                              "stepover of the diameter or less")
        feeds = ctx.feeds(self.feeds_kind, stepover_mm=stepover)
        stepdown = ctx.stepdown()
        b = ctx.builder()
        targets = linking.order_nearest(self._targets(ctx, params), b.pos, key=lambda t: t["centre"])
        counts = {"helix": 0, "air": 0}
        facts = {"levels": 0, "turns": 0.0, "passes": 0}
        floors, cleared = [], []
        for target in targets:
            z_top = heights.stock_top if target["top_z"] >= heights.part_top - 1e-6 else target["top_z"]
            floor = target["bottom_z"] - params["through_mm"] if target["through"] else target["bottom_z"] + leave
            if floor >= z_top - 1e-6:
                raise PlanError("empty_operation", f"{ctx.spec.where}: {target['ref']} has no depth to clear under the "
                                f"material's top in setup '{ctx.setup.id}' (its floor at Z {floor:.3f}), so it cuts "
                                "nothing")
            cut_levels = levels(z_top, floor, stepdown)
            if target["boss"]:
                turns, reach = self._boss(ctx, params, b, target, cut_levels, z_top, stepover, feeds, counts)
                cleared.append(reach)
            else:
                turns = self._pocket(ctx, params, b, target, cut_levels, z_top, stepover, feeds, counts)
            floors.append(floor)
            facts["levels"] = max(facts["levels"], len(cut_levels))
            facts["turns"] += turns
            facts["passes"] += len(cut_levels)
            b.rapid(z=heights.retract)
        b.rapid(z=heights.clearance)
        kinds = {"boss" if t["boss"] else "pocket" for t in targets}
        ctx.meta.update({"targets": len(targets), "kind": " and ".join(sorted(kinds)), "levels": facts["levels"],
                         "passes": facts["passes"], "turns": round(facts["turns"], 2),
                         "entries": {k: v for k, v in counts.items() if v}, "bottom_z": round(min(floors), 4),
                         "stock_to_leave": leave})
        if len(targets) == 1:
            ctx.meta["diameter_mm"] = round(2.0 * targets[0]["radius"], 4)
        if cleared:
            ctx.meta["cleared_mm"] = round(min(cleared), 4)
        return b.build()

    def _pocket(self, ctx, params, b, target, cut_levels, z_top, stepover, feeds, counts) -> float:
        """Each level: a helix at the centre, a spiral out to the wall, a finishing circle. Returns the turns."""
        import shapely

        from cadgen._internal.cam import linking
        from cadgen._internal.cam.operations._milling2d import helix_arcs, lift_and_go

        tool = ctx.tool
        r = tool.radius
        heights = ctx.heights
        leave = ctx.spec.stock_to_leave_mm
        cx, cy = target["centre"]
        wall = target["radius"]
        final = wall - leave - r
        if final <= max(ctx.tolerance_mm, _SNUG * r):
            raise PlanError("tool_too_large", f"{ctx.spec.where}: {tool.id} ({tool.plain}) is not smaller than the "
                            f"Ø{2 * wall:.4g} round pocket {target['ref']} (less the stock to leave) by a tenth of its "
                            "radius; use a smaller tool, or drill or ream it")
        if target["region"]:
            inside = shapely.Point(cx, cy).buffer(wall - 0.05, quad_segs=64)
            over = self._material(ctx, cut_levels[-1], z_top, shapely.Polygon())
            if over is not None and over.intersection(inside).area > 1e-2:
                raise PlanError("gouge", f"{ctx.spec.where}.region: the Ø{2 * wall:.4g} circle at ({cx:.3f}, {cy:.3f}) "
                                f"runs into the part above Z {cut_levels[-1]:.3f}; draw the region round the pocket "
                                "itself, or give a higher bottom_z")
        sense = 1.0 if params["climb"] else -1.0
        start = min(0.5 * r, final)
        halves = _halves(final - start, stepover)

        def scaled(feed: float, rho: float) -> float:
            # The table's feed at the cutting edge: the centre runs a smaller circle than the edge does.
            return max(1.0, round(feed * max(_ARC_FEED_FLOOR, min(1.0, rho / (rho + r)))))

        z_prev = z_top
        for k, z in enumerate(cut_levels):
            if k == 0:
                lift_and_go(b, (cx + start, cy), heights)
            else:
                b.feed(x=cx + start, y=cy, f=feeds.feed_mm_min)
            linking.helix(b, (cx, cy), start, z_prev, z, angle_deg=params["ramp_angle_deg"],
                          f=scaled(feeds.ramp_mm_min, start), clockwise=sense < 0)
            counts["helix"] += 1
            _spiral(b, (cx, cy), start, final, 0.0, sense, z, halves=halves,
                    feed=lambda rho: scaled(feeds.feed_mm_min, rho))
            helix_arcs(b, (cx, cy), final, 0.0, sense * 2 * math.pi, z, f=scaled(feeds.feed_mm_min, final))
            z_prev = z
        b.feed(x=cx, y=cy, f=feeds.feed_mm_min)
        return len(cut_levels) * halves / 2.0

    def _boss(self, ctx, params, b, target, cut_levels, z_top, stepover, feeds, counts) -> tuple[float, float]:
        """Each level: down on the outer ring (in air, or a helix along it and a circle), a spiral in to the boss,
        a finishing circle. Returns the turns and how far out from the boss's wall the material was cleared."""
        import numpy as np
        import shapely

        from cadgen._internal.cam.operations._milling2d import down_in_air, helix_arcs, in_air, lift_and_go

        tool = ctx.tool
        r = tool.radius
        heights = ctx.heights
        leave = ctx.spec.stock_to_leave_mm
        where = ctx.spec.where
        cx, cy = target["centre"]
        wall = target["radius"]
        final = wall + leave + r
        centre = shapely.Point(cx, cy)
        boss = centre.buffer(wall + max(0.05, 5.0 * float(getattr(ctx.part, "deflection_mm", 0.01))), quad_segs=64)
        other = self._material(ctx, cut_levels[-1], z_top, boss)
        room = float(other.distance(centre)) - wall if other is not None else math.inf
        if room < leave + 2 * r - 1e-6:
            raise PlanError("tool_too_large", f"{where}: the part stands {room:.3g} mm from the boss {target['ref']} "
                            f"above Z {cut_levels[-1]:.3f}, less than {tool.id}'s {tool.diameter_mm:g} mm (and the "
                            "stock to leave), so there is no room to cut round it; use a smaller tool")
        if params["clear_mm"] is not None:
            if params["clear_mm"] > room + 1e-6:
                raise PlanError("unreachable", f"{where}.clear_mm: clearing {params['clear_mm']:g} mm round the boss "
                                f"{target['ref']} would cut the part, which stands {room:.3g} mm from it above Z "
                                f"{cut_levels[-1]:.3f}; give clear_mm {math.floor(room * 100 + 1e-6) / 100:g} or less")
            outer = max(final, wall + params["clear_mm"] - r)
        else:
            stock = np.asarray(ctx.stock_outline.exterior.coords)
            farthest = float(np.max(np.hypot(stock[:, 0] - cx, stock[:, 1] - cy)))
            outer = max(final, min(farthest + r + _OFF_STOCK_MM, wall + room - 0.05 - r))
        sense = -1.0 if params["climb"] else 1.0          # clockwise round a boss for climb
        halves = _halves(outer - final, stepover)
        slope = math.tan(math.radians(params["ramp_angle_deg"]))
        f = max(1.0, round(feeds.feed_mm_min))
        phi = 0.0
        z_prev = z_top
        for k, z in enumerate(cut_levels):
            ring = (cx + outer * math.cos(phi), cy + outer * math.sin(phi))
            if k == 0:
                lift_and_go(b, ring, heights)
            else:
                # Out along the level just cleared to the outer ring.
                b.feed(x=ring[0], y=ring[1], f=feeds.feed_mm_min)
            if in_air(ctx, ring, z):
                down_in_air(b, heights, z, f=feeds.plunge_mm_min)
                counts["air"] += 1
            else:
                b.feed(z=z_prev, f=feeds.ramp_mm_min)
                sweep = sense * (z_prev - z) / (outer * slope)
                helix_arcs(b, (cx, cy), outer, phi, sweep, z, f=max(1.0, round(feeds.ramp_mm_min)))
                phi = math.fmod(phi + sweep, 2 * math.pi)
                counts["helix"] += 1
            helix_arcs(b, (cx, cy), outer, phi, sense * 2 * math.pi, z, f=f)
            _spiral(b, (cx, cy), outer, final, phi, sense, z, halves=halves, feed=lambda rho: f)
            helix_arcs(b, (cx, cy), final, phi, sense * 2 * math.pi, z, f=f)
            z_prev = z
        return len(cut_levels) * halves / 2.0, outer + r - wall


def _halves(span: float, stepover: float) -> int:
    """How many half turns a spiral takes across ``span`` (mm, radial) so no turn grows more than ``stepover``: an
    even number, so it ends on the line it starts on."""
    if abs(span) <= 1e-6:
        return 0
    return 2 * max(1, int(math.ceil(abs(span) / stepover - 1e-9)))


def _spiral(b, centre, r_from: float, r_to: float, phi: float, sense: float, z: float, *, halves: int, feed) -> None:
    """From the tool on the circle of ``r_from`` about ``centre`` at angle ``phi`` (radians), at ``z``: ``halves``
    tangent half circles (``sense`` +1 counter-clockwise) whose radius changes evenly to ``r_to``, each about the
    midpoint of its ends on the line through ``centre`` at ``phi``: true arcs, ending at angle ``phi`` on ``r_to``.
    ``feed(rho)`` is the feed of a half circle about ``rho`` from the centre on average."""
    if not halves:
        return
    cx, cy = float(centre[0]), float(centre[1])
    ux, uy = math.cos(phi), math.sin(phi)
    grow = (r_to - r_from) / halves
    for k in range(halves):
        a0, a1 = r_from + k * grow, r_from + (k + 1) * grow
        side = 1.0 if k % 2 == 0 else -1.0
        sx, sy = cx + side * a0 * ux, cy + side * a0 * uy
        ex, ey = cx - side * a1 * ux, cy - side * a1 * uy
        b.arc(ex, ey, z, centre=((sx + ex) / 2.0, (sy + ey) / 2.0, 0.0), clockwise=sense < 0, f=feed((a0 + a1) / 2.0))
