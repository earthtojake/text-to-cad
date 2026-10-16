"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/types/project_settings.proto')
_sym_db = _symbol_database.Default()
from ...common.types import base_types_pb2 as common_dot_types_dot_base__types__pb2
from ...common.types import enums_pb2 as common_dot_types_dot_enums__pb2
from ...board import board_types_pb2 as board_dot_board__types__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n#common/types/project_settings.proto\x12\x14kiapi.common.project\x1a\x1dcommon/types/base_types.proto\x1a\x18common/types/enums.proto\x1a\x17board/board_types.proto"\x98\x05\n\x15NetClassBoardSettings\x124\n\tclearance\x18\x01 \x01(\x0b2\x1c.kiapi.common.types.DistanceH\x00\x88\x01\x01\x126\n\x0btrack_width\x18\x02 \x01(\x0b2\x1c.kiapi.common.types.DistanceH\x01\x88\x01\x01\x12@\n\x15diff_pair_track_width\x18\x03 \x01(\x0b2\x1c.kiapi.common.types.DistanceH\x02\x88\x01\x01\x128\n\rdiff_pair_gap\x18\x04 \x01(\x0b2\x1c.kiapi.common.types.DistanceH\x03\x88\x01\x01\x12<\n\x11diff_pair_via_gap\x18\x05 \x01(\x0b2\x1c.kiapi.common.types.DistanceH\x04\x88\x01\x01\x123\n\tvia_stack\x18\x06 \x01(\x0b2\x1b.kiapi.board.types.PadStackH\x05\x88\x01\x01\x128\n\x0emicrovia_stack\x18\x07 \x01(\x0b2\x1b.kiapi.board.types.PadStackH\x06\x88\x01\x01\x12-\n\x05color\x18\x08 \x01(\x0b2\x19.kiapi.common.types.ColorH\x07\x88\x01\x01\x12\x1b\n\x0etuning_profile\x18\t \x01(\tH\x08\x88\x01\x01B\x0c\n\n_clearanceB\x0e\n\x0c_track_widthB\x18\n\x16_diff_pair_track_widthB\x10\n\x0e_diff_pair_gapB\x14\n\x12_diff_pair_via_gapB\x0c\n\n_via_stackB\x11\n\x0f_microvia_stackB\x08\n\x06_colorB\x11\n\x0f_tuning_profile"\xab\x02\n\x19NetClassSchematicSettings\x125\n\nwire_width\x18\x01 \x01(\x0b2\x1c.kiapi.common.types.DistanceH\x00\x88\x01\x01\x124\n\tbus_width\x18\x02 \x01(\x0b2\x1c.kiapi.common.types.DistanceH\x01\x88\x01\x01\x12-\n\x05color\x18\x03 \x01(\x0b2\x19.kiapi.common.types.ColorH\x02\x88\x01\x01\x12<\n\nline_style\x18\x04 \x01(\x0e2#.kiapi.common.types.StrokeLineStyleH\x03\x88\x01\x01B\r\n\x0b_wire_widthB\x0c\n\n_bus_widthB\x08\n\x06_colorB\r\n\x0b_line_style"\xa6\x02\n\x08NetClass\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x15\n\x08priority\x18\x02 \x01(\x05H\x00\x88\x01\x01\x12?\n\x05board\x18\x03 \x01(\x0b2+.kiapi.common.project.NetClassBoardSettingsH\x01\x88\x01\x01\x12G\n\tschematic\x18\x04 \x01(\x0b2/.kiapi.common.project.NetClassSchematicSettingsH\x02\x88\x01\x01\x120\n\x04type\x18\x05 \x01(\x0e2".kiapi.common.project.NetClassType\x12\x14\n\x0cconstituents\x18\x06 \x03(\tB\x0b\n\t_priorityB\x08\n\x06_boardB\x0c\n\n_schematic"5\n\x12NetClassAssignment\x12\x0b\n\x03net\x18\x01 \x01(\t\x12\x12\n\nnetclasses\x18\x02 \x03(\t">\n\x19NetClassPatternAssignment\x12\x0f\n\x07pattern\x18\x01 \x01(\t\x12\x10\n\x08netclass\x18\x02 \x01(\t"\x88\x01\n\rTextVariables\x12E\n\tvariables\x18\x01 \x03(\x0b22.kiapi.common.project.TextVariables.VariablesEntry\x1a0\n\x0eVariablesEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x028\x01*C\n\x0cNetClassType\x12\x0f\n\x0bNCT_UNKNOWN\x10\x00\x12\x10\n\x0cNCT_EXPLICIT\x10\x01\x12\x10\n\x0cNCT_IMPLICIT\x10\x02b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.types.project_settings_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_TEXTVARIABLES_VARIABLESENTRY']._loaded_options = None
    _globals['_TEXTVARIABLES_VARIABLESENTRY']._serialized_options = b'8\x01'
    _globals['_NETCLASSTYPE']._serialized_start = 1667
    _globals['_NETCLASSTYPE']._serialized_end = 1734
    _globals['_NETCLASSBOARDSETTINGS']._serialized_start = 144
    _globals['_NETCLASSBOARDSETTINGS']._serialized_end = 808
    _globals['_NETCLASSSCHEMATICSETTINGS']._serialized_start = 811
    _globals['_NETCLASSSCHEMATICSETTINGS']._serialized_end = 1110
    _globals['_NETCLASS']._serialized_start = 1113
    _globals['_NETCLASS']._serialized_end = 1407
    _globals['_NETCLASSASSIGNMENT']._serialized_start = 1409
    _globals['_NETCLASSASSIGNMENT']._serialized_end = 1462
    _globals['_NETCLASSPATTERNASSIGNMENT']._serialized_start = 1464
    _globals['_NETCLASSPATTERNASSIGNMENT']._serialized_end = 1526
    _globals['_TEXTVARIABLES']._serialized_start = 1529
    _globals['_TEXTVARIABLES']._serialized_end = 1665
    _globals['_TEXTVARIABLES_VARIABLESENTRY']._serialized_start = 1617
    _globals['_TEXTVARIABLES_VARIABLESENTRY']._serialized_end = 1665