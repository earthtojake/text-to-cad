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

import base64
import sys
from collections.abc import Sequence
from pathlib import Path

import zstandard

from cadgen.kipy.geometry import (
    Angle,
    Box2,
    PolygonWithHoles,
    PolyLine,
    Vector2,
    arc_angle,
    arc_bounding_box,
    arc_center,
    arc_end_angle,
    arc_radius,
    arc_start_angle,
)
from cadgen.kipy.proto.common import types
from cadgen.kipy.proto.common.types import (
    base_types_pb2,
    embedded_files_pb2,
    jobs_pb2,
    library_types_pb2,
    variants_pb2,
)
from cadgen.kipy.proto.common.types.base_types_pb2 import (  # noqa
    KIID,
    GraphicFillType,
    LineEndingStyle,
    PageOrientation,
    PageSize,
)

# Re-exported protobuf enum types
from cadgen.kipy.proto.common.types.embedded_files_pb2 import (
    EmbeddedFileType,
)
from cadgen.kipy.proto.common.types.enums_pb2 import (  # noqa
    HorizontalAlignment,
    PathType,
    StrokeLineStyle,
    VerticalAlignment,
)
from cadgen.kipy.util.units import to_mm
from cadgen.kipy.wrapper import MutableWrapperSequence, Wrapper

if sys.version_info >= (3, 13):
    from warnings import deprecated
else:
    from typing_extensions import deprecated

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


class Commit:
    def __init__(self, id: KIID):
        self._id = id

    @property
    def id(self) -> KIID:
        return self._id


class SheetPath(Wrapper):
    """Represents the path to a unique sheet instance or symbol instance in a schematic"""

    def __init__(
        self,
        proto: types.SheetPath | None = None,
        proto_ref: types.SheetPath | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.SheetPath()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return "/" + "/".join([id.value for id in self.path])

    @property
    def path(self) -> list[KIID]:
        return list(self._proto.path)

    @path.setter
    def path(self, path: list[KIID]):
        del self._proto.path[:]
        self._proto.path.extend(path)

    @property
    def path_human_readable(self) -> str:
        """The sheet path with human-readable sheet names.  May not be available in all contexts
        (for example, is not present in contexts where the SheetPath is sourced from a board
        object)"""
        return self._proto.path_human_readable


class Color(Wrapper):
    def __init__(
        self,
        proto: types.Color | None = None,
        proto_ref: types.Color | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.Color()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def red(self) -> float:
        return self._proto.r

    @red.setter
    def red(self, red: float):
        self._proto.r = red

    @property
    def green(self) -> float:
        return self._proto.g

    @green.setter
    def green(self, green: float):
        self._proto.g = green

    @property
    def blue(self) -> float:
        return self._proto.b

    @blue.setter
    def blue(self, blue: float):
        self._proto.b = blue

    @property
    def alpha(self) -> float:
        return self._proto.a

    @alpha.setter
    def alpha(self, alpha: float):
        self._proto.a = alpha


class TextAttributes(Wrapper):
    def __init__(
        self,
        proto: types.TextAttributes | None = None,
        proto_ref: types.TextAttributes | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.TextAttributes()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"TextAttributes(font_name={self.font_name}, angle={self.angle}, "
            f"line_spacing={self.line_spacing}, italic={self.italic}, bold={self.bold}, "
            f"underlined={self.underlined}, mirrored={self.mirrored}, multiline={self.multiline}, "
            f"keep_upright={self.keep_upright}, size={self.size})"
        )

    @property
    @deprecated(
        "This property will always return True in KiCad 9, and will be removed in KiCad 10"
    )
    def visible(self) -> bool:
        """
        .. deprecated:: 0.3.0 removed in KiCad 9.0.1

        Text items are always visible as of 9.0.1, only Fields can be set to hidden
        """
        return self._proto.visible

    @visible.setter
    def visible(self, visible: bool):
        self._proto.visible = visible

    @property
    def font_name(self) -> str:
        return self._proto.font_name

    @font_name.setter
    def font_name(self, font_name: str):
        self._proto.font_name = font_name

    @property
    def angle(self) -> float:
        """The orientation of the text in degrees"""
        return self._proto.angle.value_degrees

    @angle.setter
    def angle(self, angle: float):
        self._proto.angle.value_degrees = angle

    @property
    def line_spacing(self) -> float:
        return self._proto.line_spacing

    @line_spacing.setter
    def line_spacing(self, line_spacing: float):
        self._proto.line_spacing = line_spacing

    @property
    def stroke_width(self) -> int:
        return self._proto.stroke_width.value_nm

    @stroke_width.setter
    def stroke_width(self, stroke_width: int):
        self._proto.stroke_width.value_nm = stroke_width

    @property
    def italic(self) -> bool:
        return self._proto.italic

    @italic.setter
    def italic(self, italic: bool):
        self._proto.italic = italic

    @property
    def bold(self) -> bool:
        return self._proto.bold

    @bold.setter
    def bold(self, bold: bool):
        self._proto.bold = bold

    @property
    def underlined(self) -> bool:
        return self._proto.underlined

    @underlined.setter
    def underlined(self, underlined: bool):
        self._proto.underlined = underlined

    @property
    def mirrored(self) -> bool:
        return self._proto.mirrored

    @mirrored.setter
    def mirrored(self, mirrored: bool):
        self._proto.mirrored = mirrored

    @property
    def multiline(self) -> bool:
        return self._proto.multiline

    @multiline.setter
    def multiline(self, multiline: bool):
        self._proto.multiline = multiline

    @property
    def keep_upright(self) -> bool:
        return self._proto.keep_upright

    @keep_upright.setter
    def keep_upright(self, keep_upright: bool):
        self._proto.keep_upright = keep_upright

    @property
    def size(self) -> Vector2:
        return Vector2(proto_ref=self._proto.size)

    @size.setter
    def size(self, size: Vector2):
        self._proto.size.CopyFrom(size.proto)

    @property
    def horizontal_alignment(self) -> types.HorizontalAlignment.ValueType:
        return self._proto.horizontal_alignment

    @horizontal_alignment.setter
    def horizontal_alignment(self, alignment: types.HorizontalAlignment.ValueType):
        self._proto.horizontal_alignment = alignment

    @property
    def vertical_alignment(self) -> types.VerticalAlignment.ValueType:
        return self._proto.vertical_alignment

    @vertical_alignment.setter
    def vertical_alignment(self, alignment: types.VerticalAlignment.ValueType):
        self._proto.vertical_alignment = alignment


class LibraryIdentifier(Wrapper):
    """A KiCad library identifier (LIB_ID), consisting of a library nickname and entry name"""

    def __init__(
        self,
        proto: types.LibraryIdentifier | None = None,
        proto_ref: types.LibraryIdentifier | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.LibraryIdentifier()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def library(self) -> str:
        return self._proto.library_nickname

    @library.setter
    def library(self, library: str):
        self._proto.library_nickname = library

    @property
    def name(self) -> str:
        return self._proto.entry_name

    @name.setter
    def name(self, name: str):
        self._proto.entry_name = name

    def __str__(self) -> str:
        return f"{self.library}:{self.name}"


class LibraryStatus(Wrapper):
    def __init__(
        self,
        proto: types.LibraryStatusEntry | None = None,
        proto_ref: types.LibraryStatusEntry | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.LibraryStatusEntry()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        status = library_types_pb2.LibraryLoadStatus.Name(self.status)
        return f"LibraryStatus({self.nickname!r}, {status})"

    @property
    def nickname(self) -> str:
        """The library nickname (the first part of a LIB_ID)"""
        return self._proto.entry.nickname

    @property
    def type(self) -> library_types_pb2.LibraryType.ValueType:
        """The kind of content managed by this library"""
        return self._proto.entry.type

    @property
    def scope(self) -> library_types_pb2.LibraryTableScope.ValueType:
        """Which library table this library belongs to"""
        return self._proto.entry.scope

    @property
    def status(self) -> library_types_pb2.LibraryLoadStatus.ValueType:
        """The load status of this library"""
        return self._proto.status

    @property
    def error_message(self) -> str | None:
        """The error message if the library failed to load, otherwise ``None``"""
        if self._proto.HasField("error_message"):
            return self._proto.error_message

        return None


class StrokeAttributes(Wrapper):
    def __init__(
        self,
        proto: types.StrokeAttributes | None = None,
        proto_ref: types.StrokeAttributes | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.StrokeAttributes()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def color(self) -> Color:
        """The stroke color.  Only supported in schematic graphics."""
        return Color(proto_ref=self._proto.color)

    @color.setter
    def color(self, color: Color):
        self._proto.color.CopyFrom(color.proto)

    @property
    def width(self) -> int:
        """The stroke line width in nanometers"""
        return self._proto.width.value_nm

    @width.setter
    def width(self, width: int):
        self._proto.width.value_nm = width

    @property
    def style(self) -> types.StrokeLineStyle.ValueType:
        return self._proto.style

    @style.setter
    def style(self, style: types.StrokeLineStyle.ValueType):
        self._proto.style = style


class GraphicFillAttributes(Wrapper):
    def __init__(
        self,
        proto: types.GraphicFillAttributes | None = None,
        proto_ref: types.GraphicFillAttributes | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.GraphicFillAttributes()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def filled(self) -> bool:
        return self._proto.fill_type == types.GraphicFillType.GFT_FILLED

    @filled.setter
    def filled(self, fill: bool):
        self._proto.fill_type = (
            types.GraphicFillType.GFT_FILLED if fill else types.GraphicFillType.GFT_UNFILLED
        )

    @property
    def color(self) -> Color:
        """The fill color.  Only supported in schematic graphics."""
        return Color(proto_ref=self._proto.color)

    @color.setter
    def color(self, color: Color):
        self._proto.color.CopyFrom(color.proto)


class GraphicAttributes(Wrapper):
    def __init__(
        self,
        proto: types.GraphicAttributes | None = None,
        proto_ref: types.GraphicAttributes | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.GraphicAttributes()

        if proto is not None:
            self._proto.CopyFrom(proto)

        self._stroke = StrokeAttributes(proto_ref=self._proto.stroke)
        self._fill = GraphicFillAttributes(proto_ref=self._proto.fill)

    @property
    def stroke(self) -> StrokeAttributes:
        return self._stroke

    @property
    def fill(self) -> GraphicFillAttributes:
        return self._fill


class Text(Wrapper):
    """Common text properties (wrapper for KiCad's EDA_TEXT) shared between board and schematic"""

    def __init__(self, proto: types.Text | None = None, proto_ref: types.Text | None = None):
        self._proto = proto_ref if proto_ref is not None else types.Text()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def position(self) -> Vector2:
        return Vector2(proto_ref=self._proto.position)

    @position.setter
    def position(self, pos: Vector2):
        self._proto.position.CopyFrom(pos.proto)

    @property
    def value(self) -> str:
        return self._proto.text

    @value.setter
    def value(self, text: str):
        self._proto.text = text

    @property
    def attributes(self) -> TextAttributes:
        return TextAttributes(proto_ref=self._proto.attributes)

    @attributes.setter
    def attributes(self, attributes: TextAttributes):
        self._proto.attributes.CopyFrom(attributes.proto)


class TextBox(Wrapper):
    def __init__(
        self,
        proto: types.TextBox | None = None,
        proto_ref: types.TextBox | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.TextBox()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def top_left(self) -> Vector2:
        return Vector2(proto_ref=self._proto.top_left)

    @top_left.setter
    def top_left(self, pos: Vector2):
        self._proto.top_left.CopyFrom(pos.proto)

    @property
    def bottom_right(self) -> Vector2:
        return Vector2(proto_ref=self._proto.bottom_right)

    @bottom_right.setter
    def bottom_right(self, pos: Vector2):
        self._proto.bottom_right.CopyFrom(pos.proto)

    @property
    def attributes(self) -> TextAttributes:
        return TextAttributes(proto_ref=self._proto.attributes)

    @attributes.setter
    def attributes(self, attributes: TextAttributes):
        self._proto.attributes.CopyFrom(attributes.proto)

    @property
    def value(self) -> str:
        return self._proto.text

    @value.setter
    def value(self, text: str):
        self._proto.text = text

    @property
    def size(self) -> Vector2:
        return self.bottom_right - self.top_left

    @size.setter
    def size(self, size: Vector2):
        new_br = self.top_left + size
        self._proto.bottom_right.CopyFrom(new_br.proto)


class GraphicShape(Wrapper):
    """Represents an abstract graphic shape (not a board or schematic item)"""

    def __init__(
        self,
        proto: base_types_pb2.GraphicShape | None = None,
        proto_ref: base_types_pb2.GraphicShape | None = None,
    ):
        self._graphic_proto = proto_ref if proto_ref is not None else base_types_pb2.GraphicShape()

        if proto is not None:
            self._graphic_proto.CopyFrom(proto)

    @property
    def proto(self):
        self._pack()
        return self._graphic_proto

    @classmethod
    def from_concrete(cls, value: GraphicShape) -> GraphicShape:
        """Packs a concrete shape subclass into a GraphicShape of the static base type"""
        assert isinstance(value, cls)
        if type(value) is cls:
            return value
        proto = base_types_pb2.GraphicShape()
        proto.CopyFrom(value.proto)
        return cls(proto=proto)

    @property
    def attributes(self) -> GraphicAttributes:
        return GraphicAttributes(proto_ref=self._graphic_proto.attributes)

    @attributes.setter
    def attributes(self, attributes: GraphicAttributes):
        self._graphic_proto.attributes.CopyFrom(attributes.proto)

    def bounding_box(self) -> Box2:
        raise NotImplementedError(f"bounding_box() not implemented for {type(self).__name__}")


class Segment(GraphicShape):
    """Represents a base graphic segment (not a board or schematic item)"""

    def __init__(
        self,
        proto: base_types_pb2.GraphicShape | None = None,
        proto_ref: base_types_pb2.GraphicShape | None = None,
    ):
        self._graphic_proto = proto_ref if proto_ref is not None else base_types_pb2.GraphicShape()

        if proto is not None:
            self._graphic_proto.CopyFrom(proto)
        elif proto_ref is None:
            self._graphic_proto.segment.SetInParent()

    @classmethod
    def from_coords(cls, start: Vector2, end: Vector2) -> Self:
        """Create a segment from its endpoints.

        .. versionadded:: 0.9.0"""
        proto = base_types_pb2.GraphicShape()
        proto.segment.start.CopyFrom(start.proto)
        proto.segment.end.CopyFrom(end.proto)
        return cls(proto)

    @property
    def start(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.segment.start)

    @start.setter
    def start(self, point: Vector2):
        self._graphic_proto.segment.start.CopyFrom(point.proto)

    @property
    def end(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.segment.end)

    @end.setter
    def end(self, point: Vector2):
        self._graphic_proto.segment.end.CopyFrom(point.proto)

    def __repr__(self) -> str:
        return f"Segment(start={self.start}, end={self.end})"

    def bounding_box(self) -> Box2:
        """Calculates the bounding box of the segment"""
        return Box2.from_points([self.start, self.end])


class Arc(GraphicShape):
    """Represents a generic graphical arc (not a board or schematic item)"""

    def __init__(
        self,
        proto: base_types_pb2.GraphicShape | None = None,
        proto_ref: base_types_pb2.GraphicShape | None = None,
    ):
        self._graphic_proto = proto_ref if proto_ref is not None else base_types_pb2.GraphicShape()

        if proto is not None:
            self._graphic_proto.CopyFrom(proto)
        elif proto_ref is None:
            self._graphic_proto.arc.SetInParent()

    @classmethod
    def from_coords(cls, start: Vector2, mid: Vector2, end: Vector2) -> Self:
        """Create an arc from its start, midpoint, and end coordinates.

        .. versionadded:: 0.9.0"""
        proto = base_types_pb2.GraphicShape()
        proto.arc.start.CopyFrom(start.proto)
        proto.arc.mid.CopyFrom(mid.proto)
        proto.arc.end.CopyFrom(end.proto)
        return cls(proto)

    @property
    def start(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.arc.start)

    @start.setter
    def start(self, point: Vector2):
        self._graphic_proto.arc.start.CopyFrom(point.proto)

    @property
    def mid(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.arc.mid)

    @mid.setter
    def mid(self, point: Vector2):
        self._graphic_proto.arc.mid.CopyFrom(point.proto)

    @property
    def end(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.arc.end)

    @end.setter
    def end(self, point: Vector2):
        self._graphic_proto.arc.end.CopyFrom(point.proto)

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

    def angle(self) -> float | None:
        """Calculates the angle between the start and end of the arc in radians

        :return: The angle of the arc, or None if the arc is degenerate

        .. versionadded:: 0.4.0"""
        return arc_angle(self.start, self.mid, self.end)

    def __repr__(self) -> str:
        return f"Arc(start={self.start}, mid={self.mid}, end={self.end})"

    def bounding_box(self) -> Box2:
        return arc_bounding_box(self.start, self.mid, self.end)


class Circle(GraphicShape):
    """Represents a graphic circle (not a board or schematic item)"""

    def __init__(
        self,
        proto: base_types_pb2.GraphicShape | None = None,
        proto_ref: base_types_pb2.GraphicShape | None = None,
    ):
        self._graphic_proto = proto_ref if proto_ref is not None else base_types_pb2.GraphicShape()

        if proto is not None:
            self._graphic_proto.CopyFrom(proto)
        elif proto_ref is None:
            self._graphic_proto.circle.SetInParent()

    @classmethod
    def from_center_radius(cls, center: Vector2, radius: int) -> Self:
        """Create a circle from its center and radius.

        .. versionadded:: 0.9.0"""
        proto = base_types_pb2.GraphicShape()
        proto.circle.center.CopyFrom(center.proto)
        proto.circle.radius_point.CopyFrom(Vector2.from_xy(center.x + radius, center.y).proto)
        return cls(proto)

    @property
    def center(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.circle.center)

    @center.setter
    def center(self, point: Vector2):
        self._graphic_proto.circle.center.CopyFrom(point.proto)

    @property
    def radius_point(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.circle.radius_point)

    @radius_point.setter
    def radius_point(self, radius_point: Vector2):
        self._graphic_proto.circle.radius_point.CopyFrom(radius_point.proto)

    def radius(self) -> float:
        """Calculates the radius of the circle"""
        return (self.radius_point - self.center).length()

    def bounding_box(self) -> Box2:
        """Calculates the bounding box of the circle"""
        radius = int(self.radius() + 0.5)
        diameter = radius * 2
        return Box2.from_xywh(
            self.center.x - radius,
            self.center.y - radius,
            diameter,
            diameter,
        )

    def __repr__(self) -> str:
        return f"Circle(center={self.center}, radius={self.radius()})"


class Rectangle(GraphicShape):
    """Represents a graphic rectangle (not a board or schematic item)"""

    def __init__(
        self,
        proto: base_types_pb2.GraphicShape | None = None,
        proto_ref: base_types_pb2.GraphicShape | None = None,
    ):
        self._graphic_proto = proto_ref if proto_ref is not None else base_types_pb2.GraphicShape()

        if proto is not None:
            self._graphic_proto.CopyFrom(proto)
        elif proto_ref is None:
            self._graphic_proto.rectangle.SetInParent()

    @classmethod
    def from_coords(cls, top_left: Vector2, bottom_right: Vector2) -> Self:
        """Create a rectangle from its top-left and bottom-right corners.

        .. versionadded:: 0.9.0"""
        proto = base_types_pb2.GraphicShape()
        proto.rectangle.top_left.CopyFrom(top_left.proto)
        proto.rectangle.bottom_right.CopyFrom(bottom_right.proto)
        return cls(proto)

    @property
    def top_left(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.rectangle.top_left)

    @top_left.setter
    def top_left(self, point: Vector2):
        self._graphic_proto.rectangle.top_left.CopyFrom(point.proto)

    @property
    def bottom_right(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.rectangle.bottom_right)

    @bottom_right.setter
    def bottom_right(self, point: Vector2):
        self._graphic_proto.rectangle.bottom_right.CopyFrom(point.proto)

    def __repr__(self) -> str:
        return f"Rectangle(top_left={self.top_left}, bottom_right={self.bottom_right})"

    def bounding_box(self) -> Box2:
        """Calculates the bounding box of the rectangle"""
        return Box2.from_pos_size(self.top_left, self.bottom_right - self.top_left)


class Polygon(GraphicShape):
    """Represents a graphic polygon (not a board or schematic item)"""

    def __init__(
        self,
        proto: base_types_pb2.GraphicShape | None = None,
        proto_ref: base_types_pb2.GraphicShape | None = None,
    ):
        self._graphic_proto = proto_ref if proto_ref is not None else base_types_pb2.GraphicShape()

        if proto is not None:
            self._graphic_proto.CopyFrom(proto)
        elif proto_ref is None:
            self._graphic_proto.polygon.SetInParent()

        assert self._graphic_proto.WhichOneof("geometry") == "polygon"

    @property
    def polygons(self) -> MutableWrapperSequence[PolygonWithHoles]:
        """The polygons of this shape as a live view"""
        return MutableWrapperSequence(self._graphic_proto.polygon.polygons, PolygonWithHoles)

    def __repr__(self) -> str:
        return f"Polygon(polygons={self.polygons})"

    def bounding_box(self) -> Box2:
        """Calculates the bounding box of the polygon"""
        box = None
        for polygon in self.polygons:
            if box is None:
                box = polygon.bounding_box()
            else:
                box.merge(polygon.bounding_box())
        return box if box is not None else Box2()

    @classmethod
    def from_outline(cls, outline: PolyLine, *holes: PolyLine) -> Self:
        """Create a polygon from an outer outline and optional holes.

        The outline and holes are forced closed.

        .. versionadded:: 0.9.0"""
        result = cls()
        result.polygons.append(PolygonWithHoles())
        outline.closed = True
        result.polygons[0].outline = outline
        for hole in holes:
            result.polygons[0].add_hole(hole)
        return result


class Bezier(GraphicShape):
    """Represents a graphic bezier curve (not a board or schematic item)"""

    def __init__(
        self,
        proto: base_types_pb2.GraphicShape | None = None,
        proto_ref: base_types_pb2.GraphicShape | None = None,
    ):
        self._graphic_proto = proto_ref if proto_ref is not None else base_types_pb2.GraphicShape()

        if proto is not None:
            self._graphic_proto.CopyFrom(proto)
        elif proto_ref is None:
            self._graphic_proto.bezier.SetInParent()

    @classmethod
    def from_coords(
        cls, start: Vector2, control1: Vector2, control2: Vector2, end: Vector2
    ) -> Self:
        """Create a bezier curve from its endpoints and control points.

        .. versionadded:: 0.9.0"""
        proto = base_types_pb2.GraphicShape()
        proto.bezier.start.CopyFrom(start.proto)
        proto.bezier.control1.CopyFrom(control1.proto)
        proto.bezier.control2.CopyFrom(control2.proto)
        proto.bezier.end.CopyFrom(end.proto)
        return cls(proto)

    @property
    def start(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.bezier.start)

    @start.setter
    def start(self, point: Vector2):
        self._graphic_proto.bezier.start.CopyFrom(point.proto)

    @property
    def control1(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.bezier.control1)

    @control1.setter
    def control1(self, point: Vector2):
        self._graphic_proto.bezier.control1.CopyFrom(point.proto)

    @property
    def control2(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.bezier.control2)

    @control2.setter
    def control2(self, point: Vector2):
        self._graphic_proto.bezier.control2.CopyFrom(point.proto)

    @property
    def end(self) -> Vector2:
        return Vector2(proto_ref=self._graphic_proto.bezier.end)

    @end.setter
    def end(self, point: Vector2):
        self._graphic_proto.bezier.end.CopyFrom(point.proto)

    def __repr__(self) -> str:
        return (
            f"Bezier(start={self.start}, control1={self.control1}, "
            f"control2={self.control2}, end={self.end})"
        )

    def bounding_box(self) -> Box2:
        # TODO: maybe bring in a library for Bezier curve math so we can generate an
        # bounding box from the curve approximation like KiCad does?
        raise NotImplementedError()


class Ellipse(GraphicShape):
    """Represents a graphic ellipse (not a board or schematic item).

    .. versionadded:: 0.9.0"""

    def __init__(
        self,
        proto: base_types_pb2.GraphicShape | None = None,
        proto_ref: base_types_pb2.GraphicShape | None = None,
    ):
        self._graphic_proto = proto_ref if proto_ref is not None else base_types_pb2.GraphicShape()
        if proto is not None:
            self._graphic_proto.CopyFrom(proto)
        elif proto_ref is None:
            self._graphic_proto.ellipse.SetInParent()
        assert self._graphic_proto.WhichOneof("geometry") == "ellipse"

    def __repr__(self) -> str:
        rotation = self._graphic_proto.ellipse.rotation.value_degrees
        return (
            f"Ellipse(center={Vector2(self._graphic_proto.ellipse.center)}, "
            f"major_radius={to_mm(self._graphic_proto.ellipse.major_radius.value_nm)}, "
            f"minor_radius={to_mm(self._graphic_proto.ellipse.minor_radius.value_nm)}, "
            f"rotation={rotation})"
        )

    @classmethod
    def from_center_radii(
        cls, center: Vector2, major_radius: int, minor_radius: int, rotation: Angle | None = None
    ) -> Self:
        """Create an ellipse from its center, radii, and optional rotation."""
        proto = base_types_pb2.GraphicShape()
        proto.ellipse.center.CopyFrom(center.proto)
        proto.ellipse.major_radius.value_nm = major_radius
        proto.ellipse.minor_radius.value_nm = minor_radius
        if rotation is not None:
            proto.ellipse.rotation.CopyFrom(rotation.proto)
        return cls(proto)


class EllipseArc(GraphicShape):
    """Represents a graphic elliptical arc (not a board or schematic item).

    .. versionadded:: 0.x.0"""

    def __init__(
        self,
        proto: base_types_pb2.GraphicShape | None = None,
        proto_ref: base_types_pb2.GraphicShape | None = None,
    ):
        self._graphic_proto = proto_ref if proto_ref is not None else base_types_pb2.GraphicShape()
        if proto is not None:
            self._graphic_proto.CopyFrom(proto)
        elif proto_ref is None:
            self._graphic_proto.ellipse_arc.SetInParent()
        assert self._graphic_proto.WhichOneof("geometry") == "ellipse_arc"

    def __repr__(self) -> str:
        rotation = self._graphic_proto.ellipse.rotation.value_degrees
        return (
            f"EllipseArc(center={Vector2(self._graphic_proto.ellipse_arc.center)}, "
            f"major_radius={to_mm(self._graphic_proto.ellipse_arc.major_radius.value_nm)}, "
            f"minor_radius={to_mm(self._graphic_proto.ellipse_arc.minor_radius.value_nm)}, "
            f"start_angle={self._graphic_proto.ellipse_arc.start_angle.value_degrees}, "
            f"end_angle={self._graphic_proto.ellipse_arc.end_angle.value_degrees}, "
            f"rotation={rotation})"
        )

    @classmethod
    def from_center_radii_angles(
        cls,
        center: Vector2,
        major_radius: int,
        minor_radius: int,
        start_angle: Angle,
        end_angle: Angle,
        rotation: Angle | None = None,
    ) -> Self:
        """Create an ellipse arc from its center, radii, and angles."""
        proto = base_types_pb2.GraphicShape()
        proto.ellipse_arc.center.CopyFrom(center.proto)
        proto.ellipse_arc.major_radius.value_nm = major_radius
        proto.ellipse_arc.minor_radius.value_nm = minor_radius
        proto.ellipse_arc.start_angle.CopyFrom(start_angle.proto)
        proto.ellipse_arc.end_angle.CopyFrom(end_angle.proto)
        if rotation is not None:
            proto.ellipse_arc.rotation.CopyFrom(rotation.proto)
        return cls(proto)


def to_concrete_shape(shape: GraphicShape) -> GraphicShape | None:
    cls = {
        "segment": Segment,
        "arc": Arc,
        "circle": Circle,
        "rectangle": Rectangle,
        "polygon": Polygon,
        "bezier": Bezier,
        "ellipse": Ellipse,
        "ellipse_arc": EllipseArc,
        None: None,
    }.get(shape._graphic_proto.WhichOneof("geometry"), None)

    return cls(proto_ref=shape._graphic_proto) if cls is not None else None


class CompoundShape(Wrapper):
    """Represents a compound shape (a collection of other shapes)"""

    def __init__(self, proto: base_types_pb2.CompoundShape | None = None):
        self._proto = base_types_pb2.CompoundShape()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def shapes(self) -> MutableWrapperSequence[GraphicShape]:
        return MutableWrapperSequence(self._proto.shapes, GraphicShape, to_concrete_shape)


class TitleBlockInfo(Wrapper):
    def __init__(
        self,
        proto: types.TitleBlockInfo | None = None,
        proto_ref: types.TitleBlockInfo | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else types.TitleBlockInfo()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def title(self) -> str:
        return self._proto.title

    @title.setter
    def title(self, title: str):
        self._proto.title = title

    @property
    def date(self) -> str:
        return self._proto.date

    @date.setter
    def date(self, date: str):
        self._proto.date = date

    @property
    def revision(self) -> str:
        return self._proto.revision

    @revision.setter
    def revision(self, revision: str):
        self._proto.revision = revision

    @property
    def company(self) -> str:
        return self._proto.company

    @company.setter
    def company(self, company: str):
        self._proto.company = company

    @property
    def comments(self) -> dict[int, str]:
        return {
            1: self._proto.comment1,
            2: self._proto.comment2,
            3: self._proto.comment3,
            4: self._proto.comment4,
            5: self._proto.comment5,
            6: self._proto.comment6,
            7: self._proto.comment7,
            8: self._proto.comment8,
            9: self._proto.comment9,
        }

    @comments.setter
    def comments(self, comments: dict[int, str]):
        if 1 in comments:
            self._proto.comment1 = comments[1]
        if 2 in comments:
            self._proto.comment2 = comments[2]
        if 3 in comments:
            self._proto.comment3 = comments[3]
        if 4 in comments:
            self._proto.comment4 = comments[4]
        if 5 in comments:
            self._proto.comment5 = comments[5]
        if 6 in comments:
            self._proto.comment6 = comments[6]
        if 7 in comments:
            self._proto.comment7 = comments[7]
        if 8 in comments:
            self._proto.comment8 = comments[8]
        if 9 in comments:
            self._proto.comment9 = comments[9]


class PageSettings(Wrapper):
    def __init__(
        self,
        proto: base_types_pb2.PageSettings | None = None,
        proto_ref: base_types_pb2.PageSettings | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else base_types_pb2.PageSettings()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def page_size(self) -> base_types_pb2.PageSize.ValueType:
        return self._proto.page_size

    @page_size.setter
    def page_size(self, value: base_types_pb2.PageSize.ValueType):
        self._proto.page_size = value

    @property
    def user_page_size(self) -> Vector2:
        """Relevant only when page_size == ``PS_USER``"""
        return Vector2(proto_ref=self._proto.user_page_size)

    @user_page_size.setter
    def user_page_size(self, value: Vector2):
        self._proto.user_page_size.CopyFrom(value.proto)

    @property
    def orientation(self) -> base_types_pb2.PageOrientation.ValueType:
        return self._proto.orientation

    @orientation.setter
    def orientation(self, value: base_types_pb2.PageOrientation.ValueType):
        self._proto.orientation = value

    @property
    def drawing_sheet(self) -> str:
        """Path to a .kicad_wks drawing sheet file.
        Empty string means the default (built-in) drawing sheet is used."""
        return self._proto.drawing_sheet

    @drawing_sheet.setter
    def drawing_sheet(self, value: str):
        self._proto.drawing_sheet = value


class EmbeddedFile(Wrapper):
    """A file embedded in a document, such as a font, datasheet, or 3D model

    .. versionadded:: 0.9.0 (KiCad 10.0.7)"""

    def __init__(
        self,
        proto: embedded_files_pb2.EmbeddedFile | None = None,
        proto_ref: embedded_files_pb2.EmbeddedFile | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else embedded_files_pb2.EmbeddedFile()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, name: str):
        self._proto.name = name

    @property
    def type(self) -> EmbeddedFileType.ValueType:
        return self._proto.type

    @type.setter
    def type(self, type: EmbeddedFileType.ValueType):
        self._proto.type = type

    @property
    def data(self) -> bytes:
        """zstd-compressed payload, base64-encoded."""
        return self._proto.data

    @data.setter
    def data(self, data: bytes):
        self._proto.data = data

    @property
    def data_hash(self) -> str:
        """MurmurHash3 integrity hash"""
        return self._proto.data_hash

    @data_hash.setter
    def data_hash(self, data_hash: str):
        self._proto.data_hash = data_hash

    @classmethod
    def from_path(
        cls, path: str | Path, type: EmbeddedFileType.ValueType | None = None
    ) -> EmbeddedFile:
        """Creates a new embedded file from a file path.

        :param path: Path of the file to embed.
        :param type: Embedded file type, guessed from the extension when omitted.
        """
        path = Path(path)
        suffix = path.suffix.lstrip(".").lower()

        if type is None:
            if suffix in ("stp", "stpz", "step", "wrl", "wrz"):
                type = EmbeddedFileType.EFT_MODEL
            elif suffix in ("woff", "woff2", "ttf", "otf"):
                type = EmbeddedFileType.EFT_FONT
            elif suffix == "pdf":
                type = EmbeddedFileType.EFT_DATASHEET
            elif suffix == "kicad_wks":
                type = EmbeddedFileType.EFT_WORKSHEET
            else:
                type = EmbeddedFileType.EFT_OTHER

        return cls.from_bytes(path.read_bytes(), name=path.name, type=type)

    @classmethod
    def from_bytes(
        cls, data: bytes, name: str, type: EmbeddedFileType.ValueType = EmbeddedFileType.EFT_OTHER
    ) -> EmbeddedFile:
        """Creates a new embedded file from raw bytes."""
        file = cls()
        file.name = name
        file.type = type
        file.data = base64.b64encode(zstandard.compress(data, level=15))
        # Will be filled in by KiCad when the file is added
        file.data_hash = ""
        return file


class EmbeddedFiles(Wrapper):
    """.. versionadded:: 0.9.0 (KiCad 10.0.7)"""

    def __init__(
        self,
        proto: embedded_files_pb2.EmbeddedFiles | None = None,
        proto_ref: embedded_files_pb2.EmbeddedFiles | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else embedded_files_pb2.EmbeddedFiles()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def files(self) -> Sequence[EmbeddedFile]:
        return MutableWrapperSequence(self._proto.files, EmbeddedFile)

    @files.setter
    def files(self, files: Sequence[EmbeddedFile]):
        del self._proto.files[:]
        self._proto.files.extend(f.proto for f in files)


class CustomProperty(Wrapper):
    """A user-defined key/value property stored on a board/schematic object

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: base_types_pb2.CustomProperty | None = None,
        proto_ref: base_types_pb2.CustomProperty | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else base_types_pb2.CustomProperty()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def key(self) -> str:
        return self._proto.key

    @key.setter
    def key(self, key: str):
        self._proto.key = key

    @property
    def value(self) -> str:
        return self._proto.value

    @value.setter
    def value(self, value: str):
        self._proto.value = value

    def __repr__(self) -> str:
        return f"CustomProperty(key={self.key!r})"


class LineEnding(Wrapper):
    """.. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: base_types_pb2.LineEnding | None = None,
        proto_ref: base_types_pb2.LineEnding | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else base_types_pb2.LineEnding()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def style(self) -> LineEndingStyle.ValueType:
        return self._proto.style

    @style.setter
    def style(self, style: LineEndingStyle.ValueType):
        self._proto.style = style

    @property
    def length(self) -> int | None:
        if self._proto.HasField("length"):
            return self._proto.length.value_nm
        return None

    @length.setter
    def length(self, length: int | None):
        if length is None:
            self._proto.ClearField("length")
        else:
            self._proto.length.value_nm = length

    @property
    def width(self) -> int | None:
        if self._proto.HasField("width"):
            return self._proto.width.value_nm
        return None

    @width.setter
    def width(self, width: int | None):
        if width is None:
            self._proto.ClearField("width")
        else:
            self._proto.width.value_nm = width

    @property
    def stroke(self) -> StrokeAttributes:
        return StrokeAttributes(proto_ref=self._proto.stroke)

    @stroke.setter
    def stroke(self, stroke: StrokeAttributes):
        self._proto.stroke.CopyFrom(stroke.proto)


class DesignVariant(Wrapper):
    def __init__(
        self,
        proto: variants_pb2.DesignVariant | None = None,
        proto_ref: variants_pb2.DesignVariant | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else variants_pb2.DesignVariant()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def name(self) -> str:
        """Variant name (must be case-insensitively unique in a project)"""
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

    @property
    def description(self) -> str:
        """The default variant is addressed by the empty string"""
        return self._proto.description

    @description.setter
    def description(self, value: str):
        self._proto.description = value


class JobResult(Wrapper):
    """A result returned from running an export job.  Provides overall status and a list of
    files created by the job."""

    def __init__(
        self,
        proto: jobs_pb2.RunJobResponse | None = None,
        proto_ref: jobs_pb2.RunJobResponse | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else jobs_pb2.RunJobResponse()
        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"<JobResult succeeded={self.succeeded} "
            f"output_paths={self.output_paths} message={self.message!r}>"
        )

    def __bool__(self) -> bool:
        return self.succeeded

    @property
    def status(self) -> jobs_pb2.JobStatus.ValueType:
        return self._proto.status

    @property
    def output_paths(self) -> list[str]:
        return list(self._proto.output_path)

    @property
    def message(self) -> str:
        """Optional message containing warning or error details. Should be empty if status is
        ``JS_SUCCESS``."""
        return self._proto.message

    @property
    def succeeded(self) -> bool:
        return self._proto.status == jobs_pb2.JS_SUCCESS
