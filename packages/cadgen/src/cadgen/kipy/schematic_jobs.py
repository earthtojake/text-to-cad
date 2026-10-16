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

from cadgen.kipy.common_types import JobResult
from cadgen.kipy.proto.schematic import schematic_jobs_pb2
from cadgen.kipy.proto.schematic.schematic_jobs_pb2 import (
    BOMFilterScope,
    BOMSortDirection,
    SchematicJobPageSize,
    SchematicJobSheetMode,
    SchematicNetlistFormat,
)
from cadgen.kipy.wrapper import Wrapper

__all__ = (
    "BOM_FORMAT_CSV",
    "BOM_FORMAT_SEMICOLONS",
    "BOM_FORMAT_TSV",
    "BOMField",
    "BOMFieldSettings",
    "BOMFilterScope",
    "BOMFormatSettings",
    "BOMSortDirection",
    "JobResult",
    "PlotSettings",
    "SchematicJobPageSize",
    "SchematicJobSheetMode",
    "SchematicNetlistFormat",
)


class PlotSettings(Wrapper):
    """Shared settings for schematic plotting jobs.

    Set :attr:`plot_all` to plot every sheet. When it is set, :attr:`plot_pages`
    filters the plotted sheets by page number (e.g. ``"2"``). When :attr:`plot_all` is not set,
    :attr:`plot_pages` is ignored and only the current sheet (or sheet targeted by the
    document, if one is provided).
    """

    def __init__(
        self,
        proto: schematic_jobs_pb2.SchematicPlotSettings | None = None,
        proto_ref: schematic_jobs_pb2.SchematicPlotSettings | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_jobs_pb2.SchematicPlotSettings()
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
    def default_font(self) -> str:
        return self._proto.default_font

    @default_font.setter
    def default_font(self, value: str):
        self._proto.default_font = value

    @property
    def variant(self) -> str:
        return self._proto.variant

    @variant.setter
    def variant(self, value: str):
        self._proto.variant = value

    @property
    def plot_all(self) -> bool:
        return self._proto.plot_all

    @plot_all.setter
    def plot_all(self, value: bool):
        self._proto.plot_all = value

    @property
    def plot_drawing_sheet(self) -> bool:
        return self._proto.plot_drawing_sheet

    @plot_drawing_sheet.setter
    def plot_drawing_sheet(self, value: bool):
        self._proto.plot_drawing_sheet = value

    @property
    def plot_pages(self) -> list[str]:
        return list(self._proto.plot_pages)

    @plot_pages.setter
    def plot_pages(self, value: Sequence[str]):
        del self._proto.plot_pages[:]
        self._proto.plot_pages.extend(value)

    @property
    def show_hop_over(self) -> bool:
        return self._proto.show_hop_over

    @show_hop_over.setter
    def show_hop_over(self, value: bool):
        self._proto.show_hop_over = value

    @property
    def black_and_white(self) -> bool:
        return self._proto.black_and_white

    @black_and_white.setter
    def black_and_white(self, value: bool):
        self._proto.black_and_white = value

    @property
    def page_size(self) -> schematic_jobs_pb2.SchematicJobPageSize.ValueType:
        return self._proto.page_size

    @page_size.setter
    def page_size(self, value: schematic_jobs_pb2.SchematicJobPageSize.ValueType):
        self._proto.page_size = value

    @property
    def use_background_color(self) -> bool:
        return self._proto.use_background_color

    @use_background_color.setter
    def use_background_color(self, value: bool):
        self._proto.use_background_color = value

    @property
    def min_pen_width(self) -> int:
        return self._proto.min_pen_width

    @min_pen_width.setter
    def min_pen_width(self, value: int):
        self._proto.min_pen_width = value

    @property
    def theme(self) -> str:
        return self._proto.theme

    @theme.setter
    def theme(self, value: str):
        self._proto.theme = value

    @property
    def sheet_mode(self) -> schematic_jobs_pb2.SchematicJobSheetMode.ValueType:
        """Selects directory (all sheets) or single-file (one sheet) output semantics."""
        return self._proto.sheet_mode

    @sheet_mode.setter
    def sheet_mode(self, value: schematic_jobs_pb2.SchematicJobSheetMode.ValueType):
        self._proto.sheet_mode = value


class BOMFormatSettings(Wrapper):
    """Formatting settings for schematic BOM export jobs."""

    def __init__(
        self,
        proto: schematic_jobs_pb2.BOMFormatSettings | None = None,
        proto_ref: schematic_jobs_pb2.BOMFormatSettings | None = None,
    ):
        self._proto = (
            proto_ref if proto_ref is not None else schematic_jobs_pb2.BOMFormatSettings()
        )
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def preset_name(self) -> str:
        """If supplied, will apply a preset to the other format settings.  Built-in values 'CSV',
        'TSV', and 'Semicolons' are always available, as well as any user-saved presets."""
        return self._proto.preset_name

    @preset_name.setter
    def preset_name(self, value: str):
        self._proto.preset_name = value

    @property
    def field_delimiter(self) -> str:
        """Delimiter between fields (columns) in a data row"""
        return self._proto.field_delimiter

    @field_delimiter.setter
    def field_delimiter(self, value: str):
        self._proto.field_delimiter = value

    @property
    def string_delimiter(self) -> str:
        """Character to use for quoting strings"""
        return self._proto.string_delimiter

    @string_delimiter.setter
    def string_delimiter(self, value: str):
        self._proto.string_delimiter = value

    @property
    def ref_delimiter(self) -> str:
        """Delimiter between reference designators when exporting a list (e.g. "R1,R3,R5")"""
        return self._proto.ref_delimiter

    @ref_delimiter.setter
    def ref_delimiter(self, value: str):
        self._proto.ref_delimiter = value

    @property
    def ref_range_delimiter(self) -> str:
        """Delimiter between reference designators when exporting a range (e.g. "R1-R10")"""
        return self._proto.ref_range_delimiter

    @ref_range_delimiter.setter
    def ref_range_delimiter(self, value: str):
        self._proto.ref_range_delimiter = value

    @property
    def keep_tabs(self) -> bool:
        """Whether tab characters in field values will be preserved when exporting or stripped"""
        return self._proto.keep_tabs

    @keep_tabs.setter
    def keep_tabs(self, value: bool):
        self._proto.keep_tabs = value

    @property
    def keep_line_breaks(self) -> bool:
        """Whether line breaks in field values will be preserved when exporting or stripped"""
        return self._proto.keep_line_breaks

    @keep_line_breaks.setter
    def keep_line_breaks(self, value: bool):
        self._proto.keep_line_breaks = value

    @property
    def include_byte_order_mark(self) -> bool:
        """Whether to include a UTF-8 byte order mark at the start of the
        exported file."""
        return self._proto.include_byte_order_mark

    @include_byte_order_mark.setter
    def include_byte_order_mark(self, value: bool):
        self._proto.include_byte_order_mark = value


class BOMField(Wrapper):
    """One exported field column definition for schematic BOM jobs."""

    def __init__(
        self,
        proto: schematic_jobs_pb2.BOMField | None = None,
        proto_ref: schematic_jobs_pb2.BOMField | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_jobs_pb2.BOMField()
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def name(self) -> str:
        """The name of the field in KiCad to export"""
        return self._proto.name

    @name.setter
    def name(self, value: str):
        self._proto.name = value

    @property
    def label(self) -> str:
        """The name to give the field in the exported BOM (i.e. the column header name)"""
        return self._proto.label

    @label.setter
    def label(self, value: str):
        self._proto.label = value

    @property
    def group_by(self) -> bool:
        """Whether or not to group exported components by this field"""
        return self._proto.group_by

    @group_by.setter
    def group_by(self, value: bool):
        self._proto.group_by = value


class BOMFieldSettings(Wrapper):
    """Field-selection settings for schematic BOM export jobs."""

    def __init__(
        self,
        proto: schematic_jobs_pb2.BOMFieldSettings | None = None,
        proto_ref: schematic_jobs_pb2.BOMFieldSettings | None = None,
    ):
        self._proto = proto_ref if proto_ref is not None else schematic_jobs_pb2.BOMFieldSettings()
        if proto is not None:
            self._proto.CopyFrom(proto)

    @property
    def preset_name(self) -> str:
        """If supplied, will apply a default or user-stored preset to the other field settings.
        Default values available include 'Default Editing', 'Grouped By Value',
        'Grouped By Value and Footprint', and 'Attributes'."""
        return self._proto.preset_name

    @preset_name.setter
    def preset_name(self, value: str):
        self._proto.preset_name = value

    @property
    def fields(self) -> list[BOMField]:
        return [BOMField(proto_ref=field) for field in self._proto.fields]

    @fields.setter
    def fields(self, value: Sequence[BOMField]):
        del self._proto.fields[:]
        self._proto.fields.extend(field.proto for field in value)

    @property
    def sort_field(self) -> str:
        return self._proto.sort_field

    @sort_field.setter
    def sort_field(self, value: str):
        self._proto.sort_field = value

    @property
    def sort_direction(self) -> schematic_jobs_pb2.BOMSortDirection.ValueType:
        """Sort direction; defaults to ascending if unspecified"""
        return self._proto.sort_direction

    @sort_direction.setter
    def sort_direction(self, value: schematic_jobs_pb2.BOMSortDirection.ValueType):
        self._proto.sort_direction = value

    @property
    def filter(self) -> str:
        return self._proto.filter

    @filter.setter
    def filter(self, value: str):
        self._proto.filter = value

    @property
    def filter_scope(self) -> schematic_jobs_pb2.BOMFilterScope.ValueType:
        """Fields searched by the filter; defaults to reference designators
        if unspecified."""
        return self._proto.filter_scope

    @filter_scope.setter
    def filter_scope(self, value: schematic_jobs_pb2.BOMFilterScope.ValueType):
        self._proto.filter_scope = value


BOM_FORMAT_CSV = BOMFormatSettings()
BOM_FORMAT_CSV.field_delimiter = ","
BOM_FORMAT_CSV.string_delimiter = '"'
BOM_FORMAT_CSV.ref_delimiter = ","
"""Matches the built-in KiCad ``CSV`` BOM format preset."""

BOM_FORMAT_TSV = BOMFormatSettings()
BOM_FORMAT_TSV.field_delimiter = "\t"
BOM_FORMAT_TSV.ref_delimiter = ","
"""Matches the built-in KiCad ``TSV`` BOM format preset."""

BOM_FORMAT_SEMICOLONS = BOMFormatSettings()
BOM_FORMAT_SEMICOLONS.field_delimiter = ";"
BOM_FORMAT_SEMICOLONS.string_delimiter = "'"
BOM_FORMAT_SEMICOLONS.ref_delimiter = ","
"""Matches the built-in KiCad ``Semicolons`` BOM format preset."""
