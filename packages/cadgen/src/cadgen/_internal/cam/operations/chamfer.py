"""``chamfer`` (Chamfer): break the top edges of a face's loops with a vee or chamfer tool, at a chamfer width.

What it follows: ``faces``: a flat face facing the tool names every edge of its outline and its holes (``loops``:
``all``, the default, ``outer`` or ``inner``), the air side of each (outside the outline, inside a hole); a wall (a
plane square to XY, a cylinder or cone along Z) names the top edge of the loop it stands on. Or a ``region``:
``{"polygon": [[x, y], ...], "bottom_z": z}`` whose outline is an edge at height ``bottom_z`` with the material
inside it.

``width_mm`` (required) is the chamfer's leg across the top face. The depth comes from the tool's angle: a cone of
half angle a cuts a chamfer ``width / tan(a)`` deep (a 90° vee: 45°, as deep as it is wide). ``tip_offset_mm``
(default 0.2 for a sharp tip, 0 for a tip with a flat) puts the tool's tip that much lower, so the cut is made by
the cone, not the point: the tool's centre then runs ``tip radius + tip offset x tan(a)`` off the edge on the air
side. The tool must be wide enough for the chamfer: a cone ``diameter_mm`` across holds a chamfer up to its radius
less that offset; a wider one is refused. One pass per loop, climb by default (``direction``), entered by ramping
down along the loop from the edge's height at ``ramp_angle_deg`` (default 3), never a plunge onto the edge.

Refused, as plan errors on the operation: a chamfer on the part's top edges while stock still stands over the part's
top (``unreachable``: face it first, with a ``face`` earlier in the program, or a stock with no top allowance); the
tip under the chamfer touching the part (``gouge``: a step or a feature close under the edge; lower
``tip_offset_mm``); the tool's body over the chamfer hitting the part above a lower edge (``tool_too_large``).

The part as modelled has sharp edges there, so the chamfer cuts into it by design: the ``gouge`` check does not
judge this operation; the chamfer's width and depth are in its facts.
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, PlanError, choice, read_number
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation, region_polygon

__all__ = ["ChamferOp"]


class ChamferOp(Operation):
    name = "chamfer"
    plain = "Chamfer"
    family = "2.5D milling"
    machines = MILLS
    status = "full"
    keys = ("width_mm", "tip_offset_mm", "loops", "direction", "ramp_angle_deg")
    common_keys = ("feed", "speed")
    tool_types = ("vee", "chamfer", "engraver", "spot")
    takes_faces = True
    takes_region = True
    feeds_kind = "finish"

    def parse(self, spec, ctx):
        super().parse(spec, ctx)
        if not spec.faces and spec.region is None:
            raise CamJobError(f"{spec.where}: a chamfer needs the faces whose edges it breaks (\"faces\": [\"#o1.f3\"]) "
                              "or a \"region\" ({\"polygon\": [[x, y], ...], \"bottom_z\": z})")
        if spec.faces and spec.region is not None:
            raise CamJobError(f"{spec.where}: give a chamfer faces or a region, not both")
        extra = spec.extra
        if "width_mm" not in extra:
            raise CamJobError(f"{spec.where}: a chamfer needs \"width_mm\", the chamfer's width across the top face")
        tool = ctx.job.tool(spec.tool)
        params = {
            "width_mm": read_number(extra, "width_mm", spec.where),
            "tip_offset_mm": read_number(extra, "tip_offset_mm", spec.where,
                                         default=0.2 if tool.tip_diameter_mm <= 0 else 0.0, minimum=0.0),
            "loops": choice(extra.get("loops", "all"), ("all", "outer", "inner"), f"{spec.where}.loops"),
            "climb": choice(extra.get("direction", "climb"), ("climb", "conventional"), f"{spec.where}.direction")
            == "climb",
            "ramp_angle_deg": read_number(extra, "ramp_angle_deg", spec.where, default=3.0, maximum=45.0),
            "region": None,
        }
        half = math.radians((tool.angle_deg or 90.0) / 2.0)
        need = tool.tip_diameter_mm / 2.0 + params["tip_offset_mm"] * math.tan(half) + params["width_mm"]
        if need > tool.radius + 1e-9:
            most = tool.radius - tool.tip_diameter_mm / 2.0 - params["tip_offset_mm"] * math.tan(half)
            raise CamJobError(f"{spec.where}: {tool.id} ({tool.plain}, {tool.diameter_mm:g} mm across) chamfers at most "
                              f"{max(0.0, most):.3g} mm wide with a tip offset of {params['tip_offset_mm']:g} mm; use a "
                              "bigger tool or a narrower width_mm")
        if spec.region is not None:
            params["region"] = region_polygon(spec, where=spec.where)
            if params["region"][1] is None:
                raise CamJobError(f"{spec.where}.region needs \"bottom_z\", the height of the edge to chamfer")
        return params

    def plan(self, ctx, params):
        import numpy as np

        from cadgen._internal.cam import geom2d, linking
        from cadgen._internal.cam.operations._milling2d import Target, face_targets, lift_and_go, orient, rotate_to_nearest

        tool = ctx.tool
        tol = ctx.tolerance_mm
        heights = ctx.heights
        half = math.radians((tool.angle_deg or 90.0) / 2.0)
        width = params["width_mm"]
        tip = params["tip_offset_mm"]
        depth = width / math.tan(half)
        offset = tool.tip_diameter_mm / 2.0 + tip * math.tan(half)
        if params["region"] is not None:
            polygon, z = params["region"]
            targets = [Target(polygon=polygon, side="outside", z=z, kind="region")]
        else:
            targets = face_targets(ctx, ctx.spec.faces, where=f"{ctx.spec.where}.faces")
        rings = []
        seen = set()
        for target in targets:
            edge = target.top_z if target.kind == "wall" else target.z
            if target.kind == "under":
                raise CamJobError(f"{ctx.spec.where}.faces: {target.ref} faces away from the tool in setup "
                                  f"'{ctx.setup.id}'; chamfer its edges from a setup that faces it")
            if edge >= heights.part_top - tol:
                _faced(ctx, target.ref or "the region")
            key = (round(target.polygon.area, 3), round(target.polygon.centroid.x, 3),
                   round(target.polygon.centroid.y, 3), round(edge, 4))
            if key in seen:
                continue
            seen.add(key)
            # The tool runs on the air side: outside a face's outline, inside its holes (a wall: its own air side).
            distance = offset if target.side == "outside" else -offset
            shape = geom2d.offset(target.polygon, distance, tolerance=tol) if offset > 0 else target.polygon
            material_outer = target.side == "outside"
            found = []
            for piece in geom2d.polygons_of(shape):
                if params["loops"] in ("all", "outer") or target.kind == "wall":
                    found.append((np.asarray(piece.exterior.coords)[:, :2], material_outer, edge))
                if params["loops"] in ("all", "inner") and target.kind != "wall":
                    found.extend((np.asarray(ring.coords)[:, :2], not material_outer, edge) for ring in piece.interiors)
            _clear_of_part(ctx, [row[0] for row in found], target.ref or "the region", edge, edge - depth - tip,
                           depth, half)
            rings.extend(found)
        if not rings:
            raise PlanError("tool_too_large", f"{ctx.spec.where}: no edge to chamfer: every loop is smaller than "
                            f"{tool.id}'s tip offset from it; use a smaller tip_offset_mm or a finer tool")
        feeds = ctx.feeds(self.feeds_kind)
        b = ctx.builder()
        lowest = None
        entries = {"ramp": 0, "plunge": 0}
        ordered = linking.order_nearest(rings, b.pos, key=lambda row: tuple(row[0][0]))
        for ring, material_inside, edge in ordered:
            ring = orient(ring, material_inside=material_inside, climb=params["climb"])
            ring = rotate_to_nearest(ring, b.pos)
            z = edge - depth - tip
            if z >= heights.stock_top:
                continue
            lowest = z if lowest is None else min(lowest, z)
            lift_and_go(b, ring[0], heights)
            b.feed(z=min(heights.retract, edge + 1.0), f=feeds.feed_mm_min)
            # From the edge's height the tool is clear of the part; it ramps down along the loop into the edge.
            if linking.ramp(b, ring, edge, z, angle_deg=params["ramp_angle_deg"], f=feeds.ramp_mm_min):
                entries["ramp"] += 1
            else:
                b.feed(z=edge, f=feeds.plunge_mm_min)
                b.plunge(z=z, f=feeds.plunge_mm_min)
                entries["plunge"] += 1
            b.polyline(np.column_stack([ring[1:], np.full(len(ring) - 1, z)]), f=feeds.feed_mm_min)
            b.rapid(z=heights.retract)
        b.rapid(z=heights.clearance)
        if entries["plunge"]:
            ctx.meta["plunges"] = entries["plunge"]
        ctx.meta.update({"loops": len(rings), "width_mm": width, "depth_mm": round(depth, 4),
                         "entries": {key: value for key, value in entries.items() if value and key != "plunge"},
                         "tip_z": round(lowest, 4) if lowest is not None else None, "no_gouge_check": True,
                         "note_level": "info",
                         "note": f"chamfers {width:g} mm wide and {depth:.3g} mm deep into the modelled sharp edges "
                                 "(not judged by the gouge check)"})
        return b.build()


def _faced(ctx, what: str) -> None:
    """Refuse a chamfer on the part's top edge while stock still stands over the part's top: it starts from a cut
    surface. Faced when the stock top is the part's top, or an earlier ``face`` of the whole stock in this setup took
    it down to the part's top (its ``faced_z``)."""
    heights = ctx.heights
    tol = ctx.tolerance_mm
    if heights.stock_top <= heights.part_top + tol:
        return
    faced = [op.meta["faced_z"] for _, path in ctx.history for op in path.ops
             if op.setup == ctx.setup.id and op.op == "face" and op.meta.get("faced_z") is not None]
    if faced and min(faced) <= heights.part_top + tol:
        return
    raise PlanError("unreachable", f"{ctx.spec.where}: the chamfer on {what} starts from the part's top at Z "
                    f"{heights.part_top:.3f}, and the stock still stands {heights.stock_top - heights.part_top:.3g} mm "
                    "over it; face the stock first (a face of the whole stock before this operation, in the same "
                    "setup)")


def _clear_of_part(ctx, rings, what: str, edge: float, tip_z: float, depth: float, half: float) -> None:
    """Refuse a chamfer whose tool would touch the part away from the edge it breaks: under the chamfer the cone is
    narrower than its distance to the wall, so the tip and the cone's lower end must stay off the part there
    (``gouge``); over a lower edge, the tool's body (its cone widening to its diameter) must stay off the part standing
    above the edge (``tool_too_large``)."""
    import shapely

    tool = ctx.tool
    tol = ctx.tolerance_mm
    heights = ctx.heights
    tip_r = tool.tip_diameter_mm / 2.0
    lines = [shapely.LineString(ring) for ring in rings if len(ring) >= 2]
    if not lines:
        return
    path = shapely.union_all(lines)
    below = edge - depth
    for h in (tip_z + 1e-3, 0.5 * (tip_z + below), below - 1e-3):
        if h <= tip_z or h >= below:
            continue
        material = ctx.sections.at(h)
        cone = tip_r + (h - tip_z) * math.tan(half)
        if not material.is_empty and material.distance(path) < cone - tol:
            raise PlanError("gouge", f"{ctx.spec.where}: the tip {edge - depth - tip_z:g} mm under the chamfer on "
                            f"{what} would touch the part at Z {h:.3f}; lower tip_offset_mm or cut this edge another "
                            "way")
    if edge < heights.part_top - tol:
        widest = min(tool.radius, tip_r + (heights.part_top - tip_z) * math.tan(half))
        steps = max(2, int(math.ceil((heights.part_top - edge) / 1.0)))
        above = shapely.union_all([ctx.sections.at(edge + (heights.part_top - edge) * (k + 0.5) / steps)
                                   for k in range(steps)])
        if not above.is_empty:
            gap = above.distance(path)
            if gap < widest - tol:
                raise PlanError("tool_too_large", f"{ctx.spec.where}: {tool.id}'s body over the chamfer on {what} "
                                f"({2 * widest:.3g} mm across there) hits the part standing above the edge, "
                                f"{gap:.3g} mm away; use a smaller tool")
