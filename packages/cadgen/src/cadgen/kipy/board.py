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

import os
import reprlib
from collections.abc import Iterable, Sequence
from time import sleep
from typing import Any, Union, cast, overload

from google.protobuf.empty_pb2 import Empty

from cadgen.kipy.board_jobs import (
    Export3DSettings,
    Ipc2581ExportSettings,
    PlotSettings,
    PositionExportSettings,
    RenderSettings,
)
from cadgen.kipy.board_rules import (
    BoardDesignRules,
    BoardDesignRulesResponse,
    CustomRule,
    CustomRulesResponse,
)
from cadgen.kipy.board_types import (
    ArcTrack,
    Barcode,
    BoardEditorAppearanceSettings,
    BoardItem,
    BoardShape,
    BoardText,
    BoardTextBox,
    Constraint,
    Dimension,
    FootprintInstance,
    GridItem,
    Group,
    Net,
    Pad,
    ReferenceImage,
    ReferencePoint,
    Table,
    Track,
    Via,
    Zone,
    to_concrete_board_shape,
    to_concrete_dimension,
    unwrap,
)
from cadgen.kipy.client import ApiError, KiCadClient
from cadgen.kipy.common_types import (
    Color,
    EmbeddedFile,
    EmbeddedFiles,
    JobResult,
    LibraryIdentifier,
    TextAttributes,
    TitleBlockInfo,
)
from cadgen.kipy.editor import EditorCommandsHandler
from cadgen.kipy.geometry import Angle, Box2, PolygonWithHoles, Vector2
from cadgen.kipy.project import NetClass, Project
from cadgen.kipy.proto.board import board_commands_pb2, board_jobs_pb2, board_pb2, board_types_pb2
from cadgen.kipy.proto.board.board_commands_pb2 import (  # noqa
    BoardFlipDirection,
    BoardOriginType,
    CustomRulesStatus,
    NetlistMatchMode,
)
from cadgen.kipy.proto.board.board_jobs_pb2 import (  # noqa
    Board3DFormat,
    BoardJobPaginationMode,
    DrillFormat,
    DrillGerberPrecision,
    DrillMapFormat,
    DrillOrigin,
    DrillReportFormat,
    DrillZerosFormat,
    GerberPrecision,
    Ipc2581Version,
    OdbCompression,
    PlotDrillMarks,
    PositionFormat,
    PositionSide,
    RenderBackgroundStyle,
    RenderFormat,
    RenderQuality,
    RenderSide,
    StatsOutputFormat,
)

# Re-exported protobuf enum types
from cadgen.kipy.proto.board.board_pb2 import (  # noqa
    BoardEdgeConnectorType,
    BoardLayerClass,
    BoardStackupDielectricType,
    DielectricModel,
)
from cadgen.kipy.proto.board.board_types_pb2 import BoardLayer
from cadgen.kipy.proto.common.commands import Ping, editor_commands_pb2, project_commands_pb2
from cadgen.kipy.proto.common.commands.editor_commands_pb2 import (
    GetItemsResponse,
    HitTest,
    HitTestResponse,
    HitTestResult,
)
from cadgen.kipy.proto.common.commands.library_commands_pb2 import PlaceFromLibraryResponse
from cadgen.kipy.proto.common.envelope_pb2 import ApiStatusCode
from cadgen.kipy.proto.common.types import (
    KIID,
    DocumentSpecifier,
    KiCadObjectType,
    base_types_pb2,
    embedded_files_pb2,
    jobs_pb2,
)
from cadgen.kipy.proto.common.types.enums_pb2 import (
    Units,
)
from cadgen.kipy.variants import VariantsCommandHandler
from cadgen.kipy.wrapper import Item, Wrapper

BoardJobCommand = Union[
    board_jobs_pb2.RunBoardJobExport3D,
    board_jobs_pb2.RunBoardJobExportRender,
    board_jobs_pb2.RunBoardJobExportSvg,
    board_jobs_pb2.RunBoardJobExportDxf,
    board_jobs_pb2.RunBoardJobExportPdf,
    board_jobs_pb2.RunBoardJobExportPs,
    board_jobs_pb2.RunBoardJobExportPng,
    board_jobs_pb2.RunBoardJobExportGerbers,
    board_jobs_pb2.RunBoardJobExportDrill,
    board_jobs_pb2.RunBoardJobExportPosition,
    board_jobs_pb2.RunBoardJobExportGencad,
    board_jobs_pb2.RunBoardJobExportIpc2581,
    board_jobs_pb2.RunBoardJobExportIpcD356,
    board_jobs_pb2.RunBoardJobExportODB,
    board_jobs_pb2.RunBoardJobExportStats,
]


class ImportNetlistResult(Wrapper):
    """Result of importing a schematic netlist into the board."""

    def __init__(
        self,
        proto: board_commands_pb2.ImportNetlistResponse | None = None,
        proto_ref: board_commands_pb2.ImportNetlistResponse | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else board_commands_pb2.ImportNetlistResponse()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"<ImportNetlistResult error_count={self.error_count} "
            f"warning_count={self.warning_count} "
            f"new_footprint_count={self.new_footprint_count} "
            f"report={reprlib.repr(self.report)}>"
        )

    @property
    def report(self) -> str:
        """Human-readable report of changes and any warnings or errors."""
        return self._proto.report

    @property
    def error_count(self) -> int:
        return self._proto.error_count

    @property
    def warning_count(self) -> int:
        return self._proto.warning_count

    @property
    def new_footprint_count(self) -> int:
        return self._proto.new_footprint_count


class BoardLayerGraphicsDefaults(Wrapper):
    """The default properties for graphic items added on a given class of board layer"""

    def __init__(self, proto: board_pb2.BoardLayerGraphicsDefaults | None = None):
        self._proto = board_pb2.BoardLayerGraphicsDefaults()

        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def layer(self) -> board_pb2.BoardLayerClass.ValueType:
        """The layer class that these defaults apply to"""
        return self._proto.layer

    @layer.setter
    def layer(self, value: board_pb2.BoardLayerClass.ValueType):
        self._proto.layer = value

    @property
    def line_thickness(self) -> int:
        return self._proto.line_thickness.value_nm

    @line_thickness.setter
    def line_thickness(self, value: int):
        self._proto.line_thickness.value_nm = value

    @property
    def text(self) -> TextAttributes:
        return TextAttributes(self._proto.text)


class BoardStackupDielectricProperties(Wrapper):
    def __init__(self, proto: board_pb2.BoardStackupDielectricProperties | None = None):
        self._proto = board_pb2.BoardStackupDielectricProperties()
        if proto:
            self._proto.CopyFrom(proto)

    @property
    def epsilon_r(self) -> float:
        return self._proto.epsilon_r

    @epsilon_r.setter
    def epsilon_r(self, epsilon_r: float):
        self._proto.epsilon_r = epsilon_r

    @property
    def loss_tangent(self) -> float:
        return self._proto.loss_tangent

    @loss_tangent.setter
    def loss_tangent(self, loss_tangent: float):
        self._proto.loss_tangent = loss_tangent

    @property
    def material_name(self) -> str:
        return self._proto.material_name

    @material_name.setter
    def material_name(self, name: str):
        self._proto.material_name = name

    @property
    def thickness(self) -> int:
        return self._proto.thickness.value_nm

    @thickness.setter
    def thickness(self, thickness: int):
        self._proto.thickness.value_nm = thickness

    @property
    def thickness_locked(self) -> bool:
        """Whether the layer thickness is locked (for impedance controlled layers)

        .. versionadded:: 0.8.0 (KiCad 10.0.6)
        """
        return self._proto.thickness_locked

    @thickness_locked.setter
    def thickness_locked(self, locked: bool):
        self._proto.thickness_locked = locked

    @property
    def spec_frequency(self) -> float | None:
        """The frequency at which the dielectric properties were measured, in Hz

        .. versionadded:: 0.8.0 (KiCad 11.0)
        """
        if self._proto.HasField("spec_frequency"):
            return self._proto.spec_frequency
        return None

    @spec_frequency.setter
    def spec_frequency(self, frequency: float | None):
        if frequency is None:
            self._proto.ClearField("spec_frequency")
        else:
            self._proto.spec_frequency = frequency

    @property
    def dielectric_model(self) -> board_pb2.DielectricModel.ValueType:
        """The model used to extrapolate dielectric properties across frequency

        .. versionadded:: 0.8.0 (KiCad 11.0)
        """
        return self._proto.dielectric_model

    @dielectric_model.setter
    def dielectric_model(self, model: board_pb2.DielectricModel.ValueType):
        self._proto.dielectric_model = model


class BoardStackupDielectricLayer(Wrapper):
    def __init__(self, proto: board_pb2.BoardStackupDielectricLayer | None = None):
        self._proto = board_pb2.BoardStackupDielectricLayer()
        if proto:
            self._proto.CopyFrom(proto)

    @property
    def layers(self) -> list[BoardStackupDielectricProperties]:
        """Each dielectric layer may be made up of one or more sub-layers with different properties"""
        return [BoardStackupDielectricProperties(layer) for layer in self._proto.layer]

    @property
    def type(self) -> board_pb2.BoardStackupDielectricType.ValueType:
        """The physical type of this dielectric slot (e.g. core or prepreg)

        .. versionadded:: 0.8.0 (KiCad 10.0.6)
        """
        return self._proto.type

    @type.setter
    def type(self, value: board_pb2.BoardStackupDielectricType.ValueType):
        self._proto.type = value


class BoardStackupSoldermaskLayer(Wrapper):
    """Properties of a soldermask layer

    .. versionadded:: 0.8.0 (KiCad 10.0.6)"""

    def __init__(self, proto: board_pb2.BoardStackupSoldermaskLayer | None = None):
        self._proto = board_pb2.BoardStackupSoldermaskLayer()
        if proto:
            self._proto.CopyFrom(proto)

    @property
    def epsilon_r(self) -> float:
        return self._proto.epsilon_r

    @epsilon_r.setter
    def epsilon_r(self, value: float):
        self._proto.epsilon_r = value

    @property
    def loss_tangent(self) -> float:
        return self._proto.loss_tangent

    @loss_tangent.setter
    def loss_tangent(self, value: float):
        self._proto.loss_tangent = value

    @property
    def material_name(self) -> str:
        return self._proto.material_name

    @material_name.setter
    def material_name(self, value: str):
        self._proto.material_name = value

    @property
    def thickness(self) -> int:
        return self._proto.thickness.value_nm

    @thickness.setter
    def thickness(self, value: int):
        self._proto.thickness.value_nm = value


class BoardStackupSilkscreenLayer(Wrapper):
    """Properties of a silkscreen layer

    .. versionadded:: 0.8.0 (KiCad 10.0.6)"""

    def __init__(self, proto: board_pb2.BoardStackupSilkscreenLayer | None = None):
        self._proto = board_pb2.BoardStackupSilkscreenLayer()
        if proto:
            self._proto.CopyFrom(proto)

    @property
    def material_name(self) -> str:
        return self._proto.material_name

    @material_name.setter
    def material_name(self, value: str):
        self._proto.material_name = value


class BoardStackupLayer(Wrapper):
    def __init__(self, proto: board_pb2.BoardStackupLayer | None = None):
        self._proto = board_pb2.BoardStackupLayer()
        if proto:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return (
            f"BoardStackupLayer(layer={BoardLayer.Name(self.layer)}, user_name={self.user_name},"
            f"thickness={self.thickness}, enabled={self.enabled}, type={self.type},"
            f"material_name={self.material_name})"
        )

    @property
    def thickness(self) -> int:
        """The total thickness of this layer, in nanometers.  If this is a dielectric layer, this
        thickness may be the sum of multiple sub-layers."""
        return self._proto.thickness.value_nm

    @thickness.setter
    def thickness(self, value: int):
        self._proto.thickness.value_nm = value

    @property
    def layer(self) -> BoardLayer.ValueType:
        """The board layer this stackup entry corresponds to, or ``BL_UNDEFINED`` if this entry is
        a dielectric layer"""
        return self._proto.layer

    @layer.setter
    def layer(self, value: BoardLayer.ValueType):
        self._proto.layer = value

    @property
    def enabled(self) -> bool:
        return self._proto.enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._proto.enabled = value

    @property
    def type(self) -> board_pb2.BoardStackupLayerType.ValueType:
        return self._proto.type

    @type.setter
    def type(self, value: board_pb2.BoardStackupLayerType.ValueType):
        self._proto.type = value

    @property
    def dielectric(self) -> BoardStackupDielectricLayer | None:
        """Dielectric details, if this layer is a dielectric layer

        .. versionadded:: 0.8.0 (KiCad 10.0.6)
        """
        if self._proto.WhichOneof("details") == "dielectric":
            return BoardStackupDielectricLayer(self._proto.dielectric)
        return None

    @dielectric.setter
    def dielectric(self, value: BoardStackupDielectricLayer):
        self._proto.dielectric.CopyFrom(value.proto)

    @property
    def soldermask(self) -> BoardStackupSoldermaskLayer | None:
        """Soldermask details, if this layer is a soldermask layer

        .. versionadded:: 0.8.0 (KiCad 10.0.6)
        """
        if self._proto.WhichOneof("details") == "soldermask":
            return BoardStackupSoldermaskLayer(self._proto.soldermask)
        return None

    @soldermask.setter
    def soldermask(self, value: BoardStackupSoldermaskLayer):
        self._proto.soldermask.CopyFrom(value.proto)

    @property
    def silkscreen(self) -> BoardStackupSilkscreenLayer | None:
        """Silkscreen details, if this layer is a silkscreen layer

        .. versionadded:: 0.8.0 (KiCad 10.0.6)
        """
        if self._proto.WhichOneof("details") == "silkscreen":
            return BoardStackupSilkscreenLayer(self._proto.silkscreen)
        return None

    @silkscreen.setter
    def silkscreen(self, value: BoardStackupSilkscreenLayer):
        self._proto.silkscreen.CopyFrom(value.proto)

    @property
    def color(self) -> Color:
        return Color(self._proto.color)

    @color.setter
    def color(self, value: Color):
        self._proto.color.CopyFrom(value.proto)

    @property
    def material_name(self) -> str:
        return self._proto.material_name

    @material_name.setter
    def material_name(self, value: str):
        self._proto.material_name = value

    @property
    def user_name(self) -> str:
        """The name of the layer shown in the KiCad GUI, which may be a default value like "F.Cu"
        or may have been customized by the user. This field does not apply to dielectric layers."""
        return self._proto.user_name

    @user_name.setter
    def user_name(self, value: str):
        self._proto.user_name = value


class BoardFinish(Wrapper):
    """The board finish (e.g. ENIG, HASL, OSP) applied to exposed copper

    .. versionadded:: 0.8.0 (KiCad 10.0.6)"""

    def __init__(self, proto: board_pb2.BoardFinish | None = None):
        self._proto = board_pb2.BoardFinish()
        if proto:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"BoardFinish(type_name={self.type_name!r})"

    @property
    def type_name(self) -> str:
        """The finish type name"""
        return self._proto.type_name

    @type_name.setter
    def type_name(self, value: str):
        self._proto.type_name = value


class BoardImpedanceControl(Wrapper):
    """Whether impedance-controlled routing is enabled for this board

    .. versionadded:: 0.8.0 (KiCad 10.0.6)"""

    def __init__(self, proto: board_pb2.BoardImpedanceControl | None = None):
        self._proto = board_pb2.BoardImpedanceControl()
        if proto:
            self._proto.CopyFrom(proto)

    @property
    def is_controlled(self) -> bool:
        """True if the board uses impedance-controlled widths"""
        return self._proto.is_controlled

    @is_controlled.setter
    def is_controlled(self, value: bool):
        self._proto.is_controlled = value


class BoardEdgeConnector(Wrapper):
    """The type of edge connector present on the board

    .. versionadded:: 0.8.0 (KiCad 10.0.6)"""

    def __init__(self, proto: board_pb2.BoardEdgeConnector | None = None):
        self._proto = board_pb2.BoardEdgeConnector()
        if proto:
            self._proto.CopyFrom(proto)

    @property
    def type(self) -> board_pb2.BoardEdgeConnectorType.ValueType:
        return self._proto.type

    @type.setter
    def type(self, value: board_pb2.BoardEdgeConnectorType.ValueType):
        self._proto.type = value


class EdgePlating(Wrapper):
    """Whether the board edges are plated

    .. versionadded:: 0.8.0 (KiCad 10.0.6)"""

    def __init__(self, proto: board_pb2.EdgePlating | None = None):
        self._proto = board_pb2.EdgePlating()
        if proto:
            self._proto.CopyFrom(proto)

    @property
    def has_edge_plating(self) -> bool:
        """True if board edges are plated with copper"""
        return self._proto.has_edge_plating

    @has_edge_plating.setter
    def has_edge_plating(self, value: bool):
        self._proto.has_edge_plating = value


class BoardEdgeSettings(Wrapper):
    """Settings related to board edges, such as connectors and plating

    .. versionadded:: 0.8.0 (KiCad 10.0.6)"""

    def __init__(self, proto: board_pb2.BoardEdgeSettings | None = None):
        self._proto = board_pb2.BoardEdgeSettings()
        if proto:
            self._proto.CopyFrom(proto)

    @property
    def connector(self) -> BoardEdgeConnector:
        return BoardEdgeConnector(self._proto.connector)

    @connector.setter
    def connector(self, value: BoardEdgeConnector):
        self._proto.connector.CopyFrom(value.proto)

    @property
    def plating(self) -> EdgePlating:
        return EdgePlating(self._proto.plating)

    @plating.setter
    def plating(self, value: EdgePlating):
        self._proto.plating.CopyFrom(value.proto)


class BoardStackup(Wrapper):
    def __init__(self, proto: board_pb2.BoardStackup | None = None):
        self._proto = board_pb2.BoardStackup()
        if proto:
            self._proto.CopyFrom(proto)

    def __repr__(self) -> str:
        return f"BoardStackup(layers={self.layers})"

    @property
    def finish(self) -> BoardFinish:
        """The board finish (e.g. ENIG, HASL, OSP)

        .. versionadded:: 0.8.0
        """
        return BoardFinish(self._proto.finish)

    @finish.setter
    def finish(self, value: BoardFinish):
        self._proto.finish.CopyFrom(value.proto)

    @property
    def impedance(self) -> BoardImpedanceControl:
        """Whether impedance-controlled routing is enabled

        .. versionadded:: 0.8.0
        """
        return BoardImpedanceControl(self._proto.impedance)

    @impedance.setter
    def impedance(self, value: BoardImpedanceControl):
        self._proto.impedance.CopyFrom(value.proto)

    @property
    def edge(self) -> BoardEdgeSettings:
        """Edge connector and plating settings

        .. versionadded:: 0.8.0
        """
        return BoardEdgeSettings(self._proto.edge)

    @edge.setter
    def edge(self, value: BoardEdgeSettings):
        self._proto.edge.CopyFrom(value.proto)

    @property
    def layers(self) -> list[BoardStackupLayer]:
        """The stackup layers, in order from top to bottom of the board"""
        return [BoardStackupLayer(layer) for layer in self._proto.layers]


class Board(EditorCommandsHandler["BoardItem"], VariantsCommandHandler):
    def __init__(self, kicad: KiCadClient, document: DocumentSpecifier):
        """Represents an open board (.kicad_pcb) document in KiCad"""
        self._kicad = kicad
        self._doc = document

    def __repr__(self) -> str:
        return f"Board(filename={self.name})"

    @property
    def client(self) -> KiCadClient:
        """The KiCad client used to communicate with the API server"""
        return self._kicad

    @property
    def document(self) -> DocumentSpecifier:
        """The document specifier for the board"""
        return self._doc

    def get_project(self) -> Project:
        """Returns the project that this board is a part of"""
        return Project(self._kicad, self._doc)

    @property
    def name(self) -> str:
        """Returns the file name of the board"""
        return self._doc.board_filename

    def export_3d(
        self,
        output_path: str,
        settings: Export3DSettings | None = None,
    ) -> JobResult:
        """Exports the board as a 3D model file."""
        command = board_jobs_pb2.RunBoardJobExport3D()
        if settings is not None:
            command.CopyFrom(settings.proto)
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_render(
        self,
        output_path: str,
        settings: RenderSettings | None = None,
    ) -> JobResult:
        """Exports a raytraced 3D render of the board."""
        command = board_jobs_pb2.RunBoardJobExportRender()
        if settings is not None:
            command.CopyFrom(settings.proto)
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_svg(
        self,
        output_path: str,
        plot_settings: PlotSettings | None = None,
        fit_page_to_board: bool = False,
        precision: int = 4,
        page_mode: board_jobs_pb2.BoardJobPaginationMode.ValueType = BoardJobPaginationMode.BJPM_ALL_LAYERS_ONE_PAGE,
    ) -> JobResult:
        """Plots the board to SVG."""
        command = board_jobs_pb2.RunBoardJobExportSvg()
        if plot_settings is not None:
            command.plot_settings.CopyFrom(plot_settings.proto)
        command.fit_page_to_board = fit_page_to_board
        command.precision = precision
        command.page_mode = page_mode
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_dxf(
        self,
        output_path: str,
        plot_settings: PlotSettings | None = None,
        plot_graphic_items_using_contours: bool = False,
        polygon_mode: bool = False,
        units: Units.ValueType = Units.U_MM,
        page_mode: board_jobs_pb2.BoardJobPaginationMode.ValueType = BoardJobPaginationMode.BJPM_ALL_LAYERS_ONE_PAGE,
    ) -> JobResult:
        """Exports the board to DXF."""
        command = board_jobs_pb2.RunBoardJobExportDxf()
        if plot_settings is not None:
            command.plot_settings.CopyFrom(plot_settings.proto)
        command.plot_graphic_items_using_contours = plot_graphic_items_using_contours
        command.polygon_mode = polygon_mode
        command.units = units
        command.page_mode = page_mode
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_pdf(
        self,
        output_path: str,
        plot_settings: PlotSettings | None = None,
        include_metadata: bool = True,
        single_document: bool = True,
        page_mode: board_jobs_pb2.BoardJobPaginationMode.ValueType = BoardJobPaginationMode.BJPM_ALL_LAYERS_ONE_PAGE,
        background_color: str = "",
        front_footprint_property_popups: bool = False,
        back_footprint_property_popups: bool = False,
    ) -> JobResult:
        """Plots the board to PDF."""
        command = board_jobs_pb2.RunBoardJobExportPdf()
        if plot_settings is not None:
            command.plot_settings.CopyFrom(plot_settings.proto)
        command.include_metadata = include_metadata
        command.single_document = single_document
        command.page_mode = page_mode
        command.background_color = background_color
        command.front_footprint_property_popups = front_footprint_property_popups
        command.back_footprint_property_popups = back_footprint_property_popups
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_ps(
        self,
        output_path: str,
        plot_settings: PlotSettings | None = None,
        page_mode: board_jobs_pb2.BoardJobPaginationMode.ValueType = BoardJobPaginationMode.BJPM_ALL_LAYERS_ONE_PAGE,
        track_width_correction: float = 0.0,
        x_scale_adjust: float = 1.0,
        y_scale_adjust: float = 1.0,
        force_a4: bool = False,
        use_global_settings: bool = False,
    ) -> JobResult:
        """Plots the board to PostScript."""
        command = board_jobs_pb2.RunBoardJobExportPs()
        if plot_settings is not None:
            command.plot_settings.CopyFrom(plot_settings.proto)
        command.page_mode = page_mode
        command.track_width_correction = track_width_correction
        command.x_scale_adjust = x_scale_adjust
        command.y_scale_adjust = y_scale_adjust
        command.force_a4 = force_a4
        command.use_global_settings = use_global_settings
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_png(
        self,
        output_path: str,
        plot_settings: PlotSettings | None = None,
        dpi: int | None = None,
        antialiasing: jobs_pb2.AntialiasingMode.ValueType = jobs_pb2.AAM_UNKNOWN,
        page_mode: board_jobs_pb2.BoardJobPaginationMode.ValueType = BoardJobPaginationMode.BJPM_ALL_LAYERS_ONE_PAGE,
    ) -> JobResult:
        """Plots the board to PNG.

        :param output_path: Sets the directory or filename of the export
        :param plot_settings: Controls the general shared schematic plot settings
        :param dpi: Sets the resolution of the generated image.  When omitted, the default of 300
            is used.  KiCad accepts between 72 and 2400 DPI.
        :param antialiasing: Controls whether the output image is anti-aliased (enabled by default)
        :param page_mode: Set to ``BJPM_ALL_LAYERS_ONE_PAGE``, ``output_path`` is taken as a
            filename and one file is created.  Otherwise, the board layers in
            :class:`PlotSettings` are each plotted to a file in the directory given by
            ``output_path``.
        """
        command = board_jobs_pb2.RunBoardJobExportPng()
        if plot_settings is not None:
            command.plot_settings.CopyFrom(plot_settings.proto)
        if dpi is not None:
            command.dpi = dpi
        command.antialiasing = antialiasing
        command.page_mode = page_mode
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_gerbers(
        self,
        output_path: str,
        plot_settings: PlotSettings | None = None,
        use_board_plot_params: bool = False,
        create_gerber_job_file: bool = False,
        include_netlist_attributes: bool = True,
        use_x2_format: bool = True,
        disable_aperture_macros: bool = False,
        use_protel_file_extensions: bool = True,
        precision: board_jobs_pb2.GerberPrecision.ValueType = GerberPrecision.GP_5,
    ) -> JobResult:
        """Plots the board to Gerber files."""
        command = board_jobs_pb2.RunBoardJobExportGerbers()
        if plot_settings is not None:
            command.plot_settings.CopyFrom(plot_settings.proto)
        command.use_board_plot_params = use_board_plot_params
        command.create_gerber_job_file = create_gerber_job_file
        command.include_netlist_attributes = include_netlist_attributes
        command.use_x2_format = use_x2_format
        command.disable_aperture_macros = disable_aperture_macros
        command.use_protel_file_extensions = use_protel_file_extensions
        command.precision = precision
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_drill(
        self,
        output_path: str,
        format: board_jobs_pb2.DrillFormat.ValueType = DrillFormat.DF_EXCELLON,
        # Common options
        origin: board_jobs_pb2.DrillOrigin.ValueType = DrillOrigin.DO_UNKNOWN,
        map_format: board_jobs_pb2.DrillMapFormat.ValueType = DrillMapFormat.DMF_UNKNOWN,
        report_filename: str = "",
        # Gerber specific
        precision: board_jobs_pb2.DrillGerberPrecision.ValueType = DrillGerberPrecision.DGP_UNKNOWN,
        generate_tenting: bool = False,
        # Excellon specific
        units: Units.ValueType = Units.U_UNKNOWN,
        zeros_format: board_jobs_pb2.DrillZerosFormat.ValueType = DrillZerosFormat.DZF_UNKNOWN,
        route_oval_holes: bool = False,
        combine_pth_npth: bool = True,
        minimal_header: bool = False,
        mirror_y: bool = False,
    ) -> JobResult:
        """Exports NC drill files from the board."""
        command = board_jobs_pb2.RunBoardJobExportDrill()
        command.format = format
        # For both drills
        command.origin = origin
        command.map_format = map_format
        command.report_format = (
            DrillReportFormat.DRF_STANDARD if report_filename else DrillReportFormat.DRF_UNKNOWN
        )
        if report_filename:
            command.report_filename = os.path.join(output_path, report_filename)
        # For Gerber
        command.gerber_precision = precision
        command.gerber_generate_tenting = generate_tenting
        # For Excellon
        command.units = units
        command.zeros_format = zeros_format
        command.excellon.route_oval_holes = route_oval_holes
        command.excellon.combine_pth_npth = combine_pth_npth
        command.excellon.minimal_header = minimal_header
        command.excellon.mirror_y = mirror_y
        # Document
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_drill_gerber(
        self,
        output_path: str,
        origin: board_jobs_pb2.DrillOrigin.ValueType = DrillOrigin.DO_UNKNOWN,
        map_format: board_jobs_pb2.DrillMapFormat.ValueType = DrillMapFormat.DMF_UNKNOWN,
        report_filename: str = "",
        precision: board_jobs_pb2.DrillGerberPrecision.ValueType = DrillGerberPrecision.DGP_UNKNOWN,
        generate_tenting: bool = False,
    ) -> JobResult:
        """Exports gerber NC drill files from the board."""
        return self.export_drill(
            output_path,
            format=DrillFormat.DF_GERBER,
            origin=origin,
            map_format=map_format,
            report_filename=report_filename,
            precision=precision,
            generate_tenting=generate_tenting,
        )

    def export_drill_excellon(
        self,
        output_path: str,
        origin: board_jobs_pb2.DrillOrigin.ValueType = DrillOrigin.DO_UNKNOWN,
        map_format: board_jobs_pb2.DrillMapFormat.ValueType = DrillMapFormat.DMF_UNKNOWN,
        report_filename: str = "",
        units: Units.ValueType = Units.U_UNKNOWN,
        zeros_format: board_jobs_pb2.DrillZerosFormat.ValueType = DrillZerosFormat.DZF_UNKNOWN,
        route_oval_holes: bool = False,
        combine_pth_npth: bool = True,
        minimal_header: bool = False,
        mirror_y: bool = False,
    ) -> JobResult:
        """Exports excellon NC drill files from the board."""
        return self.export_drill(
            output_path,
            format=DrillFormat.DF_EXCELLON,
            origin=origin,
            map_format=map_format,
            report_filename=report_filename,
            units=units,
            zeros_format=zeros_format,
            route_oval_holes=route_oval_holes,
            combine_pth_npth=combine_pth_npth,
            minimal_header=minimal_header,
            mirror_y=mirror_y,
        )

    def export_position(
        self,
        output_path: str,
        settings: PositionExportSettings | None = None,
    ) -> JobResult:
        """Exports pick-and-place position files from the board."""
        command = board_jobs_pb2.RunBoardJobExportPosition()
        if settings is not None:
            command.CopyFrom(settings.proto)
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_gencad(
        self,
        output_path: str,
        flip_bottom_pads: bool = False,
        use_individual_shapes: bool = False,
        store_origin_coords: bool = False,
        use_drill_origin: bool = False,
        use_unique_pins: bool = False,
    ) -> JobResult:
        """Exports the board to GenCAD format."""
        command = board_jobs_pb2.RunBoardJobExportGencad()
        command.flip_bottom_pads = flip_bottom_pads
        command.use_individual_shapes = use_individual_shapes
        command.store_origin_coords = store_origin_coords
        command.use_drill_origin = use_drill_origin
        command.use_unique_pins = use_unique_pins
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_ipc2581(
        self,
        output_path: str,
        settings: Ipc2581ExportSettings | None = None,
    ) -> JobResult:
        """Exports the board to IPC-2581 format."""
        command = board_jobs_pb2.RunBoardJobExportIpc2581()
        if settings is not None:
            command.CopyFrom(settings.proto)
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_ipc_d356(
        self,
        output_path: str,
    ) -> JobResult:
        """Exports a board netlist in IPC-D-356 format."""
        command = board_jobs_pb2.RunBoardJobExportIpcD356()
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def import_netlist(
        self,
        netlist_path: str,
        dry_run: bool = False,
        match_mode: board_commands_pb2.NetlistMatchMode.ValueType = NetlistMatchMode.NMM_UUID,
        delete_extra_footprints: bool = True,
        update_footprints: bool = True,
        transfer_groups: bool = True,
        override_locks: bool = False,
    ) -> ImportNetlistResult:
        """Imports a netlist exported from the schematic and updates the board."""
        command = board_commands_pb2.ImportNetlist()
        command.board.CopyFrom(self._doc)
        command.netlist_path = netlist_path
        command.match_mode = match_mode
        command.delete_extra_footprints = delete_extra_footprints
        command.update_footprints = update_footprints
        command.transfer_groups = transfer_groups
        command.override_locks = override_locks
        command.dry_run = dry_run
        return ImportNetlistResult(
            self._kicad.send(command, board_commands_pb2.ImportNetlistResponse)
        )

    def export_odb(
        self,
        output_path: str,
        drawing_sheet: str = "",
        variant: str = "",
        units: Units.ValueType = Units.U_MM,
        precision: int = 6,
        compression: board_jobs_pb2.OdbCompression.ValueType = OdbCompression.ODBC_ZIP,
    ) -> JobResult:
        """Exports the board to ODB++ format."""
        command = board_jobs_pb2.RunBoardJobExportODB()
        command.drawing_sheet = drawing_sheet
        command.variant = variant
        command.units = units
        command.precision = precision
        command.compression = compression
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_stats(
        self,
        output_path: str,
        format: board_jobs_pb2.StatsOutputFormat.ValueType = StatsOutputFormat.SOF_REPORT,
        units: Units.ValueType = Units.U_MM,
        exclude_footprints_without_pads: bool = False,
        subtract_holes_from_board_area: bool = False,
        subtract_holes_from_copper_areas: bool = False,
    ) -> JobResult:
        """Exports board statistics."""
        command = board_jobs_pb2.RunBoardJobExportStats()
        command.format = format
        command.units = units
        command.exclude_footprints_without_pads = exclude_footprints_without_pads
        command.subtract_holes_from_board_area = subtract_holes_from_board_area
        command.subtract_holes_from_copper_areas = subtract_holes_from_copper_areas
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def _item_from_message(self, message: Any) -> BoardItem:
        """Converts an unwrapped protobuf message into a concrete board item wrapper"""
        return self._to_concrete_items([unwrap(message)])[0]

    def _to_concrete_items(self, items: Sequence[Wrapper]) -> list[BoardItem]:
        items_converted: list[BoardItem] = []
        for it in items:
            assert isinstance(it, BoardItem)

            if isinstance(it, Group):
                it._item_resolver = self.get_items_by_id
            elif isinstance(it, BoardShape):
                it = to_concrete_board_shape(cast(BoardShape, it))
            elif isinstance(it, Dimension):
                it = to_concrete_dimension(cast(Dimension, it))

            items_converted.append(it)
        return items_converted

    def get_items(
        self,
        types: KiCadObjectType.ValueType | Sequence[KiCadObjectType.ValueType] | None = None,
    ) -> Sequence[BoardItem]:
        """Retrieves items from the board, optionally filtering to a single or set of types

        Providing no ``types`` filter will result in all valid types for the given document
        being retrieved on KiCad 10.0.7 and newer, and is an error on older versions."""
        return self._to_concrete_items(super().get_items(types))

    def get_items_by_id(self, ids: KIID | Sequence[KIID]) -> Sequence[BoardItem]:
        """Retrieves items from the board by their KIID (internal unique identifier)

        .. versionadded:: 0.7.0 (KiCad 10.0.0)
        """
        return self._to_concrete_items(super().get_items_by_id(ids))

    def get_items_by_net(
        self,
        nets: Net | Sequence[Net],
        types: KiCadObjectType.ValueType | Sequence[KiCadObjectType.ValueType] | None = None,
    ) -> Sequence[Item]:
        """Retrieves items from the board, filtered by one or more nets

        .. versionadded:: 0.7.0 (KiCad 10.0.1)"""
        command = board_commands_pb2.GetItemsByNet()
        command.header.document.CopyFrom(self._doc)

        if isinstance(types, int):
            command.types.append(types)
        elif types is not None:
            command.types.extend(types)

        if isinstance(nets, Net):
            command.nets.append(nets.proto)
        else:
            command.nets.extend([net.proto for net in nets])

        return self._to_concrete_items(
            [unwrap(item) for item in self._kicad.send(command, GetItemsResponse).items]
        )

    def get_items_by_netclass(
        self,
        net_classes: str | Sequence[str],
        types: KiCadObjectType.ValueType | Sequence[KiCadObjectType.ValueType] | None = None,
    ) -> Sequence[Item]:
        """Retrieves items from the board, filtered by one or more net class names

        .. versionadded:: 0.7.0 (KiCad 10.0.1)"""
        command = board_commands_pb2.GetItemsByNetClass()
        command.header.document.CopyFrom(self._doc)

        if isinstance(types, int):
            command.types.append(types)
        elif types is not None:
            command.types.extend(types)

        if isinstance(net_classes, str):
            command.net_classes.append(net_classes)
        else:
            command.net_classes.extend(net_classes)

        return self._to_concrete_items(
            [unwrap(item) for item in self._kicad.send(command, GetItemsResponse).items]
        )

    def get_connected_items(
        self,
        items: BoardItem | KIID | Sequence[BoardItem | KIID],
        types: KiCadObjectType.ValueType | Sequence[KiCadObjectType.ValueType] | None = None,
    ) -> Sequence[Item]:
        """Retrieves items that are copper-connected to the given source item(s) or item IDs

        .. versionadded:: 0.7.0 (KiCad 10.0.1)"""
        command = board_commands_pb2.GetConnectedItems()
        command.header.document.CopyFrom(self._doc)

        if isinstance(types, int):
            command.types.append(types)
        elif types is not None:
            command.types.extend(types)

        source_items = [items] if isinstance(items, (BoardItem, KIID)) else items

        for source in source_items:
            command.items.append(source.id if isinstance(source, BoardItem) else source)

        return self._to_concrete_items(
            [unwrap(item) for item in self._kicad.send(command, GetItemsResponse).items]
        )

    def get_tracks(self) -> Sequence[Track | ArcTrack]:
        """Retrieves all tracks and arc tracks on the board"""
        return [
            cast(Track, item) if isinstance(item, Track) else cast(ArcTrack, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_PCB_TRACE, KiCadObjectType.KOT_PCB_ARC]
            )
        ]

    def get_vias(self) -> Sequence[Via]:
        """Retrieves all vias on the board"""
        return [cast(Via, item) for item in self.get_items(types=[KiCadObjectType.KOT_PCB_VIA])]

    def get_pads(self) -> Sequence[Pad]:
        """Retrieves all pads on the board (note that pads belong to footprints, not the board
        itself)"""
        return [cast(Pad, item) for item in self.get_items(types=[KiCadObjectType.KOT_PCB_PAD])]

    def get_footprints(self) -> Sequence[FootprintInstance]:
        """Retrieves all footprints on the board"""
        return [
            cast(FootprintInstance, item)
            for item in self.get_items(types=[KiCadObjectType.KOT_PCB_FOOTPRINT])
        ]

    def get_shapes(self) -> Sequence[BoardShape]:
        """Retrieves all graphic shapes (not including tracks or text) on the board"""
        return [
            item
            for item in (
                to_concrete_board_shape(cast(BoardShape, item))
                for item in self.get_items(types=[KiCadObjectType.KOT_PCB_SHAPE])
            )
            if item is not None
        ]

    def get_dimensions(self) -> Sequence[Dimension]:
        """Retrieves all dimension objects on the board"""
        return [
            item
            for item in (
                to_concrete_dimension(cast(Dimension, item))
                for item in self.get_items(types=[KiCadObjectType.KOT_PCB_DIMENSION])
            )
            if item is not None
        ]

    def get_text(self) -> Sequence[BoardText | BoardTextBox]:
        """Retrieves all text objects on the board"""
        return [
            cast(BoardText, item) if isinstance(item, BoardText) else cast(BoardTextBox, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_PCB_TEXT, KiCadObjectType.KOT_PCB_TEXTBOX]
            )
        ]

    def get_barcodes(self) -> Sequence[Barcode]:
        """Retrieves all barcode objects on the board

        .. versionadded:: 0.7.0"""
        return [
            cast(Barcode, item) for item in self.get_items(types=[KiCadObjectType.KOT_PCB_BARCODE])
        ]

    def get_reference_images(self) -> Sequence[ReferenceImage]:
        """Retrieves all reference image objects on the board

        .. versionadded:: 0.7.0"""
        return [
            cast(ReferenceImage, item)
            for item in self.get_items(types=[KiCadObjectType.KOT_PCB_REFERENCE_IMAGE])
        ]

    def get_tables(self) -> Sequence[Table]:
        """Retrieves all table objects on the board

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return [
            cast(Table, item) for item in self.get_items(types=[KiCadObjectType.KOT_PCB_TABLE])
        ]

    def get_grid_items(self) -> Sequence[GridItem]:
        """Retrieves all grid items on the board.

        .. versionadded:: 0.x.0 (KiCad 11)"""
        return [
            cast(GridItem, item)
            for item in self.get_items(types=[KiCadObjectType.KOT_PCB_GRIDITEM])
        ]

    def get_constraints(self) -> Sequence[Constraint]:
        """Retrieves all constraint objects on the board.

        .. versionadded:: 0.x.0 (KiCad 11)"""
        return [
            cast(Constraint, item)
            for item in self.get_items(types=[KiCadObjectType.KOT_PCB_CONSTRAINT])
        ]

    def get_reference_points(self) -> Sequence[ReferencePoint]:
        """Retrieves all reference point objects on the board

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        return [
            cast(ReferencePoint, item)
            for item in self.get_items(types=[KiCadObjectType.KOT_PCB_POINT])
        ]

    def get_zones(self) -> Sequence[Zone]:
        """Retrieves all zones (including rule areas and graphic zones) on the board"""
        return [cast(Zone, item) for item in self.get_items(types=[KiCadObjectType.KOT_PCB_ZONE])]

    def get_groups(self) -> Sequence[Group]:
        """Retrieves all groups on the board

        .. versionadded:: 0.7.0 (KiCad 10.0.0)"""
        return [
            cast(Group, item) for item in self.get_items(types=[KiCadObjectType.KOT_PCB_GROUP])
        ]

    def flip_items(
        self,
        items: BoardItem | Sequence[BoardItem],
        direction: board_commands_pb2.BoardFlipDirection.ValueType = BoardFlipDirection.BFD_LEFT_RIGHT,
    ) -> list[BoardItem]:
        """Flips one or more board items to the opposite side of the board.

        The given items must already exist on the board; each is flipped in place and the
        Python item passed in is updated with the new state from KiCad.  Returns the set
        of items that were successfully flipped.

        :param items: one or more board items to flip
        :param direction: ``BFD_LEFT_RIGHT`` (mirror around the Y axis) or
                          ``BFD_TOP_BOTTOM`` (mirror around the X axis)

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        command = board_commands_pb2.FlipItems()
        command.header.document.CopyFrom(self._doc)
        command.direction = direction

        if isinstance(items, BoardItem):
            items = [items]
        else:
            items = list(items)

        command.items.extend([item.id for item in items])

        if len(command.items) == 0:
            return []

        response = self._kicad.send(command, board_commands_pb2.FlipItemsResponse)

        flipped: list[BoardItem] = []
        for item, result in zip(items, response.flipped_items):
            if result.status.code != editor_commands_pb2.ItemStatusCode.ISC_OK:
                continue
            updated = self._to_concrete_items([unwrap(result.item)])[0]
            item.proto.CopyFrom(updated.proto)
            flipped.append(updated)
        return flipped

    def flip_items_by_id(
        self,
        items: KIID | Sequence[KIID],
        direction: board_commands_pb2.BoardFlipDirection.ValueType = BoardFlipDirection.BFD_LEFT_RIGHT,
    ) -> list[BoardItem]:
        """Flips one or more board items to the opposite side of the board by their unique IDs.

        Returns the flipped items as returned by KiCad.  Items that could not be flipped (for
        example because the ID doesn't exist or the type is not a flippable board item) will be
        omitted.

        :param items: one or more item IDs (KIID) to flip
        :param direction: ``BFD_LEFT_RIGHT`` (mirror around the Y axis) or
                          ``BFD_TOP_BOTTOM`` (mirror around the X axis)

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        command = board_commands_pb2.FlipItems()
        command.header.document.CopyFrom(self._doc)
        command.direction = direction

        if isinstance(items, KIID):
            command.items.append(items)
        else:
            command.items.extend(items)

        if len(command.items) == 0:
            return []

        response = self._kicad.send(command, board_commands_pb2.FlipItemsResponse)

        return self._to_concrete_items(
            [
                unwrap(result.item)
                for result in response.flipped_items
                if result.status.code == editor_commands_pb2.ItemStatusCode.ISC_OK
            ]
        )

    def get_nets(self, netclass_filter: str | Sequence[str] | None = None) -> Sequence[Net]:
        """Retrieves all nets on the board, optionally filtering by net class"""
        command = board_commands_pb2.GetNets()
        command.board.CopyFrom(self._doc)

        if isinstance(netclass_filter, str):
            command.netclass_filter.append(netclass_filter)
        elif netclass_filter is not None:
            command.netclass_filter.extend(netclass_filter)

        return [
            Net(net) for net in self._kicad.send(command, board_commands_pb2.NetsResponse).nets
        ]

    def get_netclass_for_nets(self, nets: Net | Sequence[Net]) -> dict[str, NetClass]:
        """Retrieves the net class for one or more nets on the board"""
        cmd = board_commands_pb2.GetNetClassForNets()
        if isinstance(nets, Net):
            cmd.net.append(nets.proto)
        else:
            cmd.net.extend([net.proto for net in nets])

        response = self._kicad.send(cmd, board_commands_pb2.NetClassForNetsResponse)
        return {key: NetClass(value) for key, value in response.classes.items()}

    def get_selection(
        self,
        types: KiCadObjectType.ValueType | Sequence[KiCadObjectType.ValueType] | None = None,
    ) -> Sequence[BoardItem]:
        return self._to_concrete_items(super().get_selection(types))

    def get_stackup(self) -> BoardStackup:
        """Retrieves the stackup for the board"""
        command = board_commands_pb2.GetBoardStackup()
        command.board.CopyFrom(self._doc)
        return BoardStackup(
            self._kicad.send(command, board_commands_pb2.BoardStackupResponse).stackup
        )

    def get_copper_layer_count(self) -> int:
        """
        :return: The number of copper layers on the current board

        .. versionadded:: 0.5.0 (with KiCad 9.0.5)
        """
        cmd = board_commands_pb2.GetBoardEnabledLayers()
        cmd.board.CopyFrom(self._doc)
        response = self._kicad.send(cmd, board_commands_pb2.BoardEnabledLayersResponse)
        return response.copper_layer_count

    def get_enabled_layers(self) -> list[board_types_pb2.BoardLayer.ValueType]:
        """
        Retrieves the list of all enabled layers in the board, including copper and non-copper layers.

        :return: A list of enabled BoardLayer enums.

        .. versionadded:: 0.5.0 (with KiCad 9.0.5)
        """
        cmd = board_commands_pb2.GetBoardEnabledLayers()
        cmd.board.CopyFrom(self._doc)
        response = self._kicad.send(cmd, board_commands_pb2.BoardEnabledLayersResponse)
        return list(response.layers)

    def set_enabled_layers(
        self,
        copper_layer_count: int,
        layers: Sequence[board_types_pb2.BoardLayer.ValueType],
    ) -> list[board_types_pb2.BoardLayer.ValueType]:
        """
        Sets the copper layer count and enabled non-copper layers for the board.

        WARNING: Any existing content on layers that are removed by this call is deleted. This operation cannot be undone.

        :param copper_layer_count: The number of copper layers to enable (must be even and >= 2).
        :param layers: The non-copper layers to enable.
        :return: The updated list of enabled BoardLayer enums.

        .. versionadded:: 0.5.0 (with KiCad 9.0.5)
        """
        cmd = board_commands_pb2.SetBoardEnabledLayers()
        cmd.board.CopyFrom(self._doc)
        cmd.copper_layer_count = copper_layer_count
        cmd.layers.extend(layers)
        response = self._kicad.send(cmd, board_commands_pb2.BoardEnabledLayersResponse)
        return list(response.layers)

    def get_graphics_defaults(self) -> dict[int, BoardLayerGraphicsDefaults]:
        """Retrieves the default graphics properties for each layer class on the board"""
        cmd = board_commands_pb2.GetGraphicsDefaults()
        cmd.board.CopyFrom(self._doc)
        reply = self._kicad.send(cmd, board_commands_pb2.GraphicsDefaultsResponse)
        return {
            board_pb2.BoardLayerClass.BLC_SILKSCREEN: BoardLayerGraphicsDefaults(
                reply.defaults.layers[0]
            ),
            board_pb2.BoardLayerClass.BLC_COPPER: BoardLayerGraphicsDefaults(
                reply.defaults.layers[1]
            ),
            board_pb2.BoardLayerClass.BLC_EDGES: BoardLayerGraphicsDefaults(
                reply.defaults.layers[2]
            ),
            board_pb2.BoardLayerClass.BLC_COURTYARD: BoardLayerGraphicsDefaults(
                reply.defaults.layers[3]
            ),
            board_pb2.BoardLayerClass.BLC_FABRICATION: BoardLayerGraphicsDefaults(
                reply.defaults.layers[4]
            ),
            board_pb2.BoardLayerClass.BLC_OTHER: BoardLayerGraphicsDefaults(
                reply.defaults.layers[5]
            ),
        }

    def get_design_rules(self) -> BoardDesignRulesResponse:
        """Retrieves the board design rules (not including custom rules).

        .. versionadded:: 0.7.0 (with KiCad 11)"""
        cmd = board_commands_pb2.GetBoardDesignRules()
        cmd.board.CopyFrom(self._doc)
        return BoardDesignRulesResponse(
            self._kicad.send(cmd, board_commands_pb2.BoardDesignRulesResponse)
        )

    def set_design_rules(self, rules: BoardDesignRules) -> BoardDesignRulesResponse:
        """Sets the board design rules.

        .. versionadded:: 0.7.0 (with KiCad 11)"""
        cmd = board_commands_pb2.SetBoardDesignRules()
        cmd.board.CopyFrom(self._doc)
        cmd.rules.CopyFrom(rules.proto)
        return BoardDesignRulesResponse(
            self._kicad.send(cmd, board_commands_pb2.BoardDesignRulesResponse)
        )

    def get_custom_design_rules(self) -> CustomRulesResponse:
        """Retrieves custom design rules and parse status / any error messages.

        .. versionadded:: 0.7.0 (with KiCad 11)"""
        cmd = board_commands_pb2.GetCustomDesignRules()
        cmd.board.CopyFrom(self._doc)
        return CustomRulesResponse(self._kicad.send(cmd, board_commands_pb2.CustomRulesResponse))

    def set_custom_design_rules(
        self,
        rules: CustomRule | Sequence[CustomRule],
    ) -> CustomRulesResponse:
        """Sets custom design rules.

        .. versionadded:: 0.7.0 (with KiCad 11)"""
        cmd = board_commands_pb2.SetCustomDesignRules()
        cmd.board.CopyFrom(self._doc)

        if isinstance(rules, CustomRule):
            cmd.rules.append(rules.proto)
        else:
            cmd.rules.extend([rule.proto for rule in rules])

        return CustomRulesResponse(self._kicad.send(cmd, board_commands_pb2.CustomRulesResponse))

    def get_embedded_files(self) -> EmbeddedFiles:
        """Retrieves the files embedded in the board

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        cmd = board_commands_pb2.GetEmbeddedFiles()
        cmd.board.CopyFrom(self._doc)
        response = self._kicad.send(cmd, embedded_files_pb2.EmbeddedFiles)
        return EmbeddedFiles(response)

    def add_embedded_files(self, files: EmbeddedFile | Sequence[EmbeddedFile]):
        """Appends the given file(s) to the board's embedded files

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        cmd = board_commands_pb2.AddEmbeddedFiles()
        cmd.board.CopyFrom(self._doc)
        files_list = [files] if isinstance(files, EmbeddedFile) else files
        cmd.files.files.extend([file.proto for file in files_list])
        self._kicad.send(cmd, Empty)

    def set_embedded_files(self, files: EmbeddedFile | Sequence[EmbeddedFile]):
        """Replaces all files embedded in the board with the given file(s)

        .. versionadded:: 0.9.0 (KiCad 10.0.7)"""
        cmd = board_commands_pb2.SetEmbeddedFiles()
        cmd.board.CopyFrom(self._doc)
        files_list = [files] if isinstance(files, EmbeddedFile) else files
        cmd.files.files.extend([file.proto for file in files_list])
        self._kicad.send(cmd, Empty)

    def get_title_block_info(self) -> TitleBlockInfo:
        """Retrieves the title block information for the board"""
        cmd = editor_commands_pb2.GetTitleBlockInfo()
        cmd.document.CopyFrom(self._doc)
        return TitleBlockInfo(self._kicad.send(cmd, base_types_pb2.TitleBlockInfo))

    def set_title_block_info(self, title_block: TitleBlockInfo):
        """Sets the title block information for the board

        .. versionadded:: 0.7.0 (with KiCad 10.0.1)"""
        cmd = editor_commands_pb2.SetTitleBlockInfo()
        cmd.document.CopyFrom(self._doc)
        cmd.title_block.CopyFrom(title_block.proto)
        self._kicad.send(cmd, Empty)

    def get_origin(self, origin_type: board_commands_pb2.BoardOriginType.ValueType) -> Vector2:
        """Retrieves the specified (grid or drill/place) board origin

        .. versionadded:: 0.3.0"""
        cmd = board_commands_pb2.GetBoardOrigin()
        cmd.board.CopyFrom(self._doc)
        cmd.type = origin_type
        return Vector2(self._kicad.send(cmd, base_types_pb2.Vector2))

    def set_origin(
        self, origin_type: board_commands_pb2.BoardOriginType.ValueType, origin: Vector2
    ):
        """Sets the specified (grid or drill/place) board origin

        .. versionadded:: 0.3.0"""
        cmd = board_commands_pb2.SetBoardOrigin()
        cmd.board.CopyFrom(self._doc)
        cmd.type = origin_type
        cmd.origin.CopyFrom(origin.proto)
        self._kicad.send(cmd, Empty)

    def get_layer_name(self, layer: board_types_pb2.BoardLayer.ValueType) -> str:
        """Retrieves the user-visible name of a given layer, which may be a default value like "F.Cu"
        or may have been customized by the user.  This method does not apply to dielectric layers.

        .. versionadded:: 0.6.0 (KiCad 9.0.8)"""
        cmd = board_commands_pb2.GetBoardLayerName()
        cmd.board.CopyFrom(self._doc)
        cmd.layer = layer
        return self._kicad.send(cmd, board_commands_pb2.BoardLayerNameResponse).name

    def get_layer_by_name(self, layer_name: str) -> board_types_pb2.BoardLayer.ValueType:
        """Retrieves a board layer ID from the given name, which may be either a KiCad standard
        layer name (e.g. ``In1.Cu``) or a user-defined name in the current board.  Returns
        ``BL_UNDEFINED`` if the given name doesn't map to any layer in the current board.

        .. versionadded:: 0.8.0 (KiCad 10.0.6)"""
        cmd = board_commands_pb2.GetBoardLayerByName()
        cmd.board.CopyFrom(self._doc)
        cmd.name = layer_name
        return self._kicad.send(cmd, board_commands_pb2.BoardLayerResponse).layer

    @overload
    def expand_text_variables(self, text: str, *, expand_env_vars: bool = False) -> str: ...

    @overload
    def expand_text_variables(
        self, text: list[str], *, expand_env_vars: bool = False
    ) -> list[str]: ...

    def expand_text_variables(
        self, text: str | list[str], *, expand_env_vars: bool = False
    ) -> str | list[str]:
        """Expands text variables in a string or list of strings.  Any text variables that do
        not exist will be left as-is in the output.

        :param expand_env_vars: will expand environment variables in addition to built-in
            KiCad text variables when True.
        """
        command = project_commands_pb2.ExpandTextVariables()
        command.document.CopyFrom(self._doc)
        command.expand_env_vars = expand_env_vars
        if isinstance(text, list):
            command.text.extend(text)
        else:
            command.text.append(text)
        response = self._kicad.send(command, project_commands_pb2.ExpandTextVariablesResponse)
        return (
            [text for text in response.text]
            if isinstance(text, list)
            else response.text[0]
            if len(response.text) > 0
            else ""
        )

    @overload
    def get_item_bounding_box(
        self, items: BoardItem, include_text: bool = False
    ) -> Box2 | None: ...

    @overload
    def get_item_bounding_box(
        self, items: Sequence[BoardItem], include_text: bool = False
    ) -> list[Box2 | None]: ...

    def get_item_bounding_box(
        self, items: BoardItem | Sequence[BoardItem], include_text: bool = False
    ) -> Box2 | None | list[Box2 | None]:
        """Gets the KiCad-calculated bounding box for an item or items, returning None if the item
        does not exist or has no bounding box"""
        cmd = editor_commands_pb2.GetBoundingBox()
        cmd.header.document.CopyFrom(self._doc)
        cmd.mode = (
            editor_commands_pb2.BoundingBoxMode.BBM_ITEM_AND_CHILD_TEXT
            if include_text
            else editor_commands_pb2.BoundingBoxMode.BBM_ITEM_ONLY
        )

        if isinstance(items, BoardItem):
            cmd.items.append(items.id)
        else:
            cmd.items.extend([i.id for i in items])

        response = self._kicad.send(cmd, editor_commands_pb2.GetBoundingBoxResponse)

        if isinstance(items, BoardItem):
            return Box2.from_proto(response.boxes[0]) if len(response.boxes) == 1 else None

        item_to_bbox = {item.value: bbox for item, bbox in zip(response.items, response.boxes)}
        return [
            Box2.from_proto(box)
            for box in (item_to_bbox.get(item.id.value, None) for item in items)
            if box is not None
        ]

    @overload
    def get_pad_shapes_as_polygons(
        self, pads: Pad, layer: BoardLayer.ValueType = BoardLayer.BL_F_Cu
    ) -> PolygonWithHoles | None: ...

    @overload
    def get_pad_shapes_as_polygons(
        self, pads: Sequence[Pad], layer: BoardLayer.ValueType = BoardLayer.BL_F_Cu
    ) -> list[PolygonWithHoles | None]: ...

    def get_pad_shapes_as_polygons(
        self, pads: Pad | Sequence[Pad], layer: BoardLayer.ValueType = BoardLayer.BL_F_Cu
    ) -> PolygonWithHoles | None | list[PolygonWithHoles | None]:
        """Retrieves the polygonal shape of one or more pads on a given layer.  If a pad does not
        exist or has no polygonal shape on the given layer, None will be returned for that pad."""
        cmd = board_commands_pb2.GetPadShapeAsPolygon()
        cmd.board.CopyFrom(self._doc)
        cmd.layer = layer

        if isinstance(pads, Pad):
            cmd.pads.append(pads.id)
        else:
            cmd.pads.extend([pad.id for pad in pads])

        response = self._kicad.send(cmd, board_commands_pb2.PadShapeAsPolygonResponse)

        if isinstance(pads, Pad):
            return PolygonWithHoles(response.polygons[0]) if len(response.polygons) == 1 else None

        pad_to_polygon = {
            pad.value: polygon for pad, polygon in zip(response.pads, response.polygons)
        }
        return [
            PolygonWithHoles(p)
            for p in (pad_to_polygon.get(pad.id.value, None) for pad in pads)
            if p is not None
        ]

    def check_padstack_presence_on_layers(
        self,
        items: BoardItem | Iterable[BoardItem],
        layers: board_types_pb2.BoardLayer.ValueType
        | Iterable[board_types_pb2.BoardLayer.ValueType],
    ) -> dict[BoardItem, dict[board_types_pb2.BoardLayer.ValueType, bool]]:
        """Checks if the given items with padstacks (pads or vias) have content on the given layers.

        :param items: The items to check (one or more pads or vias).
        :param layers: The layer or layers to check for padstack presence.
        :return: A dictionary mapping each item to a dictionary of layers and their presence on
                 the given layer.

        .. versionadded:: 0.4.0 with KiCad 9.0.3
        """
        cmd = board_commands_pb2.CheckPadstackPresenceOnLayers()
        cmd.board.CopyFrom(self._doc)

        items_map: dict[str, BoardItem] = {}

        if isinstance(items, BoardItem):
            cmd.items.append(items.id)
            items_map[items.id.value] = items
        else:
            cmd.items.extend([item.id for item in items])
            items_map.update({item.id.value: item for item in items})

        if isinstance(layers, int):
            cmd.layers.append(layers)
        else:
            cmd.layers.extend(layers)

        response = self._kicad.send(cmd, board_commands_pb2.PadstackPresenceResponse)

        result: dict[BoardItem, dict[board_types_pb2.BoardLayer.ValueType, bool]] = {}
        for entry in response.entries:
            if entry.item.value not in items_map:
                continue

            item = items_map[entry.item.value]
            layer = entry.layer
            presence = entry.presence is board_commands_pb2.PadstackPresence.PSP_PRESENT

            if item not in result:
                result[item] = {}

            result[item][layer] = presence

        return result

    def interactive_move(self, items: KIID | Iterable[KIID]):
        """Initiates an interactive move operation on one or more items on the board.  The user
        will be able to move the items interactively in the KiCad editor.  This is a blocking
        operation; this function will return immediately but future API calls will return ``AS_BUSY``
        until the interactive move is complete."""
        cmd = board_commands_pb2.InteractiveMoveItems()
        cmd.board.CopyFrom(self._doc)

        if isinstance(items, KIID):
            cmd.items.append(items)
        else:
            cmd.items.extend(items)

        self._kicad.send(cmd, Empty)

    def refill_zones(
        self,
        zones: KIID | Iterable[KIID] | None = None,
        block=True,
        max_poll_seconds: float = 30.0,
        poll_interval_seconds: float = 0.5,
    ):
        """Refills all zones on the board.  If block is True, this function will block until the
        refill operation is complete.  If block is False, this function will return immediately,
        and future API calls will return ``AS_BUSY`` until the refill operation is complete.

        :param zones: An optional list of zone IDs to fill.  If empty or absent, all zones will be
                      filled (Since: 0.x.0 / KiCad 11.0)
        :param block: When True (default), this call will block until the zone fill completes
                      (which could take many seconds or even minutes in some cases).  When False,
                      this call will return immediately, but the KiCad API server will not handle
                      any more requests until the zone fill has been completed.
        :param max_poll_seconds: How long to wait (when block is True) for the zone fill to finish.
        :param poll_interval_seconds: How often to check (when block is True) for the fill to have
                                      finished.
        """
        cmd = board_commands_pb2.RefillZones()
        cmd.board.CopyFrom(self._doc)

        if isinstance(zones, KIID):
            cmd.zones.append(zones)
        elif zones is not None:
            cmd.zones.extend(zones)

        self._kicad.send(cmd, Empty)

        if not block:
            return

        # Zone fill is a blocking operation that can block the entire event loop.
        # To hide this from API users somewhat, do an initial busy loop here
        sleeps = 0

        while sleeps < max_poll_seconds:
            sleep(poll_interval_seconds)
            try:
                self._kicad.send(Ping(), Empty)
            except OSError:
                # transport-layer timeout
                continue
            except ApiError as e:
                if e.code == ApiStatusCode.AS_BUSY:
                    continue
                else:
                    raise
            break

    def hit_test(self, item: Item, position: Vector2, tolerance: int = 0) -> bool:
        """Performs a hit test on a board item at a given position"""
        cmd = HitTest()
        cmd.header.document.CopyFrom(self._doc)
        cmd.id.CopyFrom(item.id)
        cmd.position.CopyFrom(position.proto)
        cmd.tolerance = tolerance
        return self._kicad.send(cmd, HitTestResponse).result == HitTestResult.HTR_HIT

    def get_visible_layers(self) -> Sequence[board_types_pb2.BoardLayer.ValueType]:
        cmd = board_commands_pb2.GetVisibleLayers()
        cmd.board.CopyFrom(self._doc)
        response = self._kicad.send(cmd, board_commands_pb2.BoardLayers)
        return response.layers

    def set_visible_layers(self, layers: Sequence[board_types_pb2.BoardLayer.ValueType]):
        cmd = board_commands_pb2.SetVisibleLayers()
        cmd.board.CopyFrom(self._doc)
        cmd.layers.extend(layers)
        self._kicad.send(cmd, Empty)

    def get_active_layer(self) -> board_types_pb2.BoardLayer.ValueType:
        cmd = board_commands_pb2.GetActiveLayer()
        cmd.board.CopyFrom(self._doc)
        response = self._kicad.send(cmd, board_commands_pb2.BoardLayerResponse)
        return response.layer

    def set_active_layer(self, layer: board_types_pb2.BoardLayer.ValueType):
        cmd = board_commands_pb2.SetActiveLayer()
        cmd.board.CopyFrom(self._doc)
        cmd.layer = layer
        self._kicad.send(cmd, Empty)

    def get_editor_appearance_settings(self) -> BoardEditorAppearanceSettings:
        cmd = board_commands_pb2.GetBoardEditorAppearanceSettings()
        response = self._kicad.send(cmd, board_commands_pb2.BoardEditorAppearanceSettings)
        return BoardEditorAppearanceSettings(response)

    def set_editor_appearance_settings(self, settings: BoardEditorAppearanceSettings):
        cmd = board_commands_pb2.SetBoardEditorAppearanceSettings()
        cmd.settings.CopyFrom(settings.proto)
        self._kicad.send(cmd, Empty)

    def get_plot_settings(self) -> PlotSettings:
        """Retrieves the board plot settings stored in the board file.

        .. versionadded:: 0.x.0
        """
        cmd = board_commands_pb2.GetBoardPlotSettings()
        cmd.board.CopyFrom(self._doc)
        response = self._kicad.send(cmd, board_commands_pb2.BoardPlotSettingsResponse)
        return PlotSettings(response.plot_settings)

    def set_plot_settings(self, plot_settings: PlotSettings):
        """Sets the board plot settings stored in the board file.

        .. versionadded:: 0.x.0
        """
        cmd = board_commands_pb2.SetBoardPlotSettings()
        cmd.board.CopyFrom(self._doc)
        cmd.plot_settings.CopyFrom(plot_settings.proto)
        self._kicad.send(cmd, Empty)

    def place_footprint_from_library(
        self,
        lib_id: LibraryIdentifier | str,
        position: Vector2,
        orientation: Angle | None = None,
        layer: board_types_pb2.BoardLayer.ValueType = board_types_pb2.BoardLayer.BL_F_Cu,
    ) -> FootprintInstance:
        """Places a footprint from a library onto the board.

        Requires that libraries be loaded, which will not be the case in headless mode until
        :meth:`~kipy.KiCad.load_all_libraries` has been called.

        :param lib_id: The footprint to place, either as a :class:`LibraryIdentifier` or a
            string such as ``"Resistor_SMD:R_0603_1608Metric"``.
        :param position: The position to place the footprint at.
        :param orientation: Optional orientation; 0 degrees if not given.
        :param layer: The copper layer to place the footprint on.  Must be ``BL_F_Cu`` or
            ``BL_B_Cu``; the footprint is flipped when placed on ``BL_B_Cu``.
        :return: The newly-placed footprint instance.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        command = board_commands_pb2.PlaceFootprintFromLibrary()
        command.header.document.CopyFrom(self._doc)

        if isinstance(lib_id, str):
            library, _, name = lib_id.partition(":")
            if name == "":
                raise ValueError("lib_id must be in the format <nickname>:<footprint name>")
            command.lib_id.library_nickname = library
            command.lib_id.entry_name = name
        else:
            command.lib_id.CopyFrom(lib_id.proto)

        command.position.CopyFrom(position.proto)

        if orientation is not None:
            command.orientation.CopyFrom(orientation.proto)

        command.layer = layer

        response = self._kicad.send(command, PlaceFromLibraryResponse)
        return cast(FootprintInstance, unwrap(response.item))
