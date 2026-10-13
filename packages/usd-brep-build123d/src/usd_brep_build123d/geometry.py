"""Geometry values as build123d defines them: Vector, Location, Plane, Axis, BoundBox, the enums.

Pure Python and numpy; nothing here calls the kernel. Rotations follow build123d's
convention (intrinsic X, then Y, then Z, in degrees) and planes its named-plane table.
"""
from __future__ import annotations

import enum
import math
from collections.abc import Iterable

import numpy as np


class Align(enum.Enum):
    MIN = "MIN"
    CENTER = "CENTER"
    MAX = "MAX"
    NONE = "NONE"


class Mode(enum.Enum):
    ADD = "ADD"
    SUBTRACT = "SUBTRACT"
    INTERSECT = "INTERSECT"
    REPLACE = "REPLACE"
    PRIVATE = "PRIVATE"


class GeomType(enum.Enum):
    PLANE = "PLANE"
    CYLINDER = "CYLINDER"
    CONE = "CONE"
    SPHERE = "SPHERE"
    TORUS = "TORUS"
    BEZIER = "BEZIER"
    BSPLINE = "BSPLINE"
    REVOLUTION = "REVOLUTION"
    EXTRUSION = "EXTRUSION"
    OFFSET = "OFFSET"
    LINE = "LINE"
    CIRCLE = "CIRCLE"
    ELLIPSE = "ELLIPSE"
    HYPERBOLA = "HYPERBOLA"
    PARABOLA = "PARABOLA"
    OTHER = "OTHER"


class Keep(enum.Enum):
    ALL = "ALL"
    BOTTOM = "BOTTOM"
    BOTH = "BOTH"
    INSIDE = "INSIDE"
    OUTSIDE = "OUTSIDE"
    TOP = "TOP"


class Kind(enum.Enum):
    ARC = "ARC"
    INTERSECTION = "INTERSECTION"
    TANGENT = "TANGENT"


class SortBy(enum.Enum):
    LENGTH = "LENGTH"
    RADIUS = "RADIUS"
    AREA = "AREA"
    VOLUME = "VOLUME"
    DISTANCE = "DISTANCE"


def is_point(item) -> bool:
    return isinstance(item, tuple) and 2 <= len(item) <= 3 and all(isinstance(c, (int, float)) for c in item)


class Vector:
    __slots__ = ("_v",)

    def __init__(self, *args):
        if len(args) == 1 and not isinstance(args[0], (int, float)):
            arg = args[0]
            if isinstance(arg, Vector):
                values = arg._v
            elif hasattr(arg, "to_tuple"):
                values = arg.to_tuple()
            else:
                values = list(arg)
        else:
            values = list(args)
        values = [float(v) for v in values]
        self._v = np.array(values + [0.0] * (3 - len(values)), float)

    X = property(lambda self: float(self._v[0]))
    Y = property(lambda self: float(self._v[1]))
    Z = property(lambda self: float(self._v[2]))
    length = property(lambda self: float(np.linalg.norm(self._v)))

    def normalized(self) -> Vector:
        return Vector(self._v / np.linalg.norm(self._v))

    def dot(self, other) -> float:
        return float(self._v @ Vector(other)._v)

    def cross(self, other) -> Vector:
        return Vector(np.cross(self._v, Vector(other)._v))

    def rotate(self, axis: Axis, angle: float) -> Vector:
        return Vector(axis_angle_matrix(axis.direction, angle) @ self._v)

    def to_tuple(self) -> tuple[float, float, float]:
        return tuple(float(c) for c in self._v)

    def __iter__(self):
        return iter(self.to_tuple())

    def __getitem__(self, index):
        return float(self._v[index])

    def __add__(self, other):
        return Vector(self._v + Vector(other)._v)

    __radd__ = __add__

    def __sub__(self, other):
        return Vector(self._v - Vector(other)._v)

    def __rsub__(self, other):
        return Vector(Vector(other)._v - self._v)

    def __mul__(self, scale):
        return Vector(self._v * scale)

    __rmul__ = __mul__

    def __truediv__(self, scale):
        return Vector(self._v / scale)

    def __neg__(self):
        return Vector(-self._v)

    def __abs__(self):
        return self.length

    def __eq__(self, other):
        try:
            return np.allclose(self._v, Vector(other)._v, atol=1e-6)
        except (TypeError, ValueError):
            return False

    def __hash__(self):
        return hash(tuple(round(c, 6) for c in self._v))

    def __repr__(self):
        return f"Vector({self.X:g}, {self.Y:g}, {self.Z:g})"


def euler_matrix(rx: float, ry: float, rz: float) -> np.ndarray:
    """build123d's default rotation: intrinsic X, then Y, then Z, in degrees."""
    a, b, c = (math.radians(x) for x in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


def axis_angle_matrix(axis, angle: float) -> np.ndarray:
    k = np.array(Vector(axis).normalized().to_tuple())
    a = math.radians(angle)
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(a) * K + (1 - math.cos(a)) * K @ K


class Location:
    """A rigid placement, held as a 4x4 matrix."""

    def __init__(self, *args):
        M = np.eye(4)
        if args:
            first = args[0]
            if isinstance(first, Location):
                M = first.M.copy()
            elif isinstance(first, Plane):
                M = first.matrix()
            elif isinstance(first, Axis):
                M = Plane(first.position, None, first.direction).matrix()
            else:
                if len(args) > 1:
                    if isinstance(args[1], (int, float)):
                        M[:3, :3] = axis_angle_matrix((0, 0, 1), args[1])
                    elif len(args) > 2 and isinstance(args[2], (int, float)):
                        M[:3, :3] = axis_angle_matrix(args[1], args[2])
                    else:
                        M[:3, :3] = euler_matrix(*Vector(args[1]))
                M[:3, 3] = Vector(first)._v
        self.M = M

    @classmethod
    def from_matrix(cls, M) -> Location:
        loc = cls()
        loc.M = np.array(M, float)
        return loc

    @property
    def position(self) -> Vector:
        return Vector(self.M[:3, 3])

    @property
    def orientation(self) -> Vector:
        """Intrinsic XYZ angles in degrees, as build123d reports them."""
        R = self.M[:3, :3]
        b = math.asin(max(-1.0, min(1.0, R[0, 2])))
        a = math.atan2(-R[1, 2], R[2, 2])
        c = math.atan2(-R[0, 1], R[0, 0])
        return Vector(*(math.degrees(x) for x in (a, b, c)))

    def inverse(self) -> Location:
        return Location.from_matrix(np.linalg.inv(self.M))

    def __neg__(self) -> Location:
        return self.inverse()

    def __mul__(self, other):
        if isinstance(other, Location):
            return Location.from_matrix(self.M @ other.M)
        if isinstance(other, Plane):
            return Location.from_matrix(self.M @ other.matrix())
        if hasattr(other, "moved"):
            return other.moved(self)
        if isinstance(other, Iterable):
            return [self * o for o in other]
        return NotImplemented

    def __eq__(self, other):
        return isinstance(other, Location) and np.allclose(self.M, other.M, atol=1e-12)

    def __repr__(self):
        return f"Location({self.position.to_tuple()}, {self.orientation.to_tuple()})"


def Pos(*args, X: float = 0.0, Y: float = 0.0, Z: float = 0.0) -> Location:  # noqa: N802
    if not args:
        return Location((X, Y, Z))
    if isinstance(args[0], (int, float)):
        return Location(Vector(*args))
    return Location(Vector(args[0]))


def Rotation(*args, X: float = 0.0, Y: float = 0.0, Z: float = 0.0) -> Location:  # noqa: N802
    if not args:
        angles = (X, Y, Z)
    elif len(args) == 1 and isinstance(args[0], (tuple, list, Vector)):
        angles = tuple(Vector(args[0]))
    else:
        angles = tuple(args) + (0.0,) * (3 - len(args))
    return Location((0, 0, 0), tuple(angles))


Rot = Rotation


class _PlaneMeta(type):
    XY = property(lambda cls: Plane((0, 0, 0), (1, 0, 0), (0, 0, 1)))
    YZ = property(lambda cls: Plane((0, 0, 0), (0, 1, 0), (1, 0, 0)))
    ZX = property(lambda cls: Plane((0, 0, 0), (0, 0, 1), (0, 1, 0)))
    XZ = property(lambda cls: Plane((0, 0, 0), (1, 0, 0), (0, -1, 0)))
    YX = property(lambda cls: Plane((0, 0, 0), (0, 1, 0), (0, 0, -1)))
    ZY = property(lambda cls: Plane((0, 0, 0), (0, 0, 1), (-1, 0, 0)))
    front = property(lambda cls: Plane((0, 0, 0), (1, 0, 0), (0, -1, 0)))
    back = property(lambda cls: Plane((0, 0, 0), (-1, 0, 0), (0, 1, 0)))
    left = property(lambda cls: Plane((0, 0, 0), (0, -1, 0), (-1, 0, 0)))
    right = property(lambda cls: Plane((0, 0, 0), (0, 1, 0), (1, 0, 0)))
    top = property(lambda cls: Plane((0, 0, 0), (1, 0, 0), (0, 0, 1)))
    bottom = property(lambda cls: Plane((0, 0, 0), (1, 0, 0), (0, 0, -1)))
    isometric = property(lambda cls: Plane((0, 0, 0), (1 / 2**0.5, 1 / 2**0.5, 0), (1 / 3**0.5, -1 / 3**0.5, 1 / 3**0.5)))


class Plane(metaclass=_PlaneMeta):
    """An origin with x and z directions (y = z x x), as build123d's Plane."""

    def __init__(self, origin=(0, 0, 0), x_dir=None, z_dir=(0, 0, 1)):
        if isinstance(origin, Location):
            M = origin.M
            origin, x_dir, z_dir = M[:3, 3], M[:3, 0], M[:3, 2]
        elif hasattr(origin, "_plane_frame"):  # a planar Face
            origin, x_dir, z_dir = origin._plane_frame()
        z = Vector(z_dir).normalized()
        if x_dir is None:
            # OpenCascade's choice of a perpendicular (gp_Ax3 from a single direction)
            x_dir = _default_x_dir(z)
        x = Vector(x_dir)
        x = (x - z * x.dot(z)).normalized()
        self.origin, self.x_dir, self.z_dir = Vector(origin), x, z
        self.y_dir = z.cross(x)

    def matrix(self) -> np.ndarray:
        M = np.eye(4)
        M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = self.x_dir._v, self.y_dir._v, self.z_dir._v, self.origin._v
        return M

    @property
    def location(self) -> Location:
        return Location(self)

    def offset(self, amount: float) -> Plane:
        return Plane(self.origin + self.z_dir * amount, self.x_dir, self.z_dir)

    def rotated(self, rotation=(0, 0, 0)) -> Plane:
        """The axes rotated (intrinsic XYZ, degrees, in global coordinates); the origin stays."""
        R = euler_matrix(*Vector(rotation))
        return Plane(self.origin, Vector(R @ self.x_dir._v), Vector(R @ self.z_dir._v))

    def move(self, loc: Location) -> Plane:
        return Plane(loc * self.location)

    def shift_origin(self, origin) -> Plane:
        return Plane(origin, self.x_dir, self.z_dir)

    def reverse(self) -> Plane:
        return Plane(self.origin, -self.x_dir, -self.z_dir)

    def __neg__(self) -> Plane:
        return self.reverse()

    def from_local_coords(self, obj):
        if hasattr(obj, "moved"):
            return obj.moved(self.location)
        return Vector(self.matrix()[:3, :3] @ Vector(obj)._v + self.origin._v)

    def to_local_coords(self, obj):
        if hasattr(obj, "moved"):
            return obj.moved(self.location.inverse())
        return Vector(self.matrix()[:3, :3].T @ (Vector(obj) - self.origin)._v)

    def __mul__(self, other):
        if isinstance(other, (Location, Plane)):
            return self.location * other
        if hasattr(other, "moved"):
            return other.moved(self.location)
        if isinstance(other, Iterable):
            return [self * o for o in other]
        return NotImplemented

    def __eq__(self, other):
        return isinstance(other, Plane) and np.allclose(self.matrix(), other.matrix(), atol=1e-9)

    def __repr__(self):
        return f"Plane(o={self.origin.to_tuple()}, x={self.x_dir.to_tuple()}, z={self.z_dir.to_tuple()})"


def _default_x_dir(z: Vector) -> Vector:
    """gp_Ax3(P, V): the X direction OpenCascade derives from a lone main direction."""
    A, B, C = z.X, z.Y, z.Z
    Aabs, Babs, Cabs = abs(A), abs(B), abs(C)
    if Babs <= Aabs and Babs <= Cabs:
        x = (-C, 0.0, A) if Aabs > Cabs else (C, 0.0, -A)
    elif Aabs <= Babs and Aabs <= Cabs:
        x = (0.0, -C, B) if Babs > Cabs else (0.0, C, -B)
    else:
        x = (-B, A, 0.0) if Aabs > Babs else (B, -A, 0.0)
    return Vector(x).normalized()


class _AxisMeta(type):
    X = property(lambda cls: Axis((0, 0, 0), (1, 0, 0)))
    Y = property(lambda cls: Axis((0, 0, 0), (0, 1, 0)))
    Z = property(lambda cls: Axis((0, 0, 0), (0, 0, 1)))


class Axis(metaclass=_AxisMeta):
    def __init__(self, origin=(0, 0, 0), direction=(0, 0, 1)):
        self.position, self.direction = Vector(origin), Vector(direction).normalized()

    @property
    def location(self) -> Location:
        return Location(self)

    def __neg__(self) -> Axis:
        return Axis(self.position, -self.direction)

    def __repr__(self):
        return f"Axis({self.position.to_tuple()}, {self.direction.to_tuple()})"


class BoundBox:
    def __init__(self, lo, hi):
        self.min, self.max = Vector(lo), Vector(hi)
        self.size = self.max - self.min

    @property
    def diagonal(self) -> float:
        return self.size.length

    def center(self) -> Vector:
        return (self.min + self.max) / 2

    def to_align_offset(self, align) -> Vector:
        return align_offset(self.min, self.max, align)

    def __repr__(self):
        return f"BoundBox({self.min}, {self.max})"


def align_offset(lo, hi, align) -> Vector:
    """The move that aligns the box [lo, hi] as build123d's to_align_offset does."""
    if align is None or align is Align.NONE:
        return Vector()
    if isinstance(align, Align):
        align = (align,) * 3
    out = []
    for a, mn, mx in zip(align, Vector(lo), Vector(hi)):
        out.append({Align.MIN: -mn, Align.CENTER: -(mn + mx) / 2, Align.MAX: -mx}.get(a, 0.0))
    return Vector(*out)


def tuplify(value, n):
    if value is None:
        return None
    return tuple(value) if isinstance(value, (tuple, list)) else (value,) * n


class Color:
    """An RGBA colour carried as a label; the kernel never sees it."""

    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], (tuple, list)):
            args = tuple(args[0])
        self.rgba = tuple(args) + ((1.0,) if len(args) == 3 else ())

    def __repr__(self):
        return f"Color{self.rgba}"
