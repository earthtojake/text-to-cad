"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/commands/base_commands.proto')
_sym_db = _symbol_database.Default()
from ...common.types import base_types_pb2 as common_dot_types_dot_base__types__pb2
from ...common.types import enums_pb2 as common_dot_types_dot_enums__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n#common/commands/base_commands.proto\x12\x15kiapi.common.commands\x1a\x1dcommon/types/base_types.proto\x1a\x18common/types/enums.proto"\x0c\n\nGetVersion"G\n\x12GetVersionResponse\x121\n\x07version\x18\x01 \x01(\x0b2 .kiapi.common.types.KiCadVersion"\x06\n\x04Ping")\n\x12GetKiCadBinaryPath\x12\x13\n\x0bbinary_name\x18\x01 \x01(\t"\x1c\n\x0cPathResponse\x12\x0c\n\x04path\x18\x01 \x01(\t"8\n\x0eGetTextExtents\x12&\n\x04text\x18\x01 \x01(\x0b2\x18.kiapi.common.types.Text"r\n\rTextOrTextBox\x12(\n\x04text\x18\x01 \x01(\x0b2\x18.kiapi.common.types.TextH\x00\x12.\n\x07textbox\x18\x02 \x01(\x0b2\x1b.kiapi.common.types.TextBoxH\x00B\x07\n\x05inner"E\n\x0fGetTextAsShapes\x122\n\x04text\x18\x01 \x03(\x0b2$.kiapi.common.commands.TextOrTextBox"w\n\x0eTextWithShapes\x122\n\x04text\x18\x01 \x01(\x0b2$.kiapi.common.commands.TextOrTextBox\x121\n\x06shapes\x18\x02 \x01(\x0b2!.kiapi.common.types.CompoundShape"Z\n\x17GetTextAsShapesResponse\x12?\n\x10text_with_shapes\x18\x01 \x03(\x0b2%.kiapi.common.commands.TextWithShapes"+\n\x15GetPluginSettingsPath\x12\x12\n\nidentifier\x18\x01 \x01(\t""\n\x0eStringResponse\x12\x10\n\x08response\x18\x01 \x01(\t"\n\n\x08GetPaths"E\n\tPathEntry\x12*\n\x04type\x18\x01 \x01(\x0e2\x1c.kiapi.common.types.PathType\x12\x0c\n\x04path\x18\x02 \x01(\t"C\n\x10GetPathsResponse\x12/\n\x05paths\x18\x01 \x03(\x0b2 .kiapi.common.commands.PathEntryb\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.commands.base_commands_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_GETVERSION']._serialized_start = 119
    _globals['_GETVERSION']._serialized_end = 131
    _globals['_GETVERSIONRESPONSE']._serialized_start = 133
    _globals['_GETVERSIONRESPONSE']._serialized_end = 204
    _globals['_PING']._serialized_start = 206
    _globals['_PING']._serialized_end = 212
    _globals['_GETKICADBINARYPATH']._serialized_start = 214
    _globals['_GETKICADBINARYPATH']._serialized_end = 255
    _globals['_PATHRESPONSE']._serialized_start = 257
    _globals['_PATHRESPONSE']._serialized_end = 285
    _globals['_GETTEXTEXTENTS']._serialized_start = 287
    _globals['_GETTEXTEXTENTS']._serialized_end = 343
    _globals['_TEXTORTEXTBOX']._serialized_start = 345
    _globals['_TEXTORTEXTBOX']._serialized_end = 459
    _globals['_GETTEXTASSHAPES']._serialized_start = 461
    _globals['_GETTEXTASSHAPES']._serialized_end = 530
    _globals['_TEXTWITHSHAPES']._serialized_start = 532
    _globals['_TEXTWITHSHAPES']._serialized_end = 651
    _globals['_GETTEXTASSHAPESRESPONSE']._serialized_start = 653
    _globals['_GETTEXTASSHAPESRESPONSE']._serialized_end = 743
    _globals['_GETPLUGINSETTINGSPATH']._serialized_start = 745
    _globals['_GETPLUGINSETTINGSPATH']._serialized_end = 788
    _globals['_STRINGRESPONSE']._serialized_start = 790
    _globals['_STRINGRESPONSE']._serialized_end = 824
    _globals['_GETPATHS']._serialized_start = 826
    _globals['_GETPATHS']._serialized_end = 836
    _globals['_PATHENTRY']._serialized_start = 838
    _globals['_PATHENTRY']._serialized_end = 907
    _globals['_GETPATHSRESPONSE']._serialized_start = 909
    _globals['_GETPATHSRESPONSE']._serialized_end = 976