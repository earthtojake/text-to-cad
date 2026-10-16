"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'schematic/schematic_jobs.proto')
_sym_db = _symbol_database.Default()
from ..common.types import jobs_pb2 as common_dot_types_dot_jobs__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1eschematic/schematic_jobs.proto\x12\x14kiapi.schematic.jobs\x1a\x17common/types/jobs.proto"\x8b\x03\n\x15SchematicPlotSettings\x12\x15\n\rdrawing_sheet\x18\x01 \x01(\t\x12\x14\n\x0cdefault_font\x18\x02 \x01(\t\x12\x0f\n\x07variant\x18\x03 \x01(\t\x12\x10\n\x08plot_all\x18\x04 \x01(\x08\x12\x1a\n\x12plot_drawing_sheet\x18\x05 \x01(\x08\x12\x12\n\nplot_pages\x18\x06 \x03(\t\x12\x15\n\rshow_hop_over\x18\x07 \x01(\x08\x12\x17\n\x0fblack_and_white\x18\x08 \x01(\x08\x12=\n\tpage_size\x18\t \x01(\x0e2*.kiapi.schematic.jobs.SchematicJobPageSize\x12\x1c\n\x14use_background_color\x18\n \x01(\x08\x12\x15\n\rmin_pen_width\x18\x0b \x01(\x05\x12\r\n\x05theme\x18\x0c \x01(\t\x12?\n\nsheet_mode\x18\r \x01(\x0e2+.kiapi.schematic.jobs.SchematicJobSheetMode"\x98\x01\n\x18RunSchematicJobExportSvg\x128\n\x0cjob_settings\x18\x01 \x01(\x0b2".kiapi.common.types.RunJobSettings\x12B\n\rplot_settings\x18\x02 \x01(\x0b2+.kiapi.schematic.jobs.SchematicPlotSettings"\x98\x01\n\x18RunSchematicJobExportDxf\x128\n\x0cjob_settings\x18\x01 \x01(\x0b2".kiapi.common.types.RunJobSettings\x12B\n\rplot_settings\x18\x02 \x01(\x0b2+.kiapi.schematic.jobs.SchematicPlotSettings"\xe7\x01\n\x18RunSchematicJobExportPdf\x128\n\x0cjob_settings\x18\x01 \x01(\x0b2".kiapi.common.types.RunJobSettings\x12B\n\rplot_settings\x18\x02 \x01(\x0b2+.kiapi.schematic.jobs.SchematicPlotSettings\x12\x17\n\x0fproperty_popups\x18\x03 \x01(\x08\x12\x1a\n\x12hierarchical_links\x18\x04 \x01(\x08\x12\x18\n\x10include_metadata\x18\x05 \x01(\x08"\x97\x01\n\x17RunSchematicJobExportPs\x128\n\x0cjob_settings\x18\x01 \x01(\x0b2".kiapi.common.types.RunJobSettings\x12B\n\rplot_settings\x18\x02 \x01(\x0b2+.kiapi.schematic.jobs.SchematicPlotSettings"\xac\x02\n\x18RunSchematicJobExportPng\x128\n\x0cjob_settings\x18\x01 \x01(\x0b2".kiapi.common.types.RunJobSettings\x12B\n\rplot_settings\x18\x02 \x01(\x0b2+.kiapi.schematic.jobs.SchematicPlotSettings\x12\x10\n\x03dpi\x18\x03 \x01(\x05H\x00\x88\x01\x01\x12:\n\x0cantialiasing\x18\x04 \x01(\x0e2$.kiapi.common.types.AntialiasingMode\x12"\n\x15plot_background_color\x18\x05 \x01(\x08H\x01\x88\x01\x01B\x06\n\x04_dpiB\x18\n\x16_plot_background_color"\xac\x01\n\x1cRunSchematicJobExportNetlist\x128\n\x0cjob_settings\x18\x01 \x01(\x0b2".kiapi.common.types.RunJobSettings\x12<\n\x06format\x18\x02 \x01(\x0e2,.kiapi.schematic.jobs.SchematicNetlistFormat\x12\x14\n\x0cvariant_name\x18\x03 \x01(\t"\xdd\x01\n\x11BOMFormatSettings\x12\x13\n\x0bpreset_name\x18\x01 \x01(\t\x12\x17\n\x0ffield_delimiter\x18\x02 \x01(\t\x12\x18\n\x10string_delimiter\x18\x03 \x01(\t\x12\x15\n\rref_delimiter\x18\x04 \x01(\t\x12\x1b\n\x13ref_range_delimiter\x18\x05 \x01(\t\x12\x11\n\tkeep_tabs\x18\x06 \x01(\x08\x12\x18\n\x10keep_line_breaks\x18\x07 \x01(\x08\x12\x1f\n\x17include_byte_order_mark\x18\x08 \x01(\x08"9\n\x08BOMField\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\r\n\x05label\x18\x02 \x01(\t\x12\x10\n\x08group_by\x18\x03 \x01(\x08"\xf7\x01\n\x10BOMFieldSettings\x12\x13\n\x0bpreset_name\x18\x01 \x01(\t\x12.\n\x06fields\x18\x02 \x03(\x0b2\x1e.kiapi.schematic.jobs.BOMField\x12\x12\n\nsort_field\x18\x03 \x01(\t\x12>\n\x0esort_direction\x18\x04 \x01(\x0e2&.kiapi.schematic.jobs.BOMSortDirection\x12\x0e\n\x06filter\x18\x05 \x01(\t\x12:\n\x0cfilter_scope\x18\x06 \x01(\x0e2$.kiapi.schematic.jobs.BOMFilterScope"\x87\x02\n\x18RunSchematicJobExportBOM\x128\n\x0cjob_settings\x18\x01 \x01(\x0b2".kiapi.common.types.RunJobSettings\x127\n\x06format\x18\x02 \x01(\x0b2\'.kiapi.schematic.jobs.BOMFormatSettings\x126\n\x06fields\x18\x03 \x01(\x0b2&.kiapi.schematic.jobs.BOMFieldSettings\x12\x13\n\x0bexclude_dnp\x18\x04 \x01(\x08\x12\x15\n\rgroup_symbols\x18\x05 \x01(\x08\x12\x14\n\x0cvariant_name\x18\x06 \x01(\t*P\n\x14SchematicJobPageSize\x12\x10\n\x0cSJPS_UNKNOWN\x10\x00\x12\r\n\tSJPS_AUTO\x10\x01\x12\x0b\n\x07SJPS_A4\x10\x02\x12\n\n\x06SJPS_A\x10\x03*U\n\x15SchematicJobSheetMode\x12\x10\n\x0cSJSM_UNKNOWN\x10\x00\x12\x13\n\x0fSJSM_ALL_SHEETS\x10\x01\x12\x15\n\x11SJSM_SINGLE_SHEET\x10\x02*\xb9\x01\n\x16SchematicNetlistFormat\x12\x0f\n\x0bSNF_UNKNOWN\x10\x00\x12\x11\n\rSNF_KICAD_XML\x10\x01\x12\x13\n\x0fSNF_KICAD_SEXPR\x10\x02\x12\x12\n\x0eSNF_ORCAD_PCB2\x10\x03\x12\x0f\n\x0bSNF_CADSTAR\x10\x04\x12\r\n\tSNF_SPICE\x10\x05\x12\x13\n\x0fSNF_SPICE_MODEL\x10\x06\x12\x0c\n\x08SNF_PADS\x10\x07\x12\x0f\n\x0bSNF_ALLEGRO\x10\x08*J\n\x10BOMSortDirection\x12\x0f\n\x0bBSD_UNKNOWN\x10\x00\x12\x11\n\rBSD_ASCENDING\x10\x01\x12\x12\n\x0eBSD_DESCENDING\x10\x02*A\n\x0eBOMFilterScope\x12\x11\n\rBFS_REFERENCE\x10\x00\x12\x0f\n\x0bBFS_VISIBLE\x10\x01\x12\x0b\n\x07BFS_ALL\x10\x02b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'schematic.schematic_jobs_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_SCHEMATICJOBPAGESIZE']._serialized_start = 2454
    _globals['_SCHEMATICJOBPAGESIZE']._serialized_end = 2534
    _globals['_SCHEMATICJOBSHEETMODE']._serialized_start = 2536
    _globals['_SCHEMATICJOBSHEETMODE']._serialized_end = 2621
    _globals['_SCHEMATICNETLISTFORMAT']._serialized_start = 2624
    _globals['_SCHEMATICNETLISTFORMAT']._serialized_end = 2809
    _globals['_BOMSORTDIRECTION']._serialized_start = 2811
    _globals['_BOMSORTDIRECTION']._serialized_end = 2885
    _globals['_BOMFILTERSCOPE']._serialized_start = 2887
    _globals['_BOMFILTERSCOPE']._serialized_end = 2952
    _globals['_SCHEMATICPLOTSETTINGS']._serialized_start = 82
    _globals['_SCHEMATICPLOTSETTINGS']._serialized_end = 477
    _globals['_RUNSCHEMATICJOBEXPORTSVG']._serialized_start = 480
    _globals['_RUNSCHEMATICJOBEXPORTSVG']._serialized_end = 632
    _globals['_RUNSCHEMATICJOBEXPORTDXF']._serialized_start = 635
    _globals['_RUNSCHEMATICJOBEXPORTDXF']._serialized_end = 787
    _globals['_RUNSCHEMATICJOBEXPORTPDF']._serialized_start = 790
    _globals['_RUNSCHEMATICJOBEXPORTPDF']._serialized_end = 1021
    _globals['_RUNSCHEMATICJOBEXPORTPS']._serialized_start = 1024
    _globals['_RUNSCHEMATICJOBEXPORTPS']._serialized_end = 1175
    _globals['_RUNSCHEMATICJOBEXPORTPNG']._serialized_start = 1178
    _globals['_RUNSCHEMATICJOBEXPORTPNG']._serialized_end = 1478
    _globals['_RUNSCHEMATICJOBEXPORTNETLIST']._serialized_start = 1481
    _globals['_RUNSCHEMATICJOBEXPORTNETLIST']._serialized_end = 1653
    _globals['_BOMFORMATSETTINGS']._serialized_start = 1656
    _globals['_BOMFORMATSETTINGS']._serialized_end = 1877
    _globals['_BOMFIELD']._serialized_start = 1879
    _globals['_BOMFIELD']._serialized_end = 1936
    _globals['_BOMFIELDSETTINGS']._serialized_start = 1939
    _globals['_BOMFIELDSETTINGS']._serialized_end = 2186
    _globals['_RUNSCHEMATICJOBEXPORTBOM']._serialized_start = 2189
    _globals['_RUNSCHEMATICJOBEXPORTBOM']._serialized_end = 2452