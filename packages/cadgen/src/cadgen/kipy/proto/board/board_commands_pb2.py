"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'board/board_commands.proto')
_sym_db = _symbol_database.Default()
from ..common.types import base_types_pb2 as common_dot_types_dot_base__types__pb2
from ..common.types import embedded_files_pb2 as common_dot_types_dot_embedded__files__pb2
from google.protobuf import any_pb2 as google_dot_protobuf_dot_any__pb2
from ..common.types import enums_pb2 as common_dot_types_dot_enums__pb2
from ..common.types import project_settings_pb2 as common_dot_types_dot_project__settings__pb2
from ..board import board_pb2 as board_dot_board__pb2
from ..board import board_rules_pb2 as board_dot_board__rules__pb2
from ..board import board_types_pb2 as board_dot_board__types__pb2
from ..board import board_jobs_pb2 as board_dot_board__jobs__pb2
from ..common.commands import editor_commands_pb2 as common_dot_commands_dot_editor__commands__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1aboard/board_commands.proto\x12\x14kiapi.board.commands\x1a\x1dcommon/types/base_types.proto\x1a!common/types/embedded_files.proto\x1a\x19google/protobuf/any.proto\x1a\x18common/types/enums.proto\x1a#common/types/project_settings.proto\x1a\x11board/board.proto\x1a\x17board/board_rules.proto\x1a\x17board/board_types.proto\x1a\x16board/board_jobs.proto\x1a%common/commands/editor_commands.proto"G\n\x0fGetBoardStackup\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"B\n\x14BoardStackupResponse\x12*\n\x07stackup\x18\x01 \x01(\x0b2\x19.kiapi.board.BoardStackup"v\n\x12UpdateBoardStackup\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12*\n\x07stackup\x18\x02 \x01(\x0b2\x19.kiapi.board.BoardStackup"M\n\x15GetBoardEnabledLayers\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"g\n\x1aBoardEnabledLayersResponse\x12\x1a\n\x12copper_layer_count\x18\x01 \x01(\r\x12-\n\x06layers\x18\x02 \x03(\x0e2\x1d.kiapi.board.types.BoardLayer"\x98\x01\n\x15SetBoardEnabledLayers\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x1a\n\x12copper_layer_count\x18\x02 \x01(\r\x12-\n\x06layers\x18\x03 \x03(\x0e2\x1d.kiapi.board.types.BoardLayer"H\n\x10GetEmbeddedFiles\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"z\n\x10AddEmbeddedFiles\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x120\n\x05files\x18\x02 \x01(\x0b2!.kiapi.common.types.EmbeddedFiles"z\n\x10SetEmbeddedFiles\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x120\n\x05files\x18\x02 \x01(\x0b2!.kiapi.common.types.EmbeddedFiles"K\n\x13GetGraphicsDefaults\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"K\n\x18GraphicsDefaultsResponse\x12/\n\x08defaults\x18\x01 \x01(\x0b2\x1d.kiapi.board.GraphicsDefaults"K\n\x13GetBoardDesignRules\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"y\n\x13SetBoardDesignRules\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12,\n\x05rules\x18\x02 \x01(\x0b2\x1d.kiapi.board.BoardDesignRules"\x8e\x01\n\x18BoardDesignRulesResponse\x12,\n\x05rules\x18\x01 \x01(\x0b2\x1d.kiapi.board.BoardDesignRules\x12D\n\x13custom_rules_status\x18\x02 \x01(\x0e2\'.kiapi.board.commands.CustomRulesStatus"L\n\x14GetCustomDesignRules\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"t\n\x14SetCustomDesignRules\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12&\n\x05rules\x18\x02 \x03(\x0b2\x17.kiapi.board.CustomRule"\x8a\x01\n\x13CustomRulesResponse\x127\n\x06status\x18\x01 \x01(\x0e2\'.kiapi.board.commands.CustomRulesStatus\x12&\n\x05rules\x18\x02 \x03(\x0b2\x17.kiapi.board.CustomRule\x12\x12\n\nerror_text\x18\x03 \x01(\t"{\n\x0eGetBoardOrigin\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x123\n\x04type\x18\x02 \x01(\x0e2%.kiapi.board.commands.BoardOriginType"\xa8\x01\n\x0eSetBoardOrigin\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x123\n\x04type\x18\x02 \x01(\x0e2%.kiapi.board.commands.BoardOriginType\x12+\n\x06origin\x18\x03 \x01(\x0b2\x1b.kiapi.common.types.Vector2"w\n\x11GetBoardLayerName\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12,\n\x05layer\x18\x02 \x01(\x0e2\x1d.kiapi.board.types.BoardLayer"&\n\x16BoardLayerNameResponse\x12\x0c\n\x04name\x18\x01 \x01(\t"Y\n\x13GetBoardLayerByName\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x0c\n\x04name\x18\x02 \x01(\t"X\n\x07GetNets\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x17\n\x0fnetclass_filter\x18\x02 \x03(\t"4\n\x0cNetsResponse\x12$\n\x04nets\x18\x01 \x03(\x0b2\x16.kiapi.board.types.Net"\x99\x01\n\rGetItemsByNet\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x122\n\x05types\x18\x02 \x03(\x0e2#.kiapi.common.types.KiCadObjectType\x12$\n\x04nets\x18\x04 \x03(\x0b2\x16.kiapi.board.types.Net"\x8d\x01\n\x12GetItemsByNetClass\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x122\n\x05types\x18\x02 \x03(\x0e2#.kiapi.common.types.KiCadObjectType\x12\x13\n\x0bnet_classes\x18\x03 \x03(\t"\xa0\x01\n\x11GetConnectedItems\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x12\'\n\x05items\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID\x122\n\x05types\x18\x03 \x03(\x0e2#.kiapi.common.types.KiCadObjectType"9\n\x12GetNetClassForNets\x12#\n\x03net\x18\x01 \x03(\x0b2\x16.kiapi.board.types.Net"\xb6\x01\n\x17NetClassForNetsResponse\x12K\n\x07classes\x18\x01 \x03(\x0b2:.kiapi.board.commands.NetClassForNetsResponse.ClassesEntry\x1aN\n\x0cClassesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12-\n\x05value\x18\x02 \x01(\x0b2\x1e.kiapi.common.project.NetClass:\x028\x01"\x95\x02\n\rImportNetlist\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x14\n\x0cnetlist_path\x18\x02 \x01(\t\x12\x0f\n\x07dry_run\x18\x03 \x01(\x08\x12:\n\nmatch_mode\x18\x04 \x01(\x0e2&.kiapi.board.commands.NetlistMatchMode\x12\x1f\n\x17delete_extra_footprints\x18\x05 \x01(\x08\x12\x19\n\x11update_footprints\x18\x06 \x01(\x08\x12\x17\n\x0ftransfer_groups\x18\x07 \x01(\x08\x12\x16\n\x0eoverride_locks\x18\x08 \x01(\x08"p\n\x15ImportNetlistResponse\x12\x13\n\x0berror_count\x18\x01 \x01(\r\x12\x15\n\rwarning_count\x18\x02 \x01(\r\x12\x1b\n\x13new_footprint_count\x18\x03 \x01(\r\x12\x0e\n\x06report\x18\x04 \x01(\t"l\n\x0bRefillZones\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\'\n\x05zones\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID"\xa2\x01\n\x14GetPadShapeAsPolygon\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12&\n\x04pads\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID\x12,\n\x05layer\x18\x03 \x01(\x0e2\x1d.kiapi.board.types.BoardLayer"{\n\x19PadShapeAsPolygonResponse\x12&\n\x04pads\x18\x01 \x03(\x0b2\x18.kiapi.common.types.KIID\x126\n\x08polygons\x18\x02 \x03(\x0b2$.kiapi.common.types.PolygonWithHoles"\xad\x01\n\x1dCheckPadstackPresenceOnLayers\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\'\n\x05items\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID\x12-\n\x06layers\x18\x03 \x03(\x0e2\x1d.kiapi.board.types.BoardLayer"\xa7\x01\n\x15PadstackPresenceEntry\x12&\n\x04item\x18\x01 \x01(\x0b2\x18.kiapi.common.types.KIID\x12,\n\x05layer\x18\x02 \x01(\x0e2\x1d.kiapi.board.types.BoardLayer\x128\n\x08presence\x18\x03 \x01(\x0e2&.kiapi.board.commands.PadstackPresence"X\n\x18PadstackPresenceResponse\x12<\n\x07entries\x18\x01 \x03(\x0b2+.kiapi.board.commands.PadstackPresenceEntry"\xe4\x01\n\x0eInjectDrcError\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x123\n\x08severity\x18\x02 \x01(\x0e2!.kiapi.board.commands.DrcSeverity\x12\x0f\n\x07message\x18\x03 \x01(\t\x12-\n\x08position\x18\x04 \x01(\x0b2\x1b.kiapi.common.types.Vector2\x12\'\n\x05items\x18\x05 \x03(\x0b2\x18.kiapi.common.types.KIID"B\n\x16InjectDrcErrorResponse\x12(\n\x06marker\x18\x01 \x01(\x0b2\x18.kiapi.common.types.KIID"H\n\x10GetVisibleLayers\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"B\n\x12BoardLayerResponse\x12,\n\x05layer\x18\x01 \x01(\x0e2\x1d.kiapi.board.types.BoardLayer"<\n\x0bBoardLayers\x12-\n\x06layers\x18\x01 \x03(\x0e2\x1d.kiapi.board.types.BoardLayer"w\n\x10SetVisibleLayers\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12-\n\x06layers\x18\x02 \x03(\x0e2\x1d.kiapi.board.types.BoardLayer"F\n\x0eGetActiveLayer\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"t\n\x0eSetActiveLayer\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12,\n\x05layer\x18\x02 \x01(\x0e2\x1d.kiapi.board.types.BoardLayer"\xb3\x02\n\x1dBoardEditorAppearanceSettings\x12N\n\x16inactive_layer_display\x18\x01 \x01(\x0e2..kiapi.board.commands.InactiveLayerDisplayMode\x12D\n\x11net_color_display\x18\x02 \x01(\x0e2).kiapi.board.commands.NetColorDisplayMode\x127\n\nboard_flip\x18\x03 \x01(\x0e2#.kiapi.board.commands.BoardFlipMode\x12C\n\x10ratsnest_display\x18\x04 \x01(\x0e2).kiapi.board.commands.RatsnestDisplayMode""\n GetBoardEditorAppearanceSettings"i\n SetBoardEditorAppearanceSettings\x12E\n\x08settings\x18\x01 \x01(\x0b23.kiapi.board.commands.BoardEditorAppearanceSettings"L\n\x14GetBoardPlotSettings\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"\x88\x01\n\x14SetBoardPlotSettings\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12:\n\rplot_settings\x18\x02 \x01(\x0b2#.kiapi.board.jobs.BoardPlotSettings"W\n\x19BoardPlotSettingsResponse\x12:\n\rplot_settings\x18\x01 \x01(\x0b2#.kiapi.board.jobs.BoardPlotSettings"\xa1\x01\n\tFlipItems\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x12\'\n\x05items\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID\x12;\n\tdirection\x18\x03 \x01(\x0e2(.kiapi.board.commands.BoardFlipDirection"g\n\x0eItemFlipResult\x121\n\x06status\x18\x01 \x01(\x0b2!.kiapi.common.commands.ItemStatus\x12"\n\x04item\x18\x02 \x01(\x0b2\x14.google.protobuf.Any"\xb7\x01\n\x11FlipItemsResponse\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x125\n\x06status\x18\x02 \x01(\x0e2%.kiapi.common.types.ItemRequestStatus\x12;\n\rflipped_items\x18\x03 \x03(\x0b2$.kiapi.board.commands.ItemFlipResult"\xb3\x02\n\x19PlaceFootprintFromLibrary\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x125\n\x06lib_id\x18\x02 \x01(\x0b2%.kiapi.common.types.LibraryIdentifier\x12-\n\x08position\x18\x03 \x01(\x0b2\x1b.kiapi.common.types.Vector2\x123\n\x0borientation\x18\x04 \x01(\x0b2\x19.kiapi.common.types.AngleH\x00\x88\x01\x01\x121\n\x05layer\x18\x05 \x01(\x0e2\x1d.kiapi.board.types.BoardLayerH\x01\x88\x01\x01B\x0e\n\x0c_orientationB\x08\n\x06_layer"u\n\x14InteractiveMoveItems\x124\n\x05board\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\'\n\x05items\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID*R\n\x11CustomRulesStatus\x12\x0f\n\x0bCRS_UNKNOWN\x10\x00\x12\x0c\n\x08CRS_NONE\x10\x01\x12\r\n\tCRS_VALID\x10\x02\x12\x0f\n\x0bCRS_INVALID\x10\x03*?\n\x0fBoardOriginType\x12\x0f\n\x0bBOT_UNKNOWN\x10\x00\x12\x0c\n\x08BOT_GRID\x10\x01\x12\r\n\tBOT_DRILL\x10\x02*D\n\x10NetlistMatchMode\x12\x0f\n\x0bNMM_UNKNOWN\x10\x00\x12\x0c\n\x08NMM_UUID\x10\x01\x12\x11\n\rNMM_REFERENCE\x10\x02*I\n\x10PadstackPresence\x12\x0f\n\x0bPSP_UNKNOWN\x10\x00\x12\x0f\n\x0bPSP_PRESENT\x10\x01\x12\x13\n\x0fPSP_NOT_PRESENT\x10\x02*\xa1\x01\n\x0bDrcSeverity\x12\x0f\n\x0bDRS_UNKNOWN\x10\x00\x12\x0f\n\x0bDRS_WARNING\x10\x01\x12\r\n\tDRS_ERROR\x10\x02\x12\x11\n\rDRS_EXCLUSION\x10\x03\x12\x0e\n\nDRS_IGNORE\x10\x04\x12\x0c\n\x08DRS_INFO\x10\x05\x12\x0e\n\nDRS_ACTION\x10\x06\x12\r\n\tDRS_DEBUG\x10\x07\x12\x11\n\rDRS_UNDEFINED\x10\x08*_\n\x18InactiveLayerDisplayMode\x12\x10\n\x0cILDM_UNKNOWN\x10\x00\x12\x0f\n\x0bILDM_NORMAL\x10\x01\x12\x0f\n\x0bILDM_DIMMED\x10\x02\x12\x0f\n\x0bILDM_HIDDEN\x10\x03*V\n\x13NetColorDisplayMode\x12\x10\n\x0cNCDM_UNKNOWN\x10\x00\x12\x0c\n\x08NCDM_ALL\x10\x01\x12\x11\n\rNCDM_RATSNEST\x10\x02\x12\x0c\n\x08NCDM_OFF\x10\x03*C\n\rBoardFlipMode\x12\x0f\n\x0bBFM_UNKNOWN\x10\x00\x12\x0e\n\nBFM_NORMAL\x10\x01\x12\x11\n\rBFM_FLIPPED_X\x10\x02*R\n\x13RatsnestDisplayMode\x12\x0f\n\x0bRDM_UNKNOWN\x10\x00\x12\x12\n\x0eRDM_ALL_LAYERS\x10\x01\x12\x16\n\x12RDM_VISIBLE_LAYERS\x10\x02*M\n\x12BoardFlipDirection\x12\x0f\n\x0bBFD_UNKNOWN\x10\x00\x12\x12\n\x0eBFD_LEFT_RIGHT\x10\x01\x12\x12\n\x0eBFD_TOP_BOTTOM\x10\x02b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'board.board_commands_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_NETCLASSFORNETSRESPONSE_CLASSESENTRY']._loaded_options = None
    _globals['_NETCLASSFORNETSRESPONSE_CLASSESENTRY']._serialized_options = b'8\x01'
    _globals['_CUSTOMRULESSTATUS']._serialized_start = 7184
    _globals['_CUSTOMRULESSTATUS']._serialized_end = 7266
    _globals['_BOARDORIGINTYPE']._serialized_start = 7268
    _globals['_BOARDORIGINTYPE']._serialized_end = 7331
    _globals['_NETLISTMATCHMODE']._serialized_start = 7333
    _globals['_NETLISTMATCHMODE']._serialized_end = 7401
    _globals['_PADSTACKPRESENCE']._serialized_start = 7403
    _globals['_PADSTACKPRESENCE']._serialized_end = 7476
    _globals['_DRCSEVERITY']._serialized_start = 7479
    _globals['_DRCSEVERITY']._serialized_end = 7640
    _globals['_INACTIVELAYERDISPLAYMODE']._serialized_start = 7642
    _globals['_INACTIVELAYERDISPLAYMODE']._serialized_end = 7737
    _globals['_NETCOLORDISPLAYMODE']._serialized_start = 7739
    _globals['_NETCOLORDISPLAYMODE']._serialized_end = 7825
    _globals['_BOARDFLIPMODE']._serialized_start = 7827
    _globals['_BOARDFLIPMODE']._serialized_end = 7894
    _globals['_RATSNESTDISPLAYMODE']._serialized_start = 7896
    _globals['_RATSNESTDISPLAYMODE']._serialized_end = 7978
    _globals['_BOARDFLIPDIRECTION']._serialized_start = 7980
    _globals['_BOARDFLIPDIRECTION']._serialized_end = 8057
    _globals['_GETBOARDSTACKUP']._serialized_start = 340
    _globals['_GETBOARDSTACKUP']._serialized_end = 411
    _globals['_BOARDSTACKUPRESPONSE']._serialized_start = 413
    _globals['_BOARDSTACKUPRESPONSE']._serialized_end = 479
    _globals['_UPDATEBOARDSTACKUP']._serialized_start = 481
    _globals['_UPDATEBOARDSTACKUP']._serialized_end = 599
    _globals['_GETBOARDENABLEDLAYERS']._serialized_start = 601
    _globals['_GETBOARDENABLEDLAYERS']._serialized_end = 678
    _globals['_BOARDENABLEDLAYERSRESPONSE']._serialized_start = 680
    _globals['_BOARDENABLEDLAYERSRESPONSE']._serialized_end = 783
    _globals['_SETBOARDENABLEDLAYERS']._serialized_start = 786
    _globals['_SETBOARDENABLEDLAYERS']._serialized_end = 938
    _globals['_GETEMBEDDEDFILES']._serialized_start = 940
    _globals['_GETEMBEDDEDFILES']._serialized_end = 1012
    _globals['_ADDEMBEDDEDFILES']._serialized_start = 1014
    _globals['_ADDEMBEDDEDFILES']._serialized_end = 1136
    _globals['_SETEMBEDDEDFILES']._serialized_start = 1138
    _globals['_SETEMBEDDEDFILES']._serialized_end = 1260
    _globals['_GETGRAPHICSDEFAULTS']._serialized_start = 1262
    _globals['_GETGRAPHICSDEFAULTS']._serialized_end = 1337
    _globals['_GRAPHICSDEFAULTSRESPONSE']._serialized_start = 1339
    _globals['_GRAPHICSDEFAULTSRESPONSE']._serialized_end = 1414
    _globals['_GETBOARDDESIGNRULES']._serialized_start = 1416
    _globals['_GETBOARDDESIGNRULES']._serialized_end = 1491
    _globals['_SETBOARDDESIGNRULES']._serialized_start = 1493
    _globals['_SETBOARDDESIGNRULES']._serialized_end = 1614
    _globals['_BOARDDESIGNRULESRESPONSE']._serialized_start = 1617
    _globals['_BOARDDESIGNRULESRESPONSE']._serialized_end = 1759
    _globals['_GETCUSTOMDESIGNRULES']._serialized_start = 1761
    _globals['_GETCUSTOMDESIGNRULES']._serialized_end = 1837
    _globals['_SETCUSTOMDESIGNRULES']._serialized_start = 1839
    _globals['_SETCUSTOMDESIGNRULES']._serialized_end = 1955
    _globals['_CUSTOMRULESRESPONSE']._serialized_start = 1958
    _globals['_CUSTOMRULESRESPONSE']._serialized_end = 2096
    _globals['_GETBOARDORIGIN']._serialized_start = 2098
    _globals['_GETBOARDORIGIN']._serialized_end = 2221
    _globals['_SETBOARDORIGIN']._serialized_start = 2224
    _globals['_SETBOARDORIGIN']._serialized_end = 2392
    _globals['_GETBOARDLAYERNAME']._serialized_start = 2394
    _globals['_GETBOARDLAYERNAME']._serialized_end = 2513
    _globals['_BOARDLAYERNAMERESPONSE']._serialized_start = 2515
    _globals['_BOARDLAYERNAMERESPONSE']._serialized_end = 2553
    _globals['_GETBOARDLAYERBYNAME']._serialized_start = 2555
    _globals['_GETBOARDLAYERBYNAME']._serialized_end = 2644
    _globals['_GETNETS']._serialized_start = 2646
    _globals['_GETNETS']._serialized_end = 2734
    _globals['_NETSRESPONSE']._serialized_start = 2736
    _globals['_NETSRESPONSE']._serialized_end = 2788
    _globals['_GETITEMSBYNET']._serialized_start = 2791
    _globals['_GETITEMSBYNET']._serialized_end = 2944
    _globals['_GETITEMSBYNETCLASS']._serialized_start = 2947
    _globals['_GETITEMSBYNETCLASS']._serialized_end = 3088
    _globals['_GETCONNECTEDITEMS']._serialized_start = 3091
    _globals['_GETCONNECTEDITEMS']._serialized_end = 3251
    _globals['_GETNETCLASSFORNETS']._serialized_start = 3253
    _globals['_GETNETCLASSFORNETS']._serialized_end = 3310
    _globals['_NETCLASSFORNETSRESPONSE']._serialized_start = 3313
    _globals['_NETCLASSFORNETSRESPONSE']._serialized_end = 3495
    _globals['_NETCLASSFORNETSRESPONSE_CLASSESENTRY']._serialized_start = 3417
    _globals['_NETCLASSFORNETSRESPONSE_CLASSESENTRY']._serialized_end = 3495
    _globals['_IMPORTNETLIST']._serialized_start = 3498
    _globals['_IMPORTNETLIST']._serialized_end = 3775
    _globals['_IMPORTNETLISTRESPONSE']._serialized_start = 3777
    _globals['_IMPORTNETLISTRESPONSE']._serialized_end = 3889
    _globals['_REFILLZONES']._serialized_start = 3891
    _globals['_REFILLZONES']._serialized_end = 3999
    _globals['_GETPADSHAPEASPOLYGON']._serialized_start = 4002
    _globals['_GETPADSHAPEASPOLYGON']._serialized_end = 4164
    _globals['_PADSHAPEASPOLYGONRESPONSE']._serialized_start = 4166
    _globals['_PADSHAPEASPOLYGONRESPONSE']._serialized_end = 4289
    _globals['_CHECKPADSTACKPRESENCEONLAYERS']._serialized_start = 4292
    _globals['_CHECKPADSTACKPRESENCEONLAYERS']._serialized_end = 4465
    _globals['_PADSTACKPRESENCEENTRY']._serialized_start = 4468
    _globals['_PADSTACKPRESENCEENTRY']._serialized_end = 4635
    _globals['_PADSTACKPRESENCERESPONSE']._serialized_start = 4637
    _globals['_PADSTACKPRESENCERESPONSE']._serialized_end = 4725
    _globals['_INJECTDRCERROR']._serialized_start = 4728
    _globals['_INJECTDRCERROR']._serialized_end = 4956
    _globals['_INJECTDRCERRORRESPONSE']._serialized_start = 4958
    _globals['_INJECTDRCERRORRESPONSE']._serialized_end = 5024
    _globals['_GETVISIBLELAYERS']._serialized_start = 5026
    _globals['_GETVISIBLELAYERS']._serialized_end = 5098
    _globals['_BOARDLAYERRESPONSE']._serialized_start = 5100
    _globals['_BOARDLAYERRESPONSE']._serialized_end = 5166
    _globals['_BOARDLAYERS']._serialized_start = 5168
    _globals['_BOARDLAYERS']._serialized_end = 5228
    _globals['_SETVISIBLELAYERS']._serialized_start = 5230
    _globals['_SETVISIBLELAYERS']._serialized_end = 5349
    _globals['_GETACTIVELAYER']._serialized_start = 5351
    _globals['_GETACTIVELAYER']._serialized_end = 5421
    _globals['_SETACTIVELAYER']._serialized_start = 5423
    _globals['_SETACTIVELAYER']._serialized_end = 5539
    _globals['_BOARDEDITORAPPEARANCESETTINGS']._serialized_start = 5542
    _globals['_BOARDEDITORAPPEARANCESETTINGS']._serialized_end = 5849
    _globals['_GETBOARDEDITORAPPEARANCESETTINGS']._serialized_start = 5851
    _globals['_GETBOARDEDITORAPPEARANCESETTINGS']._serialized_end = 5885
    _globals['_SETBOARDEDITORAPPEARANCESETTINGS']._serialized_start = 5887
    _globals['_SETBOARDEDITORAPPEARANCESETTINGS']._serialized_end = 5992
    _globals['_GETBOARDPLOTSETTINGS']._serialized_start = 5994
    _globals['_GETBOARDPLOTSETTINGS']._serialized_end = 6070
    _globals['_SETBOARDPLOTSETTINGS']._serialized_start = 6073
    _globals['_SETBOARDPLOTSETTINGS']._serialized_end = 6209
    _globals['_BOARDPLOTSETTINGSRESPONSE']._serialized_start = 6211
    _globals['_BOARDPLOTSETTINGSRESPONSE']._serialized_end = 6298
    _globals['_FLIPITEMS']._serialized_start = 6301
    _globals['_FLIPITEMS']._serialized_end = 6462
    _globals['_ITEMFLIPRESULT']._serialized_start = 6464
    _globals['_ITEMFLIPRESULT']._serialized_end = 6567
    _globals['_FLIPITEMSRESPONSE']._serialized_start = 6570
    _globals['_FLIPITEMSRESPONSE']._serialized_end = 6753
    _globals['_PLACEFOOTPRINTFROMLIBRARY']._serialized_start = 6756
    _globals['_PLACEFOOTPRINTFROMLIBRARY']._serialized_end = 7063
    _globals['_INTERACTIVEMOVEITEMS']._serialized_start = 7065
    _globals['_INTERACTIVEMOVEITEMS']._serialized_end = 7182