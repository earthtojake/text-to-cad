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

import sys
from collections.abc import Callable, Sequence

from google.protobuf.any_pb2 import Any
from google.protobuf.message import Message

from cadgen.kipy.common_types import (
    Arc,
    Bezier,
    Circle,
    CustomProperty,
    EmbeddedFiles,
    GraphicAttributes,
    LibraryIdentifier,
    Polygon,
    Rectangle,
    Segment,
    SheetPath,
    StrokeAttributes,
    Text,
    TextAttributes,
    TextBox,
)
from cadgen.kipy.geometry import (
    Angle,
    Box2,
    PolygonWithHoles,
    PolyLineNode,
    Vector2,
    Vector3D,
    arc_angle,
    arc_bounding_box,
    arc_center,
    arc_end_angle,
    arc_radius,
    arc_start_angle,
)
from cadgen.kipy.proto.board import board_commands_pb2, board_types_pb2
from cadgen.kipy.proto.board.board_commands_pb2 import (  # noqa
    BoardFlipMode,
    InactiveLayerDisplayMode,
    NetColorDisplayMode,
    RatsnestDisplayMode,
)

# Re-exported protobuf enum types
from cadgen.kipy.proto.board.board_types_pb2 import (  # noqa
    PSS_CIRCLE,
    PST_NORMAL,
    BarcodeErrorCorrection,
    BarcodeKind,
    BoardLayer,
    ChamferedRectCorners,
    ConstraintAnchor,
    ConstraintType,
    DrillChartAlign,
    DrillChartColumnId,
    DrillShape,
    IslandRemovalMode,
    PadFabricationProperty,
    PadSimElectricalType,
    PadStackShape,
    PadStackType,
    PadTeardropMode,
    PadType,
    PlacementRuleSourceType,
    SolderMaskMode,
    SolderPasteMode,
    TableStrokeMode,
    ThievingPattern,
    UnconnectedLayerRemoval,
    ViaCoveringMode,
    ViaDrillCappingMode,
    ViaDrillFillingMode,
    ViaDrillPostMachiningMode,
    ViaPluggingMode,
    ViaType,
    ZoneBorderStyle,
    ZoneConnectionStyle,
    ZoneCornerSmoothingMode,
    ZoneFillMode,
    ZoneHatchFillBorderMode,
    ZoneTeardropType,
    ZoneType,
)
from cadgen.kipy.proto.common.types import KIID, base_types_pb2
from cadgen.kipy.proto.common.types.base_types_pb2 import LockedState
from cadgen.kipy.proto.common.types.enums_pb2 import Units
from cadgen.kipy.util import unpack_any
from cadgen.kipy.util.board_layer import COPPER_LAYERS, is_copper_layer
from cadgen.kipy.util.units import from_mm
from cadgen.kipy.wrapper import Item, MutableWrapperSequence, Wrapper

if sys.version_info >= (3, 13):
    from warnings import deprecated
else:
    from typing_extensions import deprecated

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


class BoardItem(Item):
    @property
    def id(self) -> KIID:
        return self.proto.id


class Net(Wrapper):
    def __init__(self, proto: board_types_pb2.Net | None = None, name: str | None = None):
        self._proto = board_types_pb2.Net()

        if proto is not None:
            self._proto.CopyFrom(proto)

        if name:
            self.name = name

    def __repr__(self) -> str:
        return f"Net(name={self.name})"

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, name: str):
        self._proto.name = name

    @property
    @deprecated(
        "This property will be removed in KiCad 10; API clients should not rely on net codes"
    )
    def code(self) -> int:
        """
        .. deprecated:: 0.4.0
        """
        return self._proto.code.value

    def __eq__(self, other):
        if isinstance(other, Net):
            return self.name == other.name
        return NotImplemented


class Track(BoardItem):
    """Represents a straight track segment"""

    def __init__(
        self,
        proto: board_types_pb2.Track | None = None,
        proto_ref: board_types_pb2.Track | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Track()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"Track(start={self.start}, end={self.end}, layer={BoardLayer.Name(self.layer)}, "
            f"net={self.net.name})"
        )

    @property
    def locked(self) -> bool:
        """
        .. versionadded:: 0.6.0
        """
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = {
            True: LockedState.LS_LOCKED,
            False: LockedState.LS_UNLOCKED,
        }.get(locked, LockedState.LS_UNLOCKED)

    @property
    def net(self) -> Net:
        return Net(self._proto.net)

    @net.setter
    def net(self, net: Net):
        self._proto.net.CopyFrom(net.proto)

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def start(self) -> Vector2:
        return Vector2(self._proto.start)

    @start.setter
    def start(self, point: Vector2):
        self._proto.start.CopyFrom(point.proto)

    @property
    def end(self) -> Vector2:
        return Vector2(self._proto.end)

    @end.setter
    def end(self, point: Vector2):
        self._proto.end.CopyFrom(point.proto)

    @property
    def width(self) -> int:
        return self._proto.width.value_nm

    @width.setter
    def width(self, width: int):
        self._proto.width.value_nm = width

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None

    def length(self) -> float:
        """Calculates track length in nanometers"""
        return (self.end - self.start).length()

    @property
    def solder_mask(self) -> SolderMaskOverrides:
        """Solder mask overrides for this track

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return SolderMaskOverrides(proto_ref=self._proto.solder_mask)


class ArcTrack(BoardItem):
    """Represents an arc track segment"""

    def __init__(
        self,
        proto: board_types_pb2.Arc | None = None,
        proto_ref: board_types_pb2.Arc | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Arc()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"ArcTrack(start={self.start}, mid={self.mid}, end={self.end}, "
            f"layer={BoardLayer.Name(self.layer)}, net={self.net.name})"
        )

    @property
    def locked(self) -> bool:
        """
        .. versionadded:: 0.6.0
        """
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = {
            True: LockedState.LS_LOCKED,
            False: LockedState.LS_UNLOCKED,
        }.get(locked, LockedState.LS_UNLOCKED)

    @property
    def net(self) -> Net:
        return Net(self._proto.net)

    @net.setter
    def net(self, net: Net):
        self._proto.net.CopyFrom(net.proto)

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def start(self) -> Vector2:
        return Vector2(self._proto.start)

    @start.setter
    def start(self, point: Vector2):
        self._proto.start.CopyFrom(point.proto)

    @property
    def end(self) -> Vector2:
        return Vector2(self._proto.end)

    @end.setter
    def end(self, point: Vector2):
        self._proto.end.CopyFrom(point.proto)

    @property
    def width(self) -> int:
        return self._proto.width.value_nm

    @width.setter
    def width(self, width: int):
        self._proto.width.value_nm = width

    @property
    def mid(self) -> Vector2:
        return Vector2(self._proto.mid)

    @mid.setter
    def mid(self, point: Vector2):
        self._proto.mid.CopyFrom(point.proto)

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None

    @property
    def solder_mask(self) -> SolderMaskOverrides:
        """Solder mask overrides for this arc track

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return SolderMaskOverrides(proto_ref=self._proto.solder_mask)

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

    def length(self) -> float:
        """Calculates arc track length in nanometers

        :return: The length of the arc, or the distance between the start and end points if
            the arc is degenerate

        .. versionadded:: 0.3.0"""
        angle = self.angle()
        if angle is None:
            return (self.end - self.start).length()

        return angle * self.radius()

    def bounding_box(self) -> Box2:
        return arc_bounding_box(self.start, self.mid, self.end)


class BoardShape(BoardItem):
    """Represents a graphic shape on a board or footprint"""

    def __init__(
        self,
        proto: board_types_pb2.BoardGraphicShape | None = None,
        proto_ref: board_types_pb2.BoardGraphicShape | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.BoardGraphicShape()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def proto(self):
        """Returns the outer BoardGraphicShape proto.  Overrides GraphicShape.proto,
        which would otherwise shadow this via the MRO and return the inner
        GraphicShape message (the wrong type for the board item wire format)."""
        return self._proto

    @property
    def id(self) -> KIID:
        return self._proto.id

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = {
            True: LockedState.LS_LOCKED,
            False: LockedState.LS_UNLOCKED,
        }.get(locked, LockedState.LS_UNLOCKED)

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def solder_mask(self) -> SolderMaskOverrides:
        """Solder mask overrides for this shape (only applies to shapes on outer copper layers)

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return SolderMaskOverrides(proto_ref=self._proto.solder_mask)

    @property
    def net(self) -> Net:
        return Net(self._proto.net)

    @net.setter
    def net(self, net: Net):
        self._proto.net.CopyFrom(net.proto)

    @property
    def attributes(self) -> GraphicAttributes:
        return GraphicAttributes(proto_ref=self._proto.shape.attributes)

    @attributes.setter
    def attributes(self, attributes: GraphicAttributes):
        self._proto.shape.attributes.CopyFrom(attributes.proto)

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None

    def move(self, delta: Vector2):
        raise NotImplementedError(f"move() not implemented for {self.__class__.__name__}")

    def rotate(self, angle: Angle, center: Vector2):
        raise NotImplementedError(f"rotate() not implemented for {self.__class__.__name__}")


class BoardSegment(BoardShape, Segment):
    """Represents a graphic line segment (not a track) on a board or footprint"""

    def __init__(
        self,
        proto: board_types_pb2.BoardGraphicShape | None = None,
        proto_ref: board_types_pb2.BoardGraphicShape | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.BoardGraphicShape()

        if proto is not None:
            assert proto.shape.WhichOneof("geometry") == "segment"
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self._proto.shape.segment.SetInParent()

        Segment.__init__(self, proto_ref=self._proto.shape)

    def __repr__(self) -> str:
        net_repr = (
            f", net={self.net.name}"
            if is_copper_layer(self.layer) and self._proto.HasField("net")
            else ""
        )
        return (
            f"BoardSegment(start={self.start}, end={self.end}, layer={BoardLayer.Name(self.layer)}"
            f"{net_repr})"
        )

    def move(self, delta: Vector2):
        """Moves the segment by the given delta vector"""
        self.start += delta
        self.end += delta

    def rotate(self, angle: Angle, center: Vector2):
        """Rotates the segment around the given center point by the given angle"""
        self.start = self.start.rotate(angle, center)
        self.end = self.end.rotate(angle, center)


class BoardArc(BoardShape, Arc):
    """Represents a graphic arc (not a track) on a board or footprint"""

    def __init__(
        self,
        proto: board_types_pb2.BoardGraphicShape | None = None,
        proto_ref: board_types_pb2.BoardGraphicShape | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.BoardGraphicShape()

        if proto is not None:
            assert proto.shape.WhichOneof("geometry") == "arc"
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self._proto.shape.arc.SetInParent()

        Arc.__init__(self, proto_ref=self._proto.shape)

    def __repr__(self) -> str:
        net_repr = (
            f", net={self.net.name}"
            if is_copper_layer(self.layer) and self._proto.HasField("net")
            else ""
        )
        return (
            f"BoardArc(start={self.start}, mid={self.mid}, end={self.end}, "
            f"layer={BoardLayer.Name(self.layer)}{net_repr})"
        )

    def move(self, delta: Vector2):
        """Moves the arc by the given delta vector"""
        self.start += delta
        self.mid += delta
        self.end += delta

    def rotate(self, angle: Angle, center: Vector2):
        """Rotates the arc around the given center point by the given angle"""
        self.start = self.start.rotate(angle, center)
        self.mid = self.mid.rotate(angle, center)
        self.end = self.end.rotate(angle, center)


class BoardCircle(BoardShape, Circle):
    """Represents a graphic circle on a board or footprint"""

    def __init__(
        self,
        proto: board_types_pb2.BoardGraphicShape | None = None,
        proto_ref: board_types_pb2.BoardGraphicShape | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.BoardGraphicShape()

        if proto is not None:
            assert proto.shape.WhichOneof("geometry") == "circle"
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self._proto.shape.circle.SetInParent()

        Circle.__init__(self, proto_ref=self._proto.shape)

    def __repr__(self) -> str:
        net_repr = (
            f", net={self.net.name}"
            if is_copper_layer(self.layer) and self._proto.HasField("net")
            else ""
        )
        return (
            f"BoardCircle(center={self.center}, radius_point={self.radius_point}, "
            f"layer={BoardLayer.Name(self.layer)}{net_repr})"
        )

    def move(self, delta: Vector2):
        """Moves the circle by the given delta vector"""
        self.center += delta
        self.radius_point += delta

    def rotate(self, angle: Angle, center: Vector2):
        """Rotates the circle around the given center point by the given angle

        .. versionadded:: 0.5.0
        """
        self.center = self.center.rotate(angle, center)
        self.radius_point = self.radius_point.rotate(angle, center)


class BoardRectangle(BoardShape, Rectangle):
    """Represents a graphic rectangle on a board or footprint"""

    def __init__(
        self,
        proto: board_types_pb2.BoardGraphicShape | None = None,
        proto_ref: board_types_pb2.BoardGraphicShape | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.BoardGraphicShape()

        if proto is not None:
            assert proto.shape.WhichOneof("geometry") == "rectangle"
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self._proto.shape.rectangle.SetInParent()

        Rectangle.__init__(self, proto_ref=self._proto.shape)

    def __repr__(self) -> str:
        net_repr = (
            f", net={self.net.name}"
            if is_copper_layer(self.layer) and self._proto.HasField("net")
            else ""
        )
        return (
            f"BoardRectangle(top_left={self.top_left}, bottom_right={self.bottom_right}, "
            f"layer={BoardLayer.Name(self.layer)}{net_repr}"
        )

    def move(self, delta: Vector2):
        """Moves the rectangle by the given delta vector"""
        self.top_left += delta
        self.bottom_right += delta

    def rotate(self, angle: Angle, center: Vector2):
        """Rotates the rectangle around the given center point by the given angle"""
        if angle.normalize().degrees % 90 != 0:
            raise ValueError(
                "Can only rotate rectangles by multiples of 90 degrees.  Convert to a polygon instead."
            )
        self.top_left = self.top_left.rotate(angle, center)
        self.bottom_right = self.bottom_right.rotate(angle, center)


class BoardPolygon(BoardShape, Polygon):
    """Represents a graphic polygon on a board or footprint"""

    def __init__(
        self,
        proto: board_types_pb2.BoardGraphicShape | None = None,
        proto_ref: board_types_pb2.BoardGraphicShape | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.BoardGraphicShape()

        if proto is not None:
            assert proto.shape.WhichOneof("geometry") == "polygon"
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self._proto.shape.polygon.SetInParent()

        Polygon.__init__(self, proto_ref=self._proto.shape)

    def __repr__(self) -> str:
        net_repr = (
            f", net={self.net.name}"
            if is_copper_layer(self.layer) and self._proto.HasField("net")
            else ""
        )
        return (
            f"BoardPolygon(points={self.polygons}, layer={BoardLayer.Name(self.layer)}{net_repr})"
        )

    def move(self, delta: Vector2):
        """Moves the polygon by the given delta vector"""
        for polygon in self.polygons:
            polygon.move(delta)

    def rotate(self, angle: Angle, center: Vector2):
        """Rotates the polygon around the given center point by the given angle"""
        for polygon in self.polygons:
            polygon.rotate(angle, center)

    @classmethod
    def from_rectangle(cls, rectangle: BoardRectangle) -> Self:
        """Converts a BoardRectangle into a BoardPolygon with matching corners.

        Other properties of the rectangle, including UUID, are preserved."""
        obj = cls()
        obj.proto.CopyFrom(rectangle._proto)
        obj.proto.shape.ClearField("rectangle")
        obj.proto.shape.polygon.SetInParent()
        Polygon.__init__(obj, proto_ref=obj._proto.shape)

        polygon = PolygonWithHoles()
        polygon.outline.append(PolyLineNode.from_point(rectangle.top_left))
        polygon.outline.append(
            PolyLineNode.from_point(
                Vector2.from_xy(rectangle.top_left.x, rectangle.bottom_right.y)
            )
        )
        polygon.outline.append(PolyLineNode.from_point(rectangle.bottom_right))
        polygon.outline.append(
            PolyLineNode.from_point(
                Vector2.from_xy(rectangle.bottom_right.x, rectangle.top_left.y)
            )
        )
        polygon.outline.closed = True
        obj.polygons.append(polygon)
        return obj


class BoardBezier(BoardShape, Bezier):
    """Represents a graphic bezier curve on a board or footprint"""

    def __init__(
        self,
        proto: board_types_pb2.BoardGraphicShape | None = None,
        proto_ref: board_types_pb2.BoardGraphicShape | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.BoardGraphicShape()

        if proto is not None:
            assert proto.shape.WhichOneof("geometry") == "bezier"
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self._proto.shape.bezier.SetInParent()

        Bezier.__init__(self, proto_ref=self._proto.shape)

    def __repr__(self) -> str:
        net_repr = (
            f", net={self.net.name}"
            if is_copper_layer(self.layer) and self._proto.HasField("net")
            else ""
        )
        return (
            f"BoardBezier(start={self.start}, control1={self.control1}, control2={self.control2}, "
            f"end={self.end}, layer={BoardLayer.Name(self.layer)}{net_repr})"
        )

    def move(self, delta: Vector2):
        """Moves the bezier curve by the given delta vector"""
        self.start += delta
        self.control1 += delta
        self.control2 += delta
        self.end += delta

    def rotate(self, angle: Angle, center: Vector2):
        """Rotates the bezier curve around the given center point by the given angle"""
        self.start = self.start.rotate(angle, center)
        self.control1 = self.control1.rotate(angle, center)
        self.control2 = self.control2.rotate(angle, center)
        self.end = self.end.rotate(angle, center)


def to_concrete_board_shape(shape: BoardShape) -> BoardShape:
    cls = {
        "segment": BoardSegment,
        "arc": BoardArc,
        "circle": BoardCircle,
        "rectangle": BoardRectangle,
        "polygon": BoardPolygon,
        "bezier": BoardBezier,
        None: None,
    }.get(shape._proto.shape.WhichOneof("geometry"), None)

    return cls(proto_ref=shape._proto) if cls is not None else shape


class BoardText(BoardItem):
    """Represents a free text object, or the text component of a field"""

    def __init__(
        self,
        proto: board_types_pb2.BoardText | None = None,
        proto_ref: board_types_pb2.BoardText | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.BoardText()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"BoardText(value={self.value}, position={self.position}, layer={BoardLayer.Name(self.layer)})"

    def as_text(self) -> Text:
        """Returns a base Text object using the same data as this BoardText"""
        return Text(self._proto.text)

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def id(self) -> KIID:
        return self._proto.id

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = {
            True: LockedState.LS_LOCKED,
            False: LockedState.LS_UNLOCKED,
        }.get(locked, LockedState.LS_UNLOCKED)

    @property
    def position(self) -> Vector2:
        return Vector2(self._proto.text.position)

    @position.setter
    def position(self, pos: Vector2):
        self._proto.text.position.CopyFrom(pos.proto)

    @property
    def value(self) -> str:
        return self._proto.text.text

    @value.setter
    def value(self, text: str):
        self._proto.text.text = text

    @property
    def attributes(self) -> TextAttributes:
        return TextAttributes(proto_ref=self._proto.text.attributes)

    @attributes.setter
    def attributes(self, attributes: TextAttributes):
        self._proto.text.attributes.CopyFrom(attributes.proto)
        self._proto.text.attributes.CopyFrom(attributes.proto)

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None


class BoardTextBox(BoardItem):
    """Represents a text box on a board"""

    def __init__(
        self,
        proto: board_types_pb2.BoardTextBox | None = None,
        proto_ref: board_types_pb2.BoardTextBox | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.BoardTextBox()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"BoardTextBox(value={self.value}, top_left={self.top_left}, "
            f"bottom_right={self.bottom_right}, layer={BoardLayer.Name(self.layer)})"
        )

    def as_textbox(self) -> TextBox:
        """Returns a base TextBox object using the same data as this BoardText"""
        return TextBox(self._proto.textbox)

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = {
            True: LockedState.LS_LOCKED,
            False: LockedState.LS_UNLOCKED,
        }.get(locked, LockedState.LS_UNLOCKED)

    @property
    def top_left(self) -> Vector2:
        return Vector2(self._proto.textbox.top_left)

    @top_left.setter
    def top_left(self, pos: Vector2):
        self._proto.textbox.top_left.CopyFrom(pos.proto)

    @property
    def bottom_right(self) -> Vector2:
        return Vector2(self._proto.textbox.bottom_right)

    @bottom_right.setter
    def bottom_right(self, pos: Vector2):
        self._proto.textbox.bottom_right.CopyFrom(pos.proto)

    @property
    def attributes(self) -> TextAttributes:
        return TextAttributes(proto_ref=self._proto.textbox.attributes)

    @attributes.setter
    def attributes(self, attributes: TextAttributes):
        self._proto.textbox.attributes.CopyFrom(attributes.proto)

    @property
    def value(self) -> str:
        return self._proto.textbox.text

    @value.setter
    def value(self, text: str):
        self._proto.textbox.text = text

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None


class Barcode(BoardItem):
    """Represents a barcode object

    .. versionadded:: 0.7.0 (KiCad 10.0.1)"""

    def __init__(
        self,
        proto: board_types_pb2.Barcode | None = None,
        proto_ref: board_types_pb2.Barcode | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Barcode()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"Barcode(text={self.text}, kind={BarcodeKind.Name(self.kind)}, "
            f"position={self.position}, layer={BoardLayer.Name(self.layer)})"
        )

    @property
    def text(self) -> str:
        return self._proto.text

    @text.setter
    def text(self, value: str):
        self._proto.text = value

    @property
    def kind(self) -> BarcodeKind.ValueType:
        return self._proto.kind

    @kind.setter
    def kind(self, value: BarcodeKind.ValueType):
        self._proto.kind = value

    @property
    def error_correction(self) -> BarcodeErrorCorrection.ValueType:
        return self._proto.error_correction

    @error_correction.setter
    def error_correction(self, value: BarcodeErrorCorrection.ValueType):
        self._proto.error_correction = value

    @property
    def position(self) -> Vector2:
        return Vector2(self._proto.position)

    @position.setter
    def position(self, value: Vector2):
        self._proto.position.CopyFrom(value.proto)

    @property
    def orientation(self) -> Angle:
        return Angle(proto_ref=self._proto.orientation)

    @orientation.setter
    def orientation(self, value: Angle):
        self._proto.orientation.CopyFrom(value.proto)

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, value: BoardLayer.ValueType):
        self._proto.layer = value

    @property
    def width(self) -> int:
        return self._proto.width.value_nm

    @width.setter
    def width(self, value: int):
        self._proto.width.value_nm = value

    @property
    def height(self) -> int:
        return self._proto.height.value_nm

    @height.setter
    def height(self, value: int):
        self._proto.height.value_nm = value

    @property
    def show_text(self) -> bool:
        return self._proto.show_text

    @show_text.setter
    def show_text(self, value: bool):
        self._proto.show_text = value

    @property
    def text_height(self) -> int:
        return self._proto.text_height.value_nm

    @text_height.setter
    def text_height(self, value: int):
        self._proto.text_height.value_nm = value

    @property
    def knockout(self) -> bool:
        return self._proto.knockout

    @knockout.setter
    def knockout(self, value: bool):
        self._proto.knockout = value

    @property
    def knockout_margin(self) -> Vector2:
        return Vector2(self._proto.knockout_margin)

    @knockout_margin.setter
    def knockout_margin(self, value: Vector2):
        self._proto.knockout_margin.CopyFrom(value.proto)

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = LockedState.LS_LOCKED if locked else LockedState.LS_UNLOCKED

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None


class ReferenceImage(BoardItem):
    """Represents a reference image on a board (a non-plotting bitmap)

    .. versionadded:: 0.7.0 (KiCad 10.0.1)"""

    def __init__(
        self,
        proto: board_types_pb2.ReferenceImage | None = None,
        proto_ref: board_types_pb2.ReferenceImage | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.ReferenceImage()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"ReferenceImage(position={self.position}, layer={BoardLayer.Name(self.layer)}, "
            f"bytes={len(self.image_data)})"
        )

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, value: BoardLayer.ValueType):
        self._proto.layer = value

    @property
    def position(self) -> Vector2:
        return Vector2(self._proto.position)

    @position.setter
    def position(self, value: Vector2):
        self._proto.position.CopyFrom(value.proto)

    @property
    def transform_origin_offset(self) -> Vector2:
        return Vector2(self._proto.transform_origin_offset)

    @transform_origin_offset.setter
    def transform_origin_offset(self, value: Vector2):
        self._proto.transform_origin_offset.CopyFrom(value.proto)

    @property
    def image_scale(self) -> float:
        return self._proto.image_scale.value

    @image_scale.setter
    def image_scale(self, value: float):
        self._proto.image_scale.value = value

    @property
    def image_data(self) -> bytes:
        return self._proto.image_data

    @image_data.setter
    def image_data(self, value: bytes):
        self._proto.image_data = value

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = LockedState.LS_LOCKED if locked else LockedState.LS_UNLOCKED

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None


class Field(BoardItem):
    """Represents a footprint field"""

    def __init__(
        self,
        proto: board_types_pb2.Field | None = None,
        proto_ref: board_types_pb2.Field | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Field()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"Field(name={self.name}, text={self.text}, layer={BoardLayer.Name(self.layer)})"

    @property
    def field_id(self) -> int:
        return self._proto.id.id

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, name: str):
        self._proto.name = name

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.text.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.text.layer = layer

    @property
    def text(self) -> BoardText:
        return BoardText(proto_ref=self._proto.text)

    @text.setter
    def text(self, text: BoardText):
        """
        .. versionadded:: 0.4.0 (setter)
        """
        self._proto.text.CopyFrom(text.proto)

    @property
    def visible(self) -> bool:
        """
        .. versionadded:: 0.3.0 with KiCad 9.0.1
        """
        return self._proto.visible

    @visible.setter
    def visible(self, visible: bool):
        self._proto.visible = visible


class ThermalSpokeSettings(Wrapper):
    def __init__(
        self,
        proto: board_types_pb2.ThermalSpokeSettings | None = None,
        proto_ref: board_types_pb2.ThermalSpokeSettings | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_types_pb2.ThermalSpokeSettings()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def width(self) -> int | None:
        if self._proto.HasField("width"):
            return self._proto.width.value_nm
        return None

    @width.setter
    def width(self, width: int):
        if width is None:
            self._proto.ClearField("width")
        else:
            self._proto.width.value_nm = width

    @property
    def angle(self) -> Angle:
        return Angle(proto_ref=self._proto.angle)

    @angle.setter
    def angle(self, angle: Angle):
        self._proto.angle.CopyFrom(angle.proto)

    @property
    def gap(self) -> int | None:
        if self._proto.HasField("gap"):
            return self._proto.gap.value_nm
        return None

    @gap.setter
    def gap(self, gap: int | None):
        if gap is None:
            self._proto.ClearField("gap")
        else:
            self._proto.gap.value_nm = gap


class ZoneConnectionSettings(Wrapper):
    def __init__(
        self,
        proto: board_types_pb2.ZoneConnectionSettings | None = None,
        proto_ref: board_types_pb2.ZoneConnectionSettings | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_types_pb2.ZoneConnectionSettings()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def zone_connection(self) -> ZoneConnectionStyle.ValueType:
        return self._proto.zone_connection

    @zone_connection.setter
    def zone_connection(self, zone_connection: ZoneConnectionStyle.ValueType):
        self._proto.zone_connection = zone_connection

    @property
    def thermal_spokes(self) -> ThermalSpokeSettings:
        return ThermalSpokeSettings(proto_ref=self._proto.thermal_spokes)


class SolderMaskOverrides(Wrapper):
    def __init__(
        self,
        proto: board_types_pb2.SolderMaskOverrides | None = None,
        proto_ref: board_types_pb2.SolderMaskOverrides | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.SolderMaskOverrides()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def solder_mask_margin(self) -> int | None:
        """Solder mask expansion/contraction.  Absence of this field means the margin will be taken
        from this object's parent or the board design rules."""
        if self._proto.HasField("solder_mask_margin"):
            return self._proto.solder_mask_margin.value_nm
        return None

    @solder_mask_margin.setter
    def solder_mask_margin(self, margin_nm: int | None):
        if margin_nm is None:
            self._proto.ClearField("solder_mask_margin")
        else:
            self._proto.solder_mask_margin.value_nm = margin_nm

    @property
    def expose_copper(self) -> bool:
        """Whether to expose (remove) solder mask over this item

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return self._proto.expose_copper

    @expose_copper.setter
    def expose_copper(self, expose: bool):
        self._proto.expose_copper = expose


class SolderPasteOverrides(Wrapper):
    def __init__(
        self,
        proto: board_types_pb2.SolderPasteOverrides | None = None,
        proto_ref: board_types_pb2.SolderPasteOverrides | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_types_pb2.SolderPasteOverrides()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def solder_paste_margin(self) -> int | None:
        """Solder paste expansion/contraction"""
        if self._proto.HasField("solder_paste_margin"):
            return self._proto.solder_paste_margin.value_nm
        return None

    @solder_paste_margin.setter
    def solder_paste_margin(self, margin_nm: int | None):
        if margin_nm is None:
            self._proto.ClearField("solder_paste_margin")
        else:
            self._proto.solder_paste_margin.value_nm = margin_nm

    @property
    def solder_paste_margin_ratio(self) -> float | None:
        """Solder paste expansion/contraction ratio"""
        if self._proto.HasField("solder_paste_margin_ratio"):
            return self._proto.solder_paste_margin_ratio.value
        return None

    @solder_paste_margin_ratio.setter
    def solder_paste_margin_ratio(self, ratio: float | None):
        if ratio is None:
            self._proto.ClearField("solder_paste_margin_ratio")
        else:
            self._proto.solder_paste_margin_ratio.value = ratio


class PadTeardropSettings(Wrapper):
    """Settings for teardrops applied to pads and vias

    .. versionadded:: 0.9.0 (KiCad 10.0.7)"""

    def __init__(
        self,
        proto: board_types_pb2.PadTeardropSettings | None = None,
        proto_ref: board_types_pb2.PadTeardropSettings | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.PadTeardropSettings()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def mode(self) -> PadTeardropMode.ValueType:
        """Whether to enable teardrops"""
        return self._proto.mode

    @mode.setter
    def mode(self, mode: PadTeardropMode.ValueType):
        self._proto.mode = mode

    @property
    def curved_edges(self) -> bool:
        return self._proto.curved_edges

    @curved_edges.setter
    def curved_edges(self, curved_edges: bool):
        self._proto.curved_edges = curved_edges

    @property
    def allow_multiple_track_segments(self) -> bool:
        """True to allow a teardrop to extend over multiple connected track segments if the
        first segment is too short to achieve the best teardrop length"""
        return self._proto.allow_multiple_track_segments

    @allow_multiple_track_segments.setter
    def allow_multiple_track_segments(self, allow: bool):
        self._proto.allow_multiple_track_segments = allow

    @property
    def prefer_zone_connection(self) -> bool:
        """True to prefer zone connections over teardrops for pads connected to a copper zone"""
        return self._proto.prefer_zone_connection

    @prefer_zone_connection.setter
    def prefer_zone_connection(self, prefer: bool):
        self._proto.prefer_zone_connection = prefer

    @property
    def max_length(self) -> int | None:
        """Maximum teardrop length in nanometers, or None if no constraint is applied"""
        if self._proto.HasField("max_length"):
            return self._proto.max_length.value_nm
        return None

    @max_length.setter
    def max_length(self, length_nm: int | None):
        if length_nm is None:
            self._proto.ClearField("max_length")
        else:
            self._proto.max_length.value_nm = length_nm

    @property
    def max_width(self) -> int | None:
        """Maximum teardrop width in nanometers, or None if no constraint is applied"""
        if self._proto.HasField("max_width"):
            return self._proto.max_width.value_nm
        return None

    @max_width.setter
    def max_width(self, width_nm: int | None):
        if width_nm is None:
            self._proto.ClearField("max_width")
        else:
            self._proto.max_width.value_nm = width_nm

    @property
    def best_length_ratio(self) -> float:
        """Preferred teardrop length as a ratio of the pad/via size"""
        return self._proto.best_length_ratio

    @best_length_ratio.setter
    def best_length_ratio(self, ratio: float):
        self._proto.best_length_ratio = ratio

    @property
    def best_width_ratio(self) -> float:
        """Preferred teardrop width as a ratio of the pad/via size"""
        return self._proto.best_width_ratio

    @best_width_ratio.setter
    def best_width_ratio(self, ratio: float):
        self._proto.best_width_ratio = ratio

    @property
    def max_track_width_ratio(self) -> float:
        """Maximum ratio between the pad/via size and connected track width that will create a
        teardrop (1.0 always creates a teardrop; 0.0 never does)"""
        return self._proto.max_track_width_ratio

    @max_track_width_ratio.setter
    def max_track_width_ratio(self, ratio: float):
        self._proto.max_track_width_ratio = ratio


class PadStackLayer(Wrapper):
    def __init__(
        self,
        proto: board_types_pb2.PadStackLayer | None = None,
        proto_ref: board_types_pb2.PadStackLayer | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.PadStackLayer()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def layer(self) -> BoardLayer.ValueType:
        """The board layer of this padstack entry.  For Front/Inner/Back padstacks, In1_Cu is used
        to represent inner layers."""
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def shape(self) -> PadStackShape.ValueType:
        """The shape of the pad on this layer"""
        return self._proto.shape

    @shape.setter
    def shape(self, shape: PadStackShape.ValueType):
        self._proto.shape = shape

    @property
    def size(self) -> Vector2:
        """The size (x and y) of the shape on this layer"""
        return Vector2(self._proto.size)

    @size.setter
    def size(self, size: Vector2):
        self._proto.size.CopyFrom(size.proto)

    @property
    def offset(self) -> Vector2:
        """The offset of the center of this shape from the center of the pad (which is defined as
        the hole center)"""
        return Vector2(self._proto.offset)

    @offset.setter
    def offset(self, offset: Vector2):
        self._proto.offset.CopyFrom(offset.proto)

    @property
    def corner_rounding_ratio(self) -> float:
        """How much to round the corners of the shape by, as a fraction of min(size.x, size.y)
        Only used for ``PSS_ROUNDRECT`` or ``PSS_CHAMFEREDRECT``"""
        return self._proto.corner_rounding_ratio

    @corner_rounding_ratio.setter
    def corner_rounding_ratio(self, ratio: float):
        self._proto.corner_rounding_ratio = ratio

    @property
    def chamfer_ratio(self) -> float:
        """How much to round the corners of the shape by, as a fraction of min(size.x, size.y)
        Only used for ``PSS_CHAMFEREDRECT``"""
        return self._proto.chamfer_ratio

    @chamfer_ratio.setter
    def chamfer_ratio(self, ratio: float):
        self._proto.chamfer_ratio = ratio

    @property
    def chamfered_corners(self) -> board_types_pb2.ChamferedRectCorners:
        return self._proto.chamfered_corners

    @property
    def trapezoid_delta(self) -> Vector2:
        """The difference in side length between the short and long pads in a trapezoid.  Only one
        of x or y may be nonzero. Only used for ``PSS_TRAPEZOID``"""
        return Vector2(self._proto.trapezoid_delta)

    @trapezoid_delta.setter
    def trapezoid_delta(self, delta: Vector2):
        self._proto.trapezoid_delta.CopyFrom(delta.proto)

    @property
    def custom_shapes(self) -> MutableWrapperSequence[BoardShape]:
        """The shapes that make up a custom-shape pad on this layer"""
        return MutableWrapperSequence(
            self._proto.custom_shapes, BoardShape, to_concrete_board_shape
        )

    @custom_shapes.setter
    def custom_shapes(self, shapes: Sequence[BoardShape]):
        del self._proto.custom_shapes[:]
        self._proto.custom_shapes.extend([shape.proto for shape in shapes])

    @property
    def custom_anchor_shape(self) -> PadStackShape.ValueType:
        """If shape == ``PSS_CUSTOM``, defines the shape of the anchor (only ``PSS_CIRCLE`` and
        ``PSS_RECTANGLE`` supported at present)"""
        return self._proto.custom_anchor_shape

    @custom_anchor_shape.setter
    def custom_anchor_shape(self, shape: PadStackShape.ValueType):
        self._proto.custom_anchor_shape = shape

    @property
    def zone_settings(self) -> board_types_pb2.ZoneConnectionSettings:
        """Reserved for future use -- at the moment, zone connection settings are not per-layer"""
        return self._proto.zone_settings

    @zone_settings.setter
    def zone_settings(self, settings: board_types_pb2.ZoneConnectionSettings):
        self._proto.zone_settings.CopyFrom(settings)


class DrillProperties(Wrapper):
    def __init__(
        self,
        proto: board_types_pb2.DrillProperties | None = None,
        proto_ref: board_types_pb2.DrillProperties | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.DrillProperties()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def start_layer(self) -> BoardLayer.ValueType:
        """Lowest (closest to F_Cu) layer this drill exists on."""
        return self._proto.start_layer

    @start_layer.setter
    def start_layer(self, layer: BoardLayer.ValueType):
        self._proto.start_layer = layer

    @property
    def end_layer(self) -> BoardLayer.ValueType:
        """Highest (closest to B_Cu) layer this drill exists on."""
        return self._proto.end_layer

    @end_layer.setter
    def end_layer(self, layer: BoardLayer.ValueType):
        self._proto.end_layer = layer

    @property
    def diameter(self) -> Vector2:
        """The drill diameter, which may also be a milled slot with different X and Y dimensions"""
        return Vector2(self._proto.diameter)

    @diameter.setter
    def diameter(self, diameter: Vector2):
        self._proto.diameter.CopyFrom(diameter.proto)

    @property
    def shape(self) -> board_types_pb2.DrillShape.ValueType:
        return self._proto.shape

    @shape.setter
    def shape(self, shape: board_types_pb2.DrillShape.ValueType):
        self._proto.shape = shape

    @property
    def capped(self) -> ViaDrillCappingMode.ValueType:
        """Whether the drill is capped (e.g. for tented back drills)"""
        return self._proto.capped

    @capped.setter
    def capped(self, capped: ViaDrillCappingMode.ValueType):
        self._proto.capped = capped

    @property
    def filled(self) -> ViaDrillFillingMode.ValueType:
        """Whether the drill is filled"""
        return self._proto.filled

    @filled.setter
    def filled(self, filled: ViaDrillFillingMode.ValueType):
        self._proto.filled = filled


class PostMachiningProperties(Wrapper):
    """Post-machining properties for a drill (counterbore or countersink)

    .. versionadded:: 0.9.0"""

    def __init__(
        self,
        proto: board_types_pb2.PostMachiningProperties | None = None,
        proto_ref: board_types_pb2.PostMachiningProperties | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_types_pb2.PostMachiningProperties()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def mode(self) -> ViaDrillPostMachiningMode.ValueType:
        return self._proto.mode

    @mode.setter
    def mode(self, mode: ViaDrillPostMachiningMode.ValueType):
        self._proto.mode = mode

    @property
    def size(self) -> int:
        return self._proto.size

    @size.setter
    def size(self, size: int):
        self._proto.size = size

    @property
    def depth(self) -> int:
        return self._proto.depth

    @depth.setter
    def depth(self, depth: int):
        self._proto.depth = depth

    @property
    def angle(self) -> int:
        return self._proto.angle

    @angle.setter
    def angle(self, angle: int):
        self._proto.angle = angle


class PadStackOuterLayer(Wrapper):
    def __init__(
        self,
        proto: board_types_pb2.PadStackOuterLayer | None = None,
        proto_ref: board_types_pb2.PadStackOuterLayer | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.PadStackOuterLayer()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def solder_mask_mode(self) -> board_types_pb2.SolderMaskMode.ValueType:
        return self._proto.solder_mask_mode

    @solder_mask_mode.setter
    def solder_mask_mode(self, mode: board_types_pb2.SolderMaskMode.ValueType):
        self._proto.solder_mask_mode = mode

    @property
    def solder_paste_mode(self) -> board_types_pb2.SolderPasteMode.ValueType:
        return self._proto.solder_paste_mode

    @solder_paste_mode.setter
    def solder_paste_mode(self, mode: board_types_pb2.SolderPasteMode.ValueType):
        self._proto.solder_paste_mode = mode

    @property
    def solder_mask_settings(self) -> SolderMaskOverrides:
        """NOTE: At present, KiCad does not support different solder mask expansion settings for
        the top and bottom layers"""
        return SolderMaskOverrides(proto_ref=self._proto.solder_mask_settings)

    @solder_mask_settings.setter
    def solder_mask_settings(self, settings: SolderMaskOverrides):
        self._proto.solder_mask_settings.CopyFrom(settings.proto)

    @property
    def solder_paste_settings(self) -> SolderPasteOverrides:
        """NOTE: At present, KiCad does not support different solder paste expansion settings for
        the top and bottom layers"""
        return SolderPasteOverrides(proto_ref=self._proto.solder_paste_settings)

    @solder_paste_settings.setter
    def solder_paste_settings(self, settings: SolderPasteOverrides):
        self._proto.solder_paste_settings.CopyFrom(settings.proto)

    @property
    def plugging_mode(self) -> ViaPluggingMode.ValueType:
        """
        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return self._proto.plugging_mode

    @plugging_mode.setter
    def plugging_mode(self, mode: ViaPluggingMode.ValueType):
        self._proto.plugging_mode = mode

    @property
    def covering_mode(self) -> ViaCoveringMode.ValueType:
        """
        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return self._proto.covering_mode

    @covering_mode.setter
    def covering_mode(self, mode: ViaCoveringMode.ValueType):
        self._proto.covering_mode = mode


class PadStack(BoardItem):
    def __init__(
        self,
        proto: board_types_pb2.PadStack | None = None,
        proto_ref: board_types_pb2.PadStack | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.PadStack()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def type(self) -> board_types_pb2.PadStackType.ValueType:
        """What type of pad stack this represents."""
        return self._proto.type

    @type.setter
    def type(self, type: board_types_pb2.PadStackType.ValueType):
        self._proto.type = type

        layer_map = {layer.layer: layer for layer in self._proto.copper_layers}

        required_layers = {
            board_types_pb2.PadStackType.PST_NORMAL: [BoardLayer.BL_F_Cu],
            board_types_pb2.PadStackType.PST_FRONT_INNER_BACK: [
                BoardLayer.BL_F_Cu,
                BoardLayer.BL_In1_Cu,
                BoardLayer.BL_B_Cu,
            ],
            board_types_pb2.PadStackType.PST_CUSTOM: [layer for layer in COPPER_LAYERS],
        }.get(type, [])

        for layer, value in layer_map.items():
            if layer not in required_layers:
                self._proto.copper_layers.remove(value)

        for layer in required_layers:
            if layer not in layer_map:
                self._add_copper_layer(layer)

    @property
    def layers(self) -> Sequence[BoardLayer.ValueType]:
        return self._proto.layers

    @layers.setter
    def layers(self, layers: Sequence[BoardLayer.ValueType]):
        del self._proto.layers[:]
        self._proto.layers.extend(layers)

    @property
    def drill(self) -> DrillProperties:
        """Properties of the drilled hole in this padstack, if it has one"""
        return DrillProperties(proto_ref=self._proto.drill)

    @property
    def unconnected_layer_removal(self) -> UnconnectedLayerRemoval.ValueType:
        """How to treat pad shapes on unconnected layers."""
        return self._proto.unconnected_layer_removal

    @unconnected_layer_removal.setter
    def unconnected_layer_removal(self, removal: UnconnectedLayerRemoval.ValueType):
        self._proto.unconnected_layer_removal = removal

    @property
    def copper_layers(self) -> MutableWrapperSequence[PadStackLayer]:
        return MutableWrapperSequence(self._proto.copper_layers, PadStackLayer)

    def copper_layer(self, layer: BoardLayer.ValueType) -> PadStackLayer | None:
        for copper_layer in self.copper_layers:
            if copper_layer.layer == layer:
                return copper_layer
        return None

    @property
    def angle(self) -> Angle:
        """The overall rotation of this padstack (affects all layers)"""
        return Angle(proto_ref=self._proto.angle)

    @angle.setter
    def angle(self, angle: Angle):
        self._proto.angle.CopyFrom(angle.proto)

    @property
    def front_outer_layers(self) -> PadStackOuterLayer:
        """Solder mask and paste settings for the front"""
        return PadStackOuterLayer(proto_ref=self._proto.front_outer_layers)

    @property
    def back_outer_layers(self) -> PadStackOuterLayer:
        """Solder mask and paste settings for the back"""
        return PadStackOuterLayer(proto_ref=self._proto.back_outer_layers)

    @property
    def zone_settings(self) -> ZoneConnectionSettings:
        """Controls for how copper zones connect to the padstack"""
        return ZoneConnectionSettings(proto_ref=self._proto.zone_settings)

    @property
    def secondary_drill(self) -> DrillProperties:
        """
        .. versionadded:: 0.9.0"""
        return DrillProperties(proto_ref=self._proto.secondary_drill)

    @secondary_drill.setter
    def secondary_drill(self, drill: DrillProperties):
        self._proto.secondary_drill.CopyFrom(drill.proto)

    @property
    def tertiary_drill(self) -> DrillProperties:
        """
        .. versionadded:: 0.9.0"""
        return DrillProperties(proto_ref=self._proto.tertiary_drill)

    @tertiary_drill.setter
    def tertiary_drill(self, drill: DrillProperties):
        self._proto.tertiary_drill.CopyFrom(drill.proto)

    @property
    def front_post_machining(self) -> PostMachiningProperties:
        """
        .. versionadded:: 0.9.0"""
        return PostMachiningProperties(proto_ref=self._proto.front_post_machining)

    @front_post_machining.setter
    def front_post_machining(self, properties: PostMachiningProperties):
        self._proto.front_post_machining.CopyFrom(properties.proto)

    @property
    def back_post_machining(self) -> PostMachiningProperties:
        """
        .. versionadded:: 0.9.0"""
        return PostMachiningProperties(proto_ref=self._proto.back_post_machining)

    @back_post_machining.setter
    def back_post_machining(self, properties: PostMachiningProperties):
        self._proto.back_post_machining.CopyFrom(properties.proto)

    def is_masked(self, layer: BoardLayer.ValueType = BoardLayer.BL_UNDEFINED) -> bool:
        """
        Returns true if the padstack is masked on the given copper layer, or on either layer if
        layer is ``BL_UNDEFINED``.
        """
        if layer == BoardLayer.BL_UNDEFINED:
            return (
                self.front_outer_layers.solder_mask_mode == SolderMaskMode.SMM_MASKED
                or self.back_outer_layers.solder_mask_mode == SolderMaskMode.SMM_MASKED
            )
        elif layer == BoardLayer.BL_F_Cu:
            return self.front_outer_layers.solder_mask_mode == SolderMaskMode.SMM_MASKED
        elif layer == BoardLayer.BL_B_Cu:
            return self.back_outer_layers.solder_mask_mode == SolderMaskMode.SMM_MASKED
        return False

    def _add_copper_layer(self, layer: BoardLayer.ValueType) -> board_types_pb2.PadStackLayer:
        self._proto.copper_layers.append(board_types_pb2.PadStackLayer())
        self._proto.copper_layers[-1].layer = layer
        return self._proto.copper_layers[-1]


class SymbolPinInfo(Wrapper):
    """Information about the symbol pin associated with a pad, if one exists

    .. versionadded:: 0.9.0 (KiCad 10.0.7)"""

    def __init__(
        self,
        proto: board_types_pb2.SymbolPinInfo | None = None,
        proto_ref: board_types_pb2.SymbolPinInfo | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.SymbolPinInfo()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"SymbolPinInfo(name={self.name}, type={self.type}, no_connect={self.no_connect})"

    @property
    def name(self) -> str:
        """The pin name for the associated symbol pin (empty if none exists)"""
        return self._proto.name

    @name.setter
    def name(self, name: str):
        self._proto.name = name

    @property
    def type(self) -> base_types_pb2.ElectricalPinType.ValueType:
        """The electrical type of the associated symbol pin (``EPT_UNKNOWN`` if not)"""
        return self._proto.type

    @type.setter
    def type(self, type: base_types_pb2.ElectricalPinType.ValueType):
        self._proto.type = type

    @property
    def no_connect(self) -> bool:
        """True if the pin is attached to a no-connect marker in the schematic"""
        return self._proto.no_connect

    @no_connect.setter
    def no_connect(self, no_connect: bool):
        self._proto.no_connect = no_connect


class Pad(BoardItem):
    def __init__(
        self,
        proto: board_types_pb2.Pad | None = None,
        proto_ref: board_types_pb2.Pad | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Pad()

        if proto is not None:
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self.padstack.type = PST_NORMAL

    def __repr__(self) -> str:
        return (
            f"Pad(position={self.position}, net={self.net.name}, "
            f"type={PadType.Name(self.pad_type)})"
        )

    @property
    def id(self) -> KIID:
        return self._proto.id

    @property
    def number(self) -> str:
        return self._proto.number

    @number.setter
    def number(self, number: str):
        self._proto.number = number

    @property
    def position(self) -> Vector2:
        """A pad's position is always relative to the parent footprint's origin"""
        return Vector2(self._proto.position)

    @position.setter
    def position(self, position: Vector2):
        self._proto.position.CopyFrom(position.proto)

    @property
    def fab_property(self) -> PadFabricationProperty.ValueType:
        """Fabrication property of the pad

        .. versionadded:: 0.x.0 (KiCad 10.0.7)"""
        return self._proto.fab_property

    @fab_property.setter
    def fab_property(self, fab_property: PadFabricationProperty.ValueType):
        self._proto.fab_property = fab_property

    @property
    def net(self) -> Net:
        return Net(self._proto.net)

    @net.setter
    def net(self, net: Net):
        self._proto.net.CopyFrom(net.proto)

    @property
    def pad_type(self) -> PadType.ValueType:
        """
        The type of the pad (PTH, NPTH, SMD, or edge connector).  Note that there is not a direct
        mapping between pad type and padstack properties; it is currently up to the user to ensure
        that the value of this property and the padstack properties are consistent.
        """
        return self._proto.type

    @pad_type.setter
    def pad_type(self, pad_type: PadType.ValueType):
        """
        .. versionadded:: 0.4.0 (setter)
        """
        self._proto.type = pad_type

    @property
    def padstack(self) -> PadStack:
        return PadStack(proto_ref=self._proto.pad_stack)

    @property
    def pad_to_die_length(self) -> int:
        """
        .. versionadded:: 0.5.0 (with KiCad 9.0.4)
        """
        return self._proto.pad_to_die_length.value_nm

    @pad_to_die_length.setter
    def pad_to_die_length(self, length: int):
        self._proto.pad_to_die_length.value_nm = length

    @property
    def teardrop(self) -> PadTeardropSettings:
        """Teardrop settings for this pad

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return PadTeardropSettings(proto_ref=self._proto.teardrop)

    @teardrop.setter
    def teardrop(self, settings: PadTeardropSettings):
        self._proto.teardrop.CopyFrom(settings.proto)

    @property
    def sim_electrical_type(self) -> PadSimElectricalType.ValueType:
        """The electrical type of this pad for simulation purposes

        .. versionadded:: 0.9.0"""
        return self._proto.sim_electrical_type

    @sim_electrical_type.setter
    def sim_electrical_type(self, sim_type: PadSimElectricalType.ValueType):
        self._proto.sim_electrical_type = sim_type

    @property
    def copper_clearance_override(self) -> int | None:
        """Copper-to-copper clearance override in nanometers

        .. versionadded:: 0.9.0"""
        if self._proto.HasField("copper_clearance_override"):
            return self._proto.copper_clearance_override.value_nm
        return None

    @copper_clearance_override.setter
    def copper_clearance_override(self, clearance_nm: int | None):
        if clearance_nm is None:
            self._proto.ClearField("copper_clearance_override")
        else:
            self._proto.copper_clearance_override.value_nm = clearance_nm

    @property
    def pad_to_die_delay(self) -> int | None:
        """Pad-to-die delay in attoseconds

        .. versionadded:: 0.9.0"""
        if self._proto.HasField("pad_to_die_delay"):
            return self._proto.pad_to_die_delay.value_as
        return None

    @pad_to_die_delay.setter
    def pad_to_die_delay(self, delay: int | None):
        if delay is None:
            self._proto.ClearField("pad_to_die_delay")
        else:
            self._proto.pad_to_die_delay.value_as = delay

    @property
    def symbol_pin(self) -> SymbolPinInfo:
        """Information about the associated symbol pin, if one exists

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return SymbolPinInfo(proto_ref=self._proto.symbol_pin)

    @symbol_pin.setter
    def symbol_pin(self, pin: SymbolPinInfo):
        self._proto.symbol_pin.CopyFrom(pin.proto)

    @property
    def custom_properties(self) -> MutableWrapperSequence[CustomProperty]:
        """
        .. versionadded:: 0.x.0 (KiCad 11)"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, properties: list[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(p.proto for p in properties)

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None


class Via(BoardItem):
    def __init__(
        self,
        proto: board_types_pb2.Via | None = None,
        proto_ref: board_types_pb2.Via | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Via()

        if proto is not None:
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self.type = ViaType.VT_THROUGH
            self.padstack.type = PST_NORMAL

    def __repr__(self) -> str:
        return (
            f"Via(position={self.position}, net={self.net.name}, type={ViaType.Name(self.type)}, "
            f"locked={self.locked})"
        )

    @property
    def position(self) -> Vector2:
        """The location of the via's center point"""
        return Vector2(self._proto.position)

    @position.setter
    def position(self, position: Vector2):
        self._proto.position.CopyFrom(position.proto)

    @property
    def net(self) -> Net:
        return Net(self._proto.net)

    @net.setter
    def net(self, net: Net):
        self._proto.net.CopyFrom(net.proto)

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = LockedState.LS_LOCKED if locked else LockedState.LS_UNLOCKED

    @property
    def type(self) -> ViaType.ValueType:
        """The type of the via (through, blind/buried, or micro)

        Setting this property will also update the padstack drill start and end layers as a
        side effect.

        .. versionadded:: 0.3.0 with KiCad 9.0.1
        """
        return self._proto.type

    @type.setter
    def type(self, type: ViaType.ValueType):
        self._proto.type = type

        if (
            type == ViaType.VT_THROUGH
            or self.padstack.drill.start_layer == BoardLayer.BL_UNKNOWN
            or self.padstack.drill.end_layer == BoardLayer.BL_UNKNOWN
        ):
            self.padstack.drill.start_layer = BoardLayer.BL_F_Cu
            self.padstack.drill.end_layer = BoardLayer.BL_B_Cu

    @property
    def padstack(self) -> PadStack:
        """The pad stack definition for this via."""
        return PadStack(proto_ref=self._proto.pad_stack)

    @property
    def diameter(self) -> int:
        """A helper property to get or set the diameter of the via on all copper layers.

        Warning: only makes sense if the via's padstack mode is ``PST_NORMAL``.  This will return the
        pad diameter on the front copper layer otherwise.  Setting this property will set the
        padstack mode to ``PST_NORMAL`` as a side-effect.

        To get or set the diameter for other padstack types, use the :attr:`padstack` property
        directly.

        .. versionadded:: 0.3.0 with KiCad 9.0.1"""
        if len(self.padstack.copper_layers) == 0:
            raise ValueError("Unexpected empty padstack for via!")

        return self.padstack.copper_layers[0].size.x

    @diameter.setter
    def diameter(self, diameter: int):
        self.padstack.type = PST_NORMAL
        self.padstack.copper_layers[0].size = Vector2.from_xy(diameter, diameter)

    @property
    def drill_diameter(self) -> int:
        """The diameter of the via's drill (KiCad only supports circular drills in vias)"""
        return self.padstack.drill.diameter.x

    @drill_diameter.setter
    def drill_diameter(self, diameter: int):
        self.padstack.drill.diameter = Vector2.from_xy(diameter, diameter)

    @property
    def is_free(self) -> bool:
        """Whether the via is a free (locked-from-autorouter perspective) via

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return self._proto.is_free

    @is_free.setter
    def is_free(self, is_free: bool):
        self._proto.is_free = is_free

    @property
    def teardrop(self) -> PadTeardropSettings:
        """Teardrop settings for this via

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return PadTeardropSettings(proto_ref=self._proto.teardrop)

    @teardrop.setter
    def teardrop(self, settings: PadTeardropSettings):
        self._proto.teardrop.CopyFrom(settings.proto)

    @property
    def custom_properties(self) -> MutableWrapperSequence[CustomProperty]:
        """
        .. versionadded:: 0.x.0 (KiCad 11)"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, properties: list[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(p.proto for p in properties)

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None


class FootprintAttributes(Wrapper):
    """The built-in attributes that a Footprint or FootprintInstance may have"""

    def __init__(
        self,
        proto: board_types_pb2.FootprintAttributes | None = None,
        proto_ref: board_types_pb2.FootprintAttributes | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.FootprintAttributes()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def not_in_schematic(self) -> bool:
        return self._proto.not_in_schematic

    @not_in_schematic.setter
    def not_in_schematic(self, not_in_schematic: bool):
        self._proto.not_in_schematic = not_in_schematic

    @property
    def exclude_from_bill_of_materials(self) -> bool:
        return self._proto.exclude_from_bill_of_materials

    @exclude_from_bill_of_materials.setter
    def exclude_from_bill_of_materials(self, exclude: bool):
        self._proto.exclude_from_bill_of_materials = exclude

    @property
    def exclude_from_position_files(self) -> bool:
        return self._proto.exclude_from_position_files

    @exclude_from_position_files.setter
    def exclude_from_position_files(self, exclude: bool):
        self._proto.exclude_from_position_files = exclude

    @property
    def do_not_populate(self) -> bool:
        return self._proto.do_not_populate

    @do_not_populate.setter
    def do_not_populate(self, do_not_populate: bool):
        self._proto.do_not_populate = do_not_populate

    @property
    def exempt_from_courtyard_requirement(self) -> bool:
        return self._proto.exempt_from_courtyard_requirement

    @exempt_from_courtyard_requirement.setter
    def exempt_from_courtyard_requirement(self, exempt_from_courtyard_requirement: bool):
        self._proto.exempt_from_courtyard_requirement = exempt_from_courtyard_requirement

    @property
    def allow_soldermask_bridges(self) -> bool:
        return self._proto.allow_soldermask_bridges

    @allow_soldermask_bridges.setter
    def allow_soldermask_bridges(self, allow_soldermask_bridges: bool):
        self._proto.allow_soldermask_bridges = allow_soldermask_bridges

    @property
    def exclude_from_simulation(self) -> bool:
        return self._proto.exclude_from_simulation

    @exclude_from_simulation.setter
    def exclude_from_simulation(self, exclude_from_simulation: bool):
        self._proto.exclude_from_simulation = exclude_from_simulation

    @property
    def mounting_style(self) -> board_types_pb2.FootprintMountingStyle.ValueType:
        """
        The mounting style of the footprint (SMD, through-hole, or unspecified)

        .. versionadded:: 0.3.0 with KiCad 9.0.1
        """
        return self._proto.mounting_style

    @mounting_style.setter
    def mounting_style(self, style: board_types_pb2.FootprintMountingStyle.ValueType):
        self._proto.mounting_style = style

    @property
    def description(self) -> str:
        return self._proto.description

    @description.setter
    def description(self, description: str):
        self._proto.description = description

    @property
    def keywords(self) -> str:
        return self._proto.keywords

    @keywords.setter
    def keywords(self, keywords: str):
        self._proto.keywords = keywords


class Footprint3DModel(Wrapper):
    """Represents a 3D model associated with a footprint"""

    def __init__(
        self,
        proto: board_types_pb2.Footprint3DModel | None = None,
        proto_ref: board_types_pb2.Footprint3DModel | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Footprint3DModel()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"Footprint3DModel(filename='{self.filename}', "
            f"visisble={self.visible}, opacity={self.opacity}, "
            f"rotation=({self.rotation.x}, {self.rotation.y}, {self.rotation.z}), "
            f"scale=({self.scale.x}, {self.scale.y}, {self.scale.z}))"
        )

    @property
    def filename(self) -> str:
        return self._proto.filename

    @filename.setter
    def filename(self, filename: str):
        self._proto.filename = filename

    @property
    def scale(self) -> Vector3D:
        """Scaling factor along each axis"""
        return Vector3D(self._proto.scale)

    @scale.setter
    def scale(self, scale: Vector3D):
        self._proto.scale.CopyFrom(scale.proto)

    @property
    def rotation(self) -> Vector3D:
        """Rotation around each axis, in degrees"""
        return Vector3D(self._proto.rotation)

    @rotation.setter
    def rotation(self, rotation: Vector3D):
        self._proto.rotation.CopyFrom(rotation.proto)

    @property
    def offset(self) -> Vector3D:
        """Offset from footprint center"""
        return Vector3D(self._proto.offset)

    @offset.setter
    def offset(self, offset: Vector3D):
        self._proto.offset.CopyFrom(offset.proto)

    @property
    def visible(self) -> bool:
        return self._proto.visible

    @visible.setter
    def visible(self, visible: bool):
        self._proto.visible = visible

    @property
    def opacity(self) -> float:
        return self._proto.opacity

    @opacity.setter
    def opacity(self, opacity: float):
        self._proto.opacity = opacity


class FootprintDesignRuleOverrides(Wrapper):
    """Footprint design rule overrides: all values are optional; if absent, the rules from the
    board will be used.

    .. versionadded:: 0.8.0
    """

    def __init__(
        self,
        proto: board_types_pb2.FootprintDesignRuleOverrides | None = None,
        proto_ref: board_types_pb2.FootprintDesignRuleOverrides | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_types_pb2.FootprintDesignRuleOverrides()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def solder_mask(self) -> SolderMaskOverrides | None:
        if self._proto.HasField("solder_mask"):
            return SolderMaskOverrides(proto_ref=self._proto.solder_mask)
        return None

    @solder_mask.setter
    def solder_mask(self, value: SolderMaskOverrides | None):
        if value is not None:
            self._proto.solder_mask.CopyFrom(value.proto)
        else:
            self._proto.ClearField("solder_mask")

    @property
    def solder_paste(self) -> SolderPasteOverrides | None:
        if self._proto.HasField("solder_paste"):
            return SolderPasteOverrides(proto_ref=self._proto.solder_paste)
        return None

    @solder_paste.setter
    def solder_paste(self, value: SolderPasteOverrides | None):
        if value is not None:
            self._proto.solder_paste.CopyFrom(value.proto)
        else:
            self._proto.ClearField("solder_paste")

    @property
    def copper_clearance(self) -> int | None:
        if self._proto.HasField("copper_clearance"):
            return self._proto.copper_clearance.value_nm
        return None

    @copper_clearance.setter
    def copper_clearance(self, clearance_nm: int | None):
        if clearance_nm is not None:
            self._proto.copper_clearance.value_nm = clearance_nm
        else:
            self._proto.ClearField("copper_clearance")

    @property
    def zone_connection(self) -> ZoneConnectionStyle.ValueType:
        return self._proto.zone_connection

    @zone_connection.setter
    def zone_connection(self, value: ZoneConnectionStyle.ValueType):
        self._proto.zone_connection = value


class NetTieDefinition(Wrapper):
    """Definition of one net-tie group in a footprint: a set of pad numbers that are
    shorted together

    .. versionadded:: 0.9.0 (KiCad 10.0.7)"""

    def __init__(
        self,
        proto: board_types_pb2.NetTieDefinition | None = None,
        proto_ref: board_types_pb2.NetTieDefinition | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.NetTieDefinition()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def pad_numbers(self) -> list[str]:
        return list(self._proto.pad_number)

    @pad_numbers.setter
    def pad_numbers(self, pad_numbers: list[str]):
        del self._proto.pad_number[:]
        self._proto.pad_number.extend(pad_numbers)


class JumperGroup(Wrapper):
    """A group of pad names in a footprint that are jumpered together

    .. versionadded:: 0.9.0 (KiCad 10.0.7)"""

    def __init__(
        self,
        proto: board_types_pb2.JumperGroup | None = None,
        proto_ref: board_types_pb2.JumperGroup | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.JumperGroup()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def pad_names(self) -> list[str]:
        return list(self._proto.pad_names)

    @pad_names.setter
    def pad_names(self, pad_names: list[str]):
        del self._proto.pad_names[:]
        self._proto.pad_names.extend(pad_names)


class JumperSettings(Wrapper):
    """Jumper settings for a footprint

    .. versionadded:: 0.9.0 (KiCad 10.0.7)"""

    def __init__(
        self,
        proto: board_types_pb2.JumperSettings | None = None,
        proto_ref: board_types_pb2.JumperSettings | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.JumperSettings()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def duplicate_names_are_jumpered(self) -> bool:
        """If true, duplicate pad names in this footprint are jumpered together"""
        return self._proto.duplicate_names_are_jumpered

    @duplicate_names_are_jumpered.setter
    def duplicate_names_are_jumpered(self, value: bool):
        self._proto.duplicate_names_are_jumpered = value

    @property
    def groups(self) -> MutableWrapperSequence[JumperGroup]:
        return MutableWrapperSequence(self._proto.groups, JumperGroup)

    @groups.setter
    def groups(self, groups: list[JumperGroup]):
        del self._proto.groups[:]
        self._proto.groups.extend(g.proto for g in groups)


class Footprint(Wrapper):
    """Represents the definition of a footprint (existing in a footprint library or on a board),
    which contains the child objects of the footprint (pads, text, etc).  Footprint definitions are
    contained by a FootprintInstance which represents a footprint placed on a board."""

    def __init__(
        self,
        proto: board_types_pb2.Footprint | None = None,
        proto_ref: board_types_pb2.Footprint | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Footprint()

        if proto is not None:
            self._proto.CopyFrom(proto)

        self._unwrapped_items = [unwrap(item) for item in self._proto.items]

    def _pack(self):
        """Packs all items in the footprint into the proto"""
        del self._proto.items[:]
        for item in self._unwrapped_items:
            any = Any()
            any.Pack(item.proto)
            self._proto.items.append(any)

    def __repr__(self) -> str:
        return f"Footprint(id={self.id}, items={len(self.items)})"

    @property
    def id(self) -> LibraryIdentifier:
        return LibraryIdentifier(proto_ref=self._proto.id)

    @id.setter
    def id(self, attributes: LibraryIdentifier):
        self._proto.id.CopyFrom(attributes.proto)

    @property
    def items(self) -> Sequence[Wrapper]:
        return self._unwrapped_items

    @items.setter
    def items(self, items: Sequence[Wrapper]):
        self._unwrapped_items = list(items)

    @property
    def pads(self) -> Sequence[Pad]:
        """Returns all pads in the footprint"""
        return [item for item in self.items if isinstance(item, Pad)]

    @property
    def shapes(self) -> Sequence[BoardShape]:
        """Returns all graphic shapes in the footprint"""
        return [
            item
            for item in (
                to_concrete_board_shape(shape)
                for shape in [item for item in self.items if isinstance(item, BoardShape)]
            )
            if item is not None
        ]

    @property
    def texts(self) -> Sequence[BoardText | BoardTextBox | Field]:
        """Returns all fields and free text objects in the footprint library definition"""
        return [item for item in self.items if isinstance(item, (BoardText, BoardTextBox, Field))]

    @property
    def models(self) -> Sequence[Footprint3DModel]:
        """Returns all 3D models in the footprint

        .. versionadded:: 0.3.0"""
        return [item for item in self.items if isinstance(item, Footprint3DModel)]

    def add_item(self, item: Wrapper):
        self._unwrapped_items.append(item)

    @property
    def anchor(self) -> Vector2:
        """The anchor (origin) position of the footprint

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return Vector2(self._proto.anchor)

    @anchor.setter
    def anchor(self, anchor: Vector2):
        self._proto.anchor.CopyFrom(anchor.proto)

    @property
    def net_ties(self) -> MutableWrapperSequence[NetTieDefinition]:
        """The net-tie groups defined in this footprint

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return MutableWrapperSequence(self._proto.net_ties, NetTieDefinition)

    @net_ties.setter
    def net_ties(self, net_ties: list[NetTieDefinition]):
        del self._proto.net_ties[:]
        self._proto.net_ties.extend(t.proto for t in net_ties)

    @property
    def private_layers(self) -> list[BoardLayer.ValueType]:
        """The private layers of this footprint, which are removed alongside the footprint

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return list(self._proto.private_layers)

    @private_layers.setter
    def private_layers(self, layers: list[BoardLayer.ValueType]):
        del self._proto.private_layers[:]
        self._proto.private_layers.extend(layers)

    @property
    def jumpers(self) -> JumperSettings:
        """The jumper settings for this footprint

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return JumperSettings(proto_ref=self._proto.jumpers)

    @jumpers.setter
    def jumpers(self, settings: JumperSettings):
        self._proto.jumpers.CopyFrom(settings.proto)


class FootprintInstance(BoardItem):
    """Represents a footprint instance on a board"""

    def __init__(self, proto: board_types_pb2.FootprintInstance | None = None):
        self._proto = board_types_pb2.FootprintInstance()

        if proto is not None:
            self._proto.CopyFrom(proto)

        self._definition = Footprint(proto_ref=self._proto.definition)

    @property
    def proto(self):
        self._definition._pack()
        return self.__dict__["_proto"]

    def __repr__(self) -> str:
        return f"FootprintInstance(id={self.id}, pos={self.position}, layer={BoardLayer.Name(self.layer)})"

    @property
    def id(self) -> KIID:
        return self._proto.id

    @property
    def position(self) -> Vector2:
        return Vector2(proto_ref=self._proto.position)

    @position.setter
    def position(self, position: Vector2):
        """Changes the footprint position, which will also update the positions of all the
        contained items since KiCad footprint children are stored with absolute positions"""
        delta = position - self.position

        local_delta = Vector2.from_xy(delta.x, delta.y).rotate(
            Angle.from_degrees(-self.orientation.degrees), Vector2.from_xy(0, 0)
        )

        self._proto.position.CopyFrom(position.proto)

        for field in [
            self.reference_field,
            self.value_field,
            self.datasheet_field,
            self.description_field,
        ]:
            field.text.position += delta

        for item in self.definition.items:
            if isinstance(item, Field):
                item.text.position += delta
            elif isinstance(item, (Pad, BoardText)):
                item.position += delta
            elif isinstance(item, Zone):
                # Zone outlines inside a footprint definition are stored in the footprint's
                # local coordinate frame but any filled polys are in the board frame
                item.outline.move(local_delta)

                for polygons in item.filled_polygons.values():
                    for polygon in polygons:
                        polygon.move(delta)
            elif isinstance(item, BoardTextBox):
                item.top_left += delta
                item.bottom_right += delta
            elif isinstance(item, (Barcode, ReferencePoint)):
                item.position += delta
            elif isinstance(item, Dimension):
                dimension = to_concrete_dimension(item)
                assert dimension

                if isinstance(dimension, (AlignedDimension, OrthogonalDimension, LeaderDimension)):
                    dimension.start += delta
                    dimension.end += delta
                elif isinstance(dimension, RadialDimension):
                    dimension.center += delta
                    dimension.radius_point += delta
                elif isinstance(dimension, CenterDimension):
                    dimension.center += delta
                    dimension.end += delta

                dimension.text.position += delta
            elif isinstance(item, Table):
                for cell in item.cells:
                    cell.text.top_left += delta
                    cell.text.bottom_right += delta
            elif isinstance(item, BoardShape):
                shape = to_concrete_board_shape(item)
                assert shape
                shape.move(delta)

    @property
    def orientation(self) -> Angle:
        return Angle(proto_ref=self._proto.orientation)

    @orientation.setter
    def orientation(self, orientation: Angle):
        normalized = Angle(orientation.proto).normalize180()
        live = self.orientation
        delta = normalized - live
        live.degrees = normalized.degrees

        for field in [
            self.reference_field,
            self.value_field,
            self.datasheet_field,
            self.description_field,
        ]:
            field.text.position = field.text.position.rotate(delta, self.position)
            field.text.attributes.angle += delta.degrees

        updated_items: list[Wrapper] = []
        for item in self.definition.items:
            if isinstance(item, Field):
                item.text.position = item.text.position.rotate(delta, self.position)
                item.text.attributes.angle += delta.degrees
            elif isinstance(item, Pad):
                item.position = item.position.rotate(delta, self.position)
                item.padstack.angle += delta
            elif isinstance(item, BoardText):
                item.position = item.position.rotate(delta, self.position)
                item.attributes.angle += delta.degrees
            elif isinstance(item, BoardTextBox):
                item.top_left = item.top_left.rotate(delta, self.position)
                item.bottom_right = item.bottom_right.rotate(delta, self.position)
                item.attributes.angle += delta.degrees
            elif isinstance(item, Table):
                for cell in item.cells:
                    cell.text.top_left = cell.text.top_left.rotate(delta, self.position)
                    cell.text.bottom_right = cell.text.bottom_right.rotate(delta, self.position)
                    cell.text.attributes.angle += delta.degrees
            elif isinstance(item, DrillChart):
                for cell in item.table.cells:
                    cell.text.top_left = cell.text.top_left.rotate(delta, self.position)
                    cell.text.bottom_right = cell.text.bottom_right.rotate(delta, self.position)
                    cell.text.attributes.angle += delta.degrees
            elif isinstance(item, Barcode):
                item.position = item.position.rotate(delta, self.position)
                item.orientation += delta
            elif isinstance(item, ReferencePoint):
                item.position = item.position.rotate(delta, self.position)
            elif isinstance(item, Dimension):
                dimension = to_concrete_dimension(item)
                assert dimension

                if isinstance(dimension, (AlignedDimension, OrthogonalDimension, LeaderDimension)):
                    dimension.start = dimension.start.rotate(delta, self.position)
                    dimension.end = dimension.end.rotate(delta, self.position)
                elif isinstance(dimension, RadialDimension):
                    dimension.center = dimension.center.rotate(delta, self.position)
                    dimension.radius_point = dimension.radius_point.rotate(delta, self.position)
                elif isinstance(dimension, CenterDimension):
                    dimension.center = dimension.center.rotate(delta, self.position)
                    dimension.end = dimension.end.rotate(delta, self.position)

                dimension.text.position = dimension.text.position.rotate(delta, self.position)
                dimension.text.attributes.angle += delta.degrees
            elif isinstance(item, Zone):
                # Zone outlines inside a footprint definition are stored in the footprint's
                # local coordinate frame but any filled polys are in the board frame
                for polygons in item.filled_polygons.values():
                    for polygon in polygons:
                        polygon.rotate(delta, self.position)
            elif isinstance(item, BoardShape):
                shape = to_concrete_board_shape(item)
                assert shape
                if isinstance(shape, BoardRectangle) and delta.normalize().degrees % 90 != 0:
                    shape = BoardPolygon.from_rectangle(shape)

                shape.rotate(delta, self.position)
                item = shape

            updated_items.append(item)

        self.definition.items = updated_items

    @property
    def layer(self) -> BoardLayer.ValueType:
        """The layer on which the footprint is placed (BoardLayer.BL_F_Cu or BoardLayer.BL_B_Cu)

        NOTE: Do not use this property to try to flip an existing footprint to the other side
        of a board.  Use :meth:`~kipy.board.Board.flip_items` or
        :meth:`~kipy.board.Board.flip_items_by_id` instead."""
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = LockedState.LS_LOCKED if locked else LockedState.LS_UNLOCKED

    @property
    def definition(self) -> Footprint:
        return self._definition

    @property
    def reference_field(self) -> Field:
        return Field(proto_ref=self._proto.reference_field)

    @reference_field.setter
    def reference_field(self, field: Field):
        self._proto.reference_field.CopyFrom(field.proto)

    @property
    def value_field(self) -> Field:
        return Field(proto_ref=self._proto.value_field)

    @value_field.setter
    def value_field(self, field: Field):
        self._proto.value_field.CopyFrom(field.proto)

    @property
    def datasheet_field(self) -> Field:
        return Field(proto_ref=self._proto.datasheet_field)

    @datasheet_field.setter
    def datasheet_field(self, field: Field):
        self._proto.datasheet_field.CopyFrom(field.proto)

    @property
    def description_field(self) -> Field:
        return Field(proto_ref=self._proto.description_field)

    @description_field.setter
    def description_field(self, field: Field):
        self._proto.description_field.CopyFrom(field.proto)

    @property
    def attributes(self) -> FootprintAttributes:
        return FootprintAttributes(proto_ref=self._proto.attributes)

    @property
    def overrides(self) -> FootprintDesignRuleOverrides:
        """Returns the design rule overrides for the footprint

        .. versionadded:: 0.8.0
        """
        return FootprintDesignRuleOverrides(proto_ref=self._proto.overrides)

    @overrides.setter
    def overrides(self, value: FootprintDesignRuleOverrides):
        self._proto.overrides.CopyFrom(value.proto)

    @property
    def texts_and_fields(self) -> Sequence[BoardText | BoardTextBox | Field]:
        """Returns all fields and free text objects in the footprint"""
        return [
            item
            for item in self.definition.items
            if isinstance(item, (BoardText, BoardTextBox, Field))
        ] + [
            self.reference_field,
            self.value_field,
            self.datasheet_field,
            self.description_field,
        ]

    @property
    def sheet_path(self) -> SheetPath:
        """
        The path to this footprint instance's corresponding symbol schematic sheet

        .. versionadded:: 0.4.0 with KiCad 9.0.3
        """
        return SheetPath(self._proto.symbol_path)

    @property
    def symbol_sheet_name(self) -> str:
        """The name of the hierarchical sheet the associated symbol for this footprint exists on,
        or the empty string if there is no associated symbol.

        ..versionadded:: 0.9.0 (KiCad 9.0.7)"""
        return self._proto.symbol_sheet_name

    @property
    def symbol_sheet_filename(self) -> str:
        """The filename of the hierarchical sheet the associated symbol for this footprint exists,
        on, or the empty string if there is no associated symbol.

        ..versionadded:: 0.9.0 (KiCad 9.0.7)"""
        return self._proto.symbol_sheet_filename

    @property
    def embedded_files(self) -> EmbeddedFiles | None:
        """Files embedded in this footprint instance

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        if self._proto.HasField("embedded_files"):
            return EmbeddedFiles(proto_ref=self._proto.embedded_files)
        return None

    @embedded_files.setter
    def embedded_files(self, files: EmbeddedFiles | None):
        if files is not None:
            self._proto.embedded_files.CopyFrom(files.proto)
        else:
            self._proto.ClearField("embedded_files")

    @property
    def custom_properties(self) -> MutableWrapperSequence[CustomProperty]:
        """
        .. versionadded:: 0.x.0 (KiCad 11)"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, properties: list[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(p.proto for p in properties)

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None


class ZoneFilledPolygons(Wrapper):
    """Represents the set of filled polygons of a zone on a single board layer"""

    def __init__(
        self,
        proto: board_types_pb2.ZoneFilledPolygons | None = None,
        proto_ref: board_types_pb2.ZoneFilledPolygons | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.ZoneFilledPolygons()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def shapes(self) -> Sequence[PolygonWithHoles]:
        return MutableWrapperSequence(self._proto.shapes.polygons, PolygonWithHoles)


class HatchFillSettings(Wrapper):
    """Hatch fill settings for a copper zone

    .. versionadded:: 0.9.0 (KiCad 10.0.7)"""

    def __init__(
        self,
        proto: board_types_pb2.HatchFillSettings | None = None,
        proto_ref: board_types_pb2.HatchFillSettings | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.HatchFillSettings()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def thickness(self) -> int:
        return self._proto.thickness.value_nm

    @thickness.setter
    def thickness(self, thickness_nm: int):
        self._proto.thickness.value_nm = thickness_nm

    @property
    def gap(self) -> int:
        return self._proto.gap.value_nm

    @gap.setter
    def gap(self, gap_nm: int):
        self._proto.gap.value_nm = gap_nm

    @property
    def orientation(self) -> Angle:
        return Angle(proto_ref=self._proto.orientation)

    @orientation.setter
    def orientation(self, orientation: Angle):
        self._proto.orientation.CopyFrom(orientation.proto)

    @property
    def hatch_smoothing_ratio(self) -> float:
        return self._proto.hatch_smoothing_ratio

    @hatch_smoothing_ratio.setter
    def hatch_smoothing_ratio(self, ratio: float):
        self._proto.hatch_smoothing_ratio = ratio

    @property
    def hatch_hole_min_area_ratio(self) -> float:
        return self._proto.hatch_hole_min_area_ratio

    @hatch_hole_min_area_ratio.setter
    def hatch_hole_min_area_ratio(self, ratio: float):
        self._proto.hatch_hole_min_area_ratio = ratio

    @property
    def border_mode(self) -> ZoneHatchFillBorderMode.ValueType:
        return self._proto.border_mode

    @border_mode.setter
    def border_mode(self, mode: ZoneHatchFillBorderMode.ValueType):
        self._proto.border_mode = mode


class ThievingFillSettings(Wrapper):
    """Thieving fill (fill pattern that is not connected to any net) settings for a copper zone

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.ThievingFillSettings | None = None,
        proto_ref: board_types_pb2.ThievingFillSettings | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_types_pb2.ThievingFillSettings()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def pattern(self) -> ThievingPattern.ValueType:
        return self._proto.pattern

    @pattern.setter
    def pattern(self, pattern: ThievingPattern.ValueType):
        self._proto.pattern = pattern

    @property
    def element_size(self) -> int:
        return self._proto.element_size.value_nm

    @element_size.setter
    def element_size(self, size_nm: int):
        self._proto.element_size.value_nm = size_nm

    @property
    def gap(self) -> int:
        return self._proto.gap.value_nm

    @gap.setter
    def gap(self, gap_nm: int):
        self._proto.gap.value_nm = gap_nm

    @property
    def line_width(self) -> int:
        return self._proto.line_width.value_nm

    @line_width.setter
    def line_width(self, width_nm: int):
        self._proto.line_width.value_nm = width_nm

    @property
    def stagger(self) -> bool:
        return self._proto.stagger

    @stagger.setter
    def stagger(self, stagger: bool):
        self._proto.stagger = stagger

    @property
    def orientation(self) -> Angle:
        return Angle(proto_ref=self._proto.orientation)

    @orientation.setter
    def orientation(self, orientation: Angle):
        self._proto.orientation.CopyFrom(orientation.proto)


class RuleAreaSettings(Wrapper):
    """Settings that apply only to rule area zones

    .. versionadded:: 0.9.0"""

    def __init__(
        self,
        proto: board_types_pb2.RuleAreaSettings | None = None,
        proto_ref: board_types_pb2.RuleAreaSettings | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.RuleAreaSettings()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def keepout_copper(self) -> bool:
        return self._proto.keepout_copper

    @keepout_copper.setter
    def keepout_copper(self, keepout: bool):
        self._proto.keepout_copper = keepout

    @property
    def keepout_vias(self) -> bool:
        return self._proto.keepout_vias

    @keepout_vias.setter
    def keepout_vias(self, keepout: bool):
        self._proto.keepout_vias = keepout

    @property
    def keepout_tracks(self) -> bool:
        return self._proto.keepout_tracks

    @keepout_tracks.setter
    def keepout_tracks(self, keepout: bool):
        self._proto.keepout_tracks = keepout

    @property
    def keepout_pads(self) -> bool:
        return self._proto.keepout_pads

    @keepout_pads.setter
    def keepout_pads(self, keepout: bool):
        self._proto.keepout_pads = keepout

    @property
    def keepout_footprints(self) -> bool:
        return self._proto.keepout_footprints

    @keepout_footprints.setter
    def keepout_footprints(self, keepout: bool):
        self._proto.keepout_footprints = keepout

    @property
    def placement_enabled(self) -> bool:
        return self._proto.placement_enabled

    @placement_enabled.setter
    def placement_enabled(self, enabled: bool):
        self._proto.placement_enabled = enabled

    @property
    def placement_source_type(self) -> PlacementRuleSourceType.ValueType:
        return self._proto.placement_source_type

    @placement_source_type.setter
    def placement_source_type(self, source_type: PlacementRuleSourceType.ValueType):
        self._proto.placement_source_type = source_type

    @property
    def placement_source(self) -> str:
        return self._proto.placement_source

    @placement_source.setter
    def placement_source(self, source: str):
        self._proto.placement_source = source


class ZoneLayerProperties(Wrapper):
    """Layer-specific properties for a zone

    .. versionadded:: 0.9.0"""

    def __init__(
        self,
        proto: board_types_pb2.ZoneLayerProperties | None = None,
        proto_ref: board_types_pb2.ZoneLayerProperties | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.ZoneLayerProperties()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def hatching_offset(self) -> Vector2:
        return Vector2(self._proto.hatching_offset)

    @hatching_offset.setter
    def hatching_offset(self, offset: Vector2):
        self._proto.hatching_offset.CopyFrom(offset.proto)


class Zone(BoardItem):
    """Represents a copper, graphical, or rule area zone on a board"""

    def __init__(
        self,
        proto: board_types_pb2.Zone | None = None,
        proto_ref: board_types_pb2.Zone | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Zone()

        if proto is not None:
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            # Set reasonable defaults from KiCad ZONE_SETTINGS for convenience
            self.type = ZoneType.ZT_COPPER
            self.min_thickness = from_mm(0.25)
            self.min_island_area = 10 * from_mm(1) * from_mm(1)
            self.island_mode = IslandRemovalMode.IRM_ALWAYS
            self.border_style = ZoneBorderStyle.ZBS_DIAGONAL_EDGE
            self.border_hatch_pitch = from_mm(0.5)

    def __repr__(self) -> str:
        if self.type == ZoneType.ZT_COPPER:
            assert self.net is not None
            return f"Copper Zone(net={self.net.name}, layers={self.layers})"
        elif self.type == ZoneType.ZT_RULE_AREA:
            return f"Rule Area Zone(name={self.name}, layers={self.layers})"

        return f"Zone(name={self.name}, type={self.type}, layers={self.layers})"

    @property
    def type(self) -> ZoneType.ValueType:
        return self._proto.type

    @type.setter
    def type(self, type: ZoneType.ValueType):
        self._proto.type = type

    @property
    def layers(self) -> Sequence[BoardLayer.ValueType]:
        return self._proto.layers

    @layers.setter
    def layers(self, layers: Sequence[BoardLayer.ValueType]):
        del self._proto.layers[:]
        self._proto.layers.extend(layers)

    @property
    def outline(self) -> PolygonWithHoles:
        return PolygonWithHoles(proto_ref=self._proto.outline.polygons[0])

    @outline.setter
    def outline(self, outline: PolygonWithHoles):
        """Sets the zone outline.  The outline and all holes are forced closed regardless
        of the source polygon's :class:`PolygonWithHoles` ``auto_close`` flag; zones require
        closed polygons."""
        p = base_types_pb2.PolygonWithHoles()
        p.CopyFrom(outline.proto)
        p.outline.closed = True

        for hole in p.holes:
            hole.closed = True

        del self._proto.outline.polygons[:]
        self._proto.outline.polygons.append(p)

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, name: str):
        self._proto.name = name

    @property
    def priority(self) -> int:
        return self._proto.priority

    @priority.setter
    def priority(self, priority: int):
        self._proto.priority = priority

    @property
    def filled(self) -> bool:
        return self._proto.filled

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = LockedState.LS_LOCKED if locked else LockedState.LS_UNLOCKED

    @property
    def filled_polygons(self) -> dict[BoardLayer.ValueType, list[PolygonWithHoles]]:
        return {
            filled_polygon.layer: [
                PolygonWithHoles(proto_ref=p) for p in filled_polygon.shapes.polygons
            ]
            for filled_polygon in self._proto.filled_polygons
        }

    def is_rule_area(self) -> bool:
        return self.type == ZoneType.ZT_RULE_AREA

    @property
    def connection(self) -> ZoneConnectionSettings | None:
        if self.is_rule_area():
            return None
        return ZoneConnectionSettings(proto_ref=self._proto.copper_settings.connection)

    @property
    def clearance(self) -> int | None:
        """The override (local) clearance for this filled copper zone"""
        if self.is_rule_area():
            return None
        return self._proto.copper_settings.clearance.value_nm

    @clearance.setter
    def clearance(self, clearance: int):
        if self.is_rule_area():
            raise ValueError("clearance does not apply to rule areas")
        self._proto.copper_settings.clearance.value_nm = clearance

    @property
    def min_thickness(self) -> int | None:
        if self.is_rule_area():
            return None
        return self._proto.copper_settings.min_thickness.value_nm

    @min_thickness.setter
    def min_thickness(self, thickness: int):
        if self.is_rule_area():
            raise ValueError("min thickness does not apply to rule areas")
        self._proto.copper_settings.min_thickness.value_nm = thickness

    @property
    def island_mode(self) -> IslandRemovalMode.ValueType | None:
        if self.is_rule_area():
            return None
        return self._proto.copper_settings.island_mode

    @island_mode.setter
    def island_mode(self, mode: IslandRemovalMode.ValueType):
        if self.is_rule_area():
            raise ValueError("island removal mode does not apply to rule areas")
        self._proto.copper_settings.island_mode = mode

    @property
    def min_island_area(self) -> int | None:
        if self.is_rule_area():
            return None
        return self._proto.copper_settings.min_island_area

    @min_island_area.setter
    def min_island_area(self, area: int):
        if self.is_rule_area():
            raise ValueError("minimum island area does not apply to rule areas")
        self._proto.copper_settings.min_island_area = area

    @property
    def fill_mode(self) -> ZoneFillMode.ValueType | None:
        if self.is_rule_area():
            return None
        return self._proto.copper_settings.fill_mode

    @property
    def net(self) -> Net | None:
        if self.is_rule_area():
            return None
        return Net(self._proto.copper_settings.net)

    @net.setter
    def net(self, net: Net):
        """
        Assigns a net to a copper zone (cannot be used for rule areas).

        .. versionadded:: 0.4.0 (setter)
        """
        if self.is_rule_area():
            raise ValueError("cannot assign a net to rule areas")
        self._proto.copper_settings.net.CopyFrom(net.proto)

    @property
    def teardrop(self) -> board_types_pb2.ZoneTeardropSettings | None:
        if self.is_rule_area():
            return None
        return self._proto.copper_settings.teardrop

    @property
    def hatch_settings(self) -> HatchFillSettings | None:
        """Hatch fill settings for this copper zone

        .. versionadded:: 0.x.0"""
        if self.is_rule_area() or not self._proto.copper_settings.HasField("hatch_settings"):
            return None
        return HatchFillSettings(proto_ref=self._proto.copper_settings.hatch_settings)

    @hatch_settings.setter
    def hatch_settings(self, settings: HatchFillSettings | None):
        if self.is_rule_area():
            raise ValueError("hatch settings do not apply to rule areas")
        if settings is None:
            self._proto.copper_settings.ClearField("hatch_settings")
        else:
            self._proto.copper_settings.hatch_settings.CopyFrom(settings.proto)

    @property
    def thieving_settings(self) -> ThievingFillSettings | None:
        """Thieving fill settings for this copper zone

        .. versionadded:: 0.x.0 (KiCad 11)"""
        if self.is_rule_area() or not self._proto.copper_settings.HasField("thieving_settings"):
            return None
        return ThievingFillSettings(proto_ref=self._proto.copper_settings.thieving_settings)

    @thieving_settings.setter
    def thieving_settings(self, settings: ThievingFillSettings | None):
        if self.is_rule_area():
            raise ValueError("thieving settings do not apply to rule areas")
        if settings is None:
            self._proto.copper_settings.ClearField("thieving_settings")
        else:
            self._proto.copper_settings.thieving_settings.CopyFrom(settings.proto)

    @property
    def corner_smoothing(self) -> ZoneCornerSmoothingMode.ValueType | None:
        """Corner smoothing mode for this copper zone

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        if self.is_rule_area():
            return None
        return self._proto.copper_settings.corner_smoothing

    @corner_smoothing.setter
    def corner_smoothing(self, mode: ZoneCornerSmoothingMode.ValueType):
        if self.is_rule_area():
            raise ValueError("corner smoothing does not apply to rule areas")
        self._proto.copper_settings.corner_smoothing = mode

    @property
    def corner_radius(self) -> int | None:
        """Corner radius in nanometers for this copper zone

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        if self.is_rule_area():
            return None
        return self._proto.copper_settings.corner_radius.value_nm

    @corner_radius.setter
    def corner_radius(self, radius_nm: int):
        if self.is_rule_area():
            raise ValueError("corner radius does not apply to rule areas")
        self._proto.copper_settings.corner_radius.value_nm = radius_nm

    @property
    def rule_area_settings(self) -> RuleAreaSettings | None:
        """Settings that apply only to rule area zones; None for copper zones

        .. versionadded:: 0.9.0"""
        if not self.is_rule_area():
            return None
        return RuleAreaSettings(proto_ref=self._proto.rule_area_settings)

    @rule_area_settings.setter
    def rule_area_settings(self, settings: RuleAreaSettings):
        if not self.is_rule_area():
            raise ValueError("rule area settings apply only to rule areas")
        self._proto.rule_area_settings.CopyFrom(settings.proto)

    @property
    def layer_properties(self) -> MutableWrapperSequence[ZoneLayerProperties]:
        """Per-layer properties for this zone

        .. versionadded:: 0.9.0"""
        return MutableWrapperSequence(self._proto.layer_properties, ZoneLayerProperties)

    @layer_properties.setter
    def layer_properties(self, properties: list[ZoneLayerProperties]):
        del self._proto.layer_properties[:]
        self._proto.layer_properties.extend(p.proto for p in properties)

    @property
    def custom_properties(self) -> MutableWrapperSequence[CustomProperty]:
        """
        .. versionadded:: 0.x.0 (KiCad 11)"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, properties: list[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(p.proto for p in properties)

    @property
    def border_style(self) -> ZoneBorderStyle.ValueType:
        return self._proto.border.style

    @border_style.setter
    def border_style(self, style: ZoneBorderStyle.ValueType):
        self._proto.border.style = style

    @property
    def border_hatch_pitch(self) -> int:
        return self._proto.border.pitch.value_nm

    @border_hatch_pitch.setter
    def border_hatch_pitch(self, value: int):
        self._proto.border.pitch.value_nm = value

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None

    def bounding_box(self) -> Box2:
        return self.outline.bounding_box()

    def move(self, delta: Vector2):
        """Moves the zone by the given delta vector"""
        self.outline.move(delta)
        for polygon in self.filled_polygons.values():
            for shape in polygon:
                shape.move(delta)

    def rotate(self, angle: Angle, center: Vector2):
        """Rotates the zone by the given angle around the given center point"""
        self.outline.rotate(angle, center)

        for polygon in self.filled_polygons.values():
            for shape in polygon:
                shape.rotate(angle, center)


class Dimension(BoardItem):
    """Represents a dimension object on a board"""

    def __init__(
        self,
        proto: board_types_pb2.Dimension | None = None,
        proto_ref: board_types_pb2.Dimension | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Dimension()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def id(self) -> KIID:
        return self._proto.id

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = LockedState.LS_LOCKED if locked else LockedState.LS_UNLOCKED

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def text(self) -> Text:
        return Text(proto_ref=self._proto.text)

    @text.setter
    def text(self, text: Text):
        self._proto.text.CopyFrom(text.proto)

    @property
    def override_text_enabled(self) -> bool:
        return self._proto.override_text_enabled

    @override_text_enabled.setter
    def override_text_enabled(self, enabled: bool):
        self._proto.override_text_enabled = enabled

    @property
    def override_text(self) -> str:
        return self._proto.override_text

    @override_text.setter
    def override_text(self, text: str):
        self._proto.override_text = text

    @property
    def prefix(self) -> str:
        return self._proto.prefix

    @prefix.setter
    def prefix(self, prefix: str):
        self._proto.prefix = prefix

    @property
    def suffix(self) -> str:
        return self._proto.suffix

    @suffix.setter
    def suffix(self, suffix: str):
        self._proto.suffix = suffix

    @property
    def unit(self) -> board_types_pb2.DimensionUnit.ValueType:
        return self._proto.unit

    @unit.setter
    def unit(self, unit: board_types_pb2.DimensionUnit.ValueType):
        self._proto.unit = unit

    @property
    def unit_format(self) -> board_types_pb2.DimensionUnitFormat.ValueType:
        return self._proto.unit_format

    @unit_format.setter
    def unit_format(self, format: board_types_pb2.DimensionUnitFormat.ValueType):
        self._proto.unit_format = format

    @property
    def arrow_direction(self) -> board_types_pb2.DimensionArrowDirection.ValueType:
        return self._proto.arrow_direction

    @arrow_direction.setter
    def arrow_direction(self, direction: board_types_pb2.DimensionArrowDirection.ValueType):
        self._proto.arrow_direction = direction

    @property
    def precision(self) -> board_types_pb2.DimensionPrecision.ValueType:
        return self._proto.precision

    @precision.setter
    def precision(self, precision: board_types_pb2.DimensionPrecision.ValueType):
        self._proto.precision = precision

    @property
    def suppress_trailing_zeroes(self) -> bool:
        return self._proto.suppress_trailing_zeroes

    @suppress_trailing_zeroes.setter
    def suppress_trailing_zeroes(self, suppress: bool):
        self._proto.suppress_trailing_zeroes = suppress

    @property
    def line_thickness(self) -> int:
        return self._proto.line_thickness.value_nm

    @line_thickness.setter
    def line_thickness(self, thickness: int):
        self._proto.line_thickness.value_nm = thickness

    @property
    def arrow_length(self) -> int:
        return self._proto.arrow_length.value_nm

    @arrow_length.setter
    def arrow_length(self, length: int):
        self._proto.arrow_length.value_nm = length

    @property
    def extension_offset(self) -> int:
        return self._proto.extension_offset.value_nm

    @extension_offset.setter
    def extension_offset(self, offset: int):
        self._proto.extension_offset.value_nm = offset

    @property
    def text_position(self) -> board_types_pb2.DimensionTextPosition.ValueType:
        return self._proto.text_position

    @text_position.setter
    def text_position(self, position: board_types_pb2.DimensionTextPosition.ValueType):
        self._proto.text_position = position

    @property
    def keep_text_aligned(self) -> bool:
        return self._proto.keep_text_aligned

    @keep_text_aligned.setter
    def keep_text_aligned(self, aligned: bool):
        self._proto.keep_text_aligned = aligned

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None


class AlignedDimension(Dimension):
    def __init__(
        self,
        proto: board_types_pb2.Dimension | None = None,
        proto_ref: board_types_pb2.Dimension | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Dimension()

        if proto is not None:
            assert proto.WhichOneof("dimension_style") == "aligned"
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self._proto.aligned.SetInParent()

    def __repr__(self) -> str:
        return (
            f"AlignedDimension(start={self.start}, end={self.end}, "
            f"height={self.height}, extension_height={self.extension_height})"
        )

    @property
    def start(self) -> Vector2:
        return Vector2(self._proto.aligned.start)

    @start.setter
    def start(self, start: Vector2):
        self._proto.aligned.start.CopyFrom(start.proto)

    @property
    def end(self) -> Vector2:
        return Vector2(self._proto.aligned.end)

    @end.setter
    def end(self, end: Vector2):
        self._proto.aligned.end.CopyFrom(end.proto)

    @property
    def height(self) -> int:
        return self._proto.aligned.height.value_nm

    @height.setter
    def height(self, height: int):
        self._proto.aligned.height.value_nm = height

    @property
    def extension_height(self) -> int:
        return self._proto.aligned.extension_height.value_nm

    @extension_height.setter
    def extension_height(self, extension_height: int):
        self._proto.aligned.extension_height.value_nm = extension_height


class OrthogonalDimension(Dimension):
    def __init__(
        self,
        proto: board_types_pb2.Dimension | None = None,
        proto_ref: board_types_pb2.Dimension | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Dimension()

        if proto is not None:
            assert proto.WhichOneof("dimension_style") == "orthogonal"
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self._proto.orthogonal.SetInParent()

    def __repr__(self) -> str:
        return (
            f"OrthogonalDimension(start={self.start}, end={self.end}, alignment={self.alignment})"
        )

    @property
    def start(self) -> Vector2:
        return Vector2(self._proto.orthogonal.start)

    @start.setter
    def start(self, start: Vector2):
        self._proto.orthogonal.start.CopyFrom(start.proto)

    @property
    def end(self) -> Vector2:
        return Vector2(self._proto.orthogonal.end)

    @end.setter
    def end(self, end: Vector2):
        self._proto.orthogonal.end.CopyFrom(end.proto)

    @property
    def height(self) -> int:
        return self._proto.orthogonal.height.value_nm

    @height.setter
    def height(self, height: int):
        self._proto.orthogonal.height.value_nm = height

    @property
    def extension_height(self) -> int:
        return self._proto.orthogonal.extension_height.value_nm

    @extension_height.setter
    def extension_height(self, extension_height: int):
        self._proto.orthogonal.extension_height.value_nm = extension_height

    @property
    def alignment(self) -> base_types_pb2.AxisAlignment.ValueType:
        return self._proto.orthogonal.alignment

    @alignment.setter
    def alignment(self, alignment: base_types_pb2.AxisAlignment.ValueType):
        self._proto.orthogonal.alignment = alignment


class RadialDimension(Dimension):
    def __init__(
        self,
        proto: board_types_pb2.Dimension | None = None,
        proto_ref: board_types_pb2.Dimension | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Dimension()

        if proto is not None:
            assert proto.WhichOneof("dimension_style") == "radial"
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self._proto.radial.SetInParent()

    def __repr__(self) -> str:
        return (
            f"RadialDimension(center={self.center}, radius_point={self.radius_point}, "
            f"leader_length={self.leader_length})"
        )

    @property
    def center(self) -> Vector2:
        return Vector2(self._proto.radial.center)

    @center.setter
    def center(self, center: Vector2):
        self._proto.radial.center.CopyFrom(center.proto)

    @property
    def radius_point(self) -> Vector2:
        return Vector2(self._proto.radial.radius_point)

    @radius_point.setter
    def radius_point(self, radius_point: Vector2):
        self._proto.radial.radius_point.CopyFrom(radius_point.proto)

    @property
    def leader_length(self) -> int:
        return self._proto.radial.leader_length.value_nm

    @leader_length.setter
    def leader_length(self, leader_length: int):
        self._proto.radial.leader_length.value_nm = leader_length


class LeaderDimension(Dimension):
    def __init__(
        self,
        proto: board_types_pb2.Dimension | None = None,
        proto_ref: board_types_pb2.Dimension | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Dimension()

        if proto is not None:
            assert proto.WhichOneof("dimension_style") == "leader"
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self._proto.leader.SetInParent()

    def __repr__(self) -> str:
        return (
            f"LeaderDimension(start={self.start}, end={self.end}, "
            f"border_style={self.border_style})"
        )

    @property
    def start(self) -> Vector2:
        return Vector2(self._proto.leader.start)

    @start.setter
    def start(self, start: Vector2):
        self._proto.leader.start.CopyFrom(start.proto)

    @property
    def end(self) -> Vector2:
        return Vector2(self._proto.leader.end)

    @end.setter
    def end(self, end: Vector2):
        self._proto.leader.end.CopyFrom(end.proto)

    @property
    def border_style(self) -> board_types_pb2.DimensionTextBorderStyle.ValueType:
        return self._proto.leader.border_style

    @border_style.setter
    def border_style(self, border_style: board_types_pb2.DimensionTextBorderStyle.ValueType):
        self._proto.leader.border_style = border_style


class CenterDimension(Dimension):
    def __init__(
        self,
        proto: board_types_pb2.Dimension | None = None,
        proto_ref: board_types_pb2.Dimension | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Dimension()

        if proto is not None:
            assert proto.WhichOneof("dimension_style") == "center"
            self._proto.CopyFrom(proto)
        elif proto_ref is None:
            self._proto.center.SetInParent()

    def __repr__(self) -> str:
        return f"CenterDimension(center={self.center}, end={self.end})"

    @property
    def center(self) -> Vector2:
        return Vector2(self._proto.center.center)

    @center.setter
    def center(self, center: Vector2):
        self._proto.center.center.CopyFrom(center.proto)

    @property
    def end(self) -> Vector2:
        return Vector2(self._proto.center.end)

    @end.setter
    def end(self, end: Vector2):
        self._proto.center.end.CopyFrom(end.proto)


def to_concrete_dimension(dimension: Dimension) -> Dimension:
    cls = {
        "aligned": AlignedDimension,
        "orthogonal": OrthogonalDimension,
        "radial": RadialDimension,
        "leader": LeaderDimension,
        "center": CenterDimension,
        None: None,
    }.get(dimension._proto.WhichOneof("dimension_style"), None)

    return cls(proto_ref=dimension._proto) if cls is not None else dimension


class BoardEditorAppearanceSettings(Wrapper):
    def __init__(
        self,
        proto: board_commands_pb2.BoardEditorAppearanceSettings | None = None,
        proto_ref: board_commands_pb2.BoardEditorAppearanceSettings | None = None,
    ):
        self._proto = (
            proto_ref
            if proto_ref is not None
            else board_commands_pb2.BoardEditorAppearanceSettings()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def inactive_layer_display(self) -> board_commands_pb2.InactiveLayerDisplayMode.ValueType:
        """How layers other than the active (selected) layer are displayed"""
        return self._proto.inactive_layer_display

    @inactive_layer_display.setter
    def inactive_layer_display(self, mode: board_commands_pb2.InactiveLayerDisplayMode.ValueType):
        self._proto.inactive_layer_display = mode

    @property
    def net_color_display(self) -> board_commands_pb2.NetColorDisplayMode.ValueType:
        """Whether to apply net and netclass colors to copper items and ratsnest lines"""
        return self._proto.net_color_display

    @net_color_display.setter
    def net_color_display(self, mode: board_commands_pb2.NetColorDisplayMode.ValueType):
        self._proto.net_color_display = mode

    @property
    def board_flip(self) -> board_commands_pb2.BoardFlipMode.ValueType:
        """Whether or not the board view is flipped (mirrored around the X axis)"""
        return self._proto.board_flip

    @board_flip.setter
    def board_flip(self, mode: board_commands_pb2.BoardFlipMode.ValueType):
        self._proto.board_flip = mode

    @property
    def ratsnest_display(self) -> board_commands_pb2.RatsnestDisplayMode.ValueType:
        """Whether or not ratsnest lines are drawn to hidden layers"""
        return self._proto.ratsnest_display

    @ratsnest_display.setter
    def ratsnest_display(self, mode: board_commands_pb2.RatsnestDisplayMode.ValueType):
        self._proto.ratsnest_display = mode


class Group(BoardItem):
    """Represents a group of items on a board

    Groups store item membership by ID only.  See the documentation for :attr:`items` and
    :attr:`item_ids` for details.

    .. versionadded:: 0.7.0 (KiCad 10.0.0)"""

    def __init__(
        self,
        proto: board_types_pb2.Group | None = None,
    ):
        self._proto = board_types_pb2.Group()

        if proto is not None:
            self._proto.CopyFrom(proto)

        self._item_ids = self._proto.items
        self._unwrapped_items: Sequence[BoardItem] | None = None
        self._item_resolver: Callable[[Sequence[KIID]], Sequence[BoardItem]] | None = None

    @property
    def id(self) -> KIID:
        return self._proto.id

    @property
    def name(self) -> str:
        return self._proto.name

    @property
    def item_ids(self) -> Sequence[KIID]:
        """The IDs of the group members"""
        return self._item_ids

    @item_ids.setter
    def item_ids(self, ids: Sequence[KIID]):
        """Setting this property will invalidate the cache of concrete items
        returned by the :attr:`items` property."""
        del self._proto.items[:]
        self._proto.items.extend(ids)
        self._unwrapped_items = None

    @property
    def items(self) -> Sequence[BoardItem]:
        """The members of the group, lazily resolved into actual item wrappers.

        Accessing this property will cause API traffic to resolve the items
        by their KIID from the document.

        Note that the group does not own these items; :attr:`item_ids` is the actual
        way that group membership is tracked.  This means that you cannot just
        add items to a group and then to a document by setting this :attr:`items`
        property, you also need to add the items to the document separately."""
        if self._unwrapped_items is None and self._item_resolver is not None and self._item_ids:
            self._unwrapped_items = self._item_resolver(self._item_ids)
        return self._unwrapped_items if self._unwrapped_items is not None else []

    @items.setter
    def items(self, items: Sequence[BoardItem]):
        """Sets the items in the group, replacing any existing items"""
        del self._proto.items[:]
        self._unwrapped_items = items
        for item in items:
            self._proto.items.append(item.id)

    @property
    def locked(self) -> bool:
        """
        .. versionadded:: 0.9.0"""
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = {
            True: LockedState.LS_LOCKED,
            False: LockedState.LS_UNLOCKED,
        }.get(locked, LockedState.LS_UNLOCKED)

    @property
    def lib_id(self) -> LibraryIdentifier:
        """The design block identifier for groups linked to a design block library entry

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return LibraryIdentifier(proto_ref=self._proto.lib_id)

    @lib_id.setter
    def lib_id(self, lib_id: LibraryIdentifier):
        self._proto.lib_id.CopyFrom(lib_id.proto)

    @property
    def custom_properties(self) -> MutableWrapperSequence[CustomProperty]:
        """
        .. versionadded:: 0.x.0 (KiCad 11)"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, properties: list[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(p.proto for p in properties)

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        return self._proto.parent if self._proto.HasField("parent") else None


class TableCell(Wrapper):
    """A single cell of a table

    .. versionadded:: 0.9.0 (KiCad 10.0.7)"""

    def __init__(
        self,
        proto: board_types_pb2.TableCell | None = None,
        proto_ref: board_types_pb2.TableCell | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.TableCell()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"TableCell(text={self.text.value}, column_span={self.column_span})"

    @property
    def text(self) -> BoardTextBox:
        return BoardTextBox(proto_ref=self._proto.text_box)

    @text.setter
    def text(self, text_box: BoardTextBox):
        self._proto.text_box.CopyFrom(text_box.proto)

    @property
    def column_span(self) -> int:
        return self._proto.column_span

    @column_span.setter
    def column_span(self, span: int):
        self._proto.column_span = span

    @property
    def row_span(self) -> int:
        return self._proto.row_span

    @row_span.setter
    def row_span(self, span: int):
        self._proto.row_span = span

    @property
    def custom_properties(self) -> MutableWrapperSequence[CustomProperty]:
        """
        .. versionadded:: 0.x.0 (KiCad 11)"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, properties: list[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(p.proto for p in properties)


class Table(BoardItem):
    """Represents a table on a board or footprint

    .. versionadded:: 0.9.0 (KiCad 10.0.7)"""

    def __init__(
        self,
        proto: board_types_pb2.Table | None = None,
        proto_ref: board_types_pb2.Table | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Table()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"Table(cells={self.column_count}x{len(self.cells)}, "
            f"layer={BoardLayer.Name(self.layer)})"
        )

    @property
    def id(self) -> KIID:
        return self._proto.id

    @property
    def column_count(self) -> int:
        return self._proto.column_count

    @column_count.setter
    def column_count(self, count: int):
        self._proto.column_count = count

    @property
    def column_widths(self) -> list[int]:
        return list(self._proto.column_widths)

    @column_widths.setter
    def column_widths(self, widths: list[int]):
        del self._proto.column_widths[:]
        self._proto.column_widths.extend(widths)

    @property
    def row_heights(self) -> list[int]:
        return list(self._proto.row_heights)

    @row_heights.setter
    def row_heights(self, heights: list[int]):
        del self._proto.row_heights[:]
        self._proto.row_heights.extend(heights)

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = {
            True: LockedState.LS_LOCKED,
            False: LockedState.LS_UNLOCKED,
        }.get(locked, LockedState.LS_UNLOCKED)

    @property
    def cells(self) -> MutableWrapperSequence[TableCell]:
        return MutableWrapperSequence(self._proto.cells, TableCell)

    @cells.setter
    def cells(self, cells: list[TableCell]):
        del self._proto.cells[:]
        self._proto.cells.extend(cell.proto for cell in cells)

    @property
    def external_border(self) -> TableStrokeMode.ValueType:
        return self._proto.external_border

    @external_border.setter
    def external_border(self, mode: TableStrokeMode.ValueType):
        self._proto.external_border = mode

    @property
    def header_separator(self) -> TableStrokeMode.ValueType:
        return self._proto.header_separator

    @header_separator.setter
    def header_separator(self, mode: TableStrokeMode.ValueType):
        self._proto.header_separator = mode

    @property
    def row_separators(self) -> TableStrokeMode.ValueType:
        return self._proto.row_separators

    @row_separators.setter
    def row_separators(self, mode: TableStrokeMode.ValueType):
        self._proto.row_separators = mode

    @property
    def column_separators(self) -> TableStrokeMode.ValueType:
        return self._proto.column_separators

    @column_separators.setter
    def column_separators(self, mode: TableStrokeMode.ValueType):
        self._proto.column_separators = mode

    @property
    def border_stroke(self) -> StrokeAttributes:
        return StrokeAttributes(proto_ref=self._proto.border_stroke)

    @border_stroke.setter
    def border_stroke(self, stroke: StrokeAttributes):
        self._proto.border_stroke.CopyFrom(stroke.proto)

    @property
    def separators_stroke(self) -> StrokeAttributes:
        return StrokeAttributes(proto_ref=self._proto.separators_stroke)

    @separators_stroke.setter
    def separators_stroke(self, stroke: StrokeAttributes):
        self._proto.separators_stroke.CopyFrom(stroke.proto)

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.
        """
        return self._proto.parent if self._proto.HasField("parent") else None

    @property
    def custom_properties(self) -> MutableWrapperSequence[CustomProperty]:
        """
        .. versionadded:: 0.x.0 (KiCad 11)"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, properties: list[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(p.proto for p in properties)


class ReferencePoint(BoardItem):
    """Represents a reference point marker on a board

    .. versionadded:: 0.9.0 (KiCad 10.0.7)"""

    def __init__(
        self,
        proto: board_types_pb2.ReferencePoint | None = None,
        proto_ref: board_types_pb2.ReferencePoint | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.ReferencePoint()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"ReferencePoint(position={self.position}, layer={BoardLayer.Name(self.layer)}, "
            f"size={self.size})"
        )

    @property
    def id(self) -> KIID:
        return self._proto.id

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def position(self) -> Vector2:
        return Vector2(self._proto.position)

    @position.setter
    def position(self, position: Vector2):
        self._proto.position.CopyFrom(position.proto)

    @property
    def size(self) -> int:
        """Marker size in nanometers"""
        return self._proto.size.value_nm

    @size.setter
    def size(self, size_nm: int):
        self._proto.size.value_nm = size_nm

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = {
            True: LockedState.LS_LOCKED,
            False: LockedState.LS_UNLOCKED,
        }.get(locked, LockedState.LS_UNLOCKED)

    @property
    def parent(self) -> KIID | None:
        """The ID of the parent container for this item (such as a Board or Footprint), if any.
        Read-only; item parents can only be changed by add/remove calls on the parent container.
        """
        return self._proto.parent if self._proto.HasField("parent") else None

    @property
    def custom_properties(self) -> MutableWrapperSequence[CustomProperty]:
        """
        .. versionadded:: 0.x.0 (KiCad 11)"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, properties: list[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(p.proto for p in properties)


class GridItemAffects(Wrapper):
    """Which actions a grid item affects

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.GridItemAffects | None = None,
        proto_ref: board_types_pb2.GridItemAffects | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.GridItemAffects()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def cursor(self) -> bool:
        return self._proto.cursor

    @cursor.setter
    def cursor(self, cursor: bool):
        self._proto.cursor = cursor

    @property
    def routing(self) -> bool:
        return self._proto.routing

    @routing.setter
    def routing(self, routing: bool):
        self._proto.routing = routing

    @property
    def placement(self) -> bool:
        return self._proto.placement

    @placement.setter
    def placement(self, placement: bool):
        self._proto.placement = placement


class CartesianGridItemAttributes(Wrapper):
    """.. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.CartesianGridItemAttributes | None = None,
        proto_ref: board_types_pb2.CartesianGridItemAttributes | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_types_pb2.CartesianGridItemAttributes()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def extent(self) -> Vector2:
        """Half the width of the grid in x/y axis"""
        return Vector2(self._proto.extent)

    @extent.setter
    def extent(self, extent: Vector2):
        self._proto.extent.CopyFrom(extent.proto)

    @property
    def spacing(self) -> Vector2:
        """Spacing between snap points on x/y axis"""
        return Vector2(self._proto.spacing)

    @spacing.setter
    def spacing(self, spacing: Vector2):
        self._proto.spacing.CopyFrom(spacing.proto)


class PolarGridItemAttributes(Wrapper):
    """.. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.PolarGridItemAttributes | None = None,
        proto_ref: board_types_pb2.PolarGridItemAttributes | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_types_pb2.PolarGridItemAttributes()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def radius_extent(self) -> int:
        """Radial extent from the center"""
        return self._proto.radius_extent.value_nm

    @radius_extent.setter
    def radius_extent(self, extent_nm: int):
        self._proto.radius_extent.value_nm = extent_nm

    @property
    def radius_spacing(self) -> int:
        """Radial spacing of snap points"""
        return self._proto.radius_spacing.value_nm

    @radius_spacing.setter
    def radius_spacing(self, spacing_nm: int):
        self._proto.radius_spacing.value_nm = spacing_nm

    @property
    def phi_extent(self) -> Angle:
        """Angle covered by the grid"""
        return Angle(proto_ref=self._proto.phi_extent)

    @phi_extent.setter
    def phi_extent(self, extent: Angle):
        self._proto.phi_extent.CopyFrom(extent.proto)

    @property
    def phi_spacing(self) -> Angle:
        """Angular spacing between snap points"""
        return Angle(proto_ref=self._proto.phi_spacing)

    @phi_spacing.setter
    def phi_spacing(self, spacing: Angle):
        self._proto.phi_spacing.CopyFrom(spacing.proto)


class GridItem(BoardItem):
    """A local grid placed on the board.

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.GridItem | None = None,
        proto_ref: board_types_pb2.GridItem | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.GridItem()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        geometry = "cartesian" if self.cartesian is not None else "polar"
        return f"GridItem(position={self.position}, geometry={geometry})"

    @property
    def id(self) -> KIID:
        return self._proto.id

    @property
    def position(self) -> Vector2:
        """Centre and rotation of the grid"""
        return Vector2(self._proto.position)

    @position.setter
    def position(self, position: Vector2):
        self._proto.position.CopyFrom(position.proto)

    @property
    def orientation(self) -> Angle:
        return Angle(proto_ref=self._proto.orientation)

    @orientation.setter
    def orientation(self, orientation: Angle):
        self._proto.orientation.CopyFrom(orientation.proto)

    @property
    def cartesian(self) -> CartesianGridItemAttributes | None:
        """Cartesian grid geometry, or None if the grid is polar"""
        if self._proto.WhichOneof("geometry") == "cartesian":
            return CartesianGridItemAttributes(proto_ref=self._proto.cartesian)
        return None

    @cartesian.setter
    def cartesian(self, attributes: CartesianGridItemAttributes | None):
        if attributes is None:
            if self._proto.WhichOneof("geometry") == "cartesian":
                self._proto.ClearField("cartesian")
        else:
            self._proto.cartesian.CopyFrom(attributes.proto)

    @property
    def polar(self) -> PolarGridItemAttributes | None:
        """Polar grid geometry, or None if the grid is cartesian"""
        if self._proto.WhichOneof("geometry") == "polar":
            return PolarGridItemAttributes(proto_ref=self._proto.polar)
        return None

    @polar.setter
    def polar(self, attributes: PolarGridItemAttributes | None):
        if attributes is None:
            if self._proto.WhichOneof("geometry") == "polar":
                self._proto.ClearField("polar")
        else:
            self._proto.polar.CopyFrom(attributes.proto)

    @property
    def priority(self) -> int:
        return self._proto.priority

    @priority.setter
    def priority(self, priority: int):
        self._proto.priority = priority

    @property
    def tick_interval(self) -> int:
        """Every Nth line is drawn ephasized; 0 for no major ticks"""
        return self._proto.tick_interval

    @tick_interval.setter
    def tick_interval(self, interval: int):
        self._proto.tick_interval = interval

    @property
    def affects(self) -> GridItemAffects:
        return GridItemAffects(proto_ref=self._proto.affects)

    @affects.setter
    def affects(self, affects: GridItemAffects):
        self._proto.affects.CopyFrom(affects.proto)

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = {
            True: LockedState.LS_LOCKED,
            False: LockedState.LS_UNLOCKED,
        }.get(locked, LockedState.LS_UNLOCKED)

    @property
    def custom_properties(self) -> MutableWrapperSequence[CustomProperty]:
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, properties: list[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(p.proto for p in properties)


class ConstraintMember(Wrapper):
    """.. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.ConstraintMember | None = None,
        proto_ref: board_types_pb2.ConstraintMember | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.ConstraintMember()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"ConstraintMember(item={self.item}, anchor={self.anchor})"

    @property
    def item(self) -> KIID:
        return self._proto.item

    @item.setter
    def item(self, item: KIID):
        self._proto.item.CopyFrom(item)

    @property
    def anchor(self) -> ConstraintAnchor.ValueType:
        return self._proto.anchor

    @anchor.setter
    def anchor(self, anchor: ConstraintAnchor.ValueType):
        self._proto.anchor = anchor

    @property
    def index(self) -> int | None:
        if self._proto.HasField("index"):
            return self._proto.index
        return None

    @index.setter
    def index(self, index: int | None):
        if index is None:
            self._proto.ClearField("index")
        else:
            self._proto.index = index


class Constraint(BoardItem):
    """A geometric constraint between board items

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.Constraint | None = None,
        proto_ref: board_types_pb2.Constraint | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.Constraint()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"Constraint(type={ConstraintType.Name(self.type)}, members={self.members})"

    @property
    def id(self) -> KIID:
        return self._proto.id

    @property
    def type(self) -> ConstraintType.ValueType:
        return self._proto.type

    @type.setter
    def type(self, type: ConstraintType.ValueType):
        self._proto.type = type

    @property
    def members(self) -> MutableWrapperSequence[ConstraintMember]:
        return MutableWrapperSequence(self._proto.members, ConstraintMember)

    @members.setter
    def members(self, members: list[ConstraintMember]):
        del self._proto.members[:]
        self._proto.members.extend(member.proto for member in members)

    @property
    def value(self) -> float | None:
        if self._proto.HasField("value"):
            return self._proto.value
        return None

    @value.setter
    def value(self, value: float | None):
        if value is None:
            self._proto.ClearField("value")
        else:
            self._proto.value = value

    @property
    def driving(self) -> bool:
        return self._proto.driving

    @driving.setter
    def driving(self, driving: bool):
        self._proto.driving = driving

    @property
    def custom_properties(self) -> MutableWrapperSequence[CustomProperty]:
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)


class DrillSpan(Wrapper):
    """A span of layers that a drill operation crosses

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.DrillSpan | None = None,
        proto_ref: board_types_pb2.DrillSpan | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.DrillSpan()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"DrillSpan(start={BoardLayer.Name(self.start_layer)}, "
            f"end={BoardLayer.Name(self.end_layer)}, backdrill={self.is_backdrill}, "
            f"non_plated={self.is_non_plated})"
        )

    @property
    def start_layer(self) -> BoardLayer.ValueType:
        return self._proto.start_layer

    @start_layer.setter
    def start_layer(self, layer: BoardLayer.ValueType):
        self._proto.start_layer = layer

    @property
    def end_layer(self) -> BoardLayer.ValueType:
        return self._proto.end_layer

    @end_layer.setter
    def end_layer(self, layer: BoardLayer.ValueType):
        self._proto.end_layer = layer

    @property
    def is_backdrill(self) -> bool:
        return self._proto.is_backdrill

    @is_backdrill.setter
    def is_backdrill(self, is_backdrill: bool):
        self._proto.is_backdrill = is_backdrill

    @property
    def is_non_plated(self) -> bool:
        return self._proto.is_non_plated

    @is_non_plated.setter
    def is_non_plated(self, is_non_plated: bool):
        self._proto.is_non_plated = is_non_plated


class DrillChartColumn(Wrapper):
    """A column configuration of a drill chart

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.DrillChartColumn | None = None,
        proto_ref: board_types_pb2.DrillChartColumn | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.DrillChartColumn()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"DrillChartColumn(id={DrillChartColumnId.Name(self.id)}, heading={self.heading})"

    @property
    def id(self) -> DrillChartColumnId.ValueType:
        return self._proto.id

    @id.setter
    def id(self, id: DrillChartColumnId.ValueType):
        self._proto.id = id

    @property
    def heading(self) -> str:
        return self._proto.heading

    @heading.setter
    def heading(self, heading: str):
        self._proto.heading = heading

    @property
    def align(self) -> DrillChartAlign.ValueType:
        return self._proto.align

    @align.setter
    def align(self, align: DrillChartAlign.ValueType):
        self._proto.align = align

    @property
    def width(self) -> int:
        """Column width in nanometers"""
        return self._proto.width.value_nm

    @width.setter
    def width(self, width_nm: int):
        self._proto.width.value_nm = width_nm


class DrillChartFilter(Wrapper):
    """Which kinds of drill operations a drill chart includes

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.DrillChartFilter | None = None,
        proto_ref: board_types_pb2.DrillChartFilter | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.DrillChartFilter()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"DrillChartFilter(plated={self.plated}, non_plated={self.non_plated}, "
            f"vias={self.vias}, slots={self.slots}, backdrills={self.backdrills}, "
            f"castellated={self.castellated})"
        )

    @property
    def plated(self) -> bool:
        return self._proto.plated

    @plated.setter
    def plated(self, plated: bool):
        self._proto.plated = plated

    @property
    def non_plated(self) -> bool:
        return self._proto.non_plated

    @non_plated.setter
    def non_plated(self, non_plated: bool):
        self._proto.non_plated = non_plated

    @property
    def vias(self) -> bool:
        return self._proto.vias

    @vias.setter
    def vias(self, vias: bool):
        self._proto.vias = vias

    @property
    def slots(self) -> bool:
        return self._proto.slots

    @slots.setter
    def slots(self, slots: bool):
        self._proto.slots = slots

    @property
    def backdrills(self) -> bool:
        return self._proto.backdrills

    @backdrills.setter
    def backdrills(self, backdrills: bool):
        self._proto.backdrills = backdrills

    @property
    def castellated(self) -> bool:
        return self._proto.castellated

    @castellated.setter
    def castellated(self, castellated: bool):
        self._proto.castellated = castellated


class DrillChart(BoardItem):
    """A drill chart: a table on the board that lists the drill operations used by the board.

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.DrillChart | None = None,
        proto_ref: board_types_pb2.DrillChart | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.DrillChart()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        table = self.table
        return (
            f"DrillChart(layer={BoardLayer.Name(table.layer)}, "
            f"cells={table.column_count}x{len(table.cells)}, "
            f"columns={len(self.columns)})"
        )

    @property
    def id(self) -> KIID:
        return self._proto.table.id

    @property
    def table(self) -> Table:
        """The underlying table of the drill chart.  Editing the cell contents directly
        is not supported as they will be regenerated by KiCad."""
        return Table(proto_ref=self._proto.table)

    @table.setter
    def table(self, table: Table):
        self._proto.table.CopyFrom(table.proto)

    @property
    def filter(self) -> DrillChartFilter:
        return DrillChartFilter(proto_ref=self._proto.filter)

    @filter.setter
    def filter(self, filter: DrillChartFilter):
        self._proto.filter.CopyFrom(filter.proto)

    @property
    def columns(self) -> MutableWrapperSequence[DrillChartColumn]:
        return MutableWrapperSequence(self._proto.columns, DrillChartColumn)

    @columns.setter
    def columns(self, columns: list[DrillChartColumn]):
        del self._proto.columns[:]
        self._proto.columns.extend(column.proto for column in columns)

    @property
    def units(self) -> Units.ValueType:
        return self._proto.units

    @units.setter
    def units(self, units: Units.ValueType):
        self._proto.units = units

    @property
    def precision(self) -> int:
        return self._proto.precision

    @precision.setter
    def precision(self, precision: int):
        self._proto.precision = precision

    @property
    def show_totals(self) -> bool:
        return self._proto.show_totals

    @show_totals.setter
    def show_totals(self, show_totals: bool):
        self._proto.show_totals = show_totals

    @property
    def row_shapes(self) -> dict[int, int]:
        """Map of row index to drill symbol index"""
        return dict(self._proto.row_shapes)

    @row_shapes.setter
    def row_shapes(self, row_shapes: dict[int, int]):
        self._proto.row_shapes.clear()
        self._proto.row_shapes.update(row_shapes)

    @property
    def symbol_column(self) -> int:
        """Index of the column that displays drill symbols"""
        return self._proto.symbol_column

    @symbol_column.setter
    def symbol_column(self, symbol_column: int):
        self._proto.symbol_column = symbol_column


class DrillMap(BoardItem):
    """A graphical item that generates drill markers (symbols) at all hole locations

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        proto: board_types_pb2.DrillMap | None = None,
        proto_ref: board_types_pb2.DrillMap | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_types_pb2.DrillMap()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"DrillMap(position={self.position}, layer={BoardLayer.Name(self.layer)}, "
            f"all_spans={self.all_spans})"
        )

    @property
    def id(self) -> KIID:
        return self._proto.id

    @property
    def layer(self) -> BoardLayer.ValueType:
        return self._proto.layer

    @layer.setter
    def layer(self, layer: BoardLayer.ValueType):
        self._proto.layer = layer

    @property
    def position(self) -> Vector2:
        """Drill map position is a relative offset from the true location of the holes.

        A position of (0, 0) means that the drill symbols will be overlaid on the actual
        hole locations of the board."""
        return Vector2(self._proto.position)

    @position.setter
    def position(self, position: Vector2):
        self._proto.position.CopyFrom(position.proto)

    @property
    def locked(self) -> bool:
        return self._proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self._proto.locked = {
            True: LockedState.LS_LOCKED,
            False: LockedState.LS_UNLOCKED,
        }.get(locked, LockedState.LS_UNLOCKED)

    @property
    def all_spans(self) -> bool:
        """Whether the map shows all drill spans, or only the span in :attr:`span`"""
        return self._proto.all_spans

    @all_spans.setter
    def all_spans(self, all_spans: bool):
        self._proto.all_spans = all_spans

    @property
    def span(self) -> DrillSpan:
        return DrillSpan(proto_ref=self._proto.span)

    @span.setter
    def span(self, span: DrillSpan):
        self._proto.span.CopyFrom(span.proto)

    @property
    def outline_slots(self) -> bool:
        return self._proto.outline_slots

    @outline_slots.setter
    def outline_slots(self, outline_slots: bool):
        self._proto.outline_slots = outline_slots

    @property
    def guide_cross(self) -> bool:
        return self._proto.guide_cross

    @guide_cross.setter
    def guide_cross(self, guide_cross: bool):
        self._proto.guide_cross = guide_cross

    @property
    def symbol_size(self) -> int:
        """Size of the drill symbols in nanometers"""
        return self._proto.symbol_size.value_nm

    @symbol_size.setter
    def symbol_size(self, size_nm: int):
        self._proto.symbol_size.value_nm = size_nm


_proto_to_object: dict[type[Message], type[Wrapper]] = {
    board_types_pb2.Arc: ArcTrack,
    board_types_pb2.Barcode: Barcode,
    board_types_pb2.BoardGraphicShape: BoardShape,
    board_types_pb2.BoardText: BoardText,
    board_types_pb2.BoardTextBox: BoardTextBox,
    board_types_pb2.Dimension: Dimension,
    board_types_pb2.Field: Field,
    board_types_pb2.Footprint3DModel: Footprint3DModel,
    board_types_pb2.Footprint: Footprint,
    board_types_pb2.FootprintInstance: FootprintInstance,
    board_types_pb2.Net: Net,
    board_types_pb2.Pad: Pad,
    board_types_pb2.ReferenceImage: ReferenceImage,
    board_types_pb2.Track: Track,
    board_types_pb2.Via: Via,
    board_types_pb2.Zone: Zone,
    board_types_pb2.Group: Group,
    board_types_pb2.Table: Table,
    board_types_pb2.ReferencePoint: ReferencePoint,
    board_types_pb2.GridItem: GridItem,
    board_types_pb2.Constraint: Constraint,
    board_types_pb2.DrillChart: DrillChart,
    board_types_pb2.DrillMap: DrillMap,
}


def unwrap(message: Any) -> Wrapper:
    concrete = unpack_any(message)
    wrapper = _proto_to_object.get(type(concrete), None)
    assert wrapper is not None
    return wrapper(proto=concrete)
