"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/commands/project_commands.proto')
_sym_db = _symbol_database.Default()
from ...common.types import base_types_pb2 as common_dot_types_dot_base__types__pb2
from ...common.types import project_settings_pb2 as common_dot_types_dot_project__settings__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n&common/commands/project_commands.proto\x12\x15kiapi.common.commands\x1a\x1dcommon/types/base_types.proto\x1a#common/types/project_settings.proto"F\n\rGetNetClasses\x125\n\x07project\x18\x01 \x01(\x0b2$.kiapi.common.types.ProjectSpecifier"I\n\x12NetClassesResponse\x123\n\x0bnet_classes\x18\x01 \x03(\x0b2\x1e.kiapi.common.project.NetClass"\xb1\x01\n\rSetNetClasses\x123\n\x0bnet_classes\x18\x01 \x03(\x0b2\x1e.kiapi.common.project.NetClass\x124\n\nmerge_mode\x18\x03 \x01(\x0e2 .kiapi.common.types.MapMergeMode\x125\n\x07project\x18\x04 \x01(\x0b2$.kiapi.common.types.ProjectSpecifier"O\n\x16GetNetClassAssignments\x125\n\x07project\x18\x01 \x01(\x0b2$.kiapi.common.types.ProjectSpecifier"\xaa\x01\n\x1bNetClassAssignmentsResponse\x12=\n\x0bassignments\x18\x01 \x03(\x0b2(.kiapi.common.project.NetClassAssignment\x12L\n\x13pattern_assignments\x18\x02 \x03(\x0b2/.kiapi.common.project.NetClassPatternAssignment"\x92\x02\n\x16SetNetClassAssignments\x125\n\x07project\x18\x01 \x01(\x0b2$.kiapi.common.types.ProjectSpecifier\x124\n\nmerge_mode\x18\x02 \x01(\x0e2 .kiapi.common.types.MapMergeMode\x12=\n\x0bassignments\x18\x03 \x03(\x0b2(.kiapi.common.project.NetClassAssignment\x12L\n\x13pattern_assignments\x18\x04 \x03(\x0b2/.kiapi.common.project.NetClassPatternAssignment"u\n\x13ExpandTextVariables\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x0c\n\x04text\x18\x02 \x03(\t\x12\x17\n\x0fexpand_env_vars\x18\x03 \x01(\x08"+\n\x1bExpandTextVariablesResponse\x12\x0c\n\x04text\x18\x01 \x03(\t"K\n\x10GetTextVariables\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"\xb9\x01\n\x10SetTextVariables\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x126\n\tvariables\x18\x02 \x01(\x0b2#.kiapi.common.project.TextVariables\x124\n\nmerge_mode\x18\x03 \x01(\x0e2 .kiapi.common.types.MapMergeMode"L\n\x0cOpenDocument\x12.\n\x04type\x18\x01 \x01(\x0e2 .kiapi.common.types.DocumentType\x12\x0c\n\x04path\x18\x02 \x01(\t"O\n\x14OpenDocumentResponse\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"H\n\rCloseDocument\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier""\n\x11CloseAllDocuments\x12\r\n\x05force\x18\x01 \x01(\x08"G\n\x0cSaveDocument\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"N\n\x0eCreateDocument\x12.\n\x04type\x18\x01 \x01(\x0e2 .kiapi.common.types.DocumentType\x12\x0c\n\x04path\x18\x02 \x01(\tb\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.commands.project_commands_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_GETNETCLASSES']._serialized_start = 133
    _globals['_GETNETCLASSES']._serialized_end = 203
    _globals['_NETCLASSESRESPONSE']._serialized_start = 205
    _globals['_NETCLASSESRESPONSE']._serialized_end = 278
    _globals['_SETNETCLASSES']._serialized_start = 281
    _globals['_SETNETCLASSES']._serialized_end = 458
    _globals['_GETNETCLASSASSIGNMENTS']._serialized_start = 460
    _globals['_GETNETCLASSASSIGNMENTS']._serialized_end = 539
    _globals['_NETCLASSASSIGNMENTSRESPONSE']._serialized_start = 542
    _globals['_NETCLASSASSIGNMENTSRESPONSE']._serialized_end = 712
    _globals['_SETNETCLASSASSIGNMENTS']._serialized_start = 715
    _globals['_SETNETCLASSASSIGNMENTS']._serialized_end = 989
    _globals['_EXPANDTEXTVARIABLES']._serialized_start = 991
    _globals['_EXPANDTEXTVARIABLES']._serialized_end = 1108
    _globals['_EXPANDTEXTVARIABLESRESPONSE']._serialized_start = 1110
    _globals['_EXPANDTEXTVARIABLESRESPONSE']._serialized_end = 1153
    _globals['_GETTEXTVARIABLES']._serialized_start = 1155
    _globals['_GETTEXTVARIABLES']._serialized_end = 1230
    _globals['_SETTEXTVARIABLES']._serialized_start = 1233
    _globals['_SETTEXTVARIABLES']._serialized_end = 1418
    _globals['_OPENDOCUMENT']._serialized_start = 1420
    _globals['_OPENDOCUMENT']._serialized_end = 1496
    _globals['_OPENDOCUMENTRESPONSE']._serialized_start = 1498
    _globals['_OPENDOCUMENTRESPONSE']._serialized_end = 1577
    _globals['_CLOSEDOCUMENT']._serialized_start = 1579
    _globals['_CLOSEDOCUMENT']._serialized_end = 1651
    _globals['_CLOSEALLDOCUMENTS']._serialized_start = 1653
    _globals['_CLOSEALLDOCUMENTS']._serialized_end = 1687
    _globals['_SAVEDOCUMENT']._serialized_start = 1689
    _globals['_SAVEDOCUMENT']._serialized_end = 1760
    _globals['_CREATEDOCUMENT']._serialized_start = 1762
    _globals['_CREATEDOCUMENT']._serialized_end = 1840