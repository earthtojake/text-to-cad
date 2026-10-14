"""``trace`` (Trace): follow a chain of the part's edges at a depth, the tool's centre on them or offset to one side.

What it follows: ``edges``, the part's edges as the Viewer selects them (``["#o1.e5", "#o1.e6"]``), joined end to
end into chains (:func:`~cadgen._internal.cam.operations._edges.chains`), open or closed, each level in the setup's
XY plane (a chain that climbs is refused, ``unreachable``). ``depth_mm`` (required) is how far below its edges a
chain is cut.

``offset`` says where the tool's centre runs: ``on`` (the default) on the edges; ``inside`` or ``outside`` a closed
loop; ``left`` or ``right`` of an open chain, looking along its direction of travel. The wrong pairing (``left`` on a
loop, ``inside`` on an open chain) is refused. An offset moves the centre the tool's cutting radius at the depth
(:meth:`~cadgen._internal.cam.tools.Tool.radius_at`: a flat's radius, a vee's radius ``depth_mm`` above its tip), so
the tool's edge runs on the edges at their height. An open chain with ``left`` or ``right`` must say where it starts:
``start``, a point ``[x, y]`` (WCS) at one of its ends, or its first or last edge (an edge selector); an edge in the
middle of the chain is refused as not an end. A chain with no ``start`` is cut from its end nearer the tool.

How: levels from the top of the material over the chain (the stock top when the edges lie on the part's top, else
the edges' own height) down to the depth, none deeper than ``stepdown_mm`` (the material's default). Each level is
entered by a ramp zig-zagging along the path itself at ``ramp_angle_deg`` (default 3), or straight down where the
tool is off the stock (:func:`~cadgen._internal.cam.operations._milling2d.in_air`); a path too short to ramp along
is plunged (counted in ``plunges``). A loop is cut round from where its last level ended; an open chain offset to a
side is cut from its start at every level (the same way along it each time), one on its edges back and forth.

Refused (``unreachable``) when the part stands over the path within the tool's reach at any height above the edges:
the tool cannot come down to it from this setup. A loop an inside offset closes up, or an open chain whose offset
folds over itself, is ``tool_too_large``. With ``offset: on`` the tool cuts into the part on purpose (a groove along
the edges), so the gouge check does not judge it; with an offset it does (an offset into the part is a gouge).
"""

from __future__ import annotations

import math

from cadgen._internal.cam.job_errors import CamJobError, PlanError, choice, is_number, read_number, shown
from cadgen._internal.cam.operations import MILLS
from cadgen._internal.cam.operations.base import Operation

__all__ = ["TraceOp"]

#: Where the tool's centre runs: on the edges, inside or outside a loop, left or right of an open chain.
OFFSETS = ("on", "inside", "outside", "left", "right")
#: A ``start`` point within this of a chain's end (mm) names that end.
START_MM = 0.01


class TraceOp(Operation):
    name = "trace"
    plain = "Trace"
    family = "2.5D milling"
    machines = MILLS
    status = "full"
    keys = ("edges", "depth_mm", "offset", "start", "ramp_angle_deg")
    common_keys = ("feed", "speed", "stepdown_mm")
    tool_types = ("flat", "bull", "ball", "vee", "chamfer", "engraver")
    feeds_kind = "slot"

    def parse(self, spec, ctx):
        from cadgen._internal.cam.operations._edges import EDGE_REF, edge_refs

        super().parse(spec, ctx)
        extra = spec.extra
        where = spec.where
        if "edges" not in extra:
            raise CamJobError(f"{where}: a trace needs \"edges\", the part's edges it follows (\"edges\": "
                              "[\"#o1.e5\", \"#o1.e6\"], selected in the Viewer)")
        if "depth_mm" not in extra:
            raise CamJobError(f"{where}: a trace needs \"depth_mm\", how far below its edges it cuts (like 0.5)")
        start = extra.get("start")
        if start is not None:
            if isinstance(start, str):
                if not EDGE_REF.match(start):
                    raise CamJobError(f"{where}.start must be a point [x, y] (WCS) at one end of an open chain, or "
                                      f"its first or last edge (\"#o1.e5\"), not {shown(start)}")
            elif (isinstance(start, (list, tuple)) and len(start) == 2 and all(is_number(v) for v in start)):
                start = (float(start[0]), float(start[1]))
            else:
                raise CamJobError(f"{where}.start must be a point [x, y] (WCS) at one end of an open chain, or its "
                                  f"first or last edge (\"#o1.e5\"), not {shown(start)}")
        return {
            "edges": edge_refs(extra["edges"], f"{where}.edges"),
            "depth_mm": read_number(extra, "depth_mm", where),
            "offset": choice(extra.get("offset", "on"), OFFSETS, f"{where}.offset"),
            "start": start,
            "ramp_angle_deg": read_number(extra, "ramp_angle_deg", where, default=3.0, maximum=45.0),
        }

    def _paths(self, ctx, params):
        """``[(chain, path (N, 2), fixed)]``: each chain's tool-centre path, ``fixed`` when ``start`` set its
        direction."""
        import numpy as np

        from cadgen._internal.cam.operations._edges import chains, resolve_edge

        where = ctx.spec.where
        offset = params["offset"]
        start = params["start"]
        if isinstance(start, str):
            start = resolve_edge(ctx, start, f"{where}.start").ref
        found = chains(ctx, params["edges"], f"{where}.edges")
        if isinstance(start, str) and not any(start in chain.refs for chain in found):
            raise CamJobError(f"{where}.start: {params['start']} is not one of the edges traced; name the first or "
                              "last edge of an open chain in \"edges\", or a point at one of its ends")
        reach = ctx.tool.radius_at(params["depth_mm"]) if offset != "on" else 0.0
        out = []
        used = False
        for chain in found:
            if chain.closed and offset in ("left", "right"):
                raise CamJobError(f"{where}.offset: {chain.name} is a closed loop; offset it inside or outside, or on, "
                                  f"not {offset}")
            if not chain.closed and offset in ("inside", "outside"):
                raise CamJobError(f"{where}.offset: {chain.name} is an open chain of edges with no inside; offset it "
                                  f"left or right of its direction (with \"start\"), or on, not {offset}")
            xy = np.asarray(chain.points[:, :2], dtype=float)
            fixed = False
            if not chain.closed:
                flip = _walk_from(start, chain, f"{where}.start", params["start"])
                if flip is None and offset in ("left", "right"):
                    if start is not None:
                        raise CamJobError(f"{where}.start: {_start_words(params['start'])} is not an end of the open "
                                          f"chain {chain.name}; give a point [x, y] at one of its ends, or its first "
                                          f"({chain.refs[0]}) or last ({chain.refs[-1]}) edge")
                    raise CamJobError(f"{where}.start: {chain.name} is an open chain of edges, so {offset} needs its "
                                      "direction: say where it starts with \"start\", a point [x, y] at one of its ends "
                                      f"or its first or last edge ({chain.refs[0]} or {chain.refs[-1]})")
                if flip is not None:
                    used = fixed = True
                    if flip:
                        xy = xy[::-1].copy()
            out.append((chain, self._offset(ctx, chain, xy, offset, reach), fixed))
        if start is not None and not used:
            raise CamJobError(f"{where}.start: {_start_words(params['start'])} is not an end of an open chain of the "
                              "edges traced (a closed loop has no start)")
        return out, reach

    def _offset(self, ctx, chain, xy, offset: str, reach: float):
        """The tool-centre path of a chain: ``xy`` itself (``on``), or moved ``reach`` to its side, round at its
        corners; a loop is oriented for climb with the material beyond the edges (clockwise round an outside offset,
        counter-clockwise inside)."""
        import numpy as np
        import shapely

        from cadgen._internal.cam import geom2d
        from cadgen._internal.cam.operations._milling2d import orient

        where = ctx.spec.where
        tol = ctx.tolerance_mm / 2.0
        if offset == "on" or reach <= 1e-9:
            return xy
        if chain.closed:
            loop = shapely.Polygon(xy)
            if not loop.is_valid or loop.area <= 1e-9:
                raise CamJobError(f"{where}.edges: the loop {chain.name} crosses itself; trace it on, or name a loop "
                                  "that does not")
            moved = geom2d.polygons_of(geom2d.offset(loop, reach if offset == "outside" else -reach, tolerance=tol))
            if len(moved) != 1:
                what = "closes up" if not moved else "splits in pieces"
                raise PlanError("tool_too_large", f"{where}: {ctx.tool.id} ({ctx.tool.plain}) {reach:.4g} mm "
                                f"{offset} {chain.name} {what}: the tool is too large for the loop; use a smaller tool")
            ring = np.asarray(moved[0].exterior.coords)[:, :2]
            return orient(ring, material_inside=offset == "outside", climb=True)
        line = shapely.LineString(xy)
        moved = line.offset_curve(reach if offset == "left" else -reach, quad_segs=geom2d.quad_segs(reach, tol),
                                  join_style="round")
        if moved.is_empty or moved.geom_type != "LineString":
            raise PlanError("tool_too_large", f"{where}: {ctx.tool.id} ({ctx.tool.plain}) {reach:.4g} mm to the "
                            f"{offset} of {chain.name} folds over itself: the tool is too large for its bends; use a "
                            "smaller tool")
        path = np.asarray(moved.coords)[:, :2]
        # Shapely keeps a line's direction on either side; the ends line up with the chain's own.
        if math.dist(path[0], xy[0]) > math.dist(path[-1], xy[0]):
            path = path[::-1].copy()
        return path

    def _overhead(self, ctx, chain, path, floor: float) -> None:
        """Refuse a path the part stands over, anywhere above its edges, within the tool's reach there."""
        import shapely

        from cadgen._internal.cam.operations._edges import material_heights

        tool = ctx.tool
        line = shapely.LineString(path)
        for h in material_heights(ctx, chain.z, ctx.heights.part_top):
            radius = tool.radius_at(h - floor) - 0.05
            if radius <= 0:
                continue
            over = line.buffer(radius).intersection(ctx.sections.at(h))
            if over.area > 1e-2:
                raise PlanError("unreachable", f"{ctx.spec.where}: the part stands over {chain.name} at Z {h:.3f}, "
                                f"within {tool.id}'s reach of the path, so the tool cannot come down to it from setup "
                                f"'{ctx.setup.id}'; trace it from a setup that sees it, or offset it away from the part "
                                "over it")

    def plan(self, ctx, params):
        import numpy as np

        from cadgen._internal.cam.operations._milling2d import (
            down_in_air, in_air, levels, lift_and_go, ramp_along, rotate_to_nearest,
        )

        heights = ctx.heights
        offset = params["offset"]
        angle = params["ramp_angle_deg"]
        paths, reach = self._paths(ctx, params)
        stepdown = ctx.stepdown()
        feeds = ctx.feeds("engrave" if ctx.tool.type in ("vee", "chamfer", "engraver") else self.feeds_kind)
        jobs = []
        for chain, path, fixed in paths:
            floor = chain.z - params["depth_mm"]
            self._overhead(ctx, chain, path, floor)
            z_top = heights.stock_top if chain.z >= heights.part_top - 1e-6 else chain.z
            jobs.append((chain, path, fixed, levels(z_top, floor, stepdown), z_top))
        b = ctx.builder()
        counts = {"ramp": 0, "air": 0, "plunge": 0}
        total = 0.0
        remaining = list(jobs)

        def descend(path, z_from: float, z: float) -> None:
            if in_air(ctx, path[0], z):
                down_in_air(b, heights, z, f=feeds.plunge_mm_min)
                counts["air"] += 1
                return
            b.feed(z=z_from, f=feeds.ramp_mm_min)
            if ramp_along(b, path, z_from, z, angle_deg=angle, f=feeds.ramp_mm_min):
                counts["ramp"] += 1
            else:
                b.plunge(z=z, f=feeds.plunge_mm_min)
                counts["plunge"] += 1

        while remaining:
            here = b.pos[:2]
            pick = min(range(len(remaining)), key=lambda k: min(
                math.dist(here, remaining[k][1][0]), math.dist(here, remaining[k][1][-1])))
            chain, path, fixed, cut_levels, z_top = remaining.pop(pick)
            if chain.closed:
                path = rotate_to_nearest(path, here)
            elif not fixed and math.dist(here, path[-1]) < math.dist(here, path[0]):
                path = path[::-1].copy()
            total += float(np.hypot(*np.diff(path, axis=0).T).sum())
            z_prev = z_top
            for k, z in enumerate(cut_levels):
                if k == 0:
                    lift_and_go(b, path[0], heights)
                elif not chain.closed and offset in ("left", "right"):
                    # The same way along the chain every level: back to its start over the cut just made.
                    b.rapid(z=heights.retract)
                    b.rapid(x=float(path[0][0]), y=float(path[0][1]))
                    if z_prev + 1.0 < heights.retract:
                        b.rapid(z=z_prev + 1.0)
                elif not chain.closed:
                    path = path[::-1].copy()
                descend(path, z_prev, z)
                b.polyline(np.column_stack([path[1:], np.full(len(path) - 1, z)]), f=feeds.feed_mm_min)
                z_prev = z
            b.rapid(z=heights.retract)
        b.rapid(z=heights.clearance)
        ctx.meta.update({"passes": len(jobs), "levels": max(len(job[3]) for job in jobs),
                         "entries": {k: v for k, v in counts.items() if v and k != "plunge"},
                         "length_mm": round(total, 3), "bottom_z": round(min(job[3][-1] for job in jobs), 4),
                         "offset": offset,
                         "offset_mm": round(reach, 4)})
        if counts["plunge"]:
            ctx.meta["plunges"] = counts["plunge"]
        if offset == "on":
            ctx.meta.update({"no_gouge_check": True, "note_level": "info",
                             "note": f"traces {len(jobs)} chain(s) of edges {params['depth_mm']:g} mm deep with the "
                                     "tool's centre on them, into the modelled part (not judged by the gouge check)"})
        return b.build()

    def summary(self, ctx, params):
        edges = params["edges"]
        what = " " + ", ".join(edges) if len(edges) <= 3 else f" {len(edges)} edges"
        name = f" ({ctx.spec.name})" if ctx.spec.name else ""
        return f"{self.plain}{name}{what} with {ctx.tool.id} {ctx.tool.plain}"


def _walk_from(start, chain, where: str, given) -> bool | None:
    """Whether an open ``chain`` runs backwards from where ``start`` (a canonical edge ref or a WCS point) says it
    starts; None when ``start`` is not given or names neither end. An edge in the chain's middle is refused."""
    if start is None:
        return None
    if isinstance(start, str):
        if start == chain.refs[0]:
            return False
        if start == chain.refs[-1]:
            return True
        if start in chain.refs:
            raise CamJobError(f"{where}: {given} is not an end of the chain {chain.name}; start it at its first edge "
                              f"({chain.refs[0]}) or its last ({chain.refs[-1]}), or a point at one of its ends")
        return None
    if math.dist(start, chain.points[0, :2]) <= START_MM:
        return False
    if math.dist(start, chain.points[-1, :2]) <= START_MM:
        return True
    return None


def _start_words(start) -> str:
    return f"[{start[0]:g}, {start[1]:g}]" if isinstance(start, tuple) else str(start)
