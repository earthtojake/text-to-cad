"""Shapes over usd-brep Breps, behaving as build123d's do.

usd-brep and OpenCascade disagree on conventions that build123d code depends on;
this module is where they are reconciled:

- usd-brep booleans consume their inputs and fillets edit in place, while build123d
  shapes are values: every operation works on copies (``Brep.copy`` keeps face and
  edge order, so a selected edge maps onto the copy by index).
- usd-brep builds arcs, and the straight seams of extruded arcs, as B-splines, and
  approximates some intersections OpenCascade solves exactly: an edge that is an exact
  line or circle is reported as one, because selectors filter on it.
- OpenCascade fillets the whole tangent-continuous chain through a selected edge and
  skips seams and edges between tangent faces; usd-brep fillets exactly what it is
  given and rejects such edges.
- usd-brep's straight ("linear") cross-section sets back ``r*cot(theta/2)``; build123d's
  chamfer length is the setback itself.
- A usd-brep fillet can return a body with no material where OpenCascade raises: the
  result is checked, and an empty body raises as build123d would.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterable

import numpy as np
import usd_brep as ub

from .geometry import Axis, BoundBox, GeomType, Keep, Location, Plane, SortBy, Vector

ACCURACY = 1e-6  # relative accuracy of usd-brep's integrated volumes and areas


# ------------------------------------------------------------------ kernel helpers
def transform(target, M):
    """Apply a rigid 4x4 transform to a Brep or a standalone curve, in place."""
    M = np.asarray(M, float)
    if np.allclose(M, np.eye(4), atol=1e-15):
        return target
    if np.linalg.det(M[:3, :3]) < 0:
        raise ValueError("a reflection is not a rigid move: use mirror()")
    ub.transform(target, ub.Axis2Placement(tuple(M[:3, 3]), tuple(M[:3, 0]), tuple(M[:3, 1])))
    return target


def mirror_brep(brep, plane: Plane):
    """Reflect a Brep across a plane, in place. usd-brep reflects only by scaling, so move
    the plane onto the world YZ plane, scale X by -1 and move back. The result's faces and
    edges are all B-splines (usd-brep's reflection is not type-preserving)."""
    frame = np.eye(4)
    x = plane.z_dir
    y = plane.x_dir
    frame[:3, 0], frame[:3, 1], frame[:3, 2], frame[:3, 3] = x._v, y._v, x.cross(y)._v, plane.origin._v
    transform(brep, np.linalg.inv(frame))
    ub.scale(brep, (-1.0, 1.0, 1.0))
    return transform(brep, frame)


def combine(base, tools, op):
    """``op`` over copies: usd-brep booleans consume both operands."""
    result = base.copy()
    for tool in tools:
        result = op(result, tool.copy())
    return result


def split_lumps(brep) -> list:
    """Each lump of a multi-lump Brep as its own Brep (boolean_lists against a far-away box)."""
    if ub.material_census(brep)["solid_count"] <= 1:
        return [brep]
    (lo, hi) = brep.bounding_box()
    far = ub.create_box(tuple(c + 10 * (abs(c) + 1) for c in hi), 1, 1, 1)
    breps, _ = ub.boolean_lists([brep.copy()], [], [far], [], operation=3)
    return [b for b in breps if ub.material_census(b)["solid_count"] >= 1 and b.bounding_box()[0][0] < hi[0] + 1]


def classify(handle):
    """("LINE" | "CIRCLE" | "BSPLINE", circle data) for a usd-brep edge.

    usd-brep makes arcs, and the straight seams of extruded arcs, B-splines where
    OpenCascade has analytic lines and circles, and it approximates some intersections
    OpenCascade solves exactly (a torus cut through a coaxial cylinder: a B-spline up to
    3.6e-6 mm off a circle). build123d code selects on those types, so an edge that is a
    line or circle to 1e-6 of its size is reported as one.
    """
    curve = handle.curve()
    kind = type(curve).__name__
    if kind == "Line":
        return "LINE", None
    if kind == "Circle":
        return "CIRCLE", (np.array(curve.center()), float(curve.radius()), np.array(curve.normal()))
    t0, t1 = handle.parameter_range()
    pts = np.array([handle.point_at(t0 + (t1 - t0) * k / 8) for k in range(9)])
    size = max(float(np.ptp(pts, axis=0).max()), 1e-12)
    tol = 1e-6 * max(size, 1.0)
    chord = pts[-1] - pts[0]
    open_curve = np.linalg.norm(chord) > tol
    if open_curve:
        d = chord / np.linalg.norm(chord)
        off = pts - pts[0]
        if np.linalg.norm(off - np.outer(off @ d, d), axis=1).max() < tol:
            return "LINE", None
    a, b, c = pts[0], pts[4], (pts[-1] if open_curve else pts[6])
    n = np.cross(b - a, c - a)
    if np.linalg.norm(n) < 1e-12:
        return "BSPLINE", None
    n /= np.linalg.norm(n)
    ab, ac = b - a, c - a
    centre = a + (np.cross(n, ab) * (ac @ ac) - np.cross(n, ac) * (ab @ ab)) / (2 * (np.cross(ab, ac) @ n))
    r = float(np.linalg.norm(a - centre))
    if np.abs(np.linalg.norm(pts - centre, axis=1) - r).max() < tol and np.abs((pts - centre) @ n).max() < tol:
        return "CIRCLE", (centre, r, n)
    return "BSPLINE", None


def flatten(items) -> list:
    out = []
    for item in items:
        if isinstance(item, (list, tuple, ShapeList)) and not (isinstance(item, tuple) and item and isinstance(item[0], (int, float))):
            out.extend(flatten(item))
        elif isinstance(item, Iterable) and not isinstance(item, (Shape, Sketch, str)) and hasattr(item, "__next__"):
            out.extend(flatten(list(item)))
        else:
            out.append(item)
    return out


# ------------------------------------------------------------------------ lists
class ShapeList(list):
    """build123d's selector list: filter, sort and group by geometry."""

    def filter_by(self, criterion, reverse: bool = False) -> ShapeList:
        if isinstance(criterion, GeomType):
            keep = [s for s in self if s.geom_type == criterion]
        elif isinstance(criterion, Axis):
            keep = [s for s in self if s._parallel_to(criterion.direction)]
        elif isinstance(criterion, Plane):
            keep = [s for s in self if s._in_plane(criterion)]
        else:
            keep = [s for s in self if criterion(s)]
        if reverse:
            ids = {id(s) for s in keep}
            keep = [s for s in self if id(s) not in ids]
        return ShapeList(keep)

    def _key(self, key) -> Callable:
        if key is None:
            key = Axis.Z
        if isinstance(key, Axis):
            return lambda s: (s.center() - key.position).dot(key.direction)
        if isinstance(key, SortBy):
            return {
                SortBy.LENGTH: lambda s: s.length,
                SortBy.RADIUS: lambda s: s.radius,
                SortBy.AREA: lambda s: s.area,
                SortBy.VOLUME: lambda s: s.volume,
                SortBy.DISTANCE: lambda s: s.center().length,
            }[key]
        return key

    def sort_by(self, sort_by=None, reverse: bool = False) -> ShapeList:
        return ShapeList(sorted(self, key=self._key(sort_by), reverse=reverse))

    def group_by(self, group_by=None, reverse: bool = False, tol_digits: int = 6) -> ShapeList:
        key = self._key(group_by)
        groups: dict = {}
        for s in self:
            groups.setdefault(round(key(s), tol_digits), ShapeList()).append(s)
        return ShapeList(groups[k] for k in sorted(groups, reverse=reverse))

    @property
    def first(self):
        return self[0]

    @property
    def last(self):
        return self[-1]

    def __getitem__(self, item):
        out = super().__getitem__(item)
        return ShapeList(out) if isinstance(item, slice) else out

    def __add__(self, other):
        return ShapeList(list(self) + list(other))


# ----------------------------------------------------------------- sub-shapes
class Vertex:
    _dim = 0

    def __init__(self, parent, handle):
        self.topo_parent, self._point = parent, tuple(float(c) for c in handle.point())

    X = property(lambda self: self._point[0])
    Y = property(lambda self: self._point[1])
    Z = property(lambda self: self._point[2])

    def to_tuple(self):
        return self._point

    def center(self) -> Vector:
        return Vector(self._point)

    def __eq__(self, other):
        return isinstance(other, Vertex) and np.allclose(self._point, other._point, atol=1e-7)

    def __hash__(self):
        return hash(tuple(round(c, 6) for c in self._point))


class Edge:
    _dim = 1

    def __init__(self, parent, handle, index):
        self.topo_parent, self._h, self._index = parent, handle, index
        self._kind = None

    def _classified(self):
        if self._kind is None:
            self._kind = classify(self._h)
        return self._kind

    @property
    def geom_type(self) -> GeomType:
        return GeomType[self._classified()[0]]

    def _circle(self):
        kind, data = self._classified()
        if kind != "CIRCLE":
            raise ValueError("not a circle or arc")
        return data

    radius = property(lambda self: self._circle()[1])
    arc_center = property(lambda self: Vector(self._circle()[0]))
    length = property(lambda self: float(self._h.length()))

    @property
    def is_closed(self) -> bool:
        return (self.position_at(0) - self.position_at(1)).length < 1e-7

    def normal(self) -> Vector:
        return Vector(self._circle()[2])

    def bounding_box(self) -> BoundBox:
        return BoundBox(*self._h.bounding_box(tight=True))

    def position_at(self, u: float) -> Vector:
        t0, t1 = self._h.parameter_range()
        return Vector(self._h.point_at(t0 + u * (t1 - t0)))

    def tangent_at(self, u: float = 0.5) -> Vector:
        t0, t1 = self._h.parameter_range()
        return Vector(self._h.tangent_at(t0 + u * (t1 - t0)))

    def start_point(self) -> Vector:
        return self.position_at(0)

    def end_point(self) -> Vector:
        return self.position_at(1)

    def center(self, *_args) -> Vector:
        return self.position_at(0.5)

    def faces(self) -> ShapeList:
        parent_faces = self.topo_parent._brep.faces()
        mine = self._h.faces()
        return ShapeList(Face(self.topo_parent, f, i) for i, f in enumerate(parent_faces) if f in mine)

    def vertices(self) -> ShapeList:
        return ShapeList(Vertex(self.topo_parent, v) for v in self._h.vertices())

    def _parallel_to(self, direction: Vector) -> bool:
        if self.geom_type != GeomType.LINE:
            return False
        d = (self.position_at(1) - self.position_at(0)).normalized()
        return abs(abs(d.dot(direction)) - 1) < 1e-9

    def _in_plane(self, plane: Plane) -> bool:
        return all(abs((self.position_at(u) - plane.origin).dot(plane.z_dir)) < 1e-7 for u in (0, 0.25, 0.5, 0.75, 1))

    def _face_normals(self):
        faces = self._h.faces()
        if len(faces) != 2:
            return None
        p = self.center().to_tuple()
        normals = []
        for f in faces:
            _, uvs, _ = ub.surface_closest_point(f.surface(), p)
            normals.append(np.array(f.outward_normal_at_uv(uvs[0].x, uvs[0].y)))
        return normals

    def _is_sharp(self) -> bool:
        """OpenCascade's fillet and chamfer skip seams and edges between tangent faces."""
        normals = self._face_normals()
        return normals is not None and abs(float(normals[0] @ normals[1])) < 1 - 1e-9

    def _ends(self):
        t0, t1 = self._h.parameter_range()
        return [(np.array(self._h.point_at(t)), np.array(self._h.tangent_at(t))) for t in (t0, t1)]

    def __eq__(self, other):
        return isinstance(other, Edge) and other.topo_parent is self.topo_parent and other._index == self._index

    def __hash__(self):
        return hash((id(self.topo_parent), self._index))


class Face:
    _dim = 2

    def __init__(self, parent, handle, index):
        self.topo_parent, self._h, self._index = parent, handle, index

    def _uv_mid(self):
        (u0, u1), (v0, v1) = self._h.uv_domain()
        return (u0 + u1) / 2, (v0 + v1) / 2

    @property
    def is_planar(self) -> bool:
        """Planar to 1e-9: sampled normals agree. usd-brep's own is_planar misses exactly
        planar B-spline faces (a reflected box, say) at any tolerance tighter than 1e-4."""
        (u0, u1), (v0, v1) = self._h.uv_domain()
        n0 = np.array(self._h.outward_normal_at_uv(*self._uv_mid()))
        for fu in (0.2, 0.5, 0.8):
            for fv in (0.2, 0.5, 0.8):
                n = np.array(self._h.outward_normal_at_uv(u0 + fu * (u1 - u0), v0 + fv * (v1 - v0)))
                if abs(float(n @ n0)) < 1 - 1e-9:
                    return False
        return True

    @property
    def geom_type(self) -> GeomType:
        # usd-brep's Python API does not say which analytic surface a face is
        return GeomType.PLANE if self.is_planar else GeomType.OTHER

    area = property(lambda self: float(self._h.area(ACCURACY)))

    def center(self, *_args) -> Vector:
        return Vector(self._h.centroid(ACCURACY))

    def normal_at(self, *_args) -> Vector:
        return Vector(self._h.outward_normal_at_uv(*self._uv_mid()))

    def bounding_box(self) -> BoundBox:
        return BoundBox(*self._h.bounding_box(tight=True))

    def edges(self) -> ShapeList:
        parent_edges = self.topo_parent._brep.edges()
        mine = self._h.edges()
        return ShapeList(Edge(self.topo_parent, e, i) for i, e in enumerate(parent_edges) if e in mine)

    def _plane_frame(self):
        if not self.is_planar:
            raise ValueError("Planes can only be created from planar faces")
        d = self._h.surface().derivatives(*self._uv_mid())
        x_dir = Vector(d[1]) if len(d) > 1 else None
        return self.center(), x_dir, self.normal_at()

    def _parallel_to(self, direction: Vector) -> bool:
        return self.is_planar and abs(abs(self.normal_at().dot(direction)) - 1) < 1e-9

    def _in_plane(self, plane: Plane) -> bool:
        return self._parallel_to(plane.z_dir) and abs((self.center() - plane.origin).dot(plane.z_dir)) < 1e-7

    def __eq__(self, other):
        return isinstance(other, Face) and other.topo_parent is self.topo_parent and other._index == self._index

    def __hash__(self):
        return hash((id(self.topo_parent), self._index))


# ------------------------------------------------------------------------ solids
class Shape:
    """A value: one usd-brep Brep (any number of lumps) plus build123d's labels."""

    _dim = 3

    def __init__(self, brep=None, *, label: str = "", color=None, loc=None, children=()):
        self._brep = brep
        self.label, self.color = label, color
        self._loc = np.eye(4) if loc is None else np.asarray(loc, float)
        self.children = tuple(children)
        self.joints: dict = {}
        self.parent = None

    wrapped = property(lambda self: self._brep)

    def _new(self, brep, loc=None):
        out = type(self).__new__(type(self))
        Shape.__init__(out, brep, label=self.label, color=self.color, loc=self._loc if loc is None else loc)
        return out

    # placement
    @property
    def location(self) -> Location:
        return Location.from_matrix(self._loc)

    @location.setter
    def location(self, loc: Location):
        self.locate(loc)

    def copy(self):
        return self._new(self._brep.copy())

    def moved(self, loc):
        if isinstance(loc, Plane):
            loc = loc.location
        return self._new(transform(self._brep.copy(), loc.M), loc.M @ self._loc)

    def move(self, loc):
        if isinstance(loc, Plane):
            loc = loc.location
        transform(self._brep, loc.M)
        self._loc = loc.M @ self._loc
        return self

    def locate(self, loc):
        if isinstance(loc, Plane):
            loc = loc.location
        transform(self._brep, loc.M @ np.linalg.inv(self._loc))
        self._loc = loc.M.copy()
        return self

    def located(self, loc):
        return self.copy().locate(loc)

    def rotate(self, axis: Axis, angle: float):
        from .geometry import axis_angle_matrix
        R = np.eye(4)
        R[:3, :3] = axis_angle_matrix(axis.direction, angle)
        T, Ti = np.eye(4), np.eye(4)
        T[:3, 3], Ti[:3, 3] = axis.position._v, -axis.position._v
        return self.moved(Location.from_matrix(T @ R @ Ti))

    def translate(self, vector):
        return self.moved(Location(Vector(vector)))

    def scale(self, factor: float):
        brep = self._brep.copy()
        ub.scale(brep, (factor, factor, factor))
        return self._new(brep)

    def mirror(self, about: Plane = Plane.XY):
        return self._new(mirror_brep(self._brep.copy(), about))

    def __rmul__(self, other):
        if isinstance(other, (Location, Plane)):
            return self.moved(other)
        return [self.moved(loc) for loc in other]

    # topology
    def edges(self) -> ShapeList:
        return ShapeList(Edge(self, e, i) for i, e in enumerate(self._brep.edges()))

    def faces(self) -> ShapeList:
        return ShapeList(Face(self, f, i) for i, f in enumerate(self._brep.faces()))

    def vertices(self) -> ShapeList:
        return ShapeList(Vertex(self, v) for v in self._brep.vertices())

    def edge(self):
        return self._only(self.edges(), "edge")

    def face(self):
        return self._only(self.faces(), "face")

    def solids(self) -> ShapeList:
        lumps = split_lumps(self._brep)
        if len(lumps) == 1:
            return ShapeList([self])
        return ShapeList(self._new(b) for b in lumps)

    def solid(self):
        return self._only(self.solids(), "solid")

    @staticmethod
    def _only(items, what):
        if len(items) != 1:
            raise ValueError(f"expected one {what}, found {len(items)}")
        return items[0]

    # measures
    volume = property(lambda self: float(self._brep.volume(ACCURACY)))
    area = property(lambda self: float(self._brep.area(ACCURACY)))
    is_valid = property(lambda self: bool(self._brep.is_manifold_solid()))

    def bounding_box(self, *_args, **_kwargs) -> BoundBox:
        return BoundBox(*self._brep.bounding_box(tight=True))

    def center(self, *_args) -> Vector:
        return Vector(self._brep.mass_properties(ACCURACY)["center_of_mass"])

    # booleans (values: operands are copied)
    def fuse(self, *others):
        return self._new(combine(self._brep, [o._brep for o in flatten(others)], ub.boolean_union))

    def cut(self, *others):
        return self._new(combine(self._brep, [o._brep for o in flatten(others)], ub.boolean_difference))

    def intersect(self, *others):
        return self._new(combine(self._brep, [o._brep for o in flatten(others)], ub.boolean_intersection))

    def __add__(self, other):
        return self.fuse(other)

    def __sub__(self, other):
        return self.cut(other)

    def __and__(self, other):
        return self.intersect(other)

    def split(self, plane: Plane, keep: Keep = Keep.TOP):
        """Halves by booleans with a half-space box: usd-brep's own plane ``cut`` leaves an
        open, non-manifold body."""
        top = half_space(plane, self.bounding_box())
        upper = self._new(ub.boolean_intersection(self._brep.copy(), top.copy()))
        if keep == Keep.TOP:
            return upper
        lower = self._new(ub.boolean_difference(self._brep.copy(), top))
        if keep == Keep.BOTTOM:
            return lower
        if keep == Keep.BOTH:
            return upper, lower
        raise ValueError(f"split keeps TOP, BOTTOM or BOTH, not {keep}")

    # blends
    def _tangent_chains(self, edges) -> list:
        every = self.edges()
        ends = [(e, p, t) for e in every for p, t in e._ends()]
        chosen = {e._index: e for e in edges}
        queue = list(edges)
        while queue:
            edge = queue.pop()
            for p, t in edge._ends():
                for other, q, u in ends:
                    if other._index in chosen or np.linalg.norm(p - q) > 1e-6:
                        continue
                    if abs(abs(float(t @ u)) - 1) < 1e-7 and other._is_sharp():
                        chosen[other._index] = other
                        queue.append(other)
        return list(chosen.values())

    def _blend(self, edges, radius: float, xsect, *, chamfer: bool = False, continuity: int = 1):
        sharp = [e for e in edges if e._is_sharp()]
        if not sharp:  # build123d raises here too
            raise ValueError(f"Failed creating a fillet with radius of {radius}")
        sharp = self._tangent_chains(sharp)
        radii = []
        for e in sharp:
            if chamfer:
                n1, n2 = e._face_normals()
                theta = math.pi - math.acos(max(-1.0, min(1.0, float(n1 @ n2))))
                radii.append(radius * math.tan(theta / 2))
            else:
                radii.append(radius)
        brep = self._brep.copy()
        handles = brep.edges()
        brep = ub.fillet_edges_per_edge(brep, [handles[e._index] for e in sharp], radii, [xsect] * len(sharp),
                                        continuity=continuity)
        if not brep.is_manifold_solid() or ub.material_census(brep)["solid_count"] < 1:
            raise ValueError(f"Failed creating a fillet with radius of {radius}")
        return self._new(brep)

    def fillet(self, radius: float, edge_list):
        return self._blend(list(edge_list), radius, ub.FilletXSect.CIRCULAR)

    def chamfer(self, length: float, length2: float | None, edge_list, face=None):
        if length2 not in (None, length) or face is not None:
            raise NotImplementedError("asymmetric chamfers are not supported on usd-brep")
        return self._blend(list(edge_list), length, ub.FilletXSect.LINEAR, chamfer=True)


class Part(Shape):
    pass


Solid = Part


class Compound(Part):
    """Several parts kept apart (an assembly's children); their union for kernel operations."""

    def __init__(self, obj=None, label: str = "", color=None, children=()):
        parts = [p for p in flatten([obj if obj is not None else [], list(children)]) if isinstance(p, Shape)]
        brep = None
        for p in parts:
            brep = p._brep.copy() if brep is None else ub.boolean_union(brep, p._brep.copy())
        super().__init__(brep, label=label, color=color, children=parts)

    def __iter__(self):
        return iter(self.children)

    @property
    def volume(self) -> float:
        return sum(p.volume for p in self.children) if self.children else 0.0


def half_space(plane: Plane, around: BoundBox):
    """A box covering ``around`` on the side the plane's normal points to."""
    size = 4 * max(around.diagonal, 1.0) + 2 * (around.center() - plane.origin).length
    box = ub.create_box((-size / 2, -size / 2, 0.0), size, size, size)
    return transform(box, plane.matrix())


# ----------------------------------------------------------------------- sketches
class Profile:
    """A planar face as exact boundary loops in its own XY plane, plus a placement.

    A loop is a list of ("line", p0, p1) | ("arc", centre, radius, a0_deg, a1_deg) |
    ("circle", centre, radius) | ("ellipse", centre, rx, ry); the first loop is the
    outline and any others are holes.
    """

    def __init__(self, loops, M=None):
        self.loops, self.M = loops, np.eye(4) if M is None else np.asarray(M, float)

    def moved(self, loc) -> Profile:
        M = loc.M if isinstance(loc, Location) else loc
        return Profile(self.loops, M @ self.M)

    @property
    def plane(self) -> Plane:
        return Plane(Location.from_matrix(self.M))

    def bounds_2d(self):
        pts = []
        for loop in self.loops:
            for seg in loop:
                if seg[0] == "line":
                    pts += [seg[1], seg[2]]
                elif seg[0] == "ellipse":
                    c, rx, ry = seg[1], seg[2], seg[3]
                    pts += [(c[0] - rx, c[1] - ry), (c[0] + rx, c[1] + ry)]
                else:
                    c, r = seg[1], seg[2]
                    a0, a1 = (seg[3], seg[4]) if seg[0] == "arc" else (0.0, 360.0)
                    angles = [a0, a1] + [k * 90.0 for k in range(-8, 9) if a0 <= k * 90.0 <= a1]
                    pts += [(c[0] + r * math.cos(math.radians(a)), c[1] + r * math.sin(math.radians(a))) for a in angles]
        pts = np.array(pts)
        return (*pts.min(axis=0), 0.0), (*pts.max(axis=0), 0.0)

    def mirrored(self, plane: Plane) -> Profile:
        """Reflected across a plane: the loops mirrored in their own x, the placement kept rigid
        (usd-brep curves take only rigid transforms)."""
        n = plane.z_dir._v
        R = np.eye(4)
        R[:3, :3] = np.eye(3) - 2 * np.outer(n, n)
        R[:3, 3] = 2 * (plane.origin._v @ n) * n

        def flip(seg):
            if seg[0] == "line":
                return ("line", (-seg[1][0], seg[1][1]), (-seg[2][0], seg[2][1]))
            if seg[0] == "arc":
                return ("arc", (-seg[1][0], seg[1][1]), seg[2], 180.0 - seg[4], 180.0 - seg[3])
            return (seg[0], (-seg[1][0], seg[1][1])) + tuple(seg[2:])

        return Profile([[flip(s) for s in loop] for loop in self.loops], R @ self.M @ np.diag([-1.0, 1.0, 1.0, 1.0]))

    def curves(self) -> list:
        """usd-brep curves for every segment, placed in 3D."""
        out = []
        for loop in self.loops:
            for seg in loop:
                if seg[0] == "line":
                    crv = ub.create_line_segment((*seg[1], 0.0), (*seg[2], 0.0))
                elif seg[0] == "arc":
                    crv = ub.create_arc((*seg[1], 0.0), seg[2], seg[3], seg[4])
                elif seg[0] == "ellipse":
                    crv = ub.create_ellipse((*seg[1], 0.0), seg[2], seg[3])
                else:
                    crv = ub.create_circle((*seg[1], 0.0), seg[2])
                out.append(transform(crv, self.M))
        return out


class Sketch(Shape):
    """A planar region as a tree of exact profiles combined by modes.

    usd-brep's 2D booleans exist, but its sheets cannot be extruded exactly (thickening a
    boolean_2d result crashes the interpreter, and a sheet's trimmed edges cannot be read
    back as curves). A prism or revolution of a region equals the same boolean of the
    prisms or revolutions of its pieces, so a sketch keeps its pieces and their modes, and
    extrude and revolve apply the modes as 3D booleans.
    """

    _dim = 2

    def __init__(self, tree=None, *, label: str = "", color=None):
        super().__init__(None, label=label, color=color)
        self._tree = tree

    @staticmethod
    def of(profile: Profile) -> Sketch:
        return Sketch(("leaf", profile))

    def _new_tree(self, tree):
        return Sketch(tree, label=self.label, color=self.color)

    def moved(self, loc):
        if isinstance(loc, Plane):
            loc = loc.location
        return self._new_tree(map_tree(self._tree, lambda p: p.moved(loc)))

    def mirror(self, about: Plane = Plane.XY) -> Sketch:
        return self._new_tree(map_tree(self._tree, lambda p: p.mirrored(about)))

    def profiles(self) -> list[Profile]:
        return leaves(self._tree)

    def combine(self, mode, other: Sketch) -> Sketch:
        from .geometry import Mode
        if self._tree is None:
            if mode in (Mode.ADD, Mode.REPLACE):
                return other
            raise ValueError(f"nothing to {mode.name.lower()} from")
        return self._new_tree((mode, self._tree, other._tree))

    def __add__(self, other):
        from .geometry import Mode
        return self.combine(Mode.ADD, other)

    def __sub__(self, other):
        from .geometry import Mode
        return self.combine(Mode.SUBTRACT, other)

    def __and__(self, other):
        from .geometry import Mode
        return self.combine(Mode.INTERSECT, other)

    @property
    def area(self) -> float:
        # a unit-height prism's volume is the region's area
        solid = sweep_tree(self._tree, lambda p: ub.linear_sweep(p.curves(), tuple(p.plane.z_dir), 1.0))
        return float(solid.volume(ACCURACY))

    def faces(self):
        raise NotImplementedError("a sketch's faces are evaluated when it is extruded or revolved")


def map_tree(tree, fn):
    if tree is None:
        return None
    if tree[0] == "leaf":
        return ("leaf", fn(tree[1]))
    return (tree[0], map_tree(tree[1], fn), map_tree(tree[2], fn))


def leaves(tree) -> list:
    if tree is None:
        return []
    if tree[0] == "leaf":
        return [tree[1]]
    return leaves(tree[1]) + leaves(tree[2])


def sweep_tree(tree, sweep: Callable):
    """Evaluate a sketch tree in 3D: sweep each profile, combine by the modes."""
    from .geometry import Mode
    if tree is None:
        raise ValueError("A face or sketch must be provided")
    if tree[0] == "leaf":
        return sweep(tree[1])
    mode, left, right = tree
    a, b = sweep_tree(left, sweep), sweep_tree(right, sweep)
    if mode == Mode.ADD:
        return ub.boolean_union(a, b)
    if mode == Mode.SUBTRACT:
        return ub.boolean_difference(a, b)
    if mode == Mode.INTERSECT:
        return ub.boolean_intersection(a, b)
    raise ValueError(f"unsupported sketch mode {mode}")
