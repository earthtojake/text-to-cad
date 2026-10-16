"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/types/jobs.proto')
_sym_db = _symbol_database.Default()
from ...common.types import base_types_pb2 as common_dot_types_dot_base__types__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x17common/types/jobs.proto\x12\x12kiapi.common.types\x1a\x1dcommon/types/base_types.proto"e\n\x0eRunJobResponse\x12-\n\x06status\x18\x01 \x01(\x0e2\x1d.kiapi.common.types.JobStatus\x12\x13\n\x0boutput_path\x18\x02 \x03(\t\x12\x0f\n\x07message\x18\x03 \x01(\t"^\n\x0eRunJobSettings\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x13\n\x0boutput_path\x18\x02 \x01(\t*M\n\tJobStatus\x12\x12\n\x0eJS_UNSPECIFIED\x10\x00\x12\x0e\n\nJS_SUCCESS\x10\x01\x12\x0e\n\nJS_WARNING\x10\x02\x12\x0c\n\x08JS_ERROR\x10\x03*C\n\x10AntialiasingMode\x12\x0f\n\x0bAAM_UNKNOWN\x10\x00\x12\x0c\n\x08AAM_NONE\x10\x01\x12\x10\n\x0cAAM_STANDARD\x10\x02b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.types.jobs_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_JOBSTATUS']._serialized_start = 277
    _globals['_JOBSTATUS']._serialized_end = 354
    _globals['_ANTIALIASINGMODE']._serialized_start = 356
    _globals['_ANTIALIASINGMODE']._serialized_end = 423
    _globals['_RUNJOBRESPONSE']._serialized_start = 78
    _globals['_RUNJOBRESPONSE']._serialized_end = 179
    _globals['_RUNJOBSETTINGS']._serialized_start = 181
    _globals['_RUNJOBSETTINGS']._serialized_end = 275