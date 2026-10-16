"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/envelope.proto')
_sym_db = _symbol_database.Default()
from google.protobuf import any_pb2 as google_dot_protobuf_dot_any__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x15common/envelope.proto\x12\x0ckiapi.common\x1a\x19google/protobuf/any.proto"<\n\x10ApiRequestHeader\x12\x13\n\x0bkicad_token\x18\x01 \x01(\t\x12\x13\n\x0bclient_name\x18\x02 \x01(\t"c\n\nApiRequest\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.ApiRequestHeader\x12%\n\x07message\x18\x02 \x01(\x0b2\x14.google.protobuf.Any"(\n\x11ApiResponseHeader\x12\x13\n\x0bkicad_token\x18\x01 \x01(\t"\x96\x01\n\x0bApiResponse\x12/\n\x06header\x18\x01 \x01(\x0b2\x1f.kiapi.common.ApiResponseHeader\x12/\n\x06status\x18\x02 \x01(\x0b2\x1f.kiapi.common.ApiResponseStatus\x12%\n\x07message\x18\x03 \x01(\x0b2\x14.google.protobuf.Any"W\n\x11ApiResponseStatus\x12+\n\x06status\x18\x01 \x01(\x0e2\x1b.kiapi.common.ApiStatusCode\x12\x15\n\rerror_message\x18\x02 \x01(\t*\xc3\x01\n\rApiStatusCode\x12\x0e\n\nAS_UNKNOWN\x10\x00\x12\t\n\x05AS_OK\x10\x01\x12\x0e\n\nAS_TIMEOUT\x10\x02\x12\x12\n\x0eAS_BAD_REQUEST\x10\x03\x12\x10\n\x0cAS_NOT_READY\x10\x04\x12\x10\n\x0cAS_UNHANDLED\x10\x05\x12\x15\n\x11AS_TOKEN_MISMATCH\x10\x06\x12\x0b\n\x07AS_BUSY\x10\x07\x12\x14\n\x10AS_UNIMPLEMENTED\x10\x08\x12\x15\n\x11AS_INTERNAL_ERROR\x10\tb\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.envelope_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_APISTATUSCODE']._serialized_start = 514
    _globals['_APISTATUSCODE']._serialized_end = 709
    _globals['_APIREQUESTHEADER']._serialized_start = 66
    _globals['_APIREQUESTHEADER']._serialized_end = 126
    _globals['_APIREQUEST']._serialized_start = 128
    _globals['_APIREQUEST']._serialized_end = 227
    _globals['_APIRESPONSEHEADER']._serialized_start = 229
    _globals['_APIRESPONSEHEADER']._serialized_end = 269
    _globals['_APIRESPONSE']._serialized_start = 272
    _globals['_APIRESPONSE']._serialized_end = 422
    _globals['_APIRESPONSESTATUS']._serialized_start = 424
    _globals['_APIRESPONSESTATUS']._serialized_end = 511