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
from typing import Any, cast

from google.protobuf.empty_pb2 import Empty

from cadgen.kipy.client import KiCadClient
from cadgen.kipy.common_types import LibraryIdentifier, PageSettings, SheetPath, TitleBlockInfo
from cadgen.kipy.editor import EditorCommandsHandler
from cadgen.kipy.geometry import Vector2
from cadgen.kipy.project import Project
from cadgen.kipy.proto.common.commands import editor_commands_pb2
from cadgen.kipy.proto.common.commands.editor_commands_pb2 import (
    GetPageSettings,
    HitTest,
    HitTestResponse,
    HitTestResult,
    SetPageSettings,
)
from cadgen.kipy.proto.common.commands.library_commands_pb2 import PlaceFromLibraryResponse
from cadgen.kipy.proto.common.types import (
    DocumentSpecifier,
    DocumentType,
    KiCadObjectType,
    base_types_pb2,
    jobs_pb2,
)
from cadgen.kipy.proto.schematic import schematic_jobs_pb2
from cadgen.kipy.proto.schematic.schematic_commands_pb2 import (
    GetSchematicHierarchy,
    GetSchematicNetlist,
    PlaceSymbolFromLibrary,
    SchematicHierarchyResponse,
    SchematicNetlistResponse,
)
from cadgen.kipy.schematic_jobs import (  # noqa
    BOM_FORMAT_CSV,
    BOMFieldSettings,
    BOMFilterScope,
    BOMFormatSettings,
    BOMSortDirection,
    JobResult,
    PlotSettings,
    SchematicJobPageSize,
    SchematicJobSheetMode,
    SchematicNetlistFormat,
)
from cadgen.kipy.schematic_types import (
    BusEntry,
    DirectiveLabel,
    GlobalLabel,
    Group,
    HierarchicalLabel,
    Junction,
    LocalLabel,
    NoConnectMarker,
    SchematicGraphicShape,
    SchematicHierarchy,
    SchematicImage,
    SchematicItem,
    SchematicLine,
    SchematicNet,
    SchematicRuleArea,
    SchematicSymbolInstance,
    SchematicSymbolOrientation,
    SchematicTable,
    SchematicText,
    SchematicTextBox,
    SheetInstance,
    SheetSymbol,
    unwrap,
)
from cadgen.kipy.variants import VariantsCommandHandler


class Schematic(EditorCommandsHandler["SchematicItem"], VariantsCommandHandler):
    """A representation of the schematic of a KiCad project, or a view into a subsheet of that
    schematic.  This class is the main entrypoint to interacting with or creating schematics with
    the API.  Schematics in a project may be split across many different sheets; each sheet is its
    own graphical canvas and has a unique :class:`SheetPath`.  Use :meth:`get_hierarchy` to get the
    sheets in a project, and :meth:`for_sheet` to get a version of this schematic object scoped to
    a particular sheet.  The sheet scope determines whether the result of queries like
    :meth:`get_items` covers the entire schematic or just one sheet.

    .. versionadded:: 0.x.y (KiCad 11)
    """

    def __init__(self, kicad: KiCadClient, document: DocumentSpecifier):
        self._kicad = kicad
        self._doc = document

    def __repr__(self) -> str:
        return f"Schematic(root={self.name}, path={self._doc.sheet_path.path_human_readable})"

    @property
    def client(self) -> KiCadClient:
        return self._kicad

    @property
    def document(self) -> DocumentSpecifier:
        return self._doc

    def get_project(self) -> Project:
        return Project(self._kicad, self._doc)

    @property
    def name(self) -> str:
        return self._doc.project.name + ".kicad_sch"

    def _item_from_message(self, message: Any) -> SchematicItem:
        """Converts an unwrapped protobuf message into a concrete schematic item wrapper"""
        item = cast(SchematicItem, unwrap(message))
        if isinstance(item, Group):
            item._item_resolver = self.get_items_by_id
        return item

    def _spec(self, sheet_path: SheetPath | SheetInstance | None) -> DocumentSpecifier:
        """Builds the document specifier for an item query.  When no sheet path is
        given, the specifier falls back to the sheet path this Schematic is bound to
        (see :meth:`for_sheet`).  If this Schematic is not bound to a sheet, the
        specifier has no sheet path set, which requests items from all sheets in the
        document."""
        spec = DocumentSpecifier()
        spec.type = DocumentType.DOCTYPE_SCHEMATIC
        spec.project.CopyFrom(self._doc.project)
        if isinstance(sheet_path, SheetInstance):
            spec.sheet_path.CopyFrom(sheet_path.path.proto)
        elif isinstance(sheet_path, SheetPath):
            spec.sheet_path.CopyFrom(sheet_path.proto)
        elif sheet_path is not None:
            spec.sheet_path.CopyFrom(sheet_path)
        elif self._doc.HasField("sheet_path"):
            spec.sheet_path.CopyFrom(self._doc.sheet_path)
        return spec

    def export_svg(
        self,
        output_path: str,
        plot_settings: PlotSettings | None = None,
        sheet_mode: schematic_jobs_pb2.SchematicJobSheetMode.ValueType = schematic_jobs_pb2.SJSM_UNKNOWN,
    ) -> JobResult:
        """Plots the schematic to SVG.

        :param output_path: Sets the directory or filename of the export. Relative paths are
            resolved from the project directory.
        :param plot_settings: Controls the general shared schematic plot settings
        :param sheet_mode: Set to ``SJSM_ALL_SHEETS``, ``output_path`` is taken as a directory and
            one file per sheet is created.  Otherwise, the sheet pointed to by this schematic
            object is plotted to the file given by ``output_path``.
        """
        command = schematic_jobs_pb2.RunSchematicJobExportSvg()
        if plot_settings is not None:
            command.plot_settings.CopyFrom(plot_settings.proto)
        command.plot_settings.sheet_mode = sheet_mode
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_dxf(
        self,
        output_path: str,
        plot_settings: PlotSettings | None = None,
        sheet_mode: schematic_jobs_pb2.SchematicJobSheetMode.ValueType = schematic_jobs_pb2.SJSM_UNKNOWN,
    ) -> JobResult:
        """Plots the schematic to DXF.

        :param output_path: Sets the directory or filename of the export. Relative paths are
            resolved from the project directory.
        :param plot_settings: Controls the general shared schematic plot settings
        :param sheet_mode: Set to ``SJSM_ALL_SHEETS``, ``output_path`` is taken as a directory and
            one file per sheet is created.  Otherwise, the sheet pointed to by this schematic
            object is plotted to the file given by ``output_path``.
        """
        command = schematic_jobs_pb2.RunSchematicJobExportDxf()
        if plot_settings is not None:
            command.plot_settings.CopyFrom(plot_settings.proto)
        command.plot_settings.sheet_mode = sheet_mode
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_pdf(
        self,
        output_file: str,
        plot_settings: PlotSettings | None = None,
        property_popups: bool = False,
        hierarchical_links: bool = False,
        include_metadata: bool = True,
    ) -> JobResult:
        """Plots the schematic to a single PDF file.

        :param output_file: Sets the filename of the export. Relative paths are resolved from
            the project directory.
        :param plot_settings: Controls the general shared schematic plot settings
        :param property_popups: Controls whether popup menus with object properties should be
            generated in the PDF.
        :param hierarchical_links: Controls whether hierarchical labels should be generated as
            hyperlinkst to other sheets in the PDF.
        :param include_metadata: When enabled, the generated PDF will include document properties
            from the AUTHOR and SUBJECT text variables.
        """
        command = schematic_jobs_pb2.RunSchematicJobExportPdf()
        if plot_settings is not None:
            command.plot_settings.CopyFrom(plot_settings.proto)
        command.property_popups = property_popups
        command.hierarchical_links = hierarchical_links
        command.include_metadata = include_metadata
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_file
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_ps(
        self,
        output_path: str,
        plot_settings: PlotSettings | None = None,
        sheet_mode: schematic_jobs_pb2.SchematicJobSheetMode.ValueType = schematic_jobs_pb2.SJSM_ALL_SHEETS,
    ) -> JobResult:
        """Plots the schematic to PostScript.

        :param output_path: Sets the directory or filename of the export. Relative paths are
            resolved from the project directory.
        :param plot_settings: Controls the general shared schematic plot settings
        :param sheet_mode: Set to ``SJSM_ALL_SHEETS``, ``output_path`` is taken as a directory and
            one file per sheet is created.  Otherwise, the sheet pointed to by this schematic
            object is plotted to the file given by ``output_path``.
        """
        command = schematic_jobs_pb2.RunSchematicJobExportPs()
        if plot_settings is not None:
            command.plot_settings.CopyFrom(plot_settings.proto)
        command.plot_settings.sheet_mode = sheet_mode
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_png(
        self,
        output_path: str,
        plot_settings: PlotSettings | None = None,
        dpi: int | None = None,
        antialiasing: jobs_pb2.AntialiasingMode.ValueType = jobs_pb2.AAM_STANDARD,
        sheet_mode: schematic_jobs_pb2.SchematicJobSheetMode.ValueType = schematic_jobs_pb2.SJSM_ALL_SHEETS,
    ) -> JobResult:
        """Plots the schematic to PNG.

        :param output_path: Sets the directory or filename of the export. Relative paths are
            resolved from the project directory.
        :param plot_settings: Controls the general shared schematic plot settings
        :param dpi: Sets the resolution of the generated image.  When omitted, the default of 300
            is used.  KiCad accepts between 72 and 2400 DPI.
        :param antialiasing: Controls whether the output image is anti-aliased (enabled by default)
        :param sheet_mode: Set to ``SJSM_ALL_SHEETS``, ``output_path`` is taken as a directory and
            one file per sheet is created.  Otherwise, the sheet pointed to by this schematic
            object is plotted to the file given by ``output_path``.
        """
        command = schematic_jobs_pb2.RunSchematicJobExportPng()
        if plot_settings is not None:
            command.plot_settings.CopyFrom(plot_settings.proto)
        command.plot_settings.sheet_mode = sheet_mode
        if dpi is not None:
            command.dpi = dpi
        command.antialiasing = antialiasing
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_path
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_netlist(
        self,
        output_file: str,
        format: schematic_jobs_pb2.SchematicNetlistFormat.ValueType = schematic_jobs_pb2.SNF_KICAD_SEXPR,
        variant_name: str = "",
    ) -> JobResult:
        """Exports the schematic netlist to a single output file.

        :param output_file: Sets the filename of the export. Relative paths are resolved from
            the project directory.
        :param format: Sets the netlist format to use for the export.
        :param variant_name: If non-empty, selects a schematic variant to generate the netlist
            for; uses the default variant otherwise.
        """
        command = schematic_jobs_pb2.RunSchematicJobExportNetlist()
        command.format = format
        command.variant_name = variant_name
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_file
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def export_bom(
        self,
        output_file: str,
        field_settings: BOMFieldSettings,
        format_settings: BOMFormatSettings = BOM_FORMAT_CSV,
        exclude_dnp: bool = False,
        group_symbols: bool = False,
        variant_name: str = "",
    ) -> JobResult:
        """Exports the schematic bill of materials (BOM) to a single output file.

        :param output_file: Sets the filename of the export. Relative paths are resolved from
            the project directory.
        :param field_settings: Controls which symbol fields to export (see
            :class:`~kipy.schematic_jobs.BOMFieldSettings`)
        :param format_settings: Controls the format of the BOM (see
            :class:`~kipy.schematic_jobs.BOMFormatSettings`); defaults to
            :data:`~kipy.schematic_jobs.BOM_FORMAT_CSV` (KiCad's built-in CSV preset)
        :param exclude_dnp: Excludes symbols marked as do not populate (DNP) from the BOM.
        :param group_symbols: Groups symbols together into a single BOM row when their fields
            match one of the :class:`~kipy.schematic_jobs.BOMField` where
            :attr:`~kipy.schematic_jobs.BOMField.group_by` is True.
        """
        command = schematic_jobs_pb2.RunSchematicJobExportBOM()
        command.format.CopyFrom(format_settings.proto)
        if field_settings is not None:
            command.fields.CopyFrom(field_settings.proto)
        command.exclude_dnp = exclude_dnp
        command.group_symbols = group_symbols
        command.variant_name = variant_name
        command.job_settings.document.CopyFrom(self._doc)
        command.job_settings.output_path = output_file
        return JobResult(self._kicad.send(command, jobs_pb2.RunJobResponse))

    def get_items(
        self,
        types: KiCadObjectType.ValueType | Sequence[KiCadObjectType.ValueType] | None = None,
        sheet_path: SheetPath | SheetInstance | None = None,
    ) -> Sequence[SchematicItem]:
        """Retrieves items from the schematic, optionally filtered to a single or set of
        types and/or to a single sheet.

        :param types: Optional type or types of items to retrieve.
        :param sheet_path: Optional sheet to scope the query to.  If not provided, items
            from the sheet this Schematic is bound to are returned, or from all sheets
            in the schematic if this Schematic is not bound to a sheet (see
            :meth:`for_sheet`).
        """
        return self._get_items(types, self._spec(sheet_path))

    def iter_sheets(self):
        """Iterates over all sheets in the schematic's hierarchy, depth-first, beginning
        with the root sheet."""
        yield from self.get_hierarchy()

    def hit_test(self, item: SchematicItem, position: Vector2, tolerance: int = 0) -> bool:
        """Performs a hit test on a schematic item at a given position."""
        command = HitTest()
        command.header.document.CopyFrom(self._doc)
        command.id.CopyFrom(item.id)
        command.position.CopyFrom(position.proto)
        command.tolerance = tolerance
        return self._kicad.send(command, HitTestResponse).result == HitTestResult.HTR_HIT

    def get_lines(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[SchematicLine]:
        return [
            cast(SchematicLine, item)
            for item in self.get_items(types=[KiCadObjectType.KOT_SCH_LINE], sheet_path=sheet_path)
        ]

    def get_text(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[SchematicText | SchematicTextBox]:
        return [
            cast(SchematicText, item)
            if isinstance(item, SchematicText)
            else cast(SchematicTextBox, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_SCH_TEXT, KiCadObjectType.KOT_SCH_TEXTBOX],
                sheet_path=sheet_path,
            )
        ]

    def get_shapes(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[SchematicGraphicShape]:
        return [
            cast(SchematicGraphicShape, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_SCH_SHAPE], sheet_path=sheet_path
            )
        ]

    def get_images(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[SchematicImage]:
        return [
            cast(SchematicImage, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_SCH_BITMAP], sheet_path=sheet_path
            )
        ]

    def get_labels(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[LocalLabel | GlobalLabel | HierarchicalLabel | DirectiveLabel]:
        return [
            cast("LocalLabel | GlobalLabel | HierarchicalLabel | DirectiveLabel", item)
            for item in self.get_items(
                types=[
                    KiCadObjectType.KOT_SCH_LABEL,
                    KiCadObjectType.KOT_SCH_GLOBAL_LABEL,
                    KiCadObjectType.KOT_SCH_HIER_LABEL,
                    KiCadObjectType.KOT_SCH_DIRECTIVE_LABEL,
                ],
                sheet_path=sheet_path,
            )
        ]

    def get_symbols(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[SchematicSymbolInstance]:
        return [
            cast(SchematicSymbolInstance, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_SCH_SYMBOL], sheet_path=sheet_path
            )
        ]

    def get_sheet_symbols(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[SheetSymbol]:
        return [
            cast(SheetSymbol, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_SCH_SHEET], sheet_path=sheet_path
            )
        ]

    def get_junctions(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[Junction]:
        """Returns all junctions in the schematic"""
        return [
            cast(Junction, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_SCH_JUNCTION], sheet_path=sheet_path
            )
        ]

    def get_no_connects(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[NoConnectMarker]:
        """Returns all no-connect markers in the schematic"""
        return [
            cast(NoConnectMarker, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_SCH_NO_CONNECT], sheet_path=sheet_path
            )
        ]

    def get_bus_entries(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[BusEntry]:
        """Returns all wire-to-bus and bus-to-bus entries in the schematic"""
        return [
            cast(BusEntry, item)
            for item in self.get_items(
                types=[
                    KiCadObjectType.KOT_SCH_BUS_WIRE_ENTRY,
                    KiCadObjectType.KOT_SCH_BUS_BUS_ENTRY,
                ],
                sheet_path=sheet_path,
            )
        ]

    def get_rule_areas(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[SchematicRuleArea]:
        """Returns all rule areas (schematic keepouts) in the schematic"""
        return [
            cast(SchematicRuleArea, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_SCH_RULE_AREA], sheet_path=sheet_path
            )
        ]

    def get_tables(
        self, sheet_path: SheetPath | SheetInstance | None = None
    ) -> Sequence[SchematicTable]:
        return [
            cast(SchematicTable, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_SCH_TABLE], sheet_path=sheet_path
            )
        ]

    def get_groups(self, sheet_path: SheetPath | SheetInstance | None = None) -> Sequence[Group]:
        return [
            cast(Group, item)
            for item in self.get_items(
                types=[KiCadObjectType.KOT_SCH_GROUP], sheet_path=sheet_path
            )
        ]

    def get_hierarchy(self) -> SchematicHierarchy:
        """Retrieves the sheet hierarchy of the schematic.

        The returned object provides access to the root sheet (``root``), and can
        be iterated directly to walk every sheet in the hierarchy depth-first.
        """
        command = GetSchematicHierarchy()
        command.document.CopyFrom(self._doc)
        response = self._kicad.send(command, SchematicHierarchyResponse)
        return SchematicHierarchy(
            [SheetInstance(proto=sheet) for sheet in response.top_level_sheets]
        )

    def for_sheet(self, sheet: SheetInstance | SheetPath) -> Schematic:
        """Returns a Schematic bound to the given sheet, e.g. one from :meth:`get_hierarchy` or
        one of its children.

        The returned object can be used to make calls (:meth:`get_items`, etc) on a subsheet.
        """
        spec = DocumentSpecifier()
        spec.type = DocumentType.DOCTYPE_SCHEMATIC
        spec.project.CopyFrom(self._doc.project)
        spec.sheet_path.CopyFrom(
            sheet.path.proto if isinstance(sheet, SheetInstance) else sheet.proto
        )
        return Schematic(self._kicad, spec)

    def get_netlist(
        self,
        types: KiCadObjectType.ValueType | Sequence[KiCadObjectType.ValueType] | None = None,
    ) -> list[SchematicNet]:
        command = GetSchematicNetlist()
        command.document.CopyFrom(self._doc)

        if types is not None:
            if isinstance(types, int):
                command.types.append(types)
            else:
                command.types.extend(types)

        response = self._kicad.send(command, SchematicNetlistResponse)
        return [SchematicNet(proto=net) for net in response.nets]

    def get_title_block(self) -> TitleBlockInfo:
        command = editor_commands_pb2.GetTitleBlockInfo()
        command.document.CopyFrom(self._doc)
        return TitleBlockInfo(self._kicad.send(command, base_types_pb2.TitleBlockInfo))

    def set_title_block(self, title_block: TitleBlockInfo):
        command = editor_commands_pb2.SetTitleBlockInfo()
        command.document.CopyFrom(self._doc)
        command.title_block.CopyFrom(title_block.proto)
        self._kicad.send(command, Empty)

    def get_page_settings(self) -> PageSettings:
        command = GetPageSettings()
        command.document.CopyFrom(self._doc)
        return PageSettings(self._kicad.send(command, base_types_pb2.PageSettings))

    def set_page_settings(self, page_settings: PageSettings) -> PageSettings:
        command = SetPageSettings()
        command.document.CopyFrom(self._doc)
        command.page_settings.CopyFrom(page_settings.proto)
        return PageSettings(self._kicad.send(command, base_types_pb2.PageSettings))

    def place_symbol_from_library(
        self,
        lib_id: LibraryIdentifier | str,
        position: Vector2,
        orientation: SchematicSymbolOrientation.ValueType | None = None,
        unit: int | None = None,
        reference: str | None = None,
        sheet_path: SheetPath | SheetInstance | None = None,
    ) -> SchematicSymbolInstance:
        """Places a symbol from a library onto the schematic.

        Requires that libraries be loaded, which will not be the case in headless mode until
        :meth:`~kipy.KiCad.load_all_libraries` has been called.

        If ``reference`` is not given, KiCad will either leave the symbol unannotated or
        automatically annotate it depending on the user's current auto-annotation
        preference.

        :param lib_id: The symbol to place, either as a :class:`LibraryIdentifier` or a
            string such as ``"Device:R"``.
        :param position: The position to place the symbol at.
        :param orientation: Optional orientation; ``SchematicSymbolOrientation.SSO_0`` if not given.
        :param unit: Optional unit number for multi-unit symbols; places the first unit if
            not given.
        :param reference: Optional reference designator to assign to the new symbol. KiCad
            currently requires that references be in the format <prefix><number> and automatically
            appends a letter for multi-unit symbols.  Reference designators must be unique within
            a schematic for a valid netlist to be generated.  Assigning a non-unique reference or
            one that does not meet KiCad's requirements will be accepted by the API but will result
            in a schematic that cannot be used to drive a board until the annotation is fixed.
        :param sheet_path: Optional sheet to place the symbol on; uses the sheet this
            Schematic is bound to if not given (falling back to the sheet currently
            active in KiCad if this object is not bound to a sheet).  Use :meth:`for_sheet`
            or pass an explicit ``sheet_path`` to place symbols on a subsheet if this
            object holds the root sheet.
        :return: The newly-placed symbol instance.

        .. versionadded:: 0.x.y (KiCad 11)
        """
        command = PlaceSymbolFromLibrary()
        command.header.document.CopyFrom(self._spec(sheet_path))

        if isinstance(lib_id, str):
            library, _, name = lib_id.partition(":")
            if name == "":
                raise ValueError("lib_id must be in the format <nickname>:<symbol name>")
            command.lib_id.library_nickname = library
            command.lib_id.entry_name = name
        else:
            command.lib_id.CopyFrom(lib_id.proto)

        command.position.CopyFrom(position.proto)

        if orientation is not None:
            command.orientation = orientation

        if unit is not None:
            if unit < 1:
                raise ValueError("unit must be a positive integer")
            command.unit.unit = unit

        if reference is not None:
            command.reference = reference

        response = self._kicad.send(command, PlaceFromLibraryResponse)
        item = cast(SchematicSymbolInstance, unwrap(response.item))
        return item
