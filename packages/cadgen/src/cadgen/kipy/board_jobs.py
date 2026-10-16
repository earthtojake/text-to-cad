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

from cadgen.kipy.geometry import Vector2, Vector3D
from cadgen.kipy.proto.board import board_jobs_pb2, board_types_pb2
from cadgen.kipy.proto.common.types import enums_pb2
from cadgen.kipy.wrapper import Wrapper


class PlotSettings(Wrapper):
    """Shared settings for board plotting jobs"""

    def __init__(
        self,
        proto: board_jobs_pb2.BoardPlotSettings | None = None,
        proto_ref: board_jobs_pb2.BoardPlotSettings | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_jobs_pb2.BoardPlotSettings()
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def layers(self) -> list[board_types_pb2.BoardLayer.ValueType]:
        """The layers to plot.  Jobs will generally fail if no layers are specified."""
        return list(self._proto.layers)

    @layers.setter
    def layers(self, value: Sequence[board_types_pb2.BoardLayer.ValueType]):
        del self._proto.layers[:]
        self._proto.layers.extend(value)

    @property
    def common_layers(self) -> list[board_types_pb2.BoardLayer.ValueType]:
        return list(self._proto.common_layers)

    @common_layers.setter
    def common_layers(self, value: Sequence[board_types_pb2.BoardLayer.ValueType]):
        del self._proto.common_layers[:]
        self._proto.common_layers.extend(value)

    @property
    def color_theme(self) -> str:
        return self._proto.color_theme

    @color_theme.setter
    def color_theme(self, value: str):
        self._proto.color_theme = value

    @property
    def drawing_sheet(self) -> str:
        return self._proto.drawing_sheet

    @drawing_sheet.setter
    def drawing_sheet(self, value: str):
        self._proto.drawing_sheet = value

    @property
    def variant(self) -> str:
        return self._proto.variant

    @variant.setter
    def variant(self, value: str):
        self._proto.variant = value

    @property
    def mirror(self) -> bool:
        return self._proto.mirror

    @mirror.setter
    def mirror(self, value: bool):
        self._proto.mirror = value

    @property
    def black_and_white(self) -> bool:
        return self._proto.black_and_white

    @black_and_white.setter
    def black_and_white(self, value: bool):
        self._proto.black_and_white = value

    @property
    def negative(self) -> bool:
        return self._proto.negative

    @negative.setter
    def negative(self, value: bool):
        self._proto.negative = value

    @property
    def scale(self) -> float:
        return self._proto.scale

    @scale.setter
    def scale(self, value: float):
        self._proto.scale = value

    @property
    def sketch_pads_on_fab_layers(self) -> bool:
        return self._proto.sketch_pads_on_fab_layers

    @sketch_pads_on_fab_layers.setter
    def sketch_pads_on_fab_layers(self, value: bool):
        self._proto.sketch_pads_on_fab_layers = value

    @property
    def hide_dnp_footprints_on_fab_layers(self) -> bool:
        return self._proto.hide_dnp_footprints_on_fab_layers

    @hide_dnp_footprints_on_fab_layers.setter
    def hide_dnp_footprints_on_fab_layers(self, value: bool):
        self._proto.hide_dnp_footprints_on_fab_layers = value

    @property
    def sketch_dnp_footprints_on_fab_layers(self) -> bool:
        return self._proto.sketch_dnp_footprints_on_fab_layers

    @sketch_dnp_footprints_on_fab_layers.setter
    def sketch_dnp_footprints_on_fab_layers(self, value: bool):
        self._proto.sketch_dnp_footprints_on_fab_layers = value

    @property
    def crossout_dnp_footprints_on_fab_layers(self) -> bool:
        return self._proto.crossout_dnp_footprints_on_fab_layers

    @crossout_dnp_footprints_on_fab_layers.setter
    def crossout_dnp_footprints_on_fab_layers(self, value: bool):
        self._proto.crossout_dnp_footprints_on_fab_layers = value

    @property
    def plot_footprint_values(self) -> bool:
        return self._proto.plot_footprint_values

    @plot_footprint_values.setter
    def plot_footprint_values(self, value: bool):
        self._proto.plot_footprint_values = value

    @property
    def plot_reference_designators(self) -> bool:
        return self._proto.plot_reference_designators

    @plot_reference_designators.setter
    def plot_reference_designators(self, value: bool):
        self._proto.plot_reference_designators = value

    @property
    def plot_drawing_sheet(self) -> bool:
        return self._proto.plot_drawing_sheet

    @plot_drawing_sheet.setter
    def plot_drawing_sheet(self, value: bool):
        self._proto.plot_drawing_sheet = value

    @property
    def subtract_solder_mask_from_silk(self) -> bool:
        return self._proto.subtract_solder_mask_from_silk

    @subtract_solder_mask_from_silk.setter
    def subtract_solder_mask_from_silk(self, value: bool):
        self._proto.subtract_solder_mask_from_silk = value

    @property
    def plot_pad_numbers(self) -> bool:
        return self._proto.plot_pad_numbers

    @plot_pad_numbers.setter
    def plot_pad_numbers(self, value: bool):
        self._proto.plot_pad_numbers = value

    @property
    def drill_marks(self) -> board_jobs_pb2.PlotDrillMarks.ValueType:
        return self._proto.drill_marks

    @drill_marks.setter
    def drill_marks(self, value: board_jobs_pb2.PlotDrillMarks.ValueType):
        self._proto.drill_marks = value

    @property
    def use_drill_origin(self) -> bool:
        return self._proto.use_drill_origin

    @use_drill_origin.setter
    def use_drill_origin(self, value: bool):
        self._proto.use_drill_origin = value

    @property
    def check_zones_before_plot(self) -> bool:
        return self._proto.check_zones_before_plot

    @check_zones_before_plot.setter
    def check_zones_before_plot(self, value: bool):
        self._proto.check_zones_before_plot = value


class Export3DSettings(Wrapper):
    """Settings for 3D model export job"""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExport3D | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExport3D | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExport3D()
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def format(self) -> board_jobs_pb2.Board3DFormat.ValueType:
        return self._proto.format

    @format.setter
    def format(self, value: board_jobs_pb2.Board3DFormat.ValueType):
        self._proto.format = value

    @property
    def variant(self) -> str:
        return self._proto.variant

    @variant.setter
    def variant(self, value: str):
        self._proto.variant = value

    @property
    def net_filter(self) -> str:
        return self._proto.net_filter

    @net_filter.setter
    def net_filter(self, value: str):
        self._proto.net_filter = value

    @property
    def component_filter(self) -> str:
        return self._proto.component_filter

    @component_filter.setter
    def component_filter(self, value: str):
        self._proto.component_filter = value

    @property
    def has_user_origin(self) -> bool:
        return self._proto.has_user_origin

    @has_user_origin.setter
    def has_user_origin(self, value: bool):
        self._proto.has_user_origin = value

    @property
    def origin(self) -> Vector2:
        return Vector2(self._proto.origin)

    @origin.setter
    def origin(self, value: Vector2):
        self._proto.origin.CopyFrom(value.proto)
        self._proto.has_user_origin = True

    @property
    def overwrite(self) -> bool:
        return self._proto.overwrite

    @overwrite.setter
    def overwrite(self, value: bool):
        self._proto.overwrite = value

    @property
    def use_grid_origin(self) -> bool:
        return self._proto.use_grid_origin

    @use_grid_origin.setter
    def use_grid_origin(self, value: bool):
        self._proto.use_grid_origin = value

    @property
    def use_drill_origin(self) -> bool:
        return self._proto.use_drill_origin

    @use_drill_origin.setter
    def use_drill_origin(self, value: bool):
        self._proto.use_drill_origin = value

    @property
    def use_defined_origin(self) -> bool:
        return self._proto.use_defined_origin

    @use_defined_origin.setter
    def use_defined_origin(self, value: bool):
        self._proto.use_defined_origin = value

    @property
    def use_pcb_center_origin(self) -> bool:
        return self._proto.use_pcb_center_origin

    @use_pcb_center_origin.setter
    def use_pcb_center_origin(self, value: bool):
        self._proto.use_pcb_center_origin = value

    @property
    def include_unspecified(self) -> bool:
        return self._proto.include_unspecified

    @include_unspecified.setter
    def include_unspecified(self, value: bool):
        self._proto.include_unspecified = value

    @property
    def include_dnp(self) -> bool:
        return self._proto.include_dnp

    @include_dnp.setter
    def include_dnp(self, value: bool):
        self._proto.include_dnp = value

    @property
    def substitute_models(self) -> bool:
        return self._proto.substitute_models

    @substitute_models.setter
    def substitute_models(self, value: bool):
        self._proto.substitute_models = value

    @property
    def board_outlines_chaining_epsilon(self) -> float:
        return self._proto.board_outlines_chaining_epsilon

    @board_outlines_chaining_epsilon.setter
    def board_outlines_chaining_epsilon(self, value: float):
        self._proto.board_outlines_chaining_epsilon = value

    @property
    def board_only(self) -> bool:
        return self._proto.board_only

    @board_only.setter
    def board_only(self, value: bool):
        self._proto.board_only = value

    @property
    def cut_vias_in_body(self) -> bool:
        return self._proto.cut_vias_in_body

    @cut_vias_in_body.setter
    def cut_vias_in_body(self, value: bool):
        self._proto.cut_vias_in_body = value

    @property
    def export_board_body(self) -> bool:
        return self._proto.export_board_body

    @export_board_body.setter
    def export_board_body(self, value: bool):
        self._proto.export_board_body = value

    @property
    def export_components(self) -> bool:
        return self._proto.export_components

    @export_components.setter
    def export_components(self, value: bool):
        self._proto.export_components = value

    @property
    def export_tracks_and_vias(self) -> bool:
        return self._proto.export_tracks_and_vias

    @export_tracks_and_vias.setter
    def export_tracks_and_vias(self, value: bool):
        self._proto.export_tracks_and_vias = value

    @property
    def export_pads(self) -> bool:
        return self._proto.export_pads

    @export_pads.setter
    def export_pads(self, value: bool):
        self._proto.export_pads = value

    @property
    def export_zones(self) -> bool:
        return self._proto.export_zones

    @export_zones.setter
    def export_zones(self, value: bool):
        self._proto.export_zones = value

    @property
    def export_inner_copper(self) -> bool:
        return self._proto.export_inner_copper

    @export_inner_copper.setter
    def export_inner_copper(self, value: bool):
        self._proto.export_inner_copper = value

    @property
    def export_silkscreen(self) -> bool:
        return self._proto.export_silkscreen

    @export_silkscreen.setter
    def export_silkscreen(self, value: bool):
        self._proto.export_silkscreen = value

    @property
    def export_soldermask(self) -> bool:
        return self._proto.export_soldermask

    @export_soldermask.setter
    def export_soldermask(self, value: bool):
        self._proto.export_soldermask = value

    @property
    def fuse_shapes(self) -> bool:
        return self._proto.fuse_shapes

    @fuse_shapes.setter
    def fuse_shapes(self, value: bool):
        self._proto.fuse_shapes = value

    @property
    def fill_all_vias(self) -> bool:
        return self._proto.fill_all_vias

    @fill_all_vias.setter
    def fill_all_vias(self, value: bool):
        self._proto.fill_all_vias = value

    @property
    def optimize_step(self) -> bool:
        return self._proto.optimize_step

    @optimize_step.setter
    def optimize_step(self, value: bool):
        self._proto.optimize_step = value

    @property
    def extra_pad_thickness(self) -> bool:
        return self._proto.extra_pad_thickness

    @extra_pad_thickness.setter
    def extra_pad_thickness(self, value: bool):
        self._proto.extra_pad_thickness = value

    @property
    def vrml_units(self) -> enums_pb2.Units.ValueType:
        """Inches, millimeters, meters, or tenths of an inch are accepted"""
        return self._proto.vrml_units

    @vrml_units.setter
    def vrml_units(self, value: enums_pb2.Units.ValueType):
        self._proto.vrml_units = value

    @property
    def vrml_model_dir(self) -> str:
        return self._proto.vrml_model_dir

    @vrml_model_dir.setter
    def vrml_model_dir(self, value: str):
        self._proto.vrml_model_dir = value

    @property
    def vrml_relative_paths(self) -> bool:
        return self._proto.vrml_relative_paths

    @vrml_relative_paths.setter
    def vrml_relative_paths(self, value: bool):
        self._proto.vrml_relative_paths = value


class RenderSettings(Wrapper):
    """Settings for 3D render export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportRender | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportRender | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportRender()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def format(self) -> board_jobs_pb2.RenderFormat.ValueType:
        return self._proto.format

    @format.setter
    def format(self, value: board_jobs_pb2.RenderFormat.ValueType):
        self._proto.format = value

    @property
    def quality(self) -> board_jobs_pb2.RenderQuality.ValueType:
        return self._proto.quality

    @quality.setter
    def quality(self, value: board_jobs_pb2.RenderQuality.ValueType):
        self._proto.quality = value

    @property
    def background_style(self) -> board_jobs_pb2.RenderBackgroundStyle.ValueType:
        return self._proto.background_style

    @background_style.setter
    def background_style(self, value: board_jobs_pb2.RenderBackgroundStyle.ValueType):
        self._proto.background_style = value

    @property
    def width(self) -> int:
        return self._proto.width

    @width.setter
    def width(self, value: int):
        self._proto.width = value

    @property
    def height(self) -> int:
        return self._proto.height

    @height.setter
    def height(self, value: int):
        self._proto.height = value

    @property
    def appearance_preset(self) -> str:
        return self._proto.appearance_preset

    @appearance_preset.setter
    def appearance_preset(self, value: str):
        self._proto.appearance_preset = value

    @property
    def use_board_stackup_colors(self) -> bool:
        return self._proto.use_board_stackup_colors

    @use_board_stackup_colors.setter
    def use_board_stackup_colors(self, value: bool):
        self._proto.use_board_stackup_colors = value

    @property
    def side(self) -> board_jobs_pb2.RenderSide.ValueType:
        return self._proto.side

    @side.setter
    def side(self, value: board_jobs_pb2.RenderSide.ValueType):
        self._proto.side = value

    @property
    def zoom(self) -> float:
        return self._proto.zoom

    @zoom.setter
    def zoom(self, value: float):
        self._proto.zoom = value

    @property
    def perspective(self) -> bool:
        return self._proto.perspective

    @perspective.setter
    def perspective(self, value: bool):
        self._proto.perspective = value

    @property
    def rotation(self) -> Vector3D:
        return Vector3D(self._proto.rotation)

    @rotation.setter
    def rotation(self, value: Vector3D):
        self._proto.rotation.CopyFrom(value.proto)

    @property
    def pan(self) -> Vector3D:
        return Vector3D(self._proto.pan)

    @pan.setter
    def pan(self, value: Vector3D):
        self._proto.pan.CopyFrom(value.proto)

    @property
    def pivot(self) -> Vector3D:
        return Vector3D(self._proto.pivot)

    @pivot.setter
    def pivot(self, value: Vector3D):
        self._proto.pivot.CopyFrom(value.proto)

    @property
    def procedural_textures(self) -> bool:
        return self._proto.procedural_textures

    @procedural_textures.setter
    def procedural_textures(self, value: bool):
        self._proto.procedural_textures = value

    @property
    def floor(self) -> bool:
        return self._proto.floor

    @floor.setter
    def floor(self, value: bool):
        self._proto.floor = value

    @property
    def anti_alias(self) -> bool:
        return self._proto.anti_alias

    @anti_alias.setter
    def anti_alias(self, value: bool):
        self._proto.anti_alias = value

    @property
    def post_process(self) -> bool:
        return self._proto.post_process

    @post_process.setter
    def post_process(self, value: bool):
        self._proto.post_process = value

    @property
    def light_top_intensity(self) -> Vector3D:
        return Vector3D(self._proto.light_top_intensity)

    @light_top_intensity.setter
    def light_top_intensity(self, value: Vector3D):
        self._proto.light_top_intensity.CopyFrom(value.proto)

    @property
    def light_bottom_intensity(self) -> Vector3D:
        return Vector3D(self._proto.light_bottom_intensity)

    @light_bottom_intensity.setter
    def light_bottom_intensity(self, value: Vector3D):
        self._proto.light_bottom_intensity.CopyFrom(value.proto)

    @property
    def light_camera_intensity(self) -> Vector3D:
        return Vector3D(self._proto.light_camera_intensity)

    @light_camera_intensity.setter
    def light_camera_intensity(self, value: Vector3D):
        self._proto.light_camera_intensity.CopyFrom(value.proto)

    @property
    def light_side_intensity(self) -> Vector3D:
        return Vector3D(self._proto.light_side_intensity)

    @light_side_intensity.setter
    def light_side_intensity(self, value: Vector3D):
        self._proto.light_side_intensity.CopyFrom(value.proto)

    @property
    def light_side_elevation(self) -> int:
        return self._proto.light_side_elevation

    @light_side_elevation.setter
    def light_side_elevation(self, value: int):
        self._proto.light_side_elevation = value


class PositionExportSettings(Wrapper):
    """Settings for position file export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportPosition | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportPosition | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportPosition()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def use_drill_place_file_origin(self) -> bool | None:
        if not self._proto.HasField("use_drill_place_file_origin"):
            return None
        return self._proto.use_drill_place_file_origin

    @use_drill_place_file_origin.setter
    def use_drill_place_file_origin(self, value: bool | None):
        if value is None:
            self._proto.ClearField("use_drill_place_file_origin")
            return
        self._proto.use_drill_place_file_origin = value

    @property
    def smd_only(self) -> bool:
        return self._proto.smd_only

    @smd_only.setter
    def smd_only(self, value: bool):
        self._proto.smd_only = value

    @property
    def exclude_footprints_with_th(self) -> bool:
        return self._proto.exclude_footprints_with_th

    @exclude_footprints_with_th.setter
    def exclude_footprints_with_th(self, value: bool):
        self._proto.exclude_footprints_with_th = value

    @property
    def exclude_dnp(self) -> bool:
        return self._proto.exclude_dnp

    @exclude_dnp.setter
    def exclude_dnp(self, value: bool):
        self._proto.exclude_dnp = value

    @property
    def exclude_from_bom(self) -> bool:
        return self._proto.exclude_from_bom

    @exclude_from_bom.setter
    def exclude_from_bom(self, value: bool):
        self._proto.exclude_from_bom = value

    @property
    def negate_bottom_x(self) -> bool:
        return self._proto.negate_bottom_x

    @negate_bottom_x.setter
    def negate_bottom_x(self, value: bool):
        self._proto.negate_bottom_x = value

    @property
    def single_file(self) -> bool:
        return self._proto.single_file

    @single_file.setter
    def single_file(self, value: bool):
        self._proto.single_file = value

    @property
    def naked_filename(self) -> bool:
        return self._proto.naked_filename

    @naked_filename.setter
    def naked_filename(self, value: bool):
        self._proto.naked_filename = value

    @property
    def side(self) -> board_jobs_pb2.PositionSide.ValueType:
        return self._proto.side

    @side.setter
    def side(self, value: board_jobs_pb2.PositionSide.ValueType):
        self._proto.side = value

    @property
    def units(self) -> enums_pb2.Units.ValueType:
        """Inches or millimeters are accepted"""
        return self._proto.units

    @units.setter
    def units(self, value: enums_pb2.Units.ValueType):
        self._proto.units = value

    @property
    def format(self) -> board_jobs_pb2.PositionFormat.ValueType:
        return self._proto.format

    @format.setter
    def format(self, value: board_jobs_pb2.PositionFormat.ValueType):
        self._proto.format = value

    @property
    def include_board_edge_for_gerber(self) -> bool | None:
        if not self._proto.HasField("include_board_edge_for_gerber"):
            return None
        return self._proto.include_board_edge_for_gerber

    @include_board_edge_for_gerber.setter
    def include_board_edge_for_gerber(self, value: bool | None):
        if value is None:
            self._proto.ClearField("include_board_edge_for_gerber")
            return
        self._proto.include_board_edge_for_gerber = value

    @property
    def variant(self) -> str:
        return self._proto.variant

    @variant.setter
    def variant(self, value: str):
        self._proto.variant = value


class Ipc2581ExportSettings(Wrapper):
    """Settings for IPC-2581 export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportIpc2581 | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportIpc2581 | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportIpc2581()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def drawing_sheet(self) -> str:
        return self._proto.drawing_sheet

    @drawing_sheet.setter
    def drawing_sheet(self, value: str):
        self._proto.drawing_sheet = value

    @property
    def variant(self) -> str:
        return self._proto.variant

    @variant.setter
    def variant(self, value: str):
        self._proto.variant = value

    @property
    def units(self) -> enums_pb2.Units.ValueType:
        """Inches or millimeters are accepted"""
        return self._proto.units

    @units.setter
    def units(self, value: enums_pb2.Units.ValueType):
        self._proto.units = value

    @property
    def version(self) -> board_jobs_pb2.Ipc2581Version.ValueType:
        return self._proto.version

    @version.setter
    def version(self, value: board_jobs_pb2.Ipc2581Version.ValueType):
        self._proto.version = value

    @property
    def precision(self) -> int | None:
        if not self._proto.HasField("precision"):
            return None
        return self._proto.precision

    @precision.setter
    def precision(self, value: int | None):
        if value is None:
            self._proto.ClearField("precision")
            return
        self._proto.precision = value

    @property
    def compress(self) -> bool:
        return self._proto.compress

    @compress.setter
    def compress(self, value: bool):
        self._proto.compress = value

    @property
    def internal_id_column(self) -> str:
        return self._proto.internal_id_column

    @internal_id_column.setter
    def internal_id_column(self, value: str):
        self._proto.internal_id_column = value

    @property
    def manufacturer_part_number_column(self) -> str:
        return self._proto.manufacturer_part_number_column

    @manufacturer_part_number_column.setter
    def manufacturer_part_number_column(self, value: str):
        self._proto.manufacturer_part_number_column = value

    @property
    def manufacturer_column(self) -> str:
        return self._proto.manufacturer_column

    @manufacturer_column.setter
    def manufacturer_column(self, value: str):
        self._proto.manufacturer_column = value

    @property
    def distributor_part_number_column(self) -> str:
        return self._proto.distributor_part_number_column

    @distributor_part_number_column.setter
    def distributor_part_number_column(self, value: str):
        self._proto.distributor_part_number_column = value

    @property
    def distributor_column(self) -> str:
        return self._proto.distributor_column

    @distributor_column.setter
    def distributor_column(self, value: str):
        self._proto.distributor_column = value

    @property
    def bom_revision(self) -> str:
        return self._proto.bom_revision

    @bom_revision.setter
    def bom_revision(self, value: str):
        self._proto.bom_revision = value


class SvgExportSettings(Wrapper):
    """Settings for SVG export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportSvg | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportSvg | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportSvg()
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def plot_settings(self) -> PlotSettings:
        return PlotSettings(proto_ref=self._proto.plot_settings)

    @plot_settings.setter
    def plot_settings(self, value: PlotSettings):
        self._proto.plot_settings.CopyFrom(value.proto)

    @property
    def fit_page_to_board(self) -> bool:
        return self._proto.fit_page_to_board

    @fit_page_to_board.setter
    def fit_page_to_board(self, value: bool):
        self._proto.fit_page_to_board = value

    @property
    def precision(self) -> int:
        return self._proto.precision

    @precision.setter
    def precision(self, value: int):
        self._proto.precision = value

    @property
    def page_mode(self) -> board_jobs_pb2.BoardJobPaginationMode.ValueType:
        """Supports ``BJPM_ALL_LAYERS_ONE_PAGE`` and ``BJPM_EACH_LAYER_OWN_FILE``."""
        return self._proto.page_mode

    @page_mode.setter
    def page_mode(self, value: board_jobs_pb2.BoardJobPaginationMode.ValueType):
        self._proto.page_mode = value


class DxfExportSettings(Wrapper):
    """Settings for DXF export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportDxf | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportDxf | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportDxf()
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def plot_settings(self) -> PlotSettings:
        return PlotSettings(proto_ref=self._proto.plot_settings)

    @plot_settings.setter
    def plot_settings(self, value: PlotSettings):
        self._proto.plot_settings.CopyFrom(value.proto)

    @property
    def plot_graphic_items_using_contours(self) -> bool:
        return self._proto.plot_graphic_items_using_contours

    @plot_graphic_items_using_contours.setter
    def plot_graphic_items_using_contours(self, value: bool):
        self._proto.plot_graphic_items_using_contours = value

    @property
    def polygon_mode(self) -> bool:
        return self._proto.polygon_mode

    @polygon_mode.setter
    def polygon_mode(self, value: bool):
        self._proto.polygon_mode = value

    @property
    def units(self) -> enums_pb2.Units.ValueType:
        """Inches or millimeters are accepted"""
        return self._proto.units

    @units.setter
    def units(self, value: enums_pb2.Units.ValueType):
        self._proto.units = value

    @property
    def page_mode(self) -> board_jobs_pb2.BoardJobPaginationMode.ValueType:
        """Supports ``BJPM_ALL_LAYERS_ONE_PAGE`` and ``BJPM_EACH_LAYER_OWN_FILE``."""
        return self._proto.page_mode

    @page_mode.setter
    def page_mode(self, value: board_jobs_pb2.BoardJobPaginationMode.ValueType):
        self._proto.page_mode = value


class PdfExportSettings(Wrapper):
    """Settings for PDF export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportPdf | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportPdf | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportPdf()
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def plot_settings(self) -> PlotSettings:
        return PlotSettings(proto_ref=self._proto.plot_settings)

    @plot_settings.setter
    def plot_settings(self, value: PlotSettings):
        self._proto.plot_settings.CopyFrom(value.proto)

    @property
    def front_footprint_property_popups(self) -> bool:
        return self._proto.front_footprint_property_popups

    @front_footprint_property_popups.setter
    def front_footprint_property_popups(self, value: bool):
        self._proto.front_footprint_property_popups = value

    @property
    def back_footprint_property_popups(self) -> bool:
        return self._proto.back_footprint_property_popups

    @back_footprint_property_popups.setter
    def back_footprint_property_popups(self, value: bool):
        self._proto.back_footprint_property_popups = value

    @property
    def include_metadata(self) -> bool:
        return self._proto.include_metadata

    @include_metadata.setter
    def include_metadata(self, value: bool):
        self._proto.include_metadata = value

    @property
    def single_document(self) -> bool:
        return self._proto.single_document

    @single_document.setter
    def single_document(self, value: bool):
        self._proto.single_document = value

    @property
    def page_mode(self) -> board_jobs_pb2.BoardJobPaginationMode.ValueType:
        return self._proto.page_mode

    @page_mode.setter
    def page_mode(self, value: board_jobs_pb2.BoardJobPaginationMode.ValueType):
        self._proto.page_mode = value

    @property
    def background_color(self) -> str:
        return self._proto.background_color

    @background_color.setter
    def background_color(self, value: str):
        self._proto.background_color = value


class PsExportSettings(Wrapper):
    """Settings for PostScript export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportPs | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportPs | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportPs()
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def plot_settings(self) -> PlotSettings:
        return PlotSettings(proto_ref=self._proto.plot_settings)

    @plot_settings.setter
    def plot_settings(self, value: PlotSettings):
        self._proto.plot_settings.CopyFrom(value.proto)

    @property
    def page_mode(self) -> board_jobs_pb2.BoardJobPaginationMode.ValueType:
        """Supports ``BJPM_ALL_LAYERS_ONE_PAGE`` and ``BJPM_EACH_LAYER_OWN_FILE``."""
        return self._proto.page_mode

    @page_mode.setter
    def page_mode(self, value: board_jobs_pb2.BoardJobPaginationMode.ValueType):
        self._proto.page_mode = value

    @property
    def track_width_correction(self) -> float:
        return self._proto.track_width_correction

    @track_width_correction.setter
    def track_width_correction(self, value: float):
        self._proto.track_width_correction = value

    @property
    def x_scale_adjust(self) -> float:
        return self._proto.x_scale_adjust

    @x_scale_adjust.setter
    def x_scale_adjust(self, value: float):
        self._proto.x_scale_adjust = value

    @property
    def y_scale_adjust(self) -> float:
        return self._proto.y_scale_adjust

    @y_scale_adjust.setter
    def y_scale_adjust(self, value: float):
        self._proto.y_scale_adjust = value

    @property
    def force_a4(self) -> bool:
        return self._proto.force_a4

    @force_a4.setter
    def force_a4(self, value: bool):
        self._proto.force_a4 = value

    @property
    def use_global_settings(self) -> bool:
        return self._proto.use_global_settings

    @use_global_settings.setter
    def use_global_settings(self, value: bool):
        self._proto.use_global_settings = value


class GerberExportSettings(Wrapper):
    """Settings for Gerber export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportGerbers | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportGerbers | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportGerbers()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def plot_settings(self) -> PlotSettings:
        return PlotSettings(proto_ref=self._proto.plot_settings)

    @plot_settings.setter
    def plot_settings(self, value: PlotSettings):
        self._proto.plot_settings.CopyFrom(value.proto)

    @property
    def use_board_plot_params(self) -> bool:
        """If true, the Gerber plot settings stored in the board file are used instead of the
        settings provided in this class.  When set, the layers list is derived from the
        board's plot layer selection."""
        return self._proto.use_board_plot_params

    @use_board_plot_params.setter
    def use_board_plot_params(self, value: bool):
        self._proto.use_board_plot_params = value

    @property
    def create_gerber_job_file(self) -> bool:
        """If true, a Gerber job file (.gbrjob) is created alongside the plot outputs."""
        return self._proto.create_gerber_job_file

    @create_gerber_job_file.setter
    def create_gerber_job_file(self, value: bool):
        self._proto.create_gerber_job_file = value

    @property
    def include_netlist_attributes(self) -> bool:
        """If true, Gerber X2 netlist attributes are included in the plot outputs."""
        return self._proto.include_netlist_attributes

    @include_netlist_attributes.setter
    def include_netlist_attributes(self, value: bool):
        self._proto.include_netlist_attributes = value

    @property
    def use_x2_format(self) -> bool:
        """If true, Gerber X2 format is used."""
        return self._proto.use_x2_format

    @use_x2_format.setter
    def use_x2_format(self, value: bool):
        self._proto.use_x2_format = value

    @property
    def disable_aperture_macros(self) -> bool:
        """If true, aperture macros are disabled in the plot outputs."""
        return self._proto.disable_aperture_macros

    @disable_aperture_macros.setter
    def disable_aperture_macros(self, value: bool):
        self._proto.disable_aperture_macros = value

    @property
    def use_protel_file_extensions(self) -> bool:
        """If true, Protel-style file extensions are used (e.g. .gbr → .gtl)."""
        return self._proto.use_protel_file_extensions

    @use_protel_file_extensions.setter
    def use_protel_file_extensions(self, value: bool):
        self._proto.use_protel_file_extensions = value

    @property
    def precision(self) -> board_jobs_pb2.GerberPrecision.ValueType:
        return self._proto.precision

    @precision.setter
    def precision(self, value: board_jobs_pb2.GerberPrecision.ValueType):
        self._proto.precision = value


class ExcellonFormatOptions(Wrapper):
    """Excellon-specific options for drill export."""

    def __init__(
        self,
        proto: board_jobs_pb2.ExcellonFormatOptions | None = None,
        proto_ref: board_jobs_pb2.ExcellonFormatOptions | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_jobs_pb2.ExcellonFormatOptions()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def mirror_y(self) -> bool | None:
        if not self._proto.HasField("mirror_y"):
            return None
        return self._proto.mirror_y

    @mirror_y.setter
    def mirror_y(self, value: bool | None):
        if value is None:
            self._proto.ClearField("mirror_y")
            return
        self._proto.mirror_y = value

    @property
    def minimal_header(self) -> bool | None:
        if not self._proto.HasField("minimal_header"):
            return None
        return self._proto.minimal_header

    @minimal_header.setter
    def minimal_header(self, value: bool | None):
        if value is None:
            self._proto.ClearField("minimal_header")
            return
        self._proto.minimal_header = value

    @property
    def combine_pth_npth(self) -> bool | None:
        if not self._proto.HasField("combine_pth_npth"):
            return None
        return self._proto.combine_pth_npth

    @combine_pth_npth.setter
    def combine_pth_npth(self, value: bool | None):
        if value is None:
            self._proto.ClearField("combine_pth_npth")
            return
        self._proto.combine_pth_npth = value

    @property
    def route_oval_holes(self) -> bool | None:
        if not self._proto.HasField("route_oval_holes"):
            return None
        return self._proto.route_oval_holes

    @route_oval_holes.setter
    def route_oval_holes(self, value: bool | None):
        if value is None:
            self._proto.ClearField("route_oval_holes")
            return
        self._proto.route_oval_holes = value


class DrillExportSettings(Wrapper):
    """Settings for drill export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportDrill | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportDrill | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportDrill()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def format(self) -> board_jobs_pb2.DrillFormat.ValueType:
        return self._proto.format

    @format.setter
    def format(self, value: board_jobs_pb2.DrillFormat.ValueType):
        self._proto.format = value

    @property
    def units(self) -> enums_pb2.Units.ValueType:
        """Inches or millimeters are accepted"""
        return self._proto.units

    @units.setter
    def units(self, value: enums_pb2.Units.ValueType):
        self._proto.units = value

    @property
    def origin(self) -> board_jobs_pb2.DrillOrigin.ValueType:
        return self._proto.origin

    @origin.setter
    def origin(self, value: board_jobs_pb2.DrillOrigin.ValueType):
        self._proto.origin = value

    @property
    def zeros_format(self) -> board_jobs_pb2.DrillZerosFormat.ValueType:
        return self._proto.zeros_format

    @zeros_format.setter
    def zeros_format(self, value: board_jobs_pb2.DrillZerosFormat.ValueType):
        self._proto.zeros_format = value

    @property
    def excellon(self) -> ExcellonFormatOptions:
        return ExcellonFormatOptions(proto_ref=self._proto.excellon)

    @excellon.setter
    def excellon(self, value: ExcellonFormatOptions):
        self._proto.excellon.CopyFrom(value.proto)

    @property
    def map_format(self) -> board_jobs_pb2.DrillMapFormat.ValueType:
        """Set to a valid value to generate a drill map.  Leave unset for no drill map."""
        return self._proto.map_format

    @map_format.setter
    def map_format(self, value: board_jobs_pb2.DrillMapFormat.ValueType):
        self._proto.map_format = value

    @property
    def gerber_precision(self) -> board_jobs_pb2.DrillGerberPrecision.ValueType:
        """When generating drill files in Gerber format, the precision to use for coordinates"""
        return self._proto.gerber_precision

    @gerber_precision.setter
    def gerber_precision(self, value: board_jobs_pb2.DrillGerberPrecision.ValueType):
        self._proto.gerber_precision = value

    @property
    def gerber_generate_tenting(self) -> bool | None:
        if not self._proto.HasField("gerber_generate_tenting"):
            return None
        return self._proto.gerber_generate_tenting

    @gerber_generate_tenting.setter
    def gerber_generate_tenting(self, value: bool | None):
        if value is None:
            self._proto.ClearField("gerber_generate_tenting")
            return
        self._proto.gerber_generate_tenting = value

    @property
    def report_format(self) -> board_jobs_pb2.DrillReportFormat.ValueType:
        """Set to a valid value to generate a drill report.  Leave unset for no report."""
        return self._proto.report_format

    @report_format.setter
    def report_format(self, value: board_jobs_pb2.DrillReportFormat.ValueType):
        self._proto.report_format = value

    @property
    def report_filename(self) -> str | None:
        if not self._proto.HasField("report_filename"):
            return None
        return self._proto.report_filename

    @report_filename.setter
    def report_filename(self, value: str | None):
        if value is None:
            self._proto.ClearField("report_filename")
            return
        self._proto.report_filename = value


class GencadExportSettings(Wrapper):
    """Settings for GenCAD export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportGencad | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportGencad | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportGencad()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def flip_bottom_pads(self) -> bool:
        return self._proto.flip_bottom_pads

    @flip_bottom_pads.setter
    def flip_bottom_pads(self, value: bool):
        self._proto.flip_bottom_pads = value

    @property
    def use_individual_shapes(self) -> bool:
        return self._proto.use_individual_shapes

    @use_individual_shapes.setter
    def use_individual_shapes(self, value: bool):
        self._proto.use_individual_shapes = value

    @property
    def store_origin_coords(self) -> bool:
        return self._proto.store_origin_coords

    @store_origin_coords.setter
    def store_origin_coords(self, value: bool):
        self._proto.store_origin_coords = value

    @property
    def use_drill_origin(self) -> bool:
        return self._proto.use_drill_origin

    @use_drill_origin.setter
    def use_drill_origin(self, value: bool):
        self._proto.use_drill_origin = value

    @property
    def use_unique_pins(self) -> bool:
        return self._proto.use_unique_pins

    @use_unique_pins.setter
    def use_unique_pins(self, value: bool):
        self._proto.use_unique_pins = value


class IpcD356ExportSettings(Wrapper):
    """Settings for IPC-D-356 export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportIpcD356 | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportIpcD356 | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportIpcD356()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)


class OdbExportSettings(Wrapper):
    """Settings for ODB++ export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportODB | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportODB | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportODB()
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def drawing_sheet(self) -> str:
        return self._proto.drawing_sheet

    @drawing_sheet.setter
    def drawing_sheet(self, value: str):
        self._proto.drawing_sheet = value

    @property
    def variant(self) -> str:
        return self._proto.variant

    @variant.setter
    def variant(self, value: str):
        self._proto.variant = value

    @property
    def units(self) -> enums_pb2.Units.ValueType:
        """Inches or millimeters are accepted"""
        return self._proto.units

    @units.setter
    def units(self, value: enums_pb2.Units.ValueType):
        self._proto.units = value

    @property
    def precision(self) -> int | None:
        if not self._proto.HasField("precision"):
            return None
        return self._proto.precision

    @precision.setter
    def precision(self, value: int | None):
        if value is None:
            self._proto.ClearField("precision")
            return
        self._proto.precision = value

    @property
    def compression(self) -> board_jobs_pb2.OdbCompression.ValueType:
        return self._proto.compression

    @compression.setter
    def compression(self, value: board_jobs_pb2.OdbCompression.ValueType):
        self._proto.compression = value


class StatsExportSettings(Wrapper):
    """Settings for board statistics export job."""

    def __init__(
        self,
        proto: board_jobs_pb2.RunBoardJobExportStats | None = None,
        proto_ref: board_jobs_pb2.RunBoardJobExportStats | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_jobs_pb2.RunBoardJobExportStats()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def format(self) -> board_jobs_pb2.StatsOutputFormat.ValueType:
        return self._proto.format

    @format.setter
    def format(self, value: board_jobs_pb2.StatsOutputFormat.ValueType):
        self._proto.format = value

    @property
    def units(self) -> enums_pb2.Units.ValueType:
        """Inches or millimeters are accepted"""
        return self._proto.units

    @units.setter
    def units(self, value: enums_pb2.Units.ValueType):
        self._proto.units = value

    @property
    def exclude_footprints_without_pads(self) -> bool:
        return self._proto.exclude_footprints_without_pads

    @exclude_footprints_without_pads.setter
    def exclude_footprints_without_pads(self, value: bool):
        self._proto.exclude_footprints_without_pads = value

    @property
    def subtract_holes_from_board_area(self) -> bool:
        return self._proto.subtract_holes_from_board_area

    @subtract_holes_from_board_area.setter
    def subtract_holes_from_board_area(self, value: bool):
        self._proto.subtract_holes_from_board_area = value

    @property
    def subtract_holes_from_copper_areas(self) -> bool:
        return self._proto.subtract_holes_from_copper_areas

    @subtract_holes_from_copper_areas.setter
    def subtract_holes_from_copper_areas(self, value: bool):
        self._proto.subtract_holes_from_copper_areas = value
