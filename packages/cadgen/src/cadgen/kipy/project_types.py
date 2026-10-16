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

from collections.abc import Sequence

from cadgen.kipy.common_types import Color
from cadgen.kipy.proto.common.types import project_settings_pb2
from cadgen.kipy.wrapper import Wrapper


class NetClass(Wrapper):
    def __init__(self, proto: project_settings_pb2.NetClass | None):
        if not proto:
            proto = project_settings_pb2.NetClass()
        self._proto = proto

        if proto.type == project_settings_pb2.NetClassType.NCT_UNKNOWN:
            self._proto.type = project_settings_pb2.NetClassType.NCT_EXPLICIT

    def __repr__(self) -> str:
        return (
            f"NetClass(name={self.name!r}, priority={self.priority!r}, clearance={self.clearance!r}, "
            f"track_width={self.track_width!r}, diff_pair_track_width={self.diff_pair_track_width!r}, "
            f"diff_pair_gap={self.diff_pair_gap!r}, diff_pair_via_gap={self.diff_pair_via_gap!r}, "
            f"via_diameter={self.via_diameter!r}, via_drill={self.via_drill!r}, "
            f"microvia_diameter={self.microvia_diameter!r}, microvia_drill={self.microvia_drill!r}, "
            f"board_color={self.board_color!r}, wire_width={self.wire_width!r}, "
            f"bus_width={self.bus_width!r}, schematic_color={self.schematic_color!r})"
        )

    @property
    def name(self) -> str:
        """The name of the netclass (the literal string "Default" for the default netclass)
        May be empty for composite netclasses"""
        return self._proto.name

    @property
    def priority(self) -> int:
        return self._proto.priority

    @priority.setter
    def priority(self, priority: int):
        self._proto.priority = priority

    @property
    def type(self) -> project_settings_pb2.NetClassType.ValueType:
        """The type (explicit or implicit) of the net class.  This is a read-only property;
        net classes created through the API must always be explicit."""
        return self._proto.type

    @property
    def constituents(self) -> list[str] | None:
        if self.type == project_settings_pb2.NetClassType.NCT_EXPLICIT:
            return None
        return list(self._proto.constituents)

    @property
    def clearance(self) -> int | None:
        if self._proto.HasField("board") and self._proto.board.HasField("clearance"):
            return self._proto.board.clearance.value_nm
        return None

    @clearance.setter
    def clearance(self, clearance: int | None):
        if clearance is None:
            self._proto.board.ClearField("clearance")
        else:
            self._proto.board.clearance.value_nm = clearance

    @property
    def track_width(self) -> int | None:
        if self._proto.HasField("board") and self._proto.board.HasField("track_width"):
            return self._proto.board.track_width.value_nm
        return None

    @track_width.setter
    def track_width(self, width: int | None):
        if width is None:
            self._proto.board.ClearField("track_width")
        else:
            self._proto.board.track_width.value_nm = width

    @property
    def diff_pair_track_width(self) -> int | None:
        if self._proto.HasField("board") and self._proto.board.HasField("diff_pair_track_width"):
            return self._proto.board.diff_pair_track_width.value_nm
        return None

    @diff_pair_track_width.setter
    def diff_pair_track_width(self, width: int | None):
        if width is None:
            self._proto.board.ClearField("diff_pair_track_width")
        else:
            self._proto.board.diff_pair_track_width.value_nm = width

    @property
    def diff_pair_gap(self) -> int | None:
        if self._proto.HasField("board") and self._proto.board.HasField("diff_pair_gap"):
            return self._proto.board.diff_pair_gap.value_nm
        return None

    @diff_pair_gap.setter
    def diff_pair_gap(self, gap: int | None):
        if gap is None:
            self._proto.board.ClearField("diff_pair_gap")
        else:
            self._proto.board.diff_pair_gap.value_nm = gap

    @property
    def diff_pair_via_gap(self) -> int | None:
        if self._proto.HasField("board") and self._proto.board.HasField("diff_pair_via_gap"):
            return self._proto.board.diff_pair_via_gap.value_nm
        return None

    @diff_pair_via_gap.setter
    def diff_pair_via_gap(self, gap: int | None):
        if gap is None:
            self._proto.board.ClearField("diff_pair_via_gap")
        else:
            self._proto.board.diff_pair_via_gap.value_nm = gap

    @property
    def via_diameter(self) -> int | None:
        if (
            self._proto.board.HasField("via_stack")
            and len(self._proto.board.via_stack.copper_layers) > 0
        ):
            return self._proto.board.via_stack.copper_layers[0].size.x_nm
        return None

    @via_diameter.setter
    def via_diameter(self, diameter: int | None):
        if diameter is None:
            self._proto.board.via_stack.ClearField("copper_layers")
        else:
            self._proto.board.via_stack.copper_layers[0].size.x_nm = diameter

    @property
    def via_drill(self) -> int | None:
        if self._proto.board.HasField("via_stack") and self._proto.board.via_stack.HasField(
            "drill"
        ):
            return self._proto.board.via_stack.drill.diameter.x_nm
        return None

    @via_drill.setter
    def via_drill(self, diameter: int | None):
        if diameter is None:
            self._proto.board.via_stack.ClearField("drill")
        else:
            self._proto.board.via_stack.drill.diameter.x_nm = diameter

    @property
    def microvia_diameter(self) -> int | None:
        if self._proto.board.HasField("microvia_stack"):
            return self._proto.board.microvia_stack.copper_layers[0].size.x_nm
        return None

    @microvia_diameter.setter
    def microvia_diameter(self, diameter: int | None):
        if diameter is None:
            self._proto.board.ClearField("microvia_stack")
        else:
            self._proto.board.microvia_stack.copper_layers[0].size.x_nm = diameter

    @property
    def microvia_drill(self) -> int | None:
        if self._proto.board.HasField(
            "microvia_stack"
        ) and self._proto.board.microvia_stack.HasField("drill"):
            return self._proto.board.microvia_stack.drill.diameter.x_nm
        return None

    @microvia_drill.setter
    def microvia_drill(self, diameter: int | None):
        if diameter is None:
            self._proto.board.microvia_stack.ClearField("drill")
        else:
            self._proto.board.microvia_stack.drill.diameter.x_nm = diameter

    @property
    def board_color(self) -> Color | None:
        if self._proto.HasField("board") and self._proto.board.HasField("color"):
            return Color(self._proto.board.color)
        return None

    @board_color.setter
    def board_color(self, color: Color | None):
        if color is None:
            self._proto.board.ClearField("color")
        else:
            self._proto.board.color.CopyFrom(color.proto)

    @property
    def wire_width(self) -> int | None:
        if self._proto.HasField("schematic") and self._proto.schematic.HasField("wire_width"):
            return self._proto.schematic.wire_width.value_nm
        return None

    @wire_width.setter
    def wire_width(self, value: int | None):
        if value is None:
            self._proto.schematic.ClearField("wire_width")
        else:
            self._proto.schematic.wire_width.value_nm = value

    @property
    def bus_width(self) -> int | None:
        if self._proto.HasField("schematic") and self._proto.schematic.HasField("bus_width"):
            return self._proto.schematic.bus_width.value_nm
        return None

    @bus_width.setter
    def bus_width(self, value: int | None):
        if value is None:
            self._proto.schematic.ClearField("bus_width")
        else:
            self._proto.schematic.bus_width.value_nm = value

    @property
    def schematic_color(self) -> Color | None:
        if self._proto.HasField("schematic") and self._proto.schematic.HasField("color"):
            return Color(self._proto.schematic.color)
        return None

    @schematic_color.setter
    def schematic_color(self, color: Color | None):
        if color is None:
            self._proto.schematic.ClearField("color")
        else:
            self._proto.schematic.color.CopyFrom(color.proto)


class NetClassAssignment(Wrapper):
    """A direct assignment of a net to a netclass

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(self, proto: project_settings_pb2.NetClassAssignment | None = None):
        self._proto = proto if proto is not None else project_settings_pb2.NetClassAssignment()

    def __repr__(self) -> str:
        return f"NetClassAssignment(net={self.net!r}, netclasses={self.netclasses!r})"

    @property
    def net(self) -> str:
        """Full net path (e.g. "/sheet1/net1"). May refer to a net that does not exist yet."""
        return self._proto.net

    @net.setter
    def net(self, net: str):
        self._proto.net = net

    @property
    def netclasses(self) -> list[str]:
        """Names of netclasses assigned to the net.
        In ``MMM_MERGE`` mode, an empty list removes all assignments for this net."""
        return list(self._proto.netclasses)

    @netclasses.setter
    def netclasses(self, netclasses: list[str]):
        self._proto.netclasses[:] = netclasses


class NetClassPatternAssignment(Wrapper):
    """A pattern that assigns any matching nets to a netclass

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(self, proto: project_settings_pb2.NetClassPatternAssignment | None = None):
        self._proto = (
            proto if proto is not None else project_settings_pb2.NetClassPatternAssignment()
        )

    def __repr__(self) -> str:
        return f"NetClassPatternAssignment(pattern={self.pattern!r}, netclass={self.netclass!r})"

    @property
    def pattern(self) -> str:
        """Wildcard pattern matched against full net paths (e.g. "/power/*")."""
        return self._proto.pattern

    @pattern.setter
    def pattern(self, pattern: str):
        self._proto.pattern = pattern

    @property
    def netclass(self) -> str:
        """Name of the netclass assigned to matching nets.
        In ``MMM_MERGE`` mode, an empty string removes the pattern."""
        return self._proto.netclass

    @netclass.setter
    def netclass(self, netclass: str):
        self._proto.netclass = netclass


class NetClassAssignments:
    """A container for project netclass assignment settings (direct and pattern).

    Note that these are the explicit assignments configured in the KiCad schematic/board setup
    dialogs.  Users may also assign netclasses by placing directive labels in the schematic;
    these assignments will not be reflected in the data returned by
    :meth:`~kipy.project.Project.get_net_class_assignments`

    .. versionadded:: 0.x.0 (KiCad 11)"""

    def __init__(
        self,
        assignments: Sequence[NetClassAssignment] = (),
        pattern_assignments: Sequence[NetClassPatternAssignment] = (),
    ):
        self.assignments = list(assignments)
        self.pattern_assignments = list(pattern_assignments)

    def __repr__(self) -> str:
        return (
            f"NetClassAssignments(assignments={self.assignments!r}, "
            f"pattern_assignments={self.pattern_assignments!r})"
        )


class TextVariables(Wrapper):
    def __init__(self, proto: project_settings_pb2.TextVariables | None):
        if not proto:
            proto = project_settings_pb2.TextVariables()
        self._proto = proto

    @property
    def variables(self) -> dict:
        return dict(self._proto.variables)

    @variables.setter
    def variables(self, value: dict):
        self._proto.variables.clear()
        self._proto.variables.update(value)

    def __getitem__(self, key: str) -> str:
        return self._proto.variables[key]

    def __setitem__(self, key: str, value: str):
        self._proto.variables[key] = value

    def __delitem__(self, key: str):
        del self._proto.variables[key]

    def __contains__(self, key: str) -> bool:
        return key in self._proto.variables

    def __iter__(self):
        return iter(self._proto.variables)

    def __len__(self) -> int:
        return len(self._proto.variables)

    def keys(self):
        return self._proto.variables.keys()

    def values(self):
        return self._proto.variables.values()

    def items(self):
        return self._proto.variables.items()

    def __repr__(self) -> str:
        return f"TextVariables({self._proto.variables})"
