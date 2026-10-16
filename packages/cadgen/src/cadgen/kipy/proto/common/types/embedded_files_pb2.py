"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/types/embedded_files.proto')
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n!common/types/embedded_files.proto\x12\x12kiapi.common.types"q\n\x0cEmbeddedFile\x12\x0c\n\x04name\x18\x01 \x01(\t\x122\n\x04type\x18\x02 \x01(\x0e2$.kiapi.common.types.EmbeddedFileType\x12\x0c\n\x04data\x18\x03 \x01(\x0c\x12\x11\n\tdata_hash\x18\x04 \x01(\t"@\n\rEmbeddedFiles\x12/\n\x05files\x18\x01 \x03(\x0b2 .kiapi.common.types.EmbeddedFile*u\n\x10EmbeddedFileType\x12\x0f\n\x0bEFT_UNKNOWN\x10\x00\x12\r\n\tEFT_OTHER\x10\x01\x12\x0c\n\x08EFT_FONT\x10\x02\x12\r\n\tEFT_MODEL\x10\x03\x12\x11\n\rEFT_WORKSHEET\x10\x04\x12\x11\n\rEFT_DATASHEET\x10\x05b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.types.embedded_files_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_EMBEDDEDFILETYPE']._serialized_start = 238
    _globals['_EMBEDDEDFILETYPE']._serialized_end = 355
    _globals['_EMBEDDEDFILE']._serialized_start = 57
    _globals['_EMBEDDEDFILE']._serialized_end = 170
    _globals['_EMBEDDEDFILES']._serialized_start = 172
    _globals['_EMBEDDEDFILES']._serialized_end = 236