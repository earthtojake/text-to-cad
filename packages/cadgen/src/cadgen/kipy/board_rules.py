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
from collections.abc import Sequence

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

from cadgen.kipy.proto.board import board_commands_pb2, board_rules_pb2, board_types_pb2
from cadgen.kipy.proto.board.board_rules_pb2 import (  # noqa
    CustomRuleConstraintType,
    CustomRuleDisallowType,
    CustomRuleLayerMode,
    DrcErrorType,
)
from cadgen.kipy.proto.common.types import base_types_pb2
from cadgen.kipy.proto.common.types.base_types_pb2 import MinOptMax, RuleSeverity  # noqa
from cadgen.kipy.wrapper import Wrapper


class MinimumConstraints(Wrapper):
    """Board-level minimum design rules"""

    def __init__(
        self,
        proto: board_rules_pb2.MinimumConstraints | None = None,
        proto_ref: board_rules_pb2.MinimumConstraints | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_rules_pb2.MinimumConstraints()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def min_clearance(self) -> int:
        return self._proto.min_clearance.value_nm

    @min_clearance.setter
    def min_clearance(self, value: int):
        self._proto.min_clearance.value_nm = value

    @property
    def min_groove_width(self) -> int:
        return self._proto.min_groove_width.value_nm

    @min_groove_width.setter
    def min_groove_width(self, value: int):
        self._proto.min_groove_width.value_nm = value

    @property
    def min_connection_width(self) -> int:
        return self._proto.min_connection_width.value_nm

    @min_connection_width.setter
    def min_connection_width(self, value: int):
        self._proto.min_connection_width.value_nm = value

    @property
    def min_track_width(self) -> int:
        return self._proto.min_track_width.value_nm

    @min_track_width.setter
    def min_track_width(self, value: int):
        self._proto.min_track_width.value_nm = value

    @property
    def min_via_annular_width(self) -> int:
        return self._proto.min_via_annular_width.value_nm

    @min_via_annular_width.setter
    def min_via_annular_width(self, value: int):
        self._proto.min_via_annular_width.value_nm = value

    @property
    def min_via_size(self) -> int:
        return self._proto.min_via_size.value_nm

    @min_via_size.setter
    def min_via_size(self, value: int):
        self._proto.min_via_size.value_nm = value

    @property
    def min_through_drill(self) -> int:
        return self._proto.min_through_drill.value_nm

    @min_through_drill.setter
    def min_through_drill(self, value: int):
        self._proto.min_through_drill.value_nm = value

    @property
    def min_microvia_size(self) -> int:
        return self._proto.min_microvia_size.value_nm

    @min_microvia_size.setter
    def min_microvia_size(self, value: int):
        self._proto.min_microvia_size.value_nm = value

    @property
    def min_microvia_drill(self) -> int:
        return self._proto.min_microvia_drill.value_nm

    @min_microvia_drill.setter
    def min_microvia_drill(self, value: int):
        self._proto.min_microvia_drill.value_nm = value

    @property
    def copper_edge_clearance(self) -> int:
        return self._proto.copper_edge_clearance.value_nm

    @copper_edge_clearance.setter
    def copper_edge_clearance(self, value: int):
        self._proto.copper_edge_clearance.value_nm = value

    @property
    def hole_clearance(self) -> int:
        return self._proto.hole_clearance.value_nm

    @hole_clearance.setter
    def hole_clearance(self, value: int):
        self._proto.hole_clearance.value_nm = value

    @property
    def hole_to_hole_min(self) -> int:
        return self._proto.hole_to_hole_min.value_nm

    @hole_to_hole_min.setter
    def hole_to_hole_min(self, value: int):
        self._proto.hole_to_hole_min.value_nm = value

    @property
    def silk_clearance(self) -> int:
        return self._proto.silk_clearance.value_nm

    @silk_clearance.setter
    def silk_clearance(self, value: int):
        self._proto.silk_clearance.value_nm = value

    @property
    def min_resolved_spokes(self) -> int:
        return self._proto.min_resolved_spokes

    @min_resolved_spokes.setter
    def min_resolved_spokes(self, value: int):
        self._proto.min_resolved_spokes = value

    @property
    def min_silk_text_height(self) -> int:
        return self._proto.min_silk_text_height.value_nm

    @min_silk_text_height.setter
    def min_silk_text_height(self, value: int):
        self._proto.min_silk_text_height.value_nm = value

    @property
    def min_silk_text_thickness(self) -> int:
        return self._proto.min_silk_text_thickness.value_nm

    @min_silk_text_thickness.setter
    def min_silk_text_thickness(self, value: int):
        self._proto.min_silk_text_thickness.value_nm = value


class PresetTrackWidth(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.PresetTrackWidth | None = None,
        proto_ref: board_rules_pb2.PresetTrackWidth | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_rules_pb2.PresetTrackWidth()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @classmethod
    def from_width(cls, width: int) -> Self:
        n = cls()
        n.width = width
        return n

    @property
    def width(self) -> int:
        return self._proto.width.value_nm

    @width.setter
    def width(self, value: int):
        self._proto.width.value_nm = value


class PresetViaDimension(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.PresetViaDimension | None = None,
        proto_ref: board_rules_pb2.PresetViaDimension | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_rules_pb2.PresetViaDimension()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def diameter(self) -> int:
        return self._proto.diameter.value_nm

    @diameter.setter
    def diameter(self, value: int):
        self._proto.diameter.value_nm = value

    @property
    def drill(self) -> int:
        return self._proto.drill.value_nm

    @drill.setter
    def drill(self, value: int):
        self._proto.drill.value_nm = value


class PresetDiffPairDimension(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.PresetDiffPairDimension | None = None,
        proto_ref: board_rules_pb2.PresetDiffPairDimension | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_rules_pb2.PresetDiffPairDimension()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def width(self) -> int:
        return self._proto.width.value_nm

    @width.setter
    def width(self, value: int):
        self._proto.width.value_nm = value

    @property
    def gap(self) -> int:
        return self._proto.gap.value_nm

    @gap.setter
    def gap(self, value: int):
        self._proto.gap.value_nm = value

    @property
    def via_gap(self) -> int:
        return self._proto.via_gap.value_nm

    @via_gap.setter
    def via_gap(self, value: int):
        self._proto.via_gap.value_nm = value


class PredefinedSizes(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.PredefinedSizes | None = None,
        proto_ref: board_rules_pb2.PredefinedSizes | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_rules_pb2.PredefinedSizes()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def tracks(self) -> list[PresetTrackWidth]:
        if "_tracks" not in self.__dict__:
            self._tracks = [PresetTrackWidth(track) for track in self._proto.tracks]
        return self._tracks

    @tracks.setter
    def tracks(self, value: Sequence[PresetTrackWidth]):
        self._tracks = list(value)

    @property
    def vias(self) -> list[PresetViaDimension]:
        if "_vias" not in self.__dict__:
            self._vias = [PresetViaDimension(via) for via in self._proto.vias]
        return self._vias

    @vias.setter
    def vias(self, value: Sequence[PresetViaDimension]):
        self._vias = list(value)

    @property
    def diff_pairs(self) -> list[PresetDiffPairDimension]:
        if "_diff_pairs" not in self.__dict__:
            self._diff_pairs = [PresetDiffPairDimension(pair) for pair in self._proto.diff_pairs]
        return self._diff_pairs

    @diff_pairs.setter
    def diff_pairs(self, value: Sequence[PresetDiffPairDimension]):
        self._diff_pairs = list(value)

    def _pack(self):
        if "_tracks" in self.__dict__:
            del self._proto.tracks[:]
            self._proto.tracks.extend(track.proto for track in self._tracks)

        if "_vias" in self.__dict__:
            del self._proto.vias[:]
            self._proto.vias.extend(via.proto for via in self._vias)

        if "_diff_pairs" in self.__dict__:
            del self._proto.diff_pairs[:]
            self._proto.diff_pairs.extend(pair.proto for pair in self._diff_pairs)


class SolderMaskPasteDefaults(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.SolderMaskPasteDefaults | None = None,
        proto_ref: board_rules_pb2.SolderMaskPasteDefaults | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_rules_pb2.SolderMaskPasteDefaults()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def mask_expansion(self) -> int:
        return self._proto.mask_expansion.value_nm

    @mask_expansion.setter
    def mask_expansion(self, value: int):
        self._proto.mask_expansion.value_nm = value

    @property
    def mask_min_width(self) -> int:
        return self._proto.mask_min_width.value_nm

    @mask_min_width.setter
    def mask_min_width(self, value: int):
        self._proto.mask_min_width.value_nm = value

    @property
    def mask_to_copper_clearance(self) -> int:
        return self._proto.mask_to_copper_clearance.value_nm

    @mask_to_copper_clearance.setter
    def mask_to_copper_clearance(self, value: int):
        self._proto.mask_to_copper_clearance.value_nm = value

    @property
    def paste_margin(self) -> int:
        return self._proto.paste_margin.value_nm

    @paste_margin.setter
    def paste_margin(self, value: int):
        self._proto.paste_margin.value_nm = value

    @property
    def paste_margin_ratio(self) -> float:
        return self._proto.paste_margin_ratio

    @paste_margin_ratio.setter
    def paste_margin_ratio(self, value: float):
        self._proto.paste_margin_ratio = value

    @property
    def allow_soldermask_bridges_in_footprints(self) -> bool:
        return self._proto.allow_soldermask_bridges_in_footprints

    @allow_soldermask_bridges_in_footprints.setter
    def allow_soldermask_bridges_in_footprints(self, value: bool):
        self._proto.allow_soldermask_bridges_in_footprints = value


class TeardropTargetParams(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.TeardropTargetParams | None = None,
        proto_ref: board_rules_pb2.TeardropTargetParams | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_rules_pb2.TeardropTargetParams()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def enabled(self) -> bool:
        return self._proto.enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._proto.enabled = value

    @property
    def max_length(self) -> int:
        return self._proto.max_length.value_nm

    @max_length.setter
    def max_length(self, value: int):
        self._proto.max_length.value_nm = value

    @property
    def max_width(self) -> int:
        return self._proto.max_width.value_nm

    @max_width.setter
    def max_width(self, value: int):
        self._proto.max_width.value_nm = value

    @property
    def best_length_ratio(self) -> float:
        return self._proto.best_length_ratio

    @best_length_ratio.setter
    def best_length_ratio(self, value: float):
        self._proto.best_length_ratio = value

    @property
    def best_width_ratio(self) -> float:
        return self._proto.best_width_ratio

    @best_width_ratio.setter
    def best_width_ratio(self, value: float):
        self._proto.best_width_ratio = value

    @property
    def width_to_size_filter_ratio(self) -> float:
        return self._proto.width_to_size_filter_ratio

    @width_to_size_filter_ratio.setter
    def width_to_size_filter_ratio(self, value: float):
        self._proto.width_to_size_filter_ratio = value

    @property
    def curved_edges(self) -> bool:
        return self._proto.curved_edges

    @curved_edges.setter
    def curved_edges(self, value: bool):
        self._proto.curved_edges = value

    @property
    def allow_two_tracks(self) -> bool:
        return self._proto.allow_two_tracks

    @allow_two_tracks.setter
    def allow_two_tracks(self, value: bool):
        self._proto.allow_two_tracks = value

    @property
    def on_pads_in_zones(self) -> bool:
        return self._proto.on_pads_in_zones

    @on_pads_in_zones.setter
    def on_pads_in_zones(self, value: bool):
        self._proto.on_pads_in_zones = value


class TeardropTargetEntry(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.TeardropTargetEntry | None = None,
        proto_ref: board_rules_pb2.TeardropTargetEntry | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_rules_pb2.TeardropTargetEntry()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def target(self) -> board_rules_pb2.TeardropTarget.ValueType:
        return self._proto.target

    @target.setter
    def target(self, value: board_rules_pb2.TeardropTarget.ValueType):
        self._proto.target = value

    @property
    def params(self) -> TeardropTargetParams:
        return TeardropTargetParams(proto_ref=self._proto.params)

    @params.setter
    def params(self, value: TeardropTargetParams):
        self._proto.params.CopyFrom(value.proto)


class TeardropDefaults(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.TeardropDefaults | None = None,
        proto_ref: board_rules_pb2.TeardropDefaults | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_rules_pb2.TeardropDefaults()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def target_vias(self) -> bool:
        return self._proto.target_vias

    @target_vias.setter
    def target_vias(self, value: bool):
        self._proto.target_vias = value

    @property
    def target_pth_pads(self) -> bool:
        return self._proto.target_pth_pads

    @target_pth_pads.setter
    def target_pth_pads(self, value: bool):
        self._proto.target_pth_pads = value

    @property
    def target_smd_pads(self) -> bool:
        return self._proto.target_smd_pads

    @target_smd_pads.setter
    def target_smd_pads(self, value: bool):
        self._proto.target_smd_pads = value

    @property
    def target_track_to_track(self) -> bool:
        return self._proto.target_track_to_track

    @target_track_to_track.setter
    def target_track_to_track(self, value: bool):
        self._proto.target_track_to_track = value

    @property
    def use_round_shapes_only(self) -> bool:
        return self._proto.use_round_shapes_only

    @use_round_shapes_only.setter
    def use_round_shapes_only(self, value: bool):
        self._proto.use_round_shapes_only = value

    @property
    def target_params(self) -> list[TeardropTargetEntry]:
        if "_target_params" not in self.__dict__:
            self._target_params = [
                TeardropTargetEntry(param) for param in self._proto.target_params
            ]
        return self._target_params

    @target_params.setter
    def target_params(self, value: Sequence[TeardropTargetEntry]):
        self._target_params = list(value)

    def _pack(self):
        if "_target_params" in self.__dict__:
            del self._proto.target_params[:]
            self._proto.target_params.extend(param.proto for param in self._target_params)


class ViaProtectionDefaults(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.ViaProtectionDefaults | None = None,
        proto_ref: board_rules_pb2.ViaProtectionDefaults | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_rules_pb2.ViaProtectionDefaults()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def tent_front(self) -> bool:
        return self._proto.tent_front

    @tent_front.setter
    def tent_front(self, value: bool):
        self._proto.tent_front = value

    @property
    def tent_back(self) -> bool:
        return self._proto.tent_back

    @tent_back.setter
    def tent_back(self, value: bool):
        self._proto.tent_back = value

    @property
    def cover_front(self) -> bool:
        return self._proto.cover_front

    @cover_front.setter
    def cover_front(self, value: bool):
        self._proto.cover_front = value

    @property
    def cover_back(self) -> bool:
        return self._proto.cover_back

    @cover_back.setter
    def cover_back(self, value: bool):
        self._proto.cover_back = value

    @property
    def plug_front(self) -> bool:
        return self._proto.plug_front

    @plug_front.setter
    def plug_front(self, value: bool):
        self._proto.plug_front = value

    @property
    def plug_back(self) -> bool:
        return self._proto.plug_back

    @plug_back.setter
    def plug_back(self, value: bool):
        self._proto.plug_back = value

    @property
    def cap(self) -> bool:
        return self._proto.cap

    @cap.setter
    def cap(self, value: bool):
        self._proto.cap = value

    @property
    def fill(self) -> bool:
        return self._proto.fill

    @fill.setter
    def fill(self, value: bool):
        self._proto.fill = value


class DrcSeveritySetting(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.DrcSeveritySetting | None = None,
        proto_ref: board_rules_pb2.DrcSeveritySetting | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_rules_pb2.DrcSeveritySetting()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def rule_type(self) -> board_rules_pb2.DrcErrorType.ValueType:
        return self._proto.rule_type

    @rule_type.setter
    def rule_type(self, value: board_rules_pb2.DrcErrorType.ValueType):
        self._proto.rule_type = value

    @property
    def severity(self) -> base_types_pb2.RuleSeverity.ValueType:
        return self._proto.severity

    @severity.setter
    def severity(self, value: base_types_pb2.RuleSeverity.ValueType):
        self._proto.severity = value


class DrcExclusion(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.DrcExclusion | None = None,
        proto_ref: board_rules_pb2.DrcExclusion | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_rules_pb2.DrcExclusion()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def marker(self) -> board_rules_pb2.DrcMarker:
        return self._proto.marker

    @marker.setter
    def marker(self, value: board_rules_pb2.DrcMarker):
        self._proto.marker.CopyFrom(value)

    @property
    def comment(self) -> str:
        return self._proto.comment

    @comment.setter
    def comment(self, value: str):
        self._proto.comment = value


class BoardDesignRules(Wrapper):
    """The base board design and netclass rules (not including custom rules)"""

    def __init__(
        self,
        proto: board_rules_pb2.BoardDesignRules | None = None,
        proto_ref: board_rules_pb2.BoardDesignRules | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_rules_pb2.BoardDesignRules()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def constraints(self) -> MinimumConstraints:
        return MinimumConstraints(proto_ref=self._proto.constraints)

    @constraints.setter
    def constraints(self, value: MinimumConstraints):
        self._proto.constraints.CopyFrom(value.proto)

    @property
    def predefined_sizes(self) -> PredefinedSizes:
        if "_predefined_sizes" not in self.__dict__:
            self._predefined_sizes = PredefinedSizes(proto_ref=self._proto.predefined_sizes)
        return self._predefined_sizes

    @predefined_sizes.setter
    def predefined_sizes(self, value: PredefinedSizes):
        self._predefined_sizes = value

    @property
    def solder_mask_paste(self) -> SolderMaskPasteDefaults:
        return SolderMaskPasteDefaults(proto_ref=self._proto.solder_mask_paste)

    @solder_mask_paste.setter
    def solder_mask_paste(self, value: SolderMaskPasteDefaults):
        self._proto.solder_mask_paste.CopyFrom(value.proto)

    @property
    def teardrops(self) -> TeardropDefaults:
        if "_teardrops" not in self.__dict__:
            self._teardrops = TeardropDefaults(proto_ref=self._proto.teardrops)
        return self._teardrops

    @teardrops.setter
    def teardrops(self, value: TeardropDefaults):
        self._teardrops = value

    @property
    def via_protection(self) -> ViaProtectionDefaults:
        return ViaProtectionDefaults(proto_ref=self._proto.via_protection)

    @via_protection.setter
    def via_protection(self, value: ViaProtectionDefaults):
        self._proto.via_protection.CopyFrom(value.proto)

    @property
    def severities(
        self,
    ) -> dict[board_rules_pb2.DrcErrorType.ValueType, base_types_pb2.RuleSeverity.ValueType]:
        if "_severities" not in self.__dict__:
            self._severities = {
                severity.rule_type: severity.severity for severity in self._proto.severities
            }
        return self._severities

    @severities.setter
    def severities(
        self,
        value: dict[board_rules_pb2.DrcErrorType.ValueType, base_types_pb2.RuleSeverity.ValueType],
    ):
        self._severities = dict(value)

    @property
    def exclusions(self) -> list[DrcExclusion]:
        if "_exclusions" not in self.__dict__:
            self._exclusions = [DrcExclusion(exclusion) for exclusion in self._proto.exclusions]
        return self._exclusions

    @exclusions.setter
    def exclusions(self, value: Sequence[DrcExclusion]):
        self._exclusions = list(value)

    def _pack(self):
        if "_predefined_sizes" in self.__dict__:
            self._proto.predefined_sizes.CopyFrom(self._predefined_sizes.proto)

        if "_teardrops" in self.__dict__:
            self._proto.teardrops.CopyFrom(self._teardrops.proto)

        if "_severities" in self.__dict__:
            del self._proto.severities[:]
            for rule_type, severity in self._severities.items():
                setting = self._proto.severities.add()
                setting.rule_type = rule_type
                setting.severity = severity

        if "_exclusions" in self.__dict__:
            del self._proto.exclusions[:]
            self._proto.exclusions.extend(exclusion.proto for exclusion in self._exclusions)


class CustomRuleDisallowSettings(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.CustomRuleDisallowSettings | None = None,
        proto_ref: board_rules_pb2.CustomRuleDisallowSettings | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_rules_pb2.CustomRuleDisallowSettings()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def types(self) -> list[board_rules_pb2.CustomRuleDisallowType.ValueType]:
        if "_types" not in self.__dict__:
            self._types = list(self._proto.types)
        return self._types

    @types.setter
    def types(self, value: Sequence[board_rules_pb2.CustomRuleDisallowType.ValueType]):
        self._types = list(value)

    def _pack(self):
        if "_types" in self.__dict__:
            del self._proto.types[:]
            self._proto.types.extend(self._types)


class CustomRuleConstraint(Wrapper):
    """Represents a (constraint ...) clause in a custom rule"""

    def __init__(
        self,
        proto: board_rules_pb2.CustomRuleConstraint | None = None,
        proto_ref: board_rules_pb2.CustomRuleConstraint | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_rules_pb2.CustomRuleConstraint()
        )

        if proto is not None:
            self._proto.CopyFrom(proto)

    @classmethod
    def from_type(cls, type: board_rules_pb2.CustomRuleConstraintType.ValueType) -> Self:
        constraint = cls()
        constraint.type = type
        return constraint

    @property
    def type(self) -> board_rules_pb2.CustomRuleConstraintType.ValueType:
        return self._proto.type

    @type.setter
    def type(self, value: board_rules_pb2.CustomRuleConstraintType.ValueType):
        self._proto.type = value

    @property
    def name(self) -> str | None:
        if self._proto.HasField("name"):
            return self._proto.name
        return None

    @name.setter
    def name(self, value: str | None):
        if value is None:
            self._proto.ClearField("name")
        else:
            self._proto.name = value

    @property
    def numeric(self) -> base_types_pb2.MinOptMax | None:
        """nanometers, picoseconds, or unitless depending on constraint type"""
        if self._proto.WhichOneof("value") == "numeric":
            return self._proto.numeric
        return None

    @numeric.setter
    def numeric(self, value: base_types_pb2.MinOptMax | None):
        if value is None:
            if self._proto.WhichOneof("value") == "numeric":
                self._proto.ClearField("numeric")
        else:
            self._proto.numeric.CopyFrom(value)

    @property
    def disallow(self) -> CustomRuleDisallowSettings:
        if "_disallow" not in self.__dict__:
            if self._proto.WhichOneof("value") == "disallow":
                self._disallow = CustomRuleDisallowSettings(proto_ref=self._proto.disallow)
            elif self.type == board_rules_pb2.CustomRuleConstraintType.CRCT_DISALLOW:
                self._proto.disallow.SetInParent()
                self._disallow = CustomRuleDisallowSettings(proto_ref=self._proto.disallow)
            else:
                raise ValueError("disallow is only available for CRCT_DISALLOW constraints")

        return self._disallow

    @disallow.setter
    def disallow(self, value: CustomRuleDisallowSettings | None):
        if value is None:
            if self._proto.WhichOneof("value") == "disallow":
                self._proto.ClearField("disallow")
            if "_disallow" in self.__dict__:
                del self._disallow
        else:
            self._disallow = value

    @property
    def zone_connection(self) -> board_types_pb2.ZoneConnectionStyle.ValueType:
        if self._proto.WhichOneof("value") == "zone_connection":
            return self._proto.zone_connection

        if self.type == board_rules_pb2.CustomRuleConstraintType.CRCT_ZONE_CONNECTION:
            self._proto.zone_connection = board_types_pb2.ZoneConnectionStyle.ZCS_UNKNOWN
            return self._proto.zone_connection

        raise ValueError("zone_connection is only available for CRCT_ZONE_CONNECTION constraints")

    @zone_connection.setter
    def zone_connection(self, value: board_types_pb2.ZoneConnectionStyle.ValueType | None):
        if value is None:
            if self._proto.WhichOneof("value") == "zone_connection":
                self._proto.ClearField("zone_connection")
        else:
            self._proto.zone_connection = value

    @property
    def assertion_expression(self) -> str:
        if self._proto.WhichOneof("value") == "assertion_expression":
            return self._proto.assertion_expression

        if self.type == board_rules_pb2.CustomRuleConstraintType.CRCT_ASSERTION:
            self._proto.assertion_expression = ""
            return self._proto.assertion_expression

        raise ValueError("assertion_expression is only available for CRCT_ASSERTION constraints")

    @assertion_expression.setter
    def assertion_expression(self, value: str | None):
        if value is None:
            if self._proto.WhichOneof("value") == "assertion_expression":
                self._proto.ClearField("assertion_expression")
        else:
            self._proto.assertion_expression = value

    @property
    def options(self) -> list[board_rules_pb2.CustomRuleConstraintOption.ValueType]:
        if "_options" not in self.__dict__:
            self._options = list(self._proto.options)
        return self._options

    @options.setter
    def options(self, value: Sequence[board_rules_pb2.CustomRuleConstraintOption.ValueType]):
        self._options = list(value)

    def _pack(self):
        if "_disallow" in self.__dict__:
            self._proto.disallow.CopyFrom(self._disallow.proto)

        if "_options" in self.__dict__:
            del self._proto.options[:]
            self._proto.options.extend(self._options)


class CustomRule(Wrapper):
    def __init__(
        self,
        proto: board_rules_pb2.CustomRule | None = None,
        proto_ref: board_rules_pb2.CustomRule | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_rules_pb2.CustomRule()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def condition(self) -> str:
        return self._proto.condition

    @condition.setter
    def condition(self, value: str):
        self._proto.condition = value

    @property
    def constraints(self) -> list[CustomRuleConstraint]:
        if "_constraints" not in self.__dict__:
            self._constraints = [
                CustomRuleConstraint(constraint) for constraint in self._proto.constraints
            ]
        return self._constraints

    @constraints.setter
    def constraints(self, value: Sequence[CustomRuleConstraint]):
        self._constraints = list(value)

    def _pack(self):
        if "_constraints" in self.__dict__:
            del self._proto.constraints[:]
            self._proto.constraints.extend(constraint.proto for constraint in self._constraints)

    @property
    def single_layer(self) -> board_types_pb2.BoardLayer.ValueType | None:
        if self._proto.WhichOneof("layer_condition") == "single_layer":
            return self._proto.single_layer
        return None

    @single_layer.setter
    def single_layer(self, value: board_types_pb2.BoardLayer.ValueType | None):
        if value is None:
            if self._proto.WhichOneof("layer_condition") == "single_layer":
                self._proto.ClearField("single_layer")
        else:
            self._proto.single_layer = value

    @property
    def layer_mode(self) -> board_rules_pb2.CustomRuleLayerMode.ValueType | None:
        if self._proto.WhichOneof("layer_condition") == "layer_mode":
            return self._proto.layer_mode
        return None

    @layer_mode.setter
    def layer_mode(self, value: board_rules_pb2.CustomRuleLayerMode.ValueType | None):
        if value is None:
            if self._proto.WhichOneof("layer_condition") == "layer_mode":
                self._proto.ClearField("layer_mode")
        else:
            self._proto.layer_mode = value

    @property
    def severity(self) -> base_types_pb2.RuleSeverity.ValueType:
        return self._proto.severity

    @severity.setter
    def severity(self, value: base_types_pb2.RuleSeverity.ValueType):
        self._proto.severity = value

    @property
    def name(self) -> str:
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

    @property
    def comments(self) -> str | None:
        if self._proto.HasField("comments"):
            return self._proto.comments
        return None

    @comments.setter
    def comments(self, value: str | None):
        if value is None:
            self._proto.ClearField("comments")
        else:
            self._proto.comments = value


class BoardDesignRulesResponse(Wrapper):
    def __init__(self, proto: board_commands_pb2.BoardDesignRulesResponse | None = None):
        self._proto = board_commands_pb2.BoardDesignRulesResponse()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def rules(self) -> BoardDesignRules:
        return BoardDesignRules(proto_ref=self._proto.rules)

    @property
    def custom_rules_status(self) -> board_commands_pb2.CustomRulesStatus.ValueType:
        return self._proto.custom_rules_status


class CustomRulesResponse(Wrapper):
    def __init__(self, proto: board_commands_pb2.CustomRulesResponse | None = None):
        self._proto = board_commands_pb2.CustomRulesResponse()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def status(self) -> board_commands_pb2.CustomRulesStatus.ValueType:
        return self._proto.status

    @property
    def rules(self) -> list[CustomRule]:
        if "_rules" not in self.__dict__:
            self._rules = [CustomRule(rule) for rule in self._proto.rules]
        return self._rules

    @rules.setter
    def rules(self, value: Sequence[CustomRule]):
        self._rules = list(value)

    def _pack(self):
        if "_rules" in self.__dict__:
            del self._proto.rules[:]
            self._proto.rules.extend(rule.proto for rule in self._rules)

    @property
    def error_text(self) -> str:
        return self._proto.error_text
