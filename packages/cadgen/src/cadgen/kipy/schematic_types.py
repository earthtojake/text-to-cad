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

from collections.abc import Callable, Sequence
from typing import cast

from google.protobuf.any_pb2 import Any
from google.protobuf.message import Message

from cadgen.kipy.common_types import (
    Color,
    CustomProperty,
    GraphicAttributes,
    GraphicFillAttributes,
    GraphicShape,
    LibraryIdentifier,
    LineEnding,
    SheetPath,
    StrokeAttributes,
    Text,
    TextAttributes,
    TextBox,
    to_concrete_shape,
)
from cadgen.kipy.geometry import Vector2
from cadgen.kipy.proto.common.types import KIID, base_types_pb2
from cadgen.kipy.proto.common.types.base_types_pb2 import ElectricalPinType, LockedState
from cadgen.kipy.proto.schematic import schematic_types_pb2
from cadgen.kipy.proto.schematic.schematic_types_pb2 import (
    BusEntryType,
    PinMapOverrideMode,
    SchematicLabelShape,
    SchematicLabelSpinStyle,
    SchematicLineType,
    SchematicPassthroughMode,
    SchematicPinOrientation,
    SchematicPinShape,
    SchematicSymbolOrientation,
    SchematicSymbolType,
    SheetSide,
    TableStrokeMode,
)
from cadgen.kipy.util import unpack_any
from cadgen.kipy.wrapper import Item, MutableWrapperSequence, Wrapper


class SchematicItem(Item):
    @property
    def id(self) -> KIID:
        return self.proto.id


class SchematicField(SchematicItem):
    """
    A field is a text item attached to another item that holds a name and value.  Some items
    (such as symbols) have mandatory fields that always exist, and other items (such as labels)
    don't have any fields by default but may have custom fields attached.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicField | None = None,
        proto_ref: schematic_types_pb2.SchematicField | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SchematicField()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"SchematicField({self.name}={self.text.value}, pos={self.text.position})"

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

    @property
    def text(self) -> Text:
        return Text(proto_ref=self._proto.text)

    @text.setter
    def text(self, value: Text):
        self._proto.text.CopyFrom(value.proto)

    @property
    def visible(self) -> bool:
        return self._proto.visible

    @visible.setter
    def visible(self, value: bool):
        self._proto.visible = value

    @property
    def show_name(self) -> bool:
        return self._proto.show_name

    @show_name.setter
    def show_name(self, value: bool):
        self._proto.show_name = value

    @property
    def allow_auto_place(self) -> bool:
        return self._proto.allow_auto_place

    @allow_auto_place.setter
    def allow_auto_place(self, value: bool):
        self._proto.allow_auto_place = value

    @property
    def is_private(self) -> bool:
        return self._proto.is_private

    @is_private.setter
    def is_private(self, value: bool):
        self._proto.is_private = value

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the field"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class SchematicLine(SchematicItem):
    """A line segment on a schematic, which may be a net or bus wire or a graphic line (see
    :attr:`type`). Wires and buses form electrical connections to each other and to pins at their
    endpoints. KiCad automatically cleans up wires (whether added in the GUI or by the API) to
    remove overlapping wire segments and split wire segments at intersections with other wire
    endpoints or pins. Wires can form connections with labels anywhere along their length.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicLine | None = None,
        proto_ref: schematic_types_pb2.SchematicLine | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SchematicLine()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"SchematicLine(start={self.start}, end={self.end}, "
            f"type={SchematicLineType.Name(self.type)})"
        )

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
    def start(self) -> Vector2:
        return Vector2(proto_ref=self._proto.start)

    @start.setter
    def start(self, value: Vector2):
        self._proto.start.CopyFrom(value.proto)

    @property
    def end(self) -> Vector2:
        return Vector2(proto_ref=self._proto.end)

    @end.setter
    def end(self, value: Vector2):
        self._proto.end.CopyFrom(value.proto)

    @property
    def type(self) -> SchematicLineType.ValueType:
        return self._proto.type

    @type.setter
    def type(self, value: SchematicLineType.ValueType):
        self._proto.type = value

    @property
    def stroke(self) -> StrokeAttributes:
        return StrokeAttributes(proto_ref=self._proto.stroke)

    @stroke.setter
    def stroke(self, value: StrokeAttributes):
        self._proto.stroke.CopyFrom(value.proto)

    @property
    def start_ending(self) -> LineEnding | None:
        if self._proto.HasField("start_ending"):
            return LineEnding(proto_ref=self._proto.start_ending)
        return None

    @start_ending.setter
    def start_ending(self, value: LineEnding | None):
        if value is not None:
            self._proto.start_ending.CopyFrom(value.proto)
        else:
            self._proto.ClearField("start_ending")

    @property
    def end_ending(self) -> LineEnding | None:
        if self._proto.HasField("end_ending"):
            return LineEnding(proto_ref=self._proto.end_ending)
        return None

    @end_ending.setter
    def end_ending(self, value: LineEnding | None):
        if value is not None:
            self._proto.end_ending.CopyFrom(value.proto)
        else:
            self._proto.ClearField("end_ending")

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the line"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class Junction(SchematicItem):
    """A junction is a circular symbol that indicates the intersection of 3 or more wire endpoints.
    Note: junctions in KiCad are computed dynamically based on line intersections.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.Junction | None = None,
        proto_ref: schematic_types_pb2.Junction | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.Junction()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"Junction(position={self.position})"

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
        return Vector2(proto_ref=self._proto.position)

    @position.setter
    def position(self, value: Vector2):
        self._proto.position.CopyFrom(value.proto)

    @property
    def diameter(self) -> int:
        return self._proto.diameter.value_nm

    @diameter.setter
    def diameter(self, value: int):
        self._proto.diameter.value_nm = value

    @property
    def color(self) -> Color:
        return Color(proto_ref=self._proto.color)

    @color.setter
    def color(self, value: Color):
        self._proto.color.CopyFrom(value.proto)

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the junction"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class NoConnectMarker(SchematicItem):
    """A no-connect marker is a X-shaped symbol that can be placed on a wire or pin, and marks the
    net it is attached to as intentionally isolated.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.NoConnectMarker | None = None,
        proto_ref: schematic_types_pb2.NoConnectMarker | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.NoConnectMarker()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"NoConnectMarker(position={self.position})"

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
        return Vector2(proto_ref=self._proto.position)

    @position.setter
    def position(self, value: Vector2):
        self._proto.position.CopyFrom(value.proto)

    @property
    def size(self) -> int:
        return self._proto.size.value_nm

    @size.setter
    def size(self, value: int):
        self._proto.size.value_nm = value

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the no-connect marker"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class BusEntry(SchematicItem):
    """A bus entry is a short diagonal wire segment that attaches a wire to a bus.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.BusEntry | None = None,
        proto_ref: schematic_types_pb2.BusEntry | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.BusEntry()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"BusEntry(position={self.position}, type={BusEntryType.Name(self.type)})"

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
        return Vector2(proto_ref=self._proto.position)

    @position.setter
    def position(self, value: Vector2):
        self._proto.position.CopyFrom(value.proto)

    @property
    def size(self) -> Vector2:
        return Vector2(proto_ref=self._proto.size)

    @size.setter
    def size(self, value: Vector2):
        self._proto.size.CopyFrom(value.proto)

    @property
    def stroke(self) -> StrokeAttributes:
        return StrokeAttributes(proto_ref=self._proto.stroke)

    @stroke.setter
    def stroke(self, value: StrokeAttributes):
        self._proto.stroke.CopyFrom(value.proto)

    @property
    def type(self) -> BusEntryType.ValueType:
        return self._proto.type

    @type.setter
    def type(self, value: BusEntryType.ValueType):
        self._proto.type = value

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the bus entry"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class SchematicText(SchematicItem):
    """A single-line text item.  Text items are used for notes and other annotations.  They do not
    impact the netlist.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicText | None = None,
        proto_ref: schematic_types_pb2.SchematicText | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SchematicText()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"SchematicText(value={self.value!r}, position={self.position})"

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
    def text(self) -> Text:
        return Text(proto_ref=self._proto.text)

    @text.setter
    def text(self, value: Text):
        self._proto.text.CopyFrom(value.proto)

    @property
    def position(self) -> Vector2:
        return Vector2(proto_ref=self._proto.text.position)

    @position.setter
    def position(self, value: Vector2):
        self._proto.text.position.CopyFrom(value.proto)

    @property
    def value(self) -> str:
        return self._proto.text.text

    @value.setter
    def value(self, value: str):
        self._proto.text.text = value

    @property
    def exclude_from_sim(self) -> bool:
        return self._proto.exclude_from_sim

    @exclude_from_sim.setter
    def exclude_from_sim(self, value: bool):
        self._proto.exclude_from_sim = value

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the text"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class SchematicTextBox(SchematicItem):
    """A multi-line text item with optional border.  Text items are used for notes and other
    annotations.  They do not impact the netlist.

    .. versionadded:: 0.x.y (KiCad 11)"""

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicTextBox | None = None,
        proto_ref: schematic_types_pb2.SchematicTextBox | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicTextBox()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"SchematicTextBox(value={self.value!r}, top_left={self.top_left}, "
            f"bottom_right={self.bottom_right})"
        )

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
    def textbox(self) -> TextBox:
        return TextBox(proto_ref=self._proto.textbox)

    @textbox.setter
    def textbox(self, value: TextBox):
        self._proto.textbox.CopyFrom(value.proto)

    @property
    def top_left(self) -> Vector2:
        return Vector2(proto_ref=self._proto.textbox.top_left)

    @top_left.setter
    def top_left(self, value: Vector2):
        self._proto.textbox.top_left.CopyFrom(value.proto)

    @property
    def bottom_right(self) -> Vector2:
        return Vector2(proto_ref=self._proto.textbox.bottom_right)

    @bottom_right.setter
    def bottom_right(self, value: Vector2):
        self._proto.textbox.bottom_right.CopyFrom(value.proto)

    @property
    def value(self) -> str:
        return self._proto.textbox.text

    @value.setter
    def value(self, value: str):
        self._proto.textbox.text = value

    @property
    def graphic_attributes(self) -> GraphicAttributes:
        return GraphicAttributes(proto_ref=self._proto.graphic_attributes)

    @graphic_attributes.setter
    def graphic_attributes(self, value: GraphicAttributes):
        self._proto.graphic_attributes.CopyFrom(value.proto)

    @property
    def exclude_from_sim(self) -> bool:
        return self._proto.exclude_from_sim

    @exclude_from_sim.setter
    def exclude_from_sim(self, value: bool):
        self._proto.exclude_from_sim = value

    @property
    def margin_left(self) -> int:
        return self._proto.margin_left.value_nm

    @margin_left.setter
    def margin_left(self, value: int):
        self._proto.margin_left.value_nm = value

    @property
    def margin_top(self) -> int:
        return self._proto.margin_top.value_nm

    @margin_top.setter
    def margin_top(self, value: int):
        self._proto.margin_top.value_nm = value

    @property
    def margin_right(self) -> int:
        return self._proto.margin_right.value_nm

    @margin_right.setter
    def margin_right(self, value: int):
        self._proto.margin_right.value_nm = value

    @property
    def margin_bottom(self) -> int:
        return self._proto.margin_bottom.value_nm

    @margin_bottom.setter
    def margin_bottom(self, value: int):
        self._proto.margin_bottom.value_nm = value

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the text box"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class SchematicGraphicShape(SchematicItem):
    """Represents a graphic shape on a schematic.

    Although the underlying GraphicShape classes are shared between board and schematic in this API,
    there are some important differences:

    1. :class:`Segment` shapes are not supported in the schematic editor.  To draw a two-point
       line segment, either create a :class:`SchematicLine` object, or create a :class:`Polygon`
       shape with only two points.

    2. :class:`Polygon` shapes are more limited than in the board editor.  The schematic editor
       supports a single polyline, and it does not use the explicit :attr:`PolyLine.closed` flag
       in :attr:`PolygonWithHoles.outline`. To create a closed polygon, duplicate the starting
       point as the last point.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicGraphicShape | None = None,
        proto_ref: schematic_types_pb2.SchematicGraphicShape | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicGraphicShape()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        shape = self.shape
        if shape is None:
            return "SchematicGraphicShape(shape=None)"
        return f"SchematicGraphicShape(shape={shape})"

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
    def shape(self) -> GraphicShape | None:
        return to_concrete_shape(GraphicShape(self._proto.shape))

    @shape.setter
    def shape(self, value: GraphicShape):
        if value.proto.WhichOneof("geometry") == "segment":
            raise ValueError(
                "SchematicGraphicShape cannot be a segment; use SchematicLine instead,"
                "or a polyline with 2 points."
            )
        self._proto.shape.CopyFrom(value.proto)

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the shape"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class SchematicImage(SchematicItem):
    """A bitmap image placed on a schematic.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicImage | None = None,
        proto_ref: schematic_types_pb2.SchematicImage | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SchematicImage()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"SchematicImage(position={self.position}, bytes={len(self.image_data)})"

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
        return Vector2(proto_ref=self._proto.position)

    @position.setter
    def position(self, value: Vector2):
        self._proto.position.CopyFrom(value.proto)

    @property
    def transform_origin_offset(self) -> Vector2:
        return Vector2(proto_ref=self._proto.transform_origin_offset)

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
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the image"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class BaseLabel(SchematicItem):
    """The base class for schematic labels.  Labels are special text items that give names to
    electrical nets on a schematic.  They form connections at their :attr:`position` to other
    connected items (such as wires or pins).

    The orientation of a label is controlled by :attr:`spin_style`, not by
    ``text.attributes.angle``: KiCad derives both the text angle and the horizontal justification
    from the spin style, and an angle set via ``text.attributes.angle`` is overwritten by
    the spin style when the label is unpacked by KiCad.  For example, ``SLSS_UP`` renders the text
    vertically with its start anchored at the label position, while ``SLSS_RIGHT`` renders it
    horizontally with the text extending away from the anchor according to the justification.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    @property
    def locked(self) -> bool:
        return self.proto.locked == LockedState.LS_LOCKED

    @locked.setter
    def locked(self, locked: bool):
        self.proto.locked = {
            True: LockedState.LS_LOCKED,
            False: LockedState.LS_UNLOCKED,
        }.get(locked, LockedState.LS_UNLOCKED)

    @property
    def position(self) -> Vector2:
        return Vector2(proto_ref=self.proto.position)

    @position.setter
    def position(self, value: Vector2):
        self.proto.position.CopyFrom(value.proto)

    @property
    def text(self) -> Text:
        """The label text.  Setting ``attributes.angle`` on this text raises
        :class:`AttributeError`; use :attr:`spin_style` to control label orientation"""
        return LabelText(proto_ref=self.proto.text)

    @text.setter
    def text(self, value: Text):
        self.proto.text.CopyFrom(value.proto)

    @property
    def spin_style(self) -> SchematicLabelSpinStyle.ValueType:
        return self.proto.spin_style

    @spin_style.setter
    def spin_style(self, value: SchematicLabelSpinStyle.ValueType):
        self.proto.spin_style = value

    @property
    def fields(self) -> Sequence[SchematicField]:
        return MutableWrapperSequence(self.proto.fields, SchematicField)

    @fields.setter
    def fields(self, value: Sequence[SchematicField]):
        del self.proto.fields[:]
        self.proto.fields.extend(field.proto for field in value)

    @property
    def fields_autoplaced(self) -> bool:
        return self.proto.fields_autoplaced

    @fields_autoplaced.setter
    def fields_autoplaced(self, value: bool):
        self.proto.fields_autoplaced = value

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the label"""
        return MutableWrapperSequence(self.proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self.proto.custom_properties[:]
        self.proto.custom_properties.extend(prop.proto for prop in value)


class LabelText(Text):
    """A :class:`Text` that rejects angle assignment, because KiCad derives label orientation
    from the label's spin style rather than from the text angle"""

    @property
    def attributes(self) -> TextAttributes:
        return _LabelAttributes(proto_ref=self._proto.attributes)

    @attributes.setter
    def attributes(self, attributes: TextAttributes):
        self._proto.attributes.CopyFrom(attributes.proto)


class _LabelAttributes(TextAttributes):
    @property
    def angle(self) -> float:
        """The orientation of the text in degrees.  Reading is supported, but assignment raises
        :class:`AttributeError` because KiCad overwrites a label's text angle from its spin style
        (see :class:`BaseLabel`)"""
        return self._proto.angle.value_degrees

    @angle.setter
    def angle(self, angle: float):
        raise AttributeError(
            "Labels do not support setting text.attributes.angle: KiCad sets label angle and "
            "justification from spin_style, and any angle set here is overwritten.  "
            "Set spin_style instead (e.g. SchematicLabelSpinStyle.SLSS_UP)"
        )


class ShapeLabel(BaseLabel):
    """A ``BaseLabel`` that can take on a graphical shape

    .. versionadded:: 0.x.y (KiCad 11)
    """

    @property
    def shape(self) -> SchematicLabelShape.ValueType:
        return self.proto.shape

    @shape.setter
    def shape(self, value: SchematicLabelShape.ValueType):
        self.proto.shape = value


class LocalLabel(BaseLabel):
    """Local labels are single-line text labels with no extra graphical decoration.  They create
    sheet-specific net labels (such as `/NET1` or `/Subsheet/NET2`).

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.LocalLabel | None = None,
        proto_ref: schematic_types_pb2.LocalLabel | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.LocalLabel()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"LocalLabel(text={self.text.value!r}, position={self.position})"


class GlobalLabel(ShapeLabel):
    """Global labels are single-line text labels with a graphical border.  They create global
    labels with no sheet-specific prefix (such as ``NET1``).

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.GlobalLabel | None = None,
        proto_ref: schematic_types_pb2.GlobalLabel | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.GlobalLabel()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"GlobalLabel(text={self.text.value!r}, position={self.position})"

    @property
    def intersheet_refs_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.intersheet_refs_field)

    @intersheet_refs_field.setter
    def intersheet_refs_field(self, value: SchematicField):
        self._proto.intersheet_refs_field.CopyFrom(value.proto)


class HierarchicalLabel(ShapeLabel):
    """Hierarchical labels are special local labels that include a hierarchical port symbol and
    match up with a hierarchical sheet pin on the sheet symbol one level up in the hierarchy.
    They indicate a net that is exposed as a sheet pin for connection elsewhere in a hierarchical
    schematic.  See also :class:`SheetPin`.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.HierarchicalLabel | None = None,
        proto_ref: schematic_types_pb2.HierarchicalLabel | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.HierarchicalLabel()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"HierarchicalLabel(text={self.text.value!r}, position={self.position})"


class DirectiveLabel(ShapeLabel):
    """Directive labels are special labels that apply specific design rules to items rather than
    applying a net name.  They can also be used to apply rules to many items by creating a
    ``SchematicRuleArea`` and placing a :class:`DirectiveLabel` on its border.  All items
    enclosed by or intersecting the border of the rule area will have the same directives applied.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.DirectiveLabel | None = None,
        proto_ref: schematic_types_pb2.DirectiveLabel | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.DirectiveLabel()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"DirectiveLabel(text={self.text.value!r}, position={self.position})"


class Group(SchematicItem):
    """Represents a group of items on a schematic.

    Groups store item membership by ID only.  See the documentation for :attr:`items` and
    :attr:`item_ids` for details.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.Group | None = None,
        proto_ref: schematic_types_pb2.Group | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.Group()

        if proto is not None:
            self._proto.CopyFrom(proto)

        self._item_ids = self._proto.items
        self._item_resolver: Callable[[Sequence[KIID]], Sequence[SchematicItem]] | None = None
        self._unwrapped_items: Sequence[SchematicItem] | None = None

    def __repr__(self) -> str:
        return f"Group(name={self.name}, items={len(self.items)})"

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
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

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
    def items(self) -> Sequence[SchematicItem]:
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
    def items(self, value: Sequence[SchematicItem]):
        """Sets the items in the group, replacing any existing items"""
        del self._proto.items[:]
        self._unwrapped_items = value
        for item in value:
            self._proto.items.append(item.id)

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the group"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class SheetPin(ShapeLabel):
    """A pin on a hierarchical sheet symbol (:class:`SheetSymbol`) that is paired with a
    hierarchical label on the subsheet (see :class:`HierarchicalLabel`).

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SheetPin | None = None,
        proto_ref: schematic_types_pb2.SheetPin | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SheetPin()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"SheetPin({self.text.value}, pos={self.position})"

    @property
    def side(self) -> SheetSide.ValueType:
        return self._proto.side

    @side.setter
    def side(self, value: SheetSide.ValueType):
        self._proto.side = value


class SheetSymbol(SchematicItem):
    """The graphical representation of a hierarchical sub-sheet on its parent sheet.  A sheet
    symbol contains the metadata about the sub-sheet such as its filename and instance name, as
    well as its pins and other graphic attributes.  Sheet symbols may also have custom fields.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SheetSymbol | None = None,
        proto_ref: schematic_types_pb2.SheetSymbol | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SheetSymbol()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"SheetSymbol(name={self.name_field.text.value}, file={self.filename_field.text.value}, pos={self.position})"

    @property
    def path(self) -> SheetPath:
        """The sheet that contains this instance.

        On a create or update request, the targeted sheet comes from the request header, and this
        field reports the sheet the returned instance was read from."""
        return SheetPath(proto_ref=self._proto.path)

    @path.setter
    def path(self, path: SheetPath):
        self._proto.path.CopyFrom(path.proto)

    @property
    def page_number(self) -> str:
        """Page numbers in KiCad are arbitrary user data and don't have to be numeric"""
        return self._proto.page_number

    @page_number.setter
    def page_number(self, page_number: str):
        self._proto.page_number = page_number

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
        return Vector2(proto_ref=self._proto.position)

    @position.setter
    def position(self, value: Vector2):
        self._proto.position.CopyFrom(value.proto)

    @property
    def size(self) -> Vector2:
        return Vector2(proto_ref=self._proto.size)

    @size.setter
    def size(self, value: Vector2):
        self._proto.size.CopyFrom(value.proto)

    @property
    def border_stroke(self) -> StrokeAttributes:
        return StrokeAttributes(proto_ref=self._proto.border_stroke)

    @border_stroke.setter
    def border_stroke(self, value: StrokeAttributes):
        self._proto.border_stroke.CopyFrom(value.proto)

    @property
    def fill(self) -> GraphicFillAttributes:
        return GraphicFillAttributes(proto_ref=self._proto.fill)

    @fill.setter
    def fill(self, value: GraphicFillAttributes):
        self._proto.fill.CopyFrom(value.proto)

    @property
    def name_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.name_field)

    @name_field.setter
    def name_field(self, value: SchematicField):
        self._proto.name_field.CopyFrom(value.proto)

    @property
    def filename_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.filename_field)

    @filename_field.setter
    def filename_field(self, value: SchematicField):
        self._proto.filename_field.CopyFrom(value.proto)

    @property
    def user_fields(self) -> Sequence[SchematicField]:
        return MutableWrapperSequence(self._proto.user_fields, SchematicField)

    @user_fields.setter
    def user_fields(self, value: Sequence[SchematicField]):
        del self._proto.user_fields[:]
        self._proto.user_fields.extend(field.proto for field in value)

    @property
    def pins(self) -> MutableWrapperSequence[SheetPin]:
        return MutableWrapperSequence(self._proto.pins, SheetPin)

    @pins.setter
    def pins(self, value: Sequence[SheetPin]):
        del self._proto.pins[:]
        self._proto.pins.extend(pin.proto for pin in value)

    @property
    def exclude_from_sim(self) -> bool:
        return self._proto.exclude_from_sim

    @exclude_from_sim.setter
    def exclude_from_sim(self, value: bool):
        self._proto.exclude_from_sim = value

    @property
    def exclude_from_bom(self) -> bool:
        return self._proto.exclude_from_bom

    @exclude_from_bom.setter
    def exclude_from_bom(self, value: bool):
        self._proto.exclude_from_bom = value

    @property
    def exclude_from_board(self) -> bool:
        return self._proto.exclude_from_board

    @exclude_from_board.setter
    def exclude_from_board(self, value: bool):
        self._proto.exclude_from_board = value

    @property
    def dnp(self) -> bool:
        return self._proto.dnp

    @dnp.setter
    def dnp(self, value: bool):
        self._proto.dnp = value

    @property
    def fields_autoplaced(self) -> bool:
        return self._proto.fields_autoplaced

    @fields_autoplaced.setter
    def fields_autoplaced(self, value: bool):
        self._proto.fields_autoplaced = value

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the sheet"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)

    @property
    def variants(self) -> Sequence[SheetVariant]:
        """The variants carried by this instance."""
        return MutableWrapperSequence(self._proto.variants.variants, SheetVariant)

    @variants.setter
    def variants(self, value: Sequence[SheetVariant]):
        del self._proto.variants.variants[:]
        self._proto.variants.variants.extend(v.proto for v in value)


class SchematicPinAlternate(Wrapper):
    """An alternate definition for a :class:`SchematicPin`.  Pins may have multiple different
    functions defined using alternates, and these will show as user-selectable when the symbol is
    placed on a schematic.  Alternates may change the name, shape, and electrical function of a
    pin, but not the number (since that is the true identity of a pin and how it maps to a
    footprint pad).

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicPinAlternate | None = None,
        proto_ref: schematic_types_pb2.SchematicPinAlternate | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicPinAlternate()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

    @property
    def shape(self) -> SchematicPinShape.ValueType:
        return self._proto.shape

    @shape.setter
    def shape(self, value: SchematicPinShape.ValueType):
        self._proto.shape = value

    @property
    def electrical_type(self) -> ElectricalPinType.ValueType:
        return self._proto.electrical_type

    @electrical_type.setter
    def electrical_type(self, value: ElectricalPinType.ValueType):
        self._proto.electrical_type = value


class SchematicPin(SchematicItem):
    """A symbol pin.  Pins form electrical connection at their :attr:`position` and then extend
    back to the symbol body by their :attr:`length`.  Pins map to footprint pads according to
    their :attr:`number` property, which, despite the name, does not need to be strictly numeric.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicPin | None = None,
        proto_ref: schematic_types_pb2.SchematicPin | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SchematicPin()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"SchematicPin(name={self.name}, number={self.number}, position={self.position})"

    @property
    def name(self) -> str:
        """A functional name for the pin, for example 'VCC'."""
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

    @property
    def number(self) -> str:
        """The identifier for this pin which maps it to a footprint pad.  May be alphanumeric."""
        return self._proto.number

    @number.setter
    def number(self, value: str):
        self._proto.number = value

    @property
    def position(self) -> Vector2:
        """Position in the symbol definition's local coordinate frame (relative to the
        symbol origin, without any rotation or mirroring applied)"""
        return Vector2(proto_ref=self._proto.position)

    @position.setter
    def position(self, value: Vector2):
        self._proto.position.CopyFrom(value.proto)

    @property
    def length(self) -> int:
        return self._proto.length.value_nm

    @length.setter
    def length(self, value: int):
        self._proto.length.value_nm = value

    @property
    def orientation(self) -> SchematicPinOrientation.ValueType:
        """Which way the pin is oriented, relative to the connection point (:attr:`position`).

        For example, ``SPO_RIGHT`` means the pin shape extends rightward from the connection
        point, which usually means the pin is placed on the *left* side of a symbol."""
        return self._proto.orientation

    @orientation.setter
    def orientation(self, value: SchematicPinOrientation.ValueType):
        self._proto.orientation = value

    @property
    def electrical_type(self) -> ElectricalPinType.ValueType:
        return self._proto.electrical_type

    @electrical_type.setter
    def electrical_type(self, value: ElectricalPinType.ValueType):
        self._proto.electrical_type = value

    @property
    def shape(self) -> SchematicPinShape.ValueType:
        return self._proto.shape

    @shape.setter
    def shape(self, value: SchematicPinShape.ValueType):
        self._proto.shape = value

    @property
    def visible(self) -> bool:
        return self._proto.visible

    @visible.setter
    def visible(self, value: bool):
        self._proto.visible = value

    @property
    def name_text_size(self) -> int:
        return self._proto.name_text_size.value_nm

    @name_text_size.setter
    def name_text_size(self, value: int):
        self._proto.name_text_size.value_nm = value

    @property
    def number_text_size(self) -> int:
        return self._proto.number_text_size.value_nm

    @number_text_size.setter
    def number_text_size(self, value: int):
        self._proto.number_text_size.value_nm = value

    @property
    def alternates(self) -> Sequence[SchematicPinAlternate]:
        return MutableWrapperSequence(self._proto.alternates, SchematicPinAlternate)

    @alternates.setter
    def alternates(self, value: Sequence[SchematicPinAlternate]):
        del self._proto.alternates[:]
        self._proto.alternates.extend(alt.proto for alt in value)

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the pin"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)

    @property
    def active_alternate(self) -> str | None:
        return self._proto.active_alternate if self._proto.HasField("active_alternate") else None

    @active_alternate.setter
    def active_alternate(self, value: str | None):
        if value is not None:
            self._proto.active_alternate = value
        else:
            self._proto.ClearField("active_alternate")


_child_item_types = (
    SchematicPin,
    SchematicField,
    SchematicGraphicShape,
    SchematicText,
    SchematicTextBox,
)


def _unpack_child_item(
    child: SchematicSymbolChild,
) -> (
    SchematicPin | SchematicField | SchematicGraphicShape | SchematicText | SchematicTextBox | Any
):
    kind = child.kind
    if kind == "SchematicPin":
        pin_proto = schematic_types_pb2.SchematicPin()
        child._proto.item.Unpack(pin_proto)
        return SchematicPin(proto=pin_proto)
    if kind == "SchematicField":
        field_proto = schematic_types_pb2.SchematicField()
        child._proto.item.Unpack(field_proto)
        return SchematicField(proto=field_proto)
    if kind == "SchematicGraphicShape":
        shape_proto = schematic_types_pb2.SchematicGraphicShape()
        child._proto.item.Unpack(shape_proto)
        return SchematicGraphicShape(proto=shape_proto)
    if kind == "SchematicText":
        text_proto = schematic_types_pb2.SchematicText()
        child._proto.item.Unpack(text_proto)
        return SchematicText(proto=text_proto)
    if kind == "SchematicTextBox":
        textbox_proto = schematic_types_pb2.SchematicTextBox()
        child._proto.item.Unpack(textbox_proto)
        return SchematicTextBox(proto=textbox_proto)
    return child._proto.item


class SchematicSymbolChild(Wrapper):
    """An item stored in a symbol definition (a pin, field, graphic shape, text, or text box).

    Pass a concrete item to :meth:`SchematicSymbol.add_item` rather than constructing this
    class directly; the child wrapper and its unit/body-style tags are created for you.
    Child item positions are relative to the symbol origin, without rotation or mirroring.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicSymbolChild | None = None,
        proto_ref: schematic_types_pb2.SchematicSymbolChild | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicSymbolChild()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)

        self._unwrapped_item: Wrapper | Any | None = None

    def _pack(self):
        if self._unwrapped_item is not None and self._unwrapped_item is not self._proto.item:
            self._proto.item.Pack(self._unwrapped_item.proto)

    @property
    def item(
        self,
    ) -> (
        SchematicPin
        | SchematicField
        | SchematicGraphicShape
        | SchematicText
        | SchematicTextBox
        | Any
    ):
        """The child's item, unpacked into a concrete wrapper when possible"""
        if self._unwrapped_item is None:
            self._unwrapped_item = _unpack_child_item(self)
        return cast(
            "SchematicPin | SchematicField | SchematicGraphicShape | SchematicText"
            " | SchematicTextBox | Any",
            self._unwrapped_item,
        )

    @item.setter
    def item(self, value: Wrapper):
        if not isinstance(value, _child_item_types):
            allowed = ", ".join(t.__name__ for t in _child_item_types)
            raise TypeError(
                f"SchematicSymbolChild.item must be one of {allowed}; got {type(value).__name__}."
                "  Note that graphic shapes must be wrapped in SchematicGraphicShape, not passed"
                " as a bare GraphicShape subclass."
            )
        self._proto.item.Pack(value.proto)
        self._unwrapped_item = value

    @property
    def unit(self) -> int | None:
        return self._proto.unit.unit if self._proto.HasField("unit") else None

    @unit.setter
    def unit(self, value: int | None):
        if value is not None:
            self._proto.unit.unit = value
        else:
            self._proto.ClearField("unit")

    @property
    def kind(self) -> str | None:
        """The type of the packed item, if valid"""
        if not self._proto.HasField("item") or len(self._proto.item.type_url) == 0:
            return None
        return self._proto.item.type_url.rsplit(".", 1)[-1]

    @property
    def is_private(self) -> bool:
        """Private items are only shown in the symbol editor, not the schematic"""
        return self._proto.is_private

    @is_private.setter
    def is_private(self, value: bool):
        self._proto.is_private = value


class SchematicSymbolAttributes(Wrapper):
    """
    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicSymbolAttributes | None = None,
        proto_ref: schematic_types_pb2.SchematicSymbolAttributes | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicSymbolAttributes()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def exclude_from_simulation(self) -> bool:
        return self._proto.exclude_from_simulation

    @exclude_from_simulation.setter
    def exclude_from_simulation(self, value: bool):
        self._proto.exclude_from_simulation = value

    @property
    def exclude_from_bill_of_materials(self) -> bool:
        return self._proto.exclude_from_bill_of_materials

    @exclude_from_bill_of_materials.setter
    def exclude_from_bill_of_materials(self, value: bool):
        self._proto.exclude_from_bill_of_materials = value

    @property
    def exclude_from_board(self) -> bool:
        return self._proto.exclude_from_board

    @exclude_from_board.setter
    def exclude_from_board(self, value: bool):
        self._proto.exclude_from_board = value

    @property
    def exclude_from_position_files(self) -> bool:
        return self._proto.exclude_from_position_files

    @exclude_from_position_files.setter
    def exclude_from_position_files(self, value: bool):
        self._proto.exclude_from_position_files = value

    @property
    def do_not_populate(self) -> bool:
        return self._proto.do_not_populate

    @do_not_populate.setter
    def do_not_populate(self, value: bool):
        self._proto.do_not_populate = value


class SchematicSymbolVariant(Wrapper):
    """
    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicSymbolVariant | None = None,
        proto_ref: schematic_types_pb2.SchematicSymbolVariant | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicSymbolVariant()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

    @property
    def description(self) -> str:
        return self._proto.description

    @description.setter
    def description(self, value: str):
        self._proto.description = value

    @property
    def attributes(self) -> SchematicSymbolAttributes:
        """complete set of attributes for a symbol with this variant"""
        return SchematicSymbolAttributes(proto_ref=self._proto.attributes)

    @attributes.setter
    def attributes(self, value: SchematicSymbolAttributes):
        self._proto.attributes.CopyFrom(value.proto)

    @property
    def fields(self) -> dict[str, str]:
        return dict(self._proto.fields)

    @fields.setter
    def fields(self, value: dict[str, str]):
        self._proto.fields.clear()
        self._proto.fields.update(value)

    @property
    def symbol_override(self) -> LibraryIdentifier | None:
        """Alternate library symbol used in this variant, if any"""
        if self._proto.HasField("symbol_override"):
            return LibraryIdentifier(proto_ref=self._proto.symbol_override)
        return None

    @symbol_override.setter
    def symbol_override(self, value: LibraryIdentifier | None):
        if value is not None:
            self._proto.symbol_override.CopyFrom(value.proto)
        else:
            self._proto.ClearField("symbol_override")

    @property
    def pin_map_override(self) -> PinMapInstanceOverride | None:
        """Per-variant pin-to-pad map override, if any"""
        if self._proto.HasField("pin_map_override"):
            return PinMapInstanceOverride(proto_ref=self._proto.pin_map_override)
        return None

    @pin_map_override.setter
    def pin_map_override(self, value: PinMapInstanceOverride | None):
        if value is not None:
            self._proto.pin_map_override.CopyFrom(value.proto)
        else:
            self._proto.ClearField("pin_map_override")


class PinMapEntry(Wrapper):
    """Maps a symbol pin to a footprint pad"""

    def __init__(
        self,
        proto: schematic_types_pb2.PinMapEntry | None = None,
        proto_ref: schematic_types_pb2.PinMapEntry | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.PinMapEntry()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def pin_number(self) -> str:
        return self._proto.pin_number

    @pin_number.setter
    def pin_number(self, value: str):
        self._proto.pin_number = value

    @property
    def pad_number(self) -> str:
        """bracketed stacked list allowed, e.g. '[4,9]'"""
        return self._proto.pad_number

    @pad_number.setter
    def pad_number(self, value: str):
        self._proto.pad_number = value


class PinMap(Wrapper):
    """A named mapping of symbol pins to footprint pads"""

    def __init__(
        self,
        proto: schematic_types_pb2.PinMap | None = None,
        proto_ref: schematic_types_pb2.PinMap | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.PinMap()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

    @property
    def entries(self) -> Sequence[PinMapEntry]:
        return MutableWrapperSequence(self._proto.entries, PinMapEntry)

    @entries.setter
    def entries(self, value: Sequence[PinMapEntry]):
        del self._proto.entries[:]
        self._proto.entries.extend(entry.proto for entry in value)


class AssociatedFootprint(Wrapper):
    """A footprint the symbol is associated with, and the name of the pin map to use for it"""

    def __init__(
        self,
        proto: schematic_types_pb2.AssociatedFootprint | None = None,
        proto_ref: schematic_types_pb2.AssociatedFootprint | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.AssociatedFootprint()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def footprint(self) -> LibraryIdentifier:
        return LibraryIdentifier(proto_ref=self._proto.footprint)

    @footprint.setter
    def footprint(self, value: LibraryIdentifier):
        self._proto.footprint.CopyFrom(value.proto)

    @property
    def map_name(self) -> str:
        return self._proto.map_name

    @map_name.setter
    def map_name(self, value: str):
        self._proto.map_name = value


class SymbolPinMaps(Wrapper):
    """Pin maps defined in a symbol and the footprints they are associated with"""

    def __init__(
        self,
        proto: schematic_types_pb2.SymbolPinMaps | None = None,
        proto_ref: schematic_types_pb2.SymbolPinMaps | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SymbolPinMaps()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def associated_footprints(self) -> Sequence[AssociatedFootprint]:
        return MutableWrapperSequence(self._proto.associated_footprints, AssociatedFootprint)

    @associated_footprints.setter
    def associated_footprints(self, value: Sequence[AssociatedFootprint]):
        del self._proto.associated_footprints[:]
        self._proto.associated_footprints.extend(fp.proto for fp in value)

    @property
    def pin_maps(self) -> Sequence[PinMap]:
        return MutableWrapperSequence(self._proto.pin_maps, PinMap)

    @pin_maps.setter
    def pin_maps(self, value: Sequence[PinMap]):
        del self._proto.pin_maps[:]
        self._proto.pin_maps.extend(pin_map.proto for pin_map in value)


class PinMapInstanceOverride(Wrapper):
    """A per-symbol-instance override of the library pin maps"""

    def __init__(
        self,
        proto: schematic_types_pb2.PinMapInstanceOverride | None = None,
        proto_ref: schematic_types_pb2.PinMapInstanceOverride | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.PinMapInstanceOverride()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def mode(self) -> PinMapOverrideMode.ValueType:
        return self._proto.mode

    @mode.setter
    def mode(self, value: PinMapOverrideMode.ValueType):
        self._proto.mode = value

    @property
    def active_map_name(self) -> str:
        return self._proto.active_map_name

    @active_map_name.setter
    def active_map_name(self, value: str):
        self._proto.active_map_name = value

    @property
    def edits(self) -> Sequence[PinMapEntry]:
        return MutableWrapperSequence(self._proto.edits, PinMapEntry)

    @edits.setter
    def edits(self, value: Sequence[PinMapEntry]):
        del self._proto.edits[:]
        self._proto.edits.extend(edit.proto for edit in value)


class JumperGroup(Wrapper):
    """A group of pins internally connected by a jumper"""

    def __init__(
        self,
        proto: schematic_types_pb2.JumperGroup | None = None,
        proto_ref: schematic_types_pb2.JumperGroup | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.JumperGroup()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def pin_numbers(self) -> Sequence[str]:
        return list(self._proto.pin_numbers)

    @pin_numbers.setter
    def pin_numbers(self, value: Sequence[str]):
        del self._proto.pin_numbers[:]
        self._proto.pin_numbers.extend(value)


class JumperSettings(Wrapper):
    """Jumper definitions for a symbol"""

    def __init__(
        self,
        proto: schematic_types_pb2.JumperSettings | None = None,
        proto_ref: schematic_types_pb2.JumperSettings | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.JumperSettings()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def duplicate_names_are_jumpered(self) -> bool:
        """True if pins with duplicate names are considered connected by a jumper"""
        return self._proto.duplicate_names_are_jumpered

    @duplicate_names_are_jumpered.setter
    def duplicate_names_are_jumpered(self, value: bool):
        self._proto.duplicate_names_are_jumpered = value

    @property
    def groups(self) -> Sequence[JumperGroup]:
        return MutableWrapperSequence(self._proto.groups, JumperGroup)

    @groups.setter
    def groups(self, value: Sequence[JumperGroup]):
        del self._proto.groups[:]
        self._proto.groups.extend(group.proto for group in value)


class SchematicUnitDisplayName(Wrapper):
    """A custom display name for one unit of a multi-unit symbol"""

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicUnitDisplayName | None = None,
        proto_ref: schematic_types_pb2.SchematicUnitDisplayName | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicUnitDisplayName()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def unit(self) -> int:
        return self._proto.unit

    @unit.setter
    def unit(self, value: int):
        self._proto.unit = value

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value


class SchematicBodyStyle(Wrapper):
    """A named body style a symbol can be displayed with"""

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicBodyStyle | None = None,
        proto_ref: schematic_types_pb2.SchematicBodyStyle | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicBodyStyle()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value


class SchematicSymbol(Wrapper):
    """A symbol definition, or a library symbol.

    Child items (pins, graphics, text, fields) are stored with positions relative to
    the symbol origin and without any rotation or mirroring applied.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicSymbol | None = None,
        proto_ref: schematic_types_pb2.SchematicSymbol | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SchematicSymbol()

        if proto is not None:
            self._proto.CopyFrom(proto)

        self._unwrapped_items = [
            SchematicSymbolChild(proto_ref=item) for item in self._proto.items
        ]

    def _pack(self):
        """Packs all child items back into the proto"""
        del self._proto.items[:]
        self._proto.items.extend(child.proto for child in self._unwrapped_items)

    @property
    def proto(self):
        self._pack()
        return self.__dict__["_proto"]

    def __repr__(self) -> str:
        return (
            f"SchematicSymbol(id={self.id}, reference={self.reference_field.text.value}, "
            f"value={self.value_field.text.value})"
        )

    @property
    def id(self) -> LibraryIdentifier:
        return LibraryIdentifier(proto_ref=self._proto.id)

    @id.setter
    def id(self, value: LibraryIdentifier):
        self._proto.id.CopyFrom(value.proto)

    @property
    def type(self) -> SchematicSymbolType.ValueType:
        """The type of the symbol (normal, local power, or global power).

        A power symbol is one that drives a net name from a single hidden power input pin. To
        create a normal power symbol, set ``type`` to ``SchematicSymbolType.SST_GLOBAL_POWER`` and
        add a single hidden pin of type ``ElectricalPinType.EPT_POWER_INPUT``, normally with length
        0.  The power symbol will drive a net according to its :attr:`value_field` contents.  A
        local power symbol (``SchematicSymbolType.SST_LOCAL_POWER``) will act like a local label
        on the sheet it is placed on rather than a global label."""
        return self._proto.type

    @type.setter
    def type(self, value: SchematicSymbolType.ValueType):
        self._proto.type = value

    @property
    def attributes(self) -> SchematicSymbolAttributes:
        return SchematicSymbolAttributes(proto_ref=self._proto.attributes)

    @attributes.setter
    def attributes(self, value: SchematicSymbolAttributes):
        self._proto.attributes.CopyFrom(value.proto)

    @property
    def reference_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.reference_field)

    @reference_field.setter
    def reference_field(self, value: SchematicField):
        self._proto.reference_field.CopyFrom(value.proto)

    @property
    def value_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.value_field)

    @value_field.setter
    def value_field(self, value: SchematicField):
        self._proto.value_field.CopyFrom(value.proto)

    @property
    def footprint_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.footprint_field)

    @footprint_field.setter
    def footprint_field(self, value: SchematicField):
        self._proto.footprint_field.CopyFrom(value.proto)

    @property
    def datasheet_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.datasheet_field)

    @datasheet_field.setter
    def datasheet_field(self, value: SchematicField):
        self._proto.datasheet_field.CopyFrom(value.proto)

    @property
    def description_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.description_field)

    @description_field.setter
    def description_field(self, value: SchematicField):
        self._proto.description_field.CopyFrom(value.proto)

    @property
    def items(self) -> Sequence[SchematicSymbolChild]:
        return self._unwrapped_items

    @items.setter
    def items(self, value: Sequence[SchematicSymbolChild]):
        self._unwrapped_items = list(value)

    def add_item(
        self,
        item: SchematicSymbolChild
        | SchematicPin
        | SchematicField
        | SchematicGraphicShape
        | SchematicText
        | SchematicTextBox,
        unit: int | None = None,
        is_private: bool = False,
    ):
        """Adds an item to the symbol definition.

        Accepts a :class:`SchematicSymbolChild` or a concrete child item (a
        :class:`SchematicPin`, :class:`SchematicField`, :class:`SchematicGraphicShape`,
        :class:`SchematicText`, or :class:`SchematicTextBox`); concrete items are wrapped
        in a :class:`SchematicSymbolChild` automatically.

        :param unit: if given, the item belongs only to this unit of a multi-unit symbol;
            otherwise it is common to all units.
        :param is_private: if true, the item is shown only in the symbol editor, not on
            the schematic.
        """
        if isinstance(item, SchematicSymbolChild):
            if unit is not None:
                item.unit = unit
            if is_private:
                item.is_private = True
            self._unwrapped_items.append(item)
        elif isinstance(item, _child_item_types):
            child = SchematicSymbolChild()
            child.item = item
            if unit is not None:
                child.unit = unit
            if is_private:
                child.is_private = True
            self._unwrapped_items.append(child)
        else:
            allowed = ", ".join(t.__name__ for t in _child_item_types)
            raise TypeError(
                f"add_item() requires a SchematicSymbolChild or one of {allowed};"
                f" got {type(item).__name__}.  Note that graphic shapes must be wrapped in"
                " SchematicGraphicShape, not passed as a bare GraphicShape subclass."
            )

    @property
    def unit_count(self) -> int:
        return self._proto.unit_count

    @unit_count.setter
    def unit_count(self, value: int):
        self._proto.unit_count = value

    @property
    def body_style_count(self) -> int:
        return len(self._proto.body_style)

    @property
    def keywords(self) -> str:
        return self._proto.keywords

    @keywords.setter
    def keywords(self, value: str):
        self._proto.keywords = value

    @property
    def pins(self) -> Sequence[SchematicPin]:
        """The symbol's pins.

        Includes pins from units that are not placed in the instance this symbol
        belongs to(for multi-unit symbols).
        """
        return [
            cast(SchematicPin, child.item) for child in self.items if child.kind == "SchematicPin"
        ]

    @property
    def fields(self) -> Sequence[SchematicField]:
        """The definition's fields"""
        return [
            cast(SchematicField, child.item)
            for child in self.items
            if child.kind == "SchematicField"
        ]

    @property
    def footprint_filters(self) -> Sequence[str]:
        return list(self._proto.footprint_filters)

    @footprint_filters.setter
    def footprint_filters(self, value: Sequence[str]):
        del self._proto.footprint_filters[:]
        self._proto.footprint_filters.extend(value)

    @property
    def body_style(self) -> Sequence[SchematicBodyStyle]:
        """Body styles the symbol can be displayed with"""
        return MutableWrapperSequence(self._proto.body_style, SchematicBodyStyle)

    @body_style.setter
    def body_style(self, value: Sequence[SchematicBodyStyle]):
        del self._proto.body_style[:]
        self._proto.body_style.extend(style.proto for style in value)

    @property
    def pin_maps(self) -> SymbolPinMaps:
        """Pin maps and their associated footprints"""
        return SymbolPinMaps(proto_ref=self._proto.pin_maps)

    @pin_maps.setter
    def pin_maps(self, value: SymbolPinMaps):
        self._proto.pin_maps.CopyFrom(value.proto)

    @property
    def jumpers(self) -> JumperSettings:
        """Jumper settings for the symbol"""
        return JumperSettings(proto_ref=self._proto.jumpers)

    @jumpers.setter
    def jumpers(self, value: JumperSettings):
        self._proto.jumpers.CopyFrom(value.proto)

    @property
    def units_locked(self) -> bool:
        return self._proto.units_locked

    @units_locked.setter
    def units_locked(self, value: bool):
        self._proto.units_locked = value

    @property
    def unit_display_names(self) -> Sequence[SchematicUnitDisplayName]:
        return MutableWrapperSequence(self._proto.unit_display_names, SchematicUnitDisplayName)

    @unit_display_names.setter
    def unit_display_names(self, value: Sequence[SchematicUnitDisplayName]):
        del self._proto.unit_display_names[:]
        self._proto.unit_display_names.extend(name.proto for name in value)

    @property
    def embedded_fonts(self) -> bool:
        return self._proto.embedded_fonts

    @embedded_fonts.setter
    def embedded_fonts(self, value: bool):
        self._proto.embedded_fonts = value

    @property
    def show_pin_numbers(self) -> bool:
        """Whether pin numbers are shown for all pins of this symbol"""
        return self._proto.show_pin_numbers

    @show_pin_numbers.setter
    def show_pin_numbers(self, value: bool):
        self._proto.show_pin_numbers = value

    @property
    def show_pin_names(self) -> bool:
        """Whether pin names are shown for all pins of this symbol"""
        return self._proto.show_pin_names

    @show_pin_names.setter
    def show_pin_names(self, value: bool):
        self._proto.show_pin_names = value

    @property
    def pin_name_offset(self) -> int:
        """Distance between the pin and its name text; 0 means the name is inside the body outline"""
        return self._proto.pin_name_offset.value_nm

    @pin_name_offset.setter
    def pin_name_offset(self, value: int):
        self._proto.pin_name_offset.value_nm = value


class SchematicSymbolTransform(Wrapper):
    """
    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicSymbolTransform | None = None,
        proto_ref: schematic_types_pb2.SchematicSymbolTransform | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicSymbolTransform()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def orientation(self) -> SchematicSymbolOrientation.ValueType:
        return self._proto.orientation

    @orientation.setter
    def orientation(self, value: SchematicSymbolOrientation.ValueType):
        self._proto.orientation = value

    @property
    def mirror_x(self) -> bool:
        return self._proto.mirror_x

    @mirror_x.setter
    def mirror_x(self, value: bool):
        self._proto.mirror_x = value

    @property
    def mirror_y(self) -> bool:
        return self._proto.mirror_y

    @mirror_y.setter
    def mirror_y(self, value: bool):
        self._proto.mirror_y = value


class SchematicSymbolInstance(SchematicItem):
    """
    An instance of a symbol placed on a schematic.

    Direct children of the instance (for example, fields) are stored in absolute coordinate
    space, meaning they are relative to a sheet.  Children of the :class:`SchematicSymbol`
    definition are in relative coordinate space and don't have rotation or mirroring applied.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicSymbolInstance | None = None,
        proto_ref: schematic_types_pb2.SchematicSymbolInstance | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicSymbolInstance()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

        self._definition = SchematicSymbol(proto_ref=self._proto.definition)

    @property
    def proto(self):
        self._definition._pack()
        return self.__dict__["_proto"]

    def __repr__(self) -> str:

        return (
            f"SchematicSymbolInstance(reference={self.reference_field.text.value}, "
            f"value={self.value_field.text.value}, unit={self.unit}, position={self.position}, "
            f"path={self.path})"
        )

    @property
    def path(self) -> SheetPath:
        """Symbol instances may refer to the same graphical symbol from multiple different sheets
        in a hierarchical schematic.  Each instance will have its own reference designator, and
        may also have a different selected unit and other attributes.

        On a create or update request, the targeted sheet comes from the request header, and this
        field reports the sheet the returned instance was read from."""
        return SheetPath(proto_ref=self._proto.path)

    @path.setter
    def path(self, value: SheetPath):
        self._proto.path.CopyFrom(value.proto)

    @property
    def position(self) -> Vector2:
        return Vector2(proto_ref=self._proto.position)

    @position.setter
    def position(self, value: Vector2):
        self._proto.position.CopyFrom(value.proto)

    @property
    def transform(self) -> SchematicSymbolTransform:
        return SchematicSymbolTransform(proto_ref=self._proto.transform)

    @transform.setter
    def transform(self, value: SchematicSymbolTransform):
        self._proto.transform.CopyFrom(value.proto)

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
    def definition(self) -> SchematicSymbol:
        return self._definition

    @definition.setter
    def definition(self, value: SchematicSymbol):
        self._proto.definition.CopyFrom(value.proto)
        self._definition = SchematicSymbol(proto_ref=self._proto.definition)

    @property
    def reference_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.reference_field)

    @reference_field.setter
    def reference_field(self, value: SchematicField):
        self._proto.reference_field.CopyFrom(value.proto)

    @property
    def reference(self) -> str:
        """The symbol's reference designator (a shortcut for self.reference_field.text.value)"""
        return self.reference_field.text.value

    @reference.setter
    def reference(self, value: str):
        self.reference_field.text.value = value

    @property
    def value(self) -> str:
        """The symbol's value (a shortcut for self.value_field.text.value)"""
        return self.value_field.text.value

    @value.setter
    def value(self, value: str):
        self.value_field.text.value = value

    @property
    def value_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.value_field)

    @value_field.setter
    def value_field(self, value: SchematicField):
        self._proto.value_field.CopyFrom(value.proto)

    @property
    def footprint_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.footprint_field)

    @footprint_field.setter
    def footprint_field(self, value: SchematicField):
        self._proto.footprint_field.CopyFrom(value.proto)

    @property
    def datasheet_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.datasheet_field)

    @datasheet_field.setter
    def datasheet_field(self, value: SchematicField):
        self._proto.datasheet_field.CopyFrom(value.proto)

    @property
    def description_field(self) -> SchematicField:
        return SchematicField(proto_ref=self._proto.description_field)

    @description_field.setter
    def description_field(self, value: SchematicField):
        self._proto.description_field.CopyFrom(value.proto)

    @property
    def attributes(self) -> SchematicSymbolAttributes:
        """The attributes of the default variant, shared by every instance of this symbol.  Give one
        instance its own attributes through a named variant instead."""
        return SchematicSymbolAttributes(proto_ref=self._proto.attributes)

    @attributes.setter
    def attributes(self, value: SchematicSymbolAttributes):
        self._proto.attributes.CopyFrom(value.proto)

    @property
    def unit(self) -> int:
        return self._proto.unit.unit

    @unit.setter
    def unit(self, value: int):
        self._proto.unit.unit = value

    @property
    def body_style(self) -> int | None:
        return self._proto.body_style.style if self._proto.HasField("body_style") else None

    @body_style.setter
    def body_style(self, value: int | None):
        if value is not None:
            self._proto.body_style.style = value
        else:
            self._proto.ClearField("body_style")

    @property
    def show_pin_names(self) -> bool:
        return self._proto.show_pin_names

    @show_pin_names.setter
    def show_pin_names(self, value: bool):
        self._proto.show_pin_names = value

    @property
    def show_pin_numbers(self) -> bool:
        return self._proto.show_pin_numbers

    @show_pin_numbers.setter
    def show_pin_numbers(self, value: bool):
        self._proto.show_pin_numbers = value

    @property
    def pin_name_offset(self) -> int:
        return self._proto.pin_name_offset.value_nm

    @pin_name_offset.setter
    def pin_name_offset(self, value: int):
        self._proto.pin_name_offset.value_nm = value

    @property
    def variants(self) -> Sequence[SchematicSymbolVariant]:
        return MutableWrapperSequence(self._proto.variants.variants, SchematicSymbolVariant)

    @variants.setter
    def variants(self, value: Sequence[SchematicSymbolVariant]):
        del self._proto.variants.variants[:]
        self._proto.variants.variants.extend(v.proto for v in value)

    @property
    def user_fields(self) -> Sequence[SchematicField]:
        return MutableWrapperSequence(self._proto.user_fields, SchematicField)

    @user_fields.setter
    def user_fields(self, value: Sequence[SchematicField]):
        del self._proto.user_fields[:]
        self._proto.user_fields.extend(f.proto for f in value)

    @property
    def pin_map_override(self) -> PinMapInstanceOverride:
        return PinMapInstanceOverride(proto_ref=self._proto.pin_map_override)

    @property
    def fields_autoplaced(self) -> bool:
        return self._proto.fields_autoplaced

    @fields_autoplaced.setter
    def fields_autoplaced(self, value: bool):
        self._proto.fields_autoplaced = value

    @property
    def passthrough(self) -> SchematicPassthroughMode.ValueType:
        return self._proto.passthrough

    @passthrough.setter
    def passthrough(self, value: SchematicPassthroughMode.ValueType):
        self._proto.passthrough = value

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the symbol instance"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class SheetInstance(Wrapper):
    """
    Data returned from e.g. GetSchematicHierarchy (read-only)

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SheetInstance | None = None,
        proto_ref: schematic_types_pb2.SheetInstance | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SheetInstance()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:

        def repr_child(c: SheetInstance, d: int):
            r = f"{'  ' * d}SheetInstance([{c.page_number}] {c.name} ({c.filename}))"

            if len(c.children) > 0:
                r += "\n"
                r += "\n".join([repr_child(child, d + 1) for child in c.children])

            return r

        if len(self.children) > 0:
            return repr_child(self, 0)

        return f"SheetInstance({self.name} [{self.page_number}] ({self.filename}))"

    @property
    def path(self) -> SheetPath:
        return SheetPath(proto_ref=self._proto.path)

    @property
    def name(self) -> str:
        return self._proto.name

    @property
    def filename(self) -> str:
        return self._proto.filename

    @property
    def page_number(self) -> str:
        return self._proto.page_number

    @property
    def children(self) -> Sequence[SheetInstance]:
        return MutableWrapperSequence(self._proto.children, SheetInstance)


class SchematicHierarchy:
    """The sheet hierarchy of a schematic, returned from
    :meth:`kipy.schematic.Schematic.get_hierarchy`.

    :attr:`root` provides the first top-level sheet of the schematic, and
    iterating the hierarchy yields every sheet depth-first, beginning with the root.

    .. versionadded:: 0.x.y (KiCad 11)"""

    def __init__(self, top_level_sheets: Sequence[SheetInstance]):
        self._top_level_sheets = list(top_level_sheets)

    @property
    def root(self) -> SheetInstance:
        """The root sheet of the schematic"""
        return self._top_level_sheets[0]

    @property
    def top_level_sheets(self) -> Sequence[SheetInstance]:
        """All top-level sheets of the schematic.  This is the root sheet, plus any
        additional sheets in multi-root hierarchies."""
        return self._top_level_sheets

    def __iter__(self):
        def walk(sheet: SheetInstance):
            yield sheet
            for child in sheet.children:
                yield from walk(child)

        for sheet in self._top_level_sheets:
            yield from walk(sheet)

    def __repr__(self) -> str:
        return f"SchematicHierarchy({self._top_level_sheets})"


class SchematicNetSheetContents(Wrapper):
    """
    Data returned from GetSchematicNetlist (read-only)

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicNetSheetContents | None = None,
        proto_ref: schematic_types_pb2.SchematicNetSheetContents | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicNetSheetContents()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"SchematicNetSheetContents({self.path}, {len(self.items)} items)"

    @property
    def path(self) -> SheetPath:
        return SheetPath(proto_ref=self._proto.path)

    @property
    def items(self) -> list[KIID]:
        return list(self._proto.items)


class SchematicNet(Wrapper):
    """
    Data returned from e.g. GetSchematicNetlist (read-only)

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicNet | None = None,
        proto_ref: schematic_types_pb2.SchematicNet | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SchematicNet()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:

        def repr_sheet(s: SchematicNetSheetContents, d: int):
            return f"{'  ' * d}{s.path} ({len(s.items)} items)"

        r = f"SchematicNet({self.name})"

        if len(self.sheets) > 0:
            r += "\n"
            r += "\n".join([repr_sheet(sheet, 1) for sheet in self.sheets])

        return r

    @property
    def name(self) -> str:
        return self._proto.name

    @property
    def sheets(self) -> Sequence[SchematicNetSheetContents]:
        return MutableWrapperSequence(self._proto.sheets, SchematicNetSheetContents)


class SheetVariant(Wrapper):
    """One sheet variant and its per-variant field values"""

    def __init__(
        self,
        proto: schematic_types_pb2.SheetVariant | None = None,
        proto_ref: schematic_types_pb2.SheetVariant | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SheetVariant()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

    @property
    def description(self) -> str | None:
        if self._proto.HasField("description"):
            return self._proto.description
        return None

    @description.setter
    def description(self, value: str | None):
        if value is not None:
            self._proto.description = value
        else:
            self._proto.ClearField("description")

    @property
    def exclude_from_sim(self) -> bool | None:
        if self._proto.HasField("exclude_from_sim"):
            return self._proto.exclude_from_sim
        return None

    @exclude_from_sim.setter
    def exclude_from_sim(self, value: bool | None):
        if value is not None:
            self._proto.exclude_from_sim = value
        else:
            self._proto.ClearField("exclude_from_sim")

    @property
    def exclude_from_bom(self) -> bool | None:
        if self._proto.HasField("exclude_from_bom"):
            return self._proto.exclude_from_bom
        return None

    @exclude_from_bom.setter
    def exclude_from_bom(self, value: bool | None):
        if value is not None:
            self._proto.exclude_from_bom = value
        else:
            self._proto.ClearField("exclude_from_bom")

    @property
    def dnp(self) -> bool | None:
        if self._proto.HasField("dnp"):
            return self._proto.dnp
        return None

    @dnp.setter
    def dnp(self, value: bool | None):
        if value is not None:
            self._proto.dnp = value
        else:
            self._proto.ClearField("dnp")

    @property
    def fields(self) -> dict[str, str]:
        """Per-variant overrides of field values, keyed by field name"""
        return dict(self._proto.fields)

    @fields.setter
    def fields(self, value: dict[str, str]):
        self._proto.fields.clear()
        self._proto.fields.update(value)


class SheetVariants(Wrapper):
    def __init__(
        self,
        proto: schematic_types_pb2.SheetVariants | None = None,
        proto_ref: schematic_types_pb2.SheetVariants | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SheetVariants()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def variants(self) -> Sequence[SheetVariant]:
        return MutableWrapperSequence(self._proto.variants, SheetVariant)

    @variants.setter
    def variants(self, value: Sequence[SheetVariant]):
        del self._proto.variants[:]
        self._proto.variants.extend(variant.proto for variant in value)


class SchematicRuleArea(SchematicItem):
    def __init__(
        self,
        proto: schematic_types_pb2.SchematicRuleArea | None = None,
        proto_ref: schematic_types_pb2.SchematicRuleArea | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicRuleArea()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"SchematicRuleArea(shape={self.shape}, dnp={self.dnp})"

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
    def shape(self) -> GraphicShape | None:
        """The rule area outline (only polygons are supported by KiCad)"""
        return to_concrete_shape(GraphicShape(self._proto.shape))

    @shape.setter
    def shape(self, value: GraphicShape):
        """Sets the rule area outline shape.  Polygon outlines are forced closed
        regardless of the source polygon's :class:`kipy.geometry.PolygonWithHoles`
        ``auto_close`` flag; KiCad requires rule areas to be closed polygons."""
        if value.proto.WhichOneof("geometry") != "polygon":
            raise ValueError("SchematicRuleArea shape must be a polygon")

        proto = base_types_pb2.GraphicShape()
        proto.CopyFrom(value.proto)

        for polygon in proto.polygon.polygons:
            polygon.outline.closed = True

        self._proto.shape.CopyFrom(proto)

    @property
    def exclude_from_sim(self) -> bool:
        return self._proto.exclude_from_sim

    @exclude_from_sim.setter
    def exclude_from_sim(self, value: bool):
        self._proto.exclude_from_sim = value

    @property
    def exclude_from_bom(self) -> bool:
        return self._proto.exclude_from_bom

    @exclude_from_bom.setter
    def exclude_from_bom(self, value: bool):
        self._proto.exclude_from_bom = value

    @property
    def exclude_from_board(self) -> bool:
        return self._proto.exclude_from_board

    @exclude_from_board.setter
    def exclude_from_board(self, value: bool):
        self._proto.exclude_from_board = value

    @property
    def dnp(self) -> bool:
        return self._proto.dnp

    @dnp.setter
    def dnp(self, value: bool):
        self._proto.dnp = value

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the rule area"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class SchematicTableCell(Wrapper):
    """A single cell of a schematic table"""

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicTableCell | None = None,
        proto_ref: schematic_types_pb2.SchematicTableCell | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_types_pb2.SchematicTableCell()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"SchematicTableCell(text={self.text_box.value!r}, "
            f"spans=({self.row_span}, {self.column_span}))"
        )

    @property
    def text_box(self) -> SchematicTextBox:
        return SchematicTextBox(proto_ref=self._proto.text_box)

    @text_box.setter
    def text_box(self, value: SchematicTextBox):
        self._proto.text_box.CopyFrom(value.proto)

    @property
    def column_span(self) -> int:
        return self._proto.column_span

    @column_span.setter
    def column_span(self, value: int):
        self._proto.column_span = value

    @property
    def row_span(self) -> int:
        return self._proto.row_span

    @row_span.setter
    def row_span(self, value: int):
        self._proto.row_span = value

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the cell"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


class SchematicTable(SchematicItem):
    """A table in a schematic"""

    def __init__(
        self,
        proto: schematic_types_pb2.SchematicTable | None = None,
        proto_ref: schematic_types_pb2.SchematicTable | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_types_pb2.SchematicTable()

        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"SchematicTable(cells={len(self.cells)}, columns={self.column_count})"

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
    def column_count(self) -> int:
        return self._proto.column_count

    @column_count.setter
    def column_count(self, value: int):
        self._proto.column_count = value

    @property
    def column_widths(self) -> Sequence[int]:
        return [width.value_nm for width in self._proto.column_widths]

    @column_widths.setter
    def column_widths(self, value: Sequence[int]):
        del self._proto.column_widths[:]
        for width in value:
            self._proto.column_widths.add().value_nm = width

    @property
    def row_heights(self) -> Sequence[int]:
        return [height.value_nm for height in self._proto.row_heights]

    @row_heights.setter
    def row_heights(self, value: Sequence[int]):
        del self._proto.row_heights[:]
        for height in value:
            self._proto.row_heights.add().value_nm = height

    @property
    def cells(self) -> Sequence[SchematicTableCell]:
        return MutableWrapperSequence(self._proto.cells, SchematicTableCell)

    @cells.setter
    def cells(self, value: Sequence[SchematicTableCell]):
        del self._proto.cells[:]
        self._proto.cells.extend(cell.proto for cell in value)

    @property
    def external_border(self) -> TableStrokeMode.ValueType:
        return self._proto.external_border

    @external_border.setter
    def external_border(self, value: TableStrokeMode.ValueType):
        self._proto.external_border = value

    @property
    def header_separator(self) -> TableStrokeMode.ValueType:
        return self._proto.header_separator

    @header_separator.setter
    def header_separator(self, value: TableStrokeMode.ValueType):
        self._proto.header_separator = value

    @property
    def row_separators(self) -> TableStrokeMode.ValueType:
        return self._proto.row_separators

    @row_separators.setter
    def row_separators(self, value: TableStrokeMode.ValueType):
        self._proto.row_separators = value

    @property
    def column_separators(self) -> TableStrokeMode.ValueType:
        return self._proto.column_separators

    @column_separators.setter
    def column_separators(self, value: TableStrokeMode.ValueType):
        self._proto.column_separators = value

    @property
    def border_stroke(self) -> StrokeAttributes:
        return StrokeAttributes(proto_ref=self._proto.border_stroke)

    @border_stroke.setter
    def border_stroke(self, value: StrokeAttributes):
        self._proto.border_stroke.CopyFrom(value.proto)

    @property
    def separators_stroke(self) -> StrokeAttributes:
        return StrokeAttributes(proto_ref=self._proto.separators_stroke)

    @separators_stroke.setter
    def separators_stroke(self, value: StrokeAttributes):
        self._proto.separators_stroke.CopyFrom(value.proto)

    @property
    def custom_properties(self) -> Sequence[CustomProperty]:
        """User-defined properties attached to the table"""
        return MutableWrapperSequence(self._proto.custom_properties, CustomProperty)

    @custom_properties.setter
    def custom_properties(self, value: Sequence[CustomProperty]):
        del self._proto.custom_properties[:]
        self._proto.custom_properties.extend(prop.proto for prop in value)


_proto_to_object: dict[type[Message], type[Wrapper]] = {
    schematic_types_pb2.SchematicField: SchematicField,
    schematic_types_pb2.SchematicLine: SchematicLine,
    schematic_types_pb2.Junction: Junction,
    schematic_types_pb2.NoConnectMarker: NoConnectMarker,
    schematic_types_pb2.BusEntry: BusEntry,
    schematic_types_pb2.SchematicText: SchematicText,
    schematic_types_pb2.SchematicTextBox: SchematicTextBox,
    schematic_types_pb2.SchematicGraphicShape: SchematicGraphicShape,
    schematic_types_pb2.SchematicImage: SchematicImage,
    schematic_types_pb2.LocalLabel: LocalLabel,
    schematic_types_pb2.GlobalLabel: GlobalLabel,
    schematic_types_pb2.HierarchicalLabel: HierarchicalLabel,
    schematic_types_pb2.DirectiveLabel: DirectiveLabel,
    schematic_types_pb2.Group: Group,
    schematic_types_pb2.SheetPin: SheetPin,
    schematic_types_pb2.SheetSymbol: SheetSymbol,
    schematic_types_pb2.SchematicPin: SchematicPin,
    schematic_types_pb2.SchematicSymbol: SchematicSymbol,
    schematic_types_pb2.SchematicSymbolInstance: SchematicSymbolInstance,
    schematic_types_pb2.SchematicRuleArea: SchematicRuleArea,
    schematic_types_pb2.SchematicTable: SchematicTable,
}


def unwrap(message: Any) -> Wrapper:
    concrete = unpack_any(message)
    wrapper = _proto_to_object.get(type(concrete), None)
    assert wrapper is not None
    return wrapper(proto=concrete)
