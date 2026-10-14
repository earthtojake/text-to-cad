"""What the 2.5D milling operations share (contour, adaptive, slot, chamfer, engrave, helix_bore, thread_mill).

Not an operation (no registry entry): the loops a face names, ring orientation for climb or conventional, even
cut levels, the clearing region of a pocket-like op at a height, holes and bosses read off the part in a setup's
WCS, safe links between cuts, and helical arcs.

* :func:`face_targets` turns ``faces`` into :class:`Target` rows. A flat face square to the tool (facing +Z or -Z in
  the setup) names its own outline: the loops of its footprint. A wall (a plane square to XY, or a cylinder or cone
  along Z) names the whole loop of the part's section it lies on, at its mid height, and which side of that loop is
  air.
* :func:`orient` orients a closed ring so the material is on the right of travel for climb milling (a clockwise
  spindle), on the left for conventional: material inside the ring runs clockwise for climb.
* :func:`levels` splits a depth into even steps no deeper than the step down, the last exactly at the bottom.
* :func:`hole_targets` reads holes (hole-wall cylinders grouped by :func:`features.holes`) and bosses (outside
  cylinders) along the setup's Z, in WCS; a counterbore's wall names the counterbore (its diameter, down to its
  shoulder), any other face of the hole the hole under it.
* :func:`link` joins two cuts at one level: a straight feed when the way is clear, else up, over and down.
* :func:`in_air` says whether the tool may come straight down at a point: off the stock's footprint and clear of the
  setup's fixture boxes (:func:`fixture_keepouts`, :func:`fixtures_clear`), so no op plans a plunge onto a vise jaw.
* :func:`helix_arcs` emits a helix as arcs (at most a half turn each) so posts write G2/G3 with Z.

Stdlib at import; numpy and shapely inside.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from cadgen._internal.cam.job_errors import CamJobError, level_count

__all__ = ["HoleTarget", "Target", "face_targets", "fixture_keepouts", "fixtures_clear", "helix_arcs", "hole_targets",
           "down_in_air", "in_air", "levels", "link", "orient", "unreachable_in"]

#: A wall is within this of square to XY (|normal z|), or a cylinder's axis within this of Z (1 - |axis z|).
_SQUARE = 1e-3


@dataclass
class Target:
    """A region an operation follows: ``polygon`` (WCS XY) and which side of it the tool runs."""

    polygon: object               # shapely Polygon
    side: str                     # "outside" | "inside" | "on"
    ref: str = ""
    #: The face's height (a flat face), or a wall's top and bottom (WCS).
    z: float | None = None
    top_z: float | None = None
    bottom_z: float | None = None
    kind: str = "flat"            # "flat" (facing +Z), "under" (facing -Z), "wall", "region"
    #: A flat face below the part's top, facing the tool (a pocket's or a step's floor).
    floor: bool = False
    extra: dict = field(default_factory=dict)


def levels(top: float, bottom: float, stepdown: float) -> list[float]:
    """Cut levels from just below ``top`` down to exactly ``bottom``: evenly split, none deeper than ``stepdown``."""
    if stepdown <= 0:
        raise CamJobError("stepdown_mm must be more than 0")
    if top - bottom <= 1e-9:
        return [float(bottom)]
    count = level_count(top, bottom, stepdown)
    return [float(top - (top - bottom) * (k + 1) / count) for k in range(count)]


def signed_area(ring) -> float:
    import numpy as np

    ring = np.asarray(ring, dtype=float)
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.dot(x[:-1], y[1:]) - np.dot(x[1:], y[:-1]))


def orient(ring, *, material_inside: bool, climb: bool):
    """``ring`` ((N, 2) or (N, 3), closed) turned so climb keeps the material on the right of travel (clockwise round
    material inside the ring, counter-clockwise round a hole's wall), conventional the other way."""
    import numpy as np

    ring = np.asarray(ring, dtype=float)
    clockwise_wanted = material_inside == climb
    is_clockwise = signed_area(ring) < 0
    return ring if clockwise_wanted == is_clockwise else ring[::-1].copy()


def rotate_to_nearest(ring, position):
    """A closed ring re-started at its vertex nearest ``position`` (x, y)."""
    import numpy as np

    ring = np.asarray(ring, dtype=float)
    body = ring[:-1]
    k = int(np.argmin(np.hypot(body[:, 0] - position[0], body[:, 1] - position[1])))
    turned = np.vstack([body[k:], body[:k]])
    return np.vstack([turned, turned[:1]])


def _face_points(ctx, ref):
    """The WCS vertices of a face's triangles."""
    import numpy as np

    vertices, _ = ctx.mesh
    triangles = ctx.face_triangles(ref)
    return np.asarray(vertices)[np.unique(triangles)]


def face_targets(ctx, refs, *, where: str, flat_only: bool = False, walls_only: bool = False) -> list[Target]:
    """One :class:`Target` per loop source a face names (see the module docstring); teaching errors for faces an
    operation cannot follow."""
    import numpy as np
    import shapely

    from cadgen._internal.cam import geom2d

    out: list[Target] = []
    part_top = ctx.heights.part_top
    for ref in refs:
        info = ctx.face(ref)
        points = _face_points(ctx, ref)
        if not len(points):
            raise CamJobError(f"{where}: {ref} has no tessellation to follow")
        normal = None if info.normal is None else ctx.wcs.vectors_to_wcs([info.normal])[0]
        axis = None if info.axis is None else ctx.wcs.vectors_to_wcs([info.axis])[0]
        flat = info.surface == "plane" and normal is not None and abs(abs(normal[2]) - 1.0) < 1e-6
        wall = (info.surface == "plane" and normal is not None and abs(normal[2]) < _SQUARE) or (
            info.surface in ("cylinder", "cone") and axis is not None and abs(abs(axis[2]) - 1.0) < _SQUARE)
        if flat and not walls_only:
            z = float(points[:, 2].mean())
            footprint = ctx.footprint(ctx.face_triangles(ref))
            up = normal[2] > 0
            for polygon in geom2d.polygons_of(footprint):
                out.append(Target(polygon=polygon, side="outside", ref=info.ref, z=z, top_z=z, bottom_z=z,
                                  kind="flat" if up else "under", floor=up and z < part_top - 1e-3))
            continue
        if wall and not flat_only:
            low, high = float(points[:, 2].min()), float(points[:, 2].max())
            mid = 0.5 * (low + high)
            section = ctx.sections.at(mid)
            best = None
            xy = shapely.points(points[:, :2])
            for polygon in geom2d.polygons_of(section):
                for ring, hole in [(polygon.exterior, False)] + [(r, True) for r in polygon.interiors]:
                    line = shapely.LineString(ring.coords)
                    distance = float(np.mean(shapely.distance(xy, line)))
                    if best is None or distance < best[0]:
                        best = (distance, ring, hole)
            tolerance = max(0.05, 5.0 * float(getattr(ctx.part, "deflection_mm", 0.01)))
            if best is None or best[0] > tolerance:
                raise CamJobError(f"{where}: {ref} is a wall, but no loop of the part's section at Z {mid:.3f} runs "
                                  "along it; name the flat face it bounds, or give a region")
            _, ring, hole = best
            polygon = shapely.Polygon(ring.coords)
            # A hole's wall: the air is inside its loop; an outline's wall: the air is outside.
            out.append(Target(polygon=polygon, side="inside" if hole else "outside", ref=info.ref, z=high,
                              top_z=high, bottom_z=low, kind="wall"))
            continue
        facing = "" if normal is None else f" facing ({', '.join(f'{v:.2f}' for v in normal)})"
        if flat_only:
            raise CamJobError(f"{where}: {ref} is a {info.surface}{facing} in setup '{ctx.setup.id}'; a "
                              f"{ctx.spec.op} names flat faces square to the tool (facing +Z or -Z)")
        if walls_only:
            raise CamJobError(f"{where}: {ref} is a {info.surface}{facing} in setup '{ctx.setup.id}'; a "
                              f"{ctx.spec.op} names walls standing square to the tool")
        raise CamJobError(f"{where}: {ref} is a {info.surface}{facing} in setup '{ctx.setup.id}'; a {ctx.spec.op} "
                          "names flat faces square to the tool or walls standing along it (planes square to XY, "
                          "cylinders along Z)")
    return out


def unreachable_in(region, radius: float, z: float, tolerance: float, into: list) -> None:
    """Add what a tool of ``radius`` cannot reach inside ``region`` (where material is removed) to ``into``, once
    per spot (the same corner at every level is one corner): the ``corner_radius`` check's ``meta["unreachable"]``."""
    from cadgen._internal.cam import geom2d

    if region is None or region.is_empty:
        return
    area = geom2d.offset(region, -radius, tolerance=tolerance)
    reached = geom2d.offset(area, radius, tolerance=tolerance) if not area.is_empty else area
    missed = region.difference(reached) if not reached.is_empty else region
    for piece in geom2d.polygons_of(missed.buffer(-1e-4).buffer(1e-4)):
        if piece.area > 1e-3:
            c = piece.representative_point()
            same = next((u for u in into if math.hypot(u["at"][0] - c.x, u["at"][1] - c.y) < 0.5), None)
            if same is None:
                into.append({"area_mm2": float(piece.area), "at": [c.x, c.y, z], "z": z})
            elif piece.area > same["area_mm2"]:
                same.update(area_mm2=float(piece.area), at=[c.x, c.y, z], z=z)


@dataclass
class HoleTarget:
    """A round feature along the setup's Z, WCS: a hole (material outside) or a boss (material inside)."""

    ref: str
    centre: tuple[float, float]
    diameter_mm: float
    top_z: float                  # the opening (a hole) or the boss's top
    bottom_z: float               # a hole's bottom, a boss's foot
    hole: bool
    through: bool = False


def hole_targets(ctx, refs, *, where: str, holes_ok: bool = True, bosses_ok: bool = False) -> list[HoleTarget]:
    """The holes (and, when ``bosses_ok``, the bosses) the faces name, one per hole however many of its faces are
    named, in WCS; a hole must open toward the tool (+Z of the setup)."""
    import numpy as np

    from cadgen._internal.cam.features import holes

    groups = None
    out: list[HoleTarget] = []
    seen: set = set()
    for ref in refs:
        info = ctx.face(ref)
        if info.surface != "cylinder":
            words = "hole walls" + (" or round bosses" if bosses_ok else "")
            raise CamJobError(f"{where}: {ref} is a {info.surface}; a {ctx.spec.op} names {words} "
                              "(cylinders: cadgen cam features lists the holes)")
        if info.hole:
            if not holes_ok:
                raise CamJobError(f"{where}: {ref} is a hole wall; a {ctx.spec.op} names round bosses")
            if groups is None:
                groups = holes(ctx.part)
            group = next((g for g in groups if info.ref in g["faces"]), None)
            if group is None:
                continue
            # A counterbore's wall names the counterbore (its diameter, down to its shoulder), not the hole under it.
            counterbore = group.get("counterbore")
            bored = counterbore is not None and abs(2.0 * float(info.radius_mm) - counterbore["diameter_mm"]) < 1e-3
            key = (group["faces"][0], bored)
            if key in seen:
                continue
            seen.add(key)
            axis = ctx.wcs.vectors_to_wcs([group["axis"]])[0]
            if axis[2] < 1.0 - 1e-6:
                raise CamJobError(f"{where}: the hole {ref} opens along {group['axis_word']}, not toward the tool in "
                                  f"setup '{ctx.setup.id}'; machine it from a setup that faces it")
            top = ctx.wcs.to_wcs([group["center_mm"]])[0]
            bottom = ctx.wcs.to_wcs([group["bottom_mm"]])[0]
            if bored:
                out.append(HoleTarget(ref=info.ref, centre=(float(top[0]), float(top[1])),
                                      diameter_mm=float(counterbore["diameter_mm"]), top_z=float(top[2]),
                                      bottom_z=float(top[2]) - float(counterbore["depth_mm"]), hole=True,
                                      through=False))
                continue
            out.append(HoleTarget(ref=group["faces"][0], centre=(float(top[0]), float(top[1])),
                                  diameter_mm=float(group["diameter_mm"]), top_z=float(top[2]),
                                  bottom_z=float(bottom[2]), hole=True, through=bool(group["through"])))
            continue
        if not bosses_ok:
            raise CamJobError(f"{where}: {ref} is the outside of a round boss, not a hole wall; a {ctx.spec.op} "
                              "names holes")
        if info.ref in seen:
            continue
        seen.add(info.ref)
        axis = ctx.wcs.vectors_to_wcs([info.axis])[0]
        if abs(abs(axis[2]) - 1.0) > 1e-6:
            raise CamJobError(f"{where}: the boss {ref} does not stand along Z in setup '{ctx.setup.id}'; machine it "
                              "from a setup that looks down its axis")
        points = _face_points(ctx, ref)
        centre = ctx.wcs.to_wcs([info.axis_point])[0]
        out.append(HoleTarget(ref=info.ref, centre=(float(centre[0]), float(centre[1])),
                              diameter_mm=2.0 * float(info.radius_mm), top_z=float(np.max(points[:, 2])),
                              bottom_z=float(np.min(points[:, 2])), hole=False))
    return out


def fixture_keepouts(ctx) -> list:
    """The setup's fixture boxes (job ``fixture``, part coordinates) in its WCS: ``(footprint, z_low, z_high)`` per
    box, the footprint a shapely polygon on the WCS XY plane."""
    import numpy as np
    import shapely

    out = []
    for box in getattr(ctx.setup, "fixtures", ()) or ():
        low, high = np.asarray(box.min_mm, dtype=float), np.asarray(box.max_mm, dtype=float)
        corners = np.array([[x, y, z] for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])])
        wcs = ctx.wcs.to_wcs(corners)
        out.append((shapely.MultiPoint(wcs[:, :2]).convex_hull, float(wcs[:, 2].min()), float(wcs[:, 2].max())))
    return out


def fixtures_clear(ctx, geometry, z: float, radius: float | None = None) -> bool:
    """The tool (``radius``, default its own) going down to ``z`` over ``geometry`` (shapely, XY: a point, a lead's
    line) keeps clear of every fixture box standing above ``z``."""
    r = ctx.tool.radius if radius is None else radius
    tol = ctx.tolerance_mm
    return all(top <= z + tol or footprint.distance(geometry) >= r + tol
               for footprint, _, top in fixture_keepouts(ctx))


def in_air(ctx, xy, z: float, *, margin: float = 0.5) -> bool:
    """The tool may come straight down at ``xy`` to ``z``: its whole circle is off the stock's footprint (the whole
    stock projected down the tool axis, nothing an earlier cut took away subtracted) by ``margin``, and the drop
    there is clear of every fixture box standing above ``z`` (:func:`fixtures_clear`)."""
    import shapely

    point = shapely.Point(float(xy[0]), float(xy[1]))
    return ctx.stock_outline.distance(point) >= ctx.tool.radius + margin and fixtures_clear(ctx, point, z)


def down_in_air(b, heights, z: float, *, f: float) -> None:
    """Straight down beside the stock to ``z`` where :func:`in_air` says it is clear: a rapid only to a millimetre over
    the stock's top, then fed, so stock bigger than the job says (sawn, or a guessed margin) is met at a feed, never a
    rapid."""
    above = heights.stock_top + 1.0
    if z < above and b.pos[2] > above:
        b.rapid(z=above)
    if b.pos[2] > z and z < above:
        b.feed(z=z, f=f)
    elif b.pos[2] > z:
        b.rapid(z=z)


def lift_and_go(b, xy, heights, *, down_to: float | None = None) -> None:
    """Up to the clearance plane, over ``xy``, down to the retract plane (or ``down_to`` when it is lower and the
    column below the retract plane is known to be clear)."""
    if b.pos[2] < heights.clearance - 1e-9 and (abs(b.pos[0] - xy[0]) > 1e-9 or abs(b.pos[1] - xy[1]) > 1e-9):
        b.rapid(z=heights.clearance)
    b.rapid(x=float(xy[0]), y=float(xy[1]))
    b.rapid(z=heights.retract)
    if down_to is not None and down_to < heights.retract:
        b.rapid(z=down_to)


def link(b, target, z: float, *, clear, heights, f: float, above=None, z_above: float | None = None) -> str:
    """From where the tool is (at ``z``) to ``target`` (x, y) at ``z``: a straight feed when the segment lies in
    ``clear`` (tool-centre space already cut at this level), else up to the retract plane, over, rapid back down to
    1 mm over ``z_above`` when ``above`` (the level above's cut area) holds the target, then fed down to ``z``.
    Returns ``"feed"`` or ``"lift"``."""
    import shapely

    here = b.pos
    if abs(here[0] - target[0]) < 1e-9 and abs(here[1] - target[1]) < 1e-9:
        b.feed(z=z, f=f)
        return "feed"
    segment = shapely.LineString([here[:2], (float(target[0]), float(target[1]))])
    if clear is not None and abs(here[2] - z) < 1e-9 and segment.within(clear.buffer(1e-6)):
        b.feed(x=float(target[0]), y=float(target[1]), z=z, f=f)
        return "feed"
    b.rapid(z=heights.retract)
    b.rapid(x=float(target[0]), y=float(target[1]))
    if above is not None and z_above is not None and above.buffer(1e-6).contains(shapely.Point(target)):
        b.rapid(z=min(heights.retract, z_above + 1.0))
    b.feed(z=z, f=f)
    return "lift"


def ramp_along(b, path, z_from: float, z_to: float, *, angle_deg: float, f: float) -> bool:
    """:func:`cadgen._internal.cam.linking.ramp`: a zig-zag that follows ``path`` itself."""
    from cadgen._internal.cam.linking import ramp

    return ramp(b, path, z_from, z_to, angle_deg=angle_deg, f=f)


def helix_arcs(b, centre, radius: float, angle0: float, sweep: float, z_end: float, *, f: float) -> None:
    """From the tool's position (on the circle about ``centre`` at ``angle0`` radians), along a helix sweeping
    ``sweep`` radians (positive: counter-clockwise) to ``z_end``, as arcs of at most a half turn."""
    cx, cy = float(centre[0]), float(centre[1])
    z0 = b.pos[2]
    pieces = max(1, int(math.ceil(abs(sweep) / math.pi - 1e-9)))
    for k in range(1, pieces + 1):
        angle = angle0 + sweep * k / pieces
        z = z0 + (z_end - z0) * k / pieces
        b.arc(cx + radius * math.cos(angle), cy + radius * math.sin(angle), z, centre=(cx, cy, 0.0),
              clockwise=sweep < 0, f=f)
