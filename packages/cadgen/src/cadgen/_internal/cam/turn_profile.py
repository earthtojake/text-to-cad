"""The turned profile of a part, the lathe tools' shapes, and the 2D geometry every turning planner, the lathe
simulator and the turning gouge check share.

**Conventions.** A lathe setup's WCS Z is the spindle axis (chuck side negative); the IR stores true geometry,
``x`` the radius, ``z`` the axial position, ``y`` 0 (posts convert to diameters). Everything here is the half-plane
of a section through the axis: shapely ``(x, y)`` is ``(radius, z)``.

**The profile** (:func:`read_profile`) is read off the exact solid: the part is cut by four planes through the
spindle axis (0, 45, 90 and 135 degrees about it, OCCT ``BRepAlgoAPI_Common`` with a plane face), each cut gives two
half-sections, and their union is the region the part sweeps when it turns: its max-radius envelope. Off-axis
features (a cross hole, a flat, a keyway) vanish from it, which is what a lathe sees; a feature that sticks OUT
between the cutting planes is caught from the tessellation (any mesh triangle beyond the envelope is revolved into
it). :meth:`TurnProfile.r_out` is the OD envelope and :meth:`TurnProfile.r_in` the bore envelope at a height.

Whether the part is a body of revolution about the setup's axis is read from its exact faces: planes across the
axis centred on it, cylinders, cones, spheres, tori and surfaces of revolution on the axis are turned; the rest are
off-axis. Under 30 % of the surface turned about the axis (or no round face on it) is refused in one sentence that
names the axis its round faces do share; off-axis faces are listed in a note (they need live tooling or a mill).

**Tool shapes** (:func:`tool_shape`) are lists of convex polygons in the half-plane relative to the IR point (the
tool's controlled point, below): an OD or ID turning insert (its nose radius, the wedge between its cutting edges
set by the insert's nose angle and the holder's lead angle, and the holder or bar beyond), a grooving or part-off
blade, a drill, a thread insert. Planners keep the tool out of the part with :func:`minkowski` (the region the IR
point may not enter is the part grown by the reflected tool), so the path is compensated for the nose radius and
the insert's clearance by construction, and the simulator sweeps the same shapes.

**The controlled point** (what the tool offsets are touched off to, so posts write G40 paths): an OD turning tool's
imaginary tip, its lowest X and its lowest Z, ``(nose centre x - r, nose centre z - r)`` for a right-hand tool
cutting towards the chuck, ``(x - r, z)`` for a neutral one; a boring bar's ``(nose centre x + r, z - r)``; a
grooving or part-off blade's tip corner on the chuck side; a drill's point; a thread insert's tip.

numpy, shapely and OCP inside the functions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from cadgen._internal.cam.job_errors import CamJobError

__all__ = ["INSERT_ANGLES", "TurnProfile", "envelope", "minkowski", "read_profile", "sweep", "tool_shape"]

#: Insert letter -> (nose angle, lead angle of the usual right-hand holder), degrees: C 80° rhombic on a 95° holder,
#: D 55° on 93°, V 35° on 93°, W 80° trigon on 95°.
INSERT_ANGLES = {"C": (80.0, 95.0), "D": (55.0, 93.0), "V": (35.0, 93.0), "W": (80.0, 95.0)}
#: How far shapes reach: the holder beyond the insert (mm), as good as infinite for a lathe part.
REACH = 400.0
#: Below this fraction of its surface turned about the axis a part is not a turned part.
MIN_REVOLVED = 0.3
_ANGLES = (0.0, 45.0, 90.0, 135.0)


# --- geometry helpers ----------------------------------------------------------------------------------

def _shapely():
    import shapely

    return shapely


def minkowski(geometry, shapes):
    """``geometry`` grown by every convex polygon of ``shapes`` (a list of (K, 2) arrays): the union of each edge
    swept by each shape, and the geometry moved by one point of it."""
    import numpy as np

    shapely = _shapely()
    if geometry is None or geometry.is_empty:
        return geometry
    edges = []
    for polygon in shapely.get_parts(geometry):
        if polygon.geom_type != "Polygon":
            continue
        for ring in (polygon.exterior, *polygon.interiors):
            coords = np.asarray(ring.coords)[:, :2]
            edges.append(np.stack([coords[:-1], coords[1:]], axis=1))
    if not edges:
        return geometry
    edges = np.concatenate(edges)
    pieces = []
    for shape in shapes:
        shape = np.asarray(shape, dtype=float)
        k = len(shape)
        points = (edges[:, :, None, :] + shape[None, None, :, :]).reshape(len(edges), 2 * k, 2)
        hulls = shapely.convex_hull(shapely.multipoints(points.reshape(-1, 2),
                                                        indices=np.repeat(np.arange(len(edges)), 2 * k)))
        pieces.extend(hulls.tolist())
        pieces.append(shapely.affinity.translate(geometry, float(shape[0, 0]), float(shape[0, 1])))
    return shapely.union_all(pieces)


def sweep(points, shapes):
    """The region a tool of ``shapes`` sweeps moving through ``points`` ((N, 2), in order): one convex hull per
    straight piece and shape, unioned."""
    import numpy as np

    shapely = _shapely()
    points = np.asarray(points, dtype=float)
    if len(points) == 0:
        return shapely.Polygon()
    if len(points) == 1:
        points = np.vstack([points, points])
    pieces = []
    for shape in shapes:
        shape = np.asarray(shape, dtype=float)
        k = len(shape)
        a, b = points[:-1], points[1:]
        hull_points = np.concatenate([a[:, None, :] + shape[None], b[:, None, :] + shape[None]], axis=1)
        hulls = shapely.convex_hull(shapely.multipoints(hull_points.reshape(-1, 2),
                                                        indices=np.repeat(np.arange(len(a)), 2 * k)))
        pieces.extend(hulls.tolist())
    return shapely.union_all(pieces)


def envelope(geometry, *, side: str, z_low: float, z_high: float):
    """The ``side`` (``max``: the OD, ``min``: the bore) x of ``geometry`` along z from ``z_high`` down to ``z_low``:
    an (N, 2) array of ``(x, z)`` points, exact for straight-edged geometry (a step is two points at one z); NaN x
    where a height has no geometry."""
    import numpy as np

    shapely = _shapely()
    if z_high <= z_low:
        return np.zeros((0, 2))
    coords = shapely.get_coordinates(geometry)
    zs = coords[:, 1] if len(coords) else np.zeros(0)
    zs = np.concatenate([zs[(zs > z_low) & (zs < z_high)], [z_low, z_high]])
    zs = np.unique(np.round(zs, 7))[::-1]
    if len(zs) < 2:
        return np.zeros((0, 2))
    tops, bottoms = zs[:-1], zs[1:]
    gap = np.minimum(1e-6, (tops - bottoms) / 4.0)
    probes = np.concatenate([tops - gap, bottoms + gap])
    bounds = geometry.bounds
    x0, x1 = bounds[0] - 1.0, bounds[2] + 1.0
    lines = shapely.linestrings(np.stack([np.column_stack([np.full(len(probes), x0), probes]),
                                          np.column_stack([np.full(len(probes), x1), probes])], axis=1))
    shapely.prepare(geometry)
    cut = shapely.intersection(lines, geometry)
    box = shapely.bounds(cut)
    value = box[:, 2] if side == "max" else box[:, 0]
    n = len(tops)
    upper, lower = value[:n], value[n:]
    # A probe a hair inside a piece is that piece's value at its end (the boundary is straight in between).
    out = np.empty((2 * n, 2))
    out[0::2, 0], out[0::2, 1] = upper, tops
    out[1::2, 0], out[1::2, 1] = lower, bottoms
    keep = np.ones(len(out), dtype=bool)
    same = (np.abs(np.diff(out[:, 0])) < 1e-9) & (np.abs(np.diff(out[:, 1])) < 1e-9)
    keep[1:][same] = False
    return out[keep]


def simplify_path(points, tolerance: float):
    """A polyline's points with the ones within ``tolerance`` of a straight run dropped (ends kept)."""
    import numpy as np

    shapely = _shapely()
    points = np.asarray(points, dtype=float)
    if len(points) < 3:
        return points
    line = shapely.LineString(points).simplify(tolerance, preserve_topology=False)
    return np.asarray(line.coords) if not line.is_empty else points[[0, -1]]


# --- tool shapes -----------------------------------------------------------------------------------------

def _circle(centre, radius: float, count: int = 24):
    import numpy as np

    angles = np.linspace(0.0, 2 * math.pi, count, endpoint=False)
    return np.column_stack([centre[0] + radius * np.cos(angles), centre[1] + radius * np.sin(angles)])


def insert_wedge(tool, *, inside: bool = False) -> tuple[float, float, tuple[float, float]]:
    """``(low, high, nose offset)``: the angles (degrees from +x towards +z) the insert's body lies between, seen
    from its nose centre, and the nose centre relative to the controlled point, for an OD tool (``inside``: a boring
    bar, the OD shape mirrored across the radius)."""
    r = max(tool.nose_radius_mm, 0.0)
    nose, lead = INSERT_ANGLES.get(tool.insert or "C", INSERT_ANGLES["C"])
    if tool.side == "neutral":
        low, high, offset = -nose / 2.0, nose / 2.0, (r, 0.0)
    else:
        low = lead - 90.0
        low, high, offset = low, low + nose, (r, r)
    if inside:
        low, high, offset = 180.0 - high, 180.0 - low, (-offset[0], offset[1])
    return low, high, offset


def tool_shape(tool, role: str, **params) -> list:
    """The tool as convex polygons ((K, 2) arrays, half-plane x = radius, y = z) around its controlled point at the
    origin. ``role``: ``od``/``id`` (a turning insert; ``id`` takes ``reach_mm``, how far the bar may stand inward of
    its nose), ``groove``/``groove_id`` (``reach_mm`` for the bore's), ``partoff``, ``drill``,
    ``thread``/``thread_id``."""
    import numpy as np

    if role in ("od", "id"):
        inside = role == "id"
        r = max(tool.nose_radius_mm, 0.005)
        low, high, offset = insert_wedge(tool, inside=inside)
        centre = np.asarray(offset, dtype=float)
        a_low, a_high = math.radians(low), math.radians(high)
        e_low = np.array([math.cos(a_low), math.sin(a_low)])
        e_high = np.array([math.cos(a_high), math.sin(a_high)])
        n_low = np.array([e_low[1], -e_low[0]])        # outward of the wedge: clockwise from its low edge
        n_high = np.array([-e_high[1], e_high[0]])     # and anticlockwise from its high edge
        length = float(params.get("reach_mm") or 3.0) if inside else 10.0
        p_low = centre + r * n_low + length * e_low
        p_high = centre + r * n_high + length * e_high
        beyond = np.array([0.0, REACH]) if inside else np.array([REACH, 0.0])
        body = np.vstack([_circle(centre, r), p_low, p_high, p_low + beyond, p_high + beyond])
        return [body]
    if role in ("groove", "partoff"):
        width = tool.width_mm
        r = min(max(tool.nose_radius_mm, 0.0), width / 2.0)
        if r > 0:
            tip = np.vstack([_circle((r, r), r, 16), _circle((r, width - r), r, 16)])
        else:
            tip = np.array([[0.0, 0.0], [0.0, width]])
        return [np.vstack([tip, [[REACH, 0.0], [REACH, width]]])]
    if role == "groove_id":
        width = tool.width_mm
        reach = float(params.get("reach_mm") or 3.0)
        blade = np.array([[0.0, 0.0], [0.0, width], [-reach, 0.0], [-reach, width]])
        bar = np.array([[-reach, 0.0], [-reach + 0.4 * reach, 0.0], [-reach, REACH], [-reach + 0.4 * reach, REACH]])
        return [blade, bar]
    if role == "drill":
        r = tool.radius
        half = math.radians((tool.point_angle if tool.type == "drill" else (tool.angle_deg or 90.0)) / 2.0)
        cone = r / math.tan(half)
        return [np.array([[0.0, 0.0], [r, cone], [r, REACH], [0.0, REACH]])]
    if role in ("thread", "thread_id"):
        h = 3.0
        flank = h * math.tan(math.radians(30.0))
        sign = 1.0 if role == "thread" else -1.0
        tip = np.array([[0.0, 0.0], [sign * h, flank], [sign * h, -flank]])
        far = np.array([[sign * REACH, flank], [sign * REACH, -flank]]) if role == "thread" else \
            np.array([[sign * h, REACH], [sign * h * 0.3, REACH]])
        return [np.vstack([tip, far])]
    raise ValueError(f"unknown lathe tool role {role!r}")


# --- the profile ---------------------------------------------------------------------------------------

@dataclass
class TurnProfile:
    """The part's turned half-section in a setup's WCS (shapely x = radius, y = z)."""

    region: Any
    z_front: float
    z_back: float
    r_max: float
    #: Faces that are not turned about the axis (``#o1.fN``): flats, cross holes, keyways.
    off_axis: tuple[str, ...] = ()
    revolved_fraction: float = 1.0
    note: str | None = None
    _od: Any = field(default=None, repr=False)
    _bore: Any = field(default=None, repr=False)

    def _curves(self):
        if self._od is None:
            self._od = envelope(self.region, side="max", z_low=self.z_back, z_high=self.z_front)
            self._bore = envelope(self.region, side="min", z_low=self.z_back, z_high=self.z_front)
        return self._od, self._bore

    @property
    def od(self):
        """The OD envelope, ``(x, z)`` from the front face to the back (a step is two points at one z)."""
        return self._curves()[0]

    @property
    def bore(self):
        """The bore envelope (x 0 where the part is solid on the axis), front to back."""
        return self._curves()[1]

    @staticmethod
    def _at(curve, z, pick):
        import numpy as np

        z = np.atleast_1d(np.asarray(z, dtype=float))
        out = np.full(len(z), np.nan)
        zs, xs = curve[:, 1], curve[:, 0]
        for k, value in enumerate(z):
            # Pieces of the curve whose z range holds the height; at a step take the side ``pick`` says.
            hits = []
            for i in range(len(curve) - 1):
                za, zb = zs[i], zs[i + 1]
                if za == zb:
                    if abs(value - za) < 1e-9:
                        hits += [xs[i], xs[i + 1]]
                    continue
                if min(za, zb) - 1e-9 <= value <= max(za, zb) + 1e-9:
                    f = (value - za) / (zb - za)
                    hits.append(xs[i] + f * (xs[i + 1] - xs[i]))
            hits = [h for h in hits if not math.isnan(h)]
            if hits:
                out[k] = pick(hits)
        return out

    def r_out(self, z):
        """The OD radius at height(s) ``z`` (the larger at a step); NaN off the part."""
        return self._at(self.od, z, max)

    def r_in(self, z):
        """The bore radius at height(s) ``z`` (0 where solid on the axis, the smaller at a step)."""
        import numpy as np

        values = self._at(self.bore, z, min)
        return np.where(values < 1e-6, 0.0, values)


def _cache(part) -> dict:
    return part.__dict__.setdefault("_turn_profiles", {})


def read_profile(part, wcs, *, tolerance_mm: float = 0.01, where: str = "") -> TurnProfile:
    """The turned profile of ``part`` about the WCS Z axis of a lathe setup (cached per setup)."""
    key = (wcs.rotation, wcs.origin, round(tolerance_mm, 6))
    cache = _cache(part)
    if key not in cache:
        cache[key] = _read_profile(part, wcs, tolerance_mm, where)
    return cache[key]


def _axis_frame(wcs):
    import numpy as np

    origin = np.asarray(wcs.from_wcs([[0.0, 0.0, 0.0]])[0], dtype=float)
    ex, ey, ez = (np.asarray(v, dtype=float) for v in wcs.vectors_from_wcs([[1, 0, 0], [0, 1, 0], [0, 0, 1]]))
    return origin, ex, ey, ez


def _axis_name(direction) -> str:
    import numpy as np

    d = np.asarray(direction, dtype=float)
    k = int(np.argmax(np.abs(d)))
    return "XYZ"[k]


def _classify(part, wcs, tolerance: float, where: str = "") -> tuple[float, list[str], str | None]:
    """``(turned fraction of the surface, off-axis face refs, why it is not a turned part or None)``."""
    import numpy as np

    origin, _, _, axis = _axis_frame(wcs)
    line_tol = max(0.02, 2.0 * tolerance)

    def off_line(point) -> float:
        v = np.asarray(point, dtype=float) - origin
        return float(np.linalg.norm(v - axis * float(v @ axis)))

    def parallel(direction) -> bool:
        return direction is not None and abs(abs(float(np.asarray(direction) @ axis)) - 1.0) < 1e-6

    total = turned = 0.0
    off_axis: list[str] = []
    round_on_axis = 0
    others: dict[tuple, float] = {}
    offset_lines: list[float] = []
    for face in part.faces.values():
        total += face.area_mm2
        ok = False
        if face.surface == "plane":
            ok = parallel(face.normal) and off_line(face.center_mm) < line_tol
        elif face.surface in ("cylinder", "cone"):
            if parallel(face.axis):
                distance = off_line(face.axis_point)
                ok = distance < line_tol
                if ok:
                    round_on_axis += 1
                elif face.surface == "cylinder" and not face.hole:
                    offset_lines.append(distance)
            if face.axis is not None and not ok:
                key = tuple(round(abs(v), 3) for v in face.axis)
                others[key] = others.get(key, 0.0) + face.area_mm2
        elif face.surface in ("sphere", "torus", "revolution"):
            ok, on_axis = _round_surface(part, face, origin, axis, line_tol)
            round_on_axis += int(on_axis)
        if ok:
            turned += face.area_mm2
        else:
            off_axis.append(face.ref)
    fraction = turned / total if total > 0 else 0.0
    why = None
    if fraction < MIN_REVOLVED or round_on_axis == 0:
        name = _axis_name(axis)
        hint = "; machine it on a mill instead"
        if others:
            best = max(others, key=others.get)
            other = _axis_name(best)
            if other != name:
                hint = (f"; its round faces run along the part's {other}: set the setup's orientation to +{other} "
                        f"(and stock.axis to \"{other.lower()}\")")
            elif offset_lines:
                hint = (f"; its round faces turn about a line {min(offset_lines):.3g} mm from the work zero: use "
                        "origin stock-top-center (on the bar's axis)")
        why = (f"{where + ': ' if where else ''}the part is not a body of revolution about this setup's spindle axis "
               f"(part {name}): only {fraction:.0%} of its surface turns about it{hint}")
    return fraction, off_axis, why


def _round_surface(part, face, origin, axis, line_tol) -> tuple[bool, bool]:
    import numpy as np
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    adaptor = BRepAdaptor_Surface(part.ocp_face(face.ordinal))

    def on_line(p) -> bool:
        v = np.array([p.X(), p.Y(), p.Z()]) - origin
        return float(np.linalg.norm(v - axis * float(v @ axis))) < line_tol

    def along(d) -> bool:
        return abs(abs(float(np.array([d.X(), d.Y(), d.Z()]) @ axis)) - 1.0) < 1e-6

    if face.surface == "sphere":
        ok = on_line(adaptor.Sphere().Location())
        return ok, ok
    if face.surface == "torus":
        ax = adaptor.Torus().Axis()
        ok = along(ax.Direction()) and on_line(ax.Location())
        return ok, ok
    ax = adaptor.AxeOfRevolution()
    ok = along(ax.Direction()) and on_line(ax.Location())
    return ok, ok


def _section_halves(part, wcs, tolerance: float) -> list:
    """The part cut by planes through the spindle axis: two half-sections (x = radius >= 0, y = z) per plane."""
    import numpy as np
    import shapely
    from OCP.BRep import BRep_Tool
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    origin, ex, ey, ez = _axis_frame(wcs)
    low, high = (np.asarray(v, dtype=float) for v in part.bbox)
    size = float(np.linalg.norm(high - low) + np.linalg.norm((low + high) / 2 - origin) + 10.0)
    solid = part.shape.wrapped
    halves = []
    big = shapely.box(0.0, -1e6, 1e6, 1e6)
    mirror_box = shapely.box(-1e6, -1e6, 0.0, 1e6)
    for angle in _ANGLES:
        a = math.radians(angle)
        u = math.cos(a) * ex + math.sin(a) * ey
        n = np.cross(ez, u)
        plane = gp_Pln(gp_Ax3(gp_Pnt(*map(float, origin)), gp_Dir(*map(float, n)), gp_Dir(*map(float, u))))
        face = BRepBuilderAPI_MakeFace(plane, -size, size, -size, size).Face()
        common = BRepAlgoAPI_Common(solid, face)
        common.Build()
        if not common.IsDone():
            continue
        result = common.Shape()
        BRepMesh_IncrementalMesh(result, max(tolerance / 2.0, 1e-3), False, 0.1, True)
        triangles = []
        explorer = TopExp_Explorer(result, TopAbs_FACE)
        while explorer.More():
            piece = TopoDS.Face_s(explorer.Current())
            location = TopLoc_Location()
            mesh = BRep_Tool.Triangulation_s(piece, location)
            if mesh is not None and mesh.NbTriangles():
                transform = location.Transformation()
                nodes = np.empty((mesh.NbNodes(), 3))
                for i in range(1, mesh.NbNodes() + 1):
                    p = mesh.Node(i).Transformed(transform)
                    nodes[i - 1] = (p.X(), p.Y(), p.Z())
                rel = nodes - origin
                flat = np.column_stack([rel @ u, rel @ ez])
                for i in range(1, mesh.NbTriangles() + 1):
                    ia, ib, ic = mesh.Triangle(i).Get()
                    triangles.append(flat[[ia - 1, ib - 1, ic - 1]])
            explorer.Next()
        if not triangles:
            continue
        tri = np.asarray(triangles)
        rings = np.concatenate([tri, tri[:, :1]], axis=1)
        polygons = shapely.polygons(rings)
        polygons = polygons[shapely.area(polygons) > 1e-12]
        section = shapely.union_all(polygons)
        halves.append(section.intersection(big))
        halves.append(shapely.affinity.scale(section.intersection(mirror_box), xfact=-1.0, yfact=1.0, origin=(0, 0)))
    return halves


def _read_profile(part, wcs, tolerance: float, where: str) -> TurnProfile:
    import numpy as np
    import shapely

    if part.kind != "step":
        raise CamJobError(f"{where + ': ' if where else ''}a lathe turns a solid part; a DXF is for cutting")
    fraction, off_axis, why = _classify(part, wcs, tolerance, where)
    if why:
        raise CamJobError(why)
    halves = [h for h in _section_halves(part, wcs, tolerance) if not h.is_empty]
    if not halves:
        raise CamJobError(f"{where + ': ' if where else ''}no section of the part crosses the spindle axis's plane; "
                          "is the work zero on the part's axis? use origin stock-top-center")
    region = shapely.union_all(halves)
    # Anything that sticks out between the cutting planes (a radial pin) is caught from the tessellation.
    vertices, triangles = part.mesh_in(wcs)
    vertices = np.asarray(vertices)
    radius = np.hypot(vertices[:, 0], vertices[:, 1])
    slack = max(2.0 * getattr(part, "deflection_mm", 0.01), 2.0 * tolerance, 0.02)
    grown = region.buffer(slack)
    outside = ~shapely.contains_xy(grown, radius, vertices[:, 2])
    if outside.any():
        tris = np.asarray(triangles)
        hit = outside[tris].any(axis=1)
        if hit.any():
            images = np.stack([radius[tris[hit]], vertices[:, 2][tris[hit]]], axis=-1)
            rings = np.concatenate([images, images[:, :1]], axis=1)
            polygons = shapely.polygons(rings)
            extra = shapely.union_all(polygons[shapely.area(polygons) > 1e-12])
            region = shapely.union_all([region, extra])
    region = shapely.make_valid(region.buffer(0))
    if region.geom_type == "MultiPolygon":
        # A sliver from the mesh check: keep the pieces that matter.
        parts = [p for p in shapely.get_parts(region) if p.area > 1e-6]
        region = shapely.union_all(parts)
    _, z0, x1, z1 = region.bounds
    note = None
    if off_axis:
        shown = ", ".join(off_axis[:6]) + (f" and {len(off_axis) - 6} more" if len(off_axis) > 6 else "")
        note = (f"{len(off_axis)} face{'s are' if len(off_axis) > 1 else ' is'} not turned about the spindle axis "
                f"({shown}): flats, cross holes or keyways need live tooling or a mill and are left uncut here")
    return TurnProfile(region=region, z_front=float(z1), z_back=float(z0), r_max=float(x1),
                       off_axis=tuple(off_axis), revolved_fraction=fraction, note=note)


# --- the bar ------------------------------------------------------------------------------------------

def bar_in_wcs(stock, wcs) -> tuple[float, float, float]:
    """``(radius, front z, back z)`` of a cylinder stock in a lathe setup's WCS."""
    import numpy as np

    cylinder = stock.cylinder or {}
    w = "xyz".index(cylinder.get("axis", "z"))
    centre = np.asarray(cylinder.get("center", [0.0, 0.0, 0.0]), dtype=float)
    ends = np.array([centre, centre])
    ends[0, w], ends[1, w] = cylinder.get("start", 0.0), cylinder.get("end", 0.0)
    z = wcs.to_wcs(ends)[:, 2]
    return float(cylinder.get("radius", 0.0)), float(z.max()), float(z.min())


def check_coaxial(stock, wcs, where: str) -> None:
    """Refuse a setup whose spindle axis is not the bar's axis."""
    import numpy as np

    cylinder = stock.cylinder
    if stock.kind != "cylinder" or not cylinder:
        raise CamJobError(f"{where}: a lathe turns bar stock; use stock "
                          "{\"kind\": \"cylinder\", \"diameter_mm\": ..}")
    w = "xyz".index(cylinder["axis"])
    bar_axis = np.zeros(3)
    bar_axis[w] = 1.0
    origin, _, _, axis = _axis_frame(wcs)
    if abs(abs(float(axis @ bar_axis)) - 1.0) > 1e-6:
        raise CamJobError(f"{where}: setup '{wcs.setup_id}' spins about the part's {_axis_name(axis)} but the bar runs "
                          f"along {cylinder['axis']}; set stock.axis to \"{_axis_name(axis).lower()}\" or the "
                          f"orientation to +{cylinder['axis'].upper()}")
    centre = np.asarray(cylinder["center"], dtype=float)
    v = origin - centre
    off = float(np.linalg.norm(v - bar_axis * float(v @ bar_axis)))
    if off > 1e-3:
        raise CamJobError(f"{where}: setup '{wcs.setup_id}' puts its work zero {off:.3g} mm off the bar's axis; a "
                          "lathe's zero sits on the spindle axis: use origin stock-top-center or part-top-center on a "
                          "round part, or an xyz on the axis")
