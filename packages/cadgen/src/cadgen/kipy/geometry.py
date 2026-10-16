# Copyright The KiCad Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the “Software”), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import math
import sys

from cadgen.kipy.proto.common import types
from cadgen.kipy.util import from_mm
from cadgen.kipy.util.units import from_mils
from cadgen.kipy.wrapper import MutableWrapperSequence, Wrapper

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


class Vector2(Wrapper):
    """Wraps a kiapi.common.types.Vector2, aka VECTOR2I"""

    def __init__(
        self,
        proto: types.Vector2 | Wrapper | None = None,
        proto_ref: types.Vector2 | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.Vector2()

        if proto is not None:
            self._proto.CopyFrom(proto.proto if isinstance(proto, Wrapper) else proto)

    def __repr__(self):
        return f"Vector2({self.x}, {self.y})"

    @classmethod
    def from_xy(cls, x_nm: int, y_nm: int) -> Self:
        """Initialize Vector2 with x and y values in nanometers"""
        proto = types.Vector2()
        proto.x_nm = x_nm
        proto.y_nm = y_nm
        return cls(proto)

    @classmethod
    def from_xy_mm(cls, x_mm: float, y_mm: float) -> Self:
        """Initialize Vector2 with x and y values in mm

        .. versionadded:: 0.3.0"""
        proto = types.Vector2()
        proto.x_nm = from_mm(x_mm)
        proto.y_nm = from_mm(y_mm)
        return cls(proto)

    @classmethod
    def from_xy_mils(cls, x_mils: float, y_mils: float) -> Self:
        """Initialize Vector2 with x and y values in mils

        .. versionadded:: 0.x.y"""
        proto = types.Vector2()
        proto.x_nm = from_mils(x_mils)
        proto.y_nm = from_mils(y_mils)
        return cls(proto)

    @property
    def x(self) -> int:
        return self._proto.x_nm

    @x.setter
    def x(self, val: int):
        self._proto.x_nm = val

    @property
    def y(self) -> int:
        return self._proto.y_nm

    @y.setter
    def y(self, val: int):
        self._proto.y_nm = val

    def __hash__(self):
        return hash((self.x, self.y))

    def __eq__(self, other):
        if isinstance(other, Vector2):
            return self.x == other.x and self.y == other.y
        return NotImplemented

    def __add__(self, other: Vector2) -> Vector2:
        r = Vector2(self._proto)
        r.x += other.x
        r.y += other.y
        return r

    def __sub__(self, other: Vector2) -> Vector2:
        r = Vector2(self._proto)
        r.x -= other.x
        r.y -= other.y
        return r

    def __neg__(self) -> Vector2:
        r = Vector2(self._proto)
        r.x = -r.x
        r.y = -r.y
        return r

    def __mul__(self, scalar: float) -> Vector2:
        r = Vector2(self._proto)
        r.x = int(float(r.x) * scalar)
        r.y = int(float(r.y) * scalar)
        return r

    def __iadd__(self, other: Vector2) -> Self:
        self.x += other.x
        self.y += other.y
        return self

    def __isub__(self, other: Vector2) -> Self:
        self.x -= other.x
        self.y -= other.y
        return self

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y)

    def angle(self) -> float:
        """Returns the angle (direction) of the vector in radians"""
        return math.atan2(self.y, self.x)

    def angle_degrees(self) -> float:
        """Returns the angle (direction) of the vector in degrees

        .. versionadded:: 0.3.0
        """
        return math.degrees(self.angle())

    def rotate(self, angle: Angle, center: Vector2) -> Vector2:
        """Rotates the vector in-place by an angle in degrees around a center point

        :param angle: The angle to rotate by
        :param center: The center point to rotate around
        :return: The rotated vector

        .. versionadded:: 0.4.0
        """
        pt_x = self.x - center.x
        pt_y = self.y - center.y
        rotation = normalize_angle_radians(angle.to_radians())

        sin_angle = math.sin(rotation)
        cos_angle = math.cos(rotation)

        self.x = int(pt_y * sin_angle + pt_x * cos_angle) + center.x
        self.y = int(pt_y * cos_angle - pt_x * sin_angle) + center.y

        return self


class Vector3D(Wrapper):
    """Wraps a kiapi.common.types.Vector3D"""

    def __init__(self, proto: types.Vector3D | None = None):
        self._proto = types.Vector3D()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self):
        return f"Vector3D({self.x}, {self.y}, {self.z})"

    @classmethod
    def from_xyz(cls, x_nm: float, y_nm: float, z_nm: float) -> Self:
        """Initialize Vector3D with x, y, and z values in nanometers"""
        proto = types.Vector3D()
        proto.x_nm = x_nm
        proto.y_nm = y_nm
        proto.z_nm = z_nm
        return cls(proto)

    @property
    def x(self) -> float:
        return self._proto.x_nm

    @x.setter
    def x(self, val: float):
        self._proto.x_nm = val

    @property
    def y(self) -> float:
        return self._proto.y_nm

    @y.setter
    def y(self, val: float):
        self._proto.y_nm = val

    @property
    def z(self) -> float:
        return self._proto.z_nm

    @z.setter
    def z(self, val: float):
        self._proto.z_nm = val

    def __hash__(self):
        return hash((self.x, self.y, self.z))

    def __eq__(self, other):
        if isinstance(other, Vector3D):
            return self.x == other.x and self.y == other.y and self.z == other.z
        return NotImplemented

    def __add__(self, other: Vector3D) -> Vector3D:
        r = Vector3D(self._proto)
        r.x += other.x
        r.y += other.y
        r.z += other.z
        return r

    def __sub__(self, other: Vector3D) -> Vector3D:
        r = Vector3D(self._proto)
        r.x -= other.x
        r.y -= other.y
        r.z -= other.z
        return r

    def __neg__(self) -> Vector3D:
        r = Vector3D(self._proto)
        r.x = -r.x
        r.y = -r.y
        r.z = -r.z
        return r

    def __mul__(self, scalar: float) -> Vector3D:
        r = Vector3D(self._proto)
        r.x = r.x * scalar
        r.y = r.y * scalar
        r.z = r.z * scalar
        return r

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)


class Box2:
    def __init__(
        self,
        pos_proto: types.Vector2 | None = None,
        size_proto: types.Vector2 | None = None,
    ):
        self._pos_proto = types.Vector2()
        self._size_proto = types.Vector2()

        if pos_proto is not None:
            self._pos_proto.CopyFrom(pos_proto)

        if size_proto is not None:
            self._size_proto.CopyFrom(size_proto)

    def __repr__(self):
        return f"Box2(pos={self.pos}, size={self.size})"

    @classmethod
    def from_xywh(cls, x_nm: int, y_nm: int, w_nm: int, h_nm: int) -> Self:
        pos = Vector2.from_xy(x_nm, y_nm)
        size = Vector2.from_xy(w_nm, h_nm)
        return cls(pos._proto, size._proto)

    @classmethod
    def from_pos_size(cls, pos: Vector2, size: Vector2) -> Self:
        return cls(pos._proto, size._proto)

    @classmethod
    def from_proto(cls, other: types.Box2) -> Self:
        return cls(other.position, other.size)

    @classmethod
    def from_points(cls, points: list[Vector2]) -> Self:
        """Constructs a box that contains all the given points

        .. versionadded:: 0.7.0"""
        if len(points) == 0:
            return cls()

        box = cls.from_pos_size(points[0], Vector2.from_xy(0, 0))

        for point in points[1:]:
            box.merge(point)

        return box

    @property
    def pos(self) -> Vector2:
        return Vector2(self._pos_proto)

    @property
    def size(self) -> Vector2:
        return Vector2(self._size_proto)

    def move(self, delta: Vector2):
        self._pos_proto.x_nm += delta.x
        self._pos_proto.y_nm += delta.y

    def center(self) -> Vector2:
        center_x = self._pos_proto.x_nm + self._size_proto.x_nm // 2
        center_y = self._pos_proto.y_nm + self._size_proto.y_nm // 2
        return Vector2.from_xy(center_x, center_y)

    def merge(self, other: Vector2 | Box2):
        if isinstance(other, Vector2):
            min_x = min(self.pos.x, other.x)
            min_y = min(self.pos.y, other.y)
            max_x = max(self.pos.x + self.size.x, other.x)
            max_y = max(self.pos.y + self.size.y, other.y)
        else:
            min_x = min(self.pos.x, other.pos.x)
            min_y = min(self.pos.y, other.pos.y)
            max_x = max(self.pos.x + self.size.x, other.pos.x + other.size.x)
            max_y = max(self.pos.y + self.size.y, other.pos.y + other.size.y)

        self._pos_proto.x_nm = min_x
        self._pos_proto.y_nm = min_y
        self._size_proto.x_nm = max_x - min_x
        self._size_proto.y_nm = max_y - min_y

    def inflate(self, amount: int):
        new_width = self.size.x + amount
        new_height = self.size.y + amount
        self._pos_proto.x_nm -= (new_width - self.size.x) // 2
        self._pos_proto.y_nm -= (new_height - self.size.y) // 2
        self._size_proto.x_nm = new_width
        self._size_proto.y_nm = new_height


class Angle(Wrapper):
    def __init__(
        self,
        proto: types.Angle | Wrapper | None = None,
        proto_ref: types.Angle | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.Angle()

        if proto is not None:
            self._proto.CopyFrom(proto.proto if isinstance(proto, Wrapper) else proto)

    def __repr__(self):
        return f"Angle({self.degrees})"

    @classmethod
    def from_degrees(cls, degrees: float) -> Self:
        """Initialize Angle with a value in degrees"""
        proto = types.Angle()
        proto.value_degrees = degrees
        return cls(proto)

    @property
    def degrees(self) -> float:
        return self._proto.value_degrees

    @degrees.setter
    def degrees(self, val: float):
        self._proto.value_degrees = val

    def __eq__(self, other):
        if isinstance(other, Angle):
            return self.degrees == other.degrees
        return NotImplemented

    def __iadd__(self, other: Angle) -> Self:
        self.degrees += other.degrees
        return self

    def __isub__(self, other: Angle) -> Self:
        self.degrees -= other.degrees
        return self

    def __add__(self, other: Angle) -> Angle:
        return Angle.from_degrees(self.degrees + other.degrees)

    def __sub__(self, other: Angle) -> Angle:
        return Angle.from_degrees(self.degrees - other.degrees)

    def __neg__(self) -> Angle:
        return Angle.from_degrees(-self.degrees)

    def __mul__(self, scalar: float) -> Angle:
        return Angle.from_degrees(self.degrees * scalar)

    def to_radians(self) -> float:
        return math.radians(self.degrees)

    def normalize(self) -> Angle:
        """Normalizes the angle to fall within the range [0, 360)

        .. versionadded:: 0.4.0"""
        while self.degrees < 0.0:
            self.degrees += 360.0

        while self.degrees >= 360.0:
            self.degrees -= 360.0

        return self

    def normalize180(self) -> Angle:
        """Normalizes the angle to fall within the range [-180, 180)

        .. versionadded:: 0.4.0"""
        while self.degrees <= -180.0:
            self.degrees += 360.0

        while self.degrees > 180.0:
            self.degrees -= 360.0

        return self


class ArcStartMidEnd(Wrapper):
    def __init__(
        self,
        proto: types.ArcStartMidEnd | None = None,
        proto_ref: types.ArcStartMidEnd | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.ArcStartMidEnd()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self):
        return f"ArcStartMidEnd(start={self.start}, mid={self.mid}, end={self.end})"

    @property
    def start(self) -> Vector2:
        return Vector2(self._proto.start)

    @start.setter
    def start(self, val: Vector2):
        self._proto.start.CopyFrom(val._proto)

    @property
    def mid(self) -> Vector2:
        return Vector2(self._proto.mid)

    @mid.setter
    def mid(self, val: Vector2):
        self._proto.mid.CopyFrom(val._proto)

    @property
    def end(self) -> Vector2:
        return Vector2(self._proto.end)

    @end.setter
    def end(self, val: Vector2):
        self._proto.end.CopyFrom(val._proto)

    def center(self) -> Vector2 | None:
        """
        Calculates the center of the arc.  Uses a different algorithm than KiCad so may have
        slightly different results.  The KiCad API preserves the start, middle, and end points of
        the arc, so any other properties such as the center point and angles must be calculated

        :return: The center of the arc, or None if the arc is degenerate
        """
        # TODO we may want to add an API call to get KiCad to calculate this for us,
        # for situations where matching KiCad's behavior exactly is important
        return arc_center(self.start, self.mid, self.end)

    def radius(self) -> float:
        """
        Calculates the radius of the arc.  Uses a different algorithm than KiCad so may have
        slightly different results.  The KiCad API preserves the start, middle, and end points of
        the arc, so any other properties such as the center point and angles must be calculated

        :return: The radius of the arc, or 0 if the arc is degenerate
        """
        # TODO we may want to add an API call to get KiCad to calculate this for us,
        # for situations where matching KiCad's behavior exactly is important
        return arc_radius(self.start, self.mid, self.end)

    def start_angle(self) -> float | None:
        return arc_start_angle(self.start, self.mid, self.end)

    def end_angle(self) -> float | None:
        return arc_end_angle(self.start, self.mid, self.end)

    def bounding_box(self) -> Box2:
        """Returns the bounding box of the arc -- not calculated by KiCad; may differ from KiCad's"""
        return arc_bounding_box(self.start, self.mid, self.end)


class PolyLineNode(Wrapper):
    def __init__(
        self,
        proto: types.PolyLineNode | None = None,
        proto_ref: types.PolyLineNode | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.PolyLineNode()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @staticmethod
    def from_point(point: Vector2) -> PolyLineNode:
        n = PolyLineNode()
        n.point = point
        return n

    @staticmethod
    def from_xy(x: int, y: int) -> PolyLineNode:
        n = PolyLineNode()
        n.point = Vector2.from_xy(x, y)
        return n

    def __repr__(self):
        if self.has_point:
            return f"PolyLineNode(point={self.point})"
        elif self.has_arc:
            return f"PolyLineNode(arc={self.arc})"
        return "PolyLineNode()"

    @property
    def has_point(self) -> bool:
        return self._proto.HasField("point")

    @property
    def point(self) -> Vector2:
        return Vector2(self._proto.point)

    @point.setter
    def point(self, val: Vector2):
        self._proto.point.CopyFrom(val._proto)

    @property
    def has_arc(self) -> bool:
        return self._proto.HasField("arc")

    @property
    def arc(self) -> ArcStartMidEnd:
        return ArcStartMidEnd(proto_ref=self._proto.arc)

    @arc.setter
    def arc(self, val: ArcStartMidEnd):
        self._proto.arc.CopyFrom(val._proto)


class PolyLine(Wrapper):
    def __init__(
        self,
        proto: types.PolyLine | None = None,
        proto_ref: types.PolyLine | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.PolyLine()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self):
        return f"PolyLine(nodes={self.nodes}, closed={self.closed})"

    @property
    def nodes(self) -> MutableWrapperSequence[PolyLineNode]:
        return MutableWrapperSequence(self._proto.nodes, PolyLineNode)

    @property
    def closed(self) -> bool:
        return self._proto.closed

    @closed.setter
    def closed(self, val: bool):
        self._proto.closed = val

    def __iter__(self):
        return iter(self.nodes)

    def __len__(self):
        return len(self.nodes)

    def __getitem__(self, index: int) -> PolyLineNode:
        return self.nodes[index]

    def __setitem__(self, index: int, value: PolyLineNode):
        self._proto.nodes[index].CopyFrom(value._proto)

    def append(self, node: PolyLineNode):
        self._proto.nodes.append(node._proto)

    def insert(self, index: int, node: PolyLineNode):
        self._proto.nodes.insert(index, node._proto)

    def remove(self, node: PolyLineNode):
        self._proto.nodes.remove(node._proto)

    def clear(self):
        self._proto.ClearField("nodes")

    def rotate(self, delta: Angle, center: Vector2):
        for node in self.nodes:
            if node.has_point:
                node.point = node.point.rotate(delta, center)
            elif node.has_arc:
                node.arc.start = node.arc.start.rotate(delta, center)
                node.arc.mid = node.arc.mid.rotate(delta, center)
                node.arc.end = node.arc.end.rotate(delta, center)


class PolygonWithHoles(Wrapper):
    def __init__(
        self,
        proto: types.PolygonWithHoles | None = None,
        proto_ref: types.PolygonWithHoles | None = None,
        auto_close: bool = True,
    ):
        """Creates a polygon with an outline and optional holes.

        :param auto_close: If true (the default), assigning :attr:`outline` forces the
            outline's :attr:`PolyLine.closed` flag to True.  Set to false to preserve the
            assigned polyline's own :attr:`PolyLine.closed` flag, e.g. to build an open polyline
            for the schematic editor.
        """
        self._proto = proto_ref if proto_ref is not None else types.PolygonWithHoles()

        if proto is not None:
            self._proto.CopyFrom(proto)

        self._auto_close = auto_close

    def __repr__(self):
        return f"PolygonWithHoles(outline={self.outline}, holes={self.holes})"

    @property
    def outline(self) -> PolyLine:
        return PolyLine(proto_ref=self._proto.outline)

    @outline.setter
    def outline(self, outline: PolyLine):
        self._proto.outline.CopyFrom(outline._proto)

        if self._auto_close:
            self._proto.outline.closed = True

    @property
    def holes(self) -> MutableWrapperSequence[PolyLine]:
        return MutableWrapperSequence(self._proto.holes, PolyLine)

    def add_hole(self, hole: PolyLine):
        # Holes must be a closed shape
        hole.closed = True
        self._proto.holes.append(hole._proto)

    def remove_hole(self, hole: PolyLine):
        self._proto.holes.remove(hole._proto)

    def bounding_box(self) -> Box2:
        if not self.outline.nodes:
            return Box2()

        min_x = math.inf
        min_y = math.inf
        max_x = -math.inf
        max_y = -math.inf

        for node in self.outline:
            if node.has_point:
                min_x = min(min_x, node.point.x)
                min_y = min(min_y, node.point.y)
                max_x = max(max_x, node.point.x)
                max_y = max(max_y, node.point.y)
            elif node.has_arc:
                box = node.arc.bounding_box()
                min_x = min(min_x, box.pos.x)
                min_y = min(min_y, box.pos.y)
                max_x = max(max_x, box.pos.x + box.size.x)
                max_y = max(max_y, box.pos.y + box.size.y)

        return Box2.from_pos_size(
            Vector2.from_xy(int(min_x), int(min_y)),
            Vector2.from_xy(int(max_x - min_x), int(max_y - min_y)),
        )

    def move(self, delta: Vector2):
        for node in self.outline:
            if node.has_point:
                node.point += delta
            elif node.has_arc:
                node.arc.start += delta
                node.arc.mid += delta
                node.arc.end += delta

        for hole in self.holes:
            for node in hole:
                if node.has_point:
                    node.point += delta
                elif node.has_arc:
                    node.arc.start += delta
                    node.arc.mid += delta
                    node.arc.end += delta

    def rotate(self, delta: Angle, center: Vector2 | None = None):
        if center is None:
            center = self.bounding_box().center()

        self.outline.rotate(delta, center)

        for hole in self.holes:
            hole.rotate(delta, center)


def arc_center(start: Vector2, mid: Vector2, end: Vector2) -> Vector2 | None:
    """
    Calculates the center of the arc.  Uses a different algorithm than KiCad so may have
    slightly different results.  The KiCad API preserves the start, middle, and end points of
    the arc, so any other properties such as the center point and angles must be calculated

    :return: The center of the arc, or None if the arc is degenerate
    """
    # TODO we may want to add an API call to get KiCad to calculate this for us,
    # for situations where matching KiCad's behavior exactly is important
    if start == end:
        return (start + mid) * 0.5

    def perpendicular_bisector(p1: Vector2, p2: Vector2):
        mid_point = (p1 + p2) * 0.5
        direction = p2 - p1
        perpendicular_direction = Vector2.from_xy(-direction.y, direction.x)
        return mid_point, perpendicular_direction

    mid1, dir1 = perpendicular_bisector(start, mid)
    mid2, dir2 = perpendicular_bisector(mid, end)

    det = float(dir1.x * dir2.y - dir1.y * dir2.x)

    if det == 0:
        return None

    # Intersect the two perpendicular bisectors to find the center
    t = ((mid2.x - mid1.x) * dir2.y - (mid2.y - mid1.y) * dir2.x) / det
    center = mid1 + (dir1 * t)

    return center


def arc_radius(start: Vector2, mid: Vector2, end: Vector2) -> float:
    """
    Calculates the radius of the arc.  Uses a different algorithm than KiCad so may have
    slightly different results.  The KiCad API preserves the start, middle, and end points of
    the arc, so any other properties such as the center point and angles must be calculated

    :return: The radius of the arc, or 0 if the arc is degenerate
    """
    # TODO we may want to add an API call to get KiCad to calculate this for us,
    # for situations where matching KiCad's behavior exactly is important
    center = arc_center(start, mid, end)
    if center is None:
        return 0

    return (start - center).length()


def normalize_angle_degrees(angle: float) -> float:
    """Normalizes an angle to fall within the range [0, 360)

    .. versionadded:: 0.3.0"""
    while angle < 0.0:
        angle += 360.0

    while angle >= 360.0:
        angle -= 360.0

    return angle


def normalize_angle_radians(angle: float) -> float:
    """Normalizes an angle to fall within the range [0, 2*pi)

    .. versionadded:: 0.3.0"""
    while angle < 0.0:
        angle += 2 * math.pi

    while angle >= 2 * math.pi:
        angle -= 2 * math.pi

    return angle


def normalize_angle_pi_radians(angle: float) -> float:
    """Normalizes an angle to fall within the range (-pi, pi]

    .. versionadded:: 0.4.0"""
    while angle <= -math.pi:
        angle += 2 * math.pi

    while angle > math.pi:
        angle -= 2 * math.pi

    return angle


def arc_start_angle(start: Vector2, mid: Vector2, end: Vector2) -> float | None:
    """Calculates the arc's starting angle in radians, normalized to [0, 2*pi)

    :return: The starting angle of the arc, or None if the arc is degenerate"""
    center = arc_center(start, mid, end)
    if center is None:
        return None

    return normalize_angle_radians((start - center).angle())


def arc_end_angle(start: Vector2, mid: Vector2, end: Vector2) -> float | None:
    """Calculates the arc's ending angle in radians, normalized to [0, 2*pi)

    :return: The ending angle of the arc, or None if the arc is degenerate"""
    center = arc_center(start, mid, end)
    if center is None:
        return None

    angle = (end - center).angle()

    start_angle = arc_start_angle(start, mid, end)
    assert start_angle is not None

    if angle == start_angle:
        angle += 2 * math.pi

    return normalize_angle_radians(angle)


def arc_angle(start: Vector2, mid: Vector2, end: Vector2) -> float | None:
    """Calculates the angle between the start and end of the arc in radians

    :return: The angle of the arc, or None if the arc is degenerate

    .. versionadded:: 0.4.0"""
    center = arc_center(start, mid, end)
    if center is None:
        return None

    angle1 = (mid - center).angle() - (start - center).angle()
    angle2 = (end - center).angle() - (mid - center).angle()

    return abs(normalize_angle_pi_radians(angle1) + normalize_angle_pi_radians(angle2))


def arc_bounding_box(start: Vector2, mid: Vector2, end: Vector2) -> Box2:
    """Calculates a bounding box for an arc

    .. versionadded:: 0.7.0"""

    def ccw_delta(start_angle: float, end_angle: float) -> float:
        return (end_angle - start_angle) % (2 * math.pi)

    center = arc_center(start, mid, end)
    if center is None:
        return Box2.from_points([start, mid, end])

    radius = arc_radius(start, mid, end)
    if radius == 0:
        return Box2.from_points([start, mid, end])

    start_angle = arc_start_angle(start, mid, end)
    mid_angle = normalize_angle_radians((mid - center).angle())
    end_angle = arc_end_angle(start, mid, end)
    assert start_angle is not None
    assert end_angle is not None

    radius_int = int(radius + 0.5)
    box = Box2.from_points([start, end])

    if start == end and mid != start:
        box.merge(Vector2.from_xy(center.x + radius_int, center.y))
        box.merge(Vector2.from_xy(center.x, center.y + radius_int))
        box.merge(Vector2.from_xy(center.x - radius_int, center.y))
        box.merge(Vector2.from_xy(center.x, center.y - radius_int))
        return box

    ccw_to_mid = ccw_delta(start_angle, mid_angle)
    ccw_to_end = ccw_delta(start_angle, end_angle)
    ccw = ccw_to_mid <= ccw_to_end

    def angle_on_arc(theta: float) -> bool:
        if ccw:
            return ccw_delta(start_angle, theta) <= ccw_to_end

        return ccw_delta(theta, start_angle) <= ccw_delta(end_angle, start_angle)

    for theta, point in (
        (0.0, Vector2.from_xy(center.x + radius_int, center.y)),
        (math.pi * 0.5, Vector2.from_xy(center.x, center.y + radius_int)),
        (math.pi, Vector2.from_xy(center.x - radius_int, center.y)),
        (math.pi * 1.5, Vector2.from_xy(center.x, center.y - radius_int)),
    ):
        if angle_on_arc(theta):
            box.merge(point)

    return box


def arc_start_angle_degrees(start: Vector2, mid: Vector2, end: Vector2) -> float | None:
    """Calculates the arc's starting angle in degrees, normalized to [0, 360)

    .. versionadded:: 0.3.0
    """
    center = arc_center(start, mid, end)
    if center is None:
        return None

    return normalize_angle_degrees((start - center).angle_degrees())


def arc_end_angle_degrees(start: Vector2, mid: Vector2, end: Vector2) -> float | None:
    """Calculates the arc's ending angle in degrees, normalized to [0, 360)

    .. versionadded:: 0.3.0
    """
    center = arc_center(start, mid, end)
    if center is None:
        return None

    angle = (end - center).angle_degrees()

    start_angle = arc_start_angle(start, mid, end)
    assert start_angle is not None

    if angle == start_angle:
        angle += 360

    return normalize_angle_degrees(angle)
