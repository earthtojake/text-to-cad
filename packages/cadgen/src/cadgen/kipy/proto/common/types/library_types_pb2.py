"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/types/library_types.proto')
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n common/types/library_types.proto\x12\x12kiapi.common.types"\xd5\x02\n\x11LibraryTableEntry\x12\x10\n\x08nickname\x18\x01 \x01(\t\x12\x0b\n\x03uri\x18\x02 \x01(\t\x12-\n\x04type\x18\x03 \x01(\x0e2\x1f.kiapi.common.types.LibraryType\x124\n\x05scope\x18\x04 \x01(\x0e2%.kiapi.common.types.LibraryTableScope\x12\x13\n\x0bdescription\x18\x05 \x01(\t\x12C\n\x07options\x18\x06 \x03(\x0b22.kiapi.common.types.LibraryTableEntry.OptionsEntry\x12\x10\n\x08disabled\x18\x07 \x01(\x08\x12\x0e\n\x06hidden\x18\x08 \x01(\x08\x12\x10\n\x08writable\x18\t \x01(\x08\x1a.\n\x0cOptionsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x028\x01"\xaf\x01\n\x12LibraryStatusEntry\x124\n\x05entry\x18\x01 \x01(\x0b2%.kiapi.common.types.LibraryTableEntry\x125\n\x06status\x18\x02 \x01(\x0e2%.kiapi.common.types.LibraryLoadStatus\x12\x1a\n\rerror_message\x18\x03 \x01(\tH\x00\x88\x01\x01B\x10\n\x0e_error_message"\x8f\x01\n\x0cLibraryTable\x12\x0c\n\x04path\x18\x01 \x01(\t\x124\n\x05scope\x18\x02 \x01(\x0e2%.kiapi.common.types.LibraryTableScope\x12\r\n\x05valid\x18\x03 \x01(\x08\x12\x1a\n\rerror_message\x18\x04 \x01(\tH\x00\x88\x01\x01B\x10\n\x0e_error_message"^\n\x1cLibraryTableMutationResponse\x124\n\x05table\x18\x01 \x01(\x0b2 .kiapi.common.types.LibraryTableH\x00\x88\x01\x01B\x08\n\x06_table"\xf3\x01\n\x14LibraryCommandStatus\x12;\n\x04code\x18\x01 \x01(\x0e2-.kiapi.common.types.LibraryCommandStatus.Code\x12\x1a\n\rerror_message\x18\x02 \x01(\tH\x00\x88\x01\x01"p\n\x04Code\x12\x0f\n\x0bLCS_UNKNOWN\x10\x00\x12\n\n\x06LCS_OK\x10\x01\x12\x11\n\rLCS_NOT_FOUND\x10\x02\x12\x11\n\rLCS_READ_ONLY\x10\x03\x12\x16\n\x12LCS_ALREADY_EXISTS\x10\x04\x12\r\n\tLCS_ERROR\x10\x05B\x10\n\x0e_error_message*S\n\x0bLibraryType\x12\x0e\n\nLT_UNKNOWN\x10\x00\x12\r\n\tLT_SYMBOL\x10\x01\x12\x10\n\x0cLT_FOOTPRINT\x10\x02\x12\x13\n\x0fLT_DESIGN_BLOCK\x10\x03*S\n\x11LibraryTableScope\x12\x0f\n\x0bLTS_UNKNOWN\x10\x00\x12\x0e\n\nLTS_GLOBAL\x10\x01\x12\x0f\n\x0bLTS_PROJECT\x10\x02\x12\x0c\n\x08LTS_BOTH\x10\x03*e\n\x11LibraryLoadStatus\x12\x0f\n\x0bLLS_UNKNOWN\x10\x00\x12\x0f\n\x0bLLS_INVALID\x10\x01\x12\x0f\n\x0bLLS_LOADING\x10\x02\x12\x0e\n\nLLS_LOADED\x10\x03\x12\r\n\tLLS_ERROR\x10\x04b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.types.library_types_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_LIBRARYTABLEENTRY_OPTIONSENTRY']._loaded_options = None
    _globals['_LIBRARYTABLEENTRY_OPTIONSENTRY']._serialized_options = b'8\x01'
    _globals['_LIBRARYTYPE']._serialized_start = 1066
    _globals['_LIBRARYTYPE']._serialized_end = 1149
    _globals['_LIBRARYTABLESCOPE']._serialized_start = 1151
    _globals['_LIBRARYTABLESCOPE']._serialized_end = 1234
    _globals['_LIBRARYLOADSTATUS']._serialized_start = 1236
    _globals['_LIBRARYLOADSTATUS']._serialized_end = 1337
    _globals['_LIBRARYTABLEENTRY']._serialized_start = 57
    _globals['_LIBRARYTABLEENTRY']._serialized_end = 398
    _globals['_LIBRARYTABLEENTRY_OPTIONSENTRY']._serialized_start = 352
    _globals['_LIBRARYTABLEENTRY_OPTIONSENTRY']._serialized_end = 398
    _globals['_LIBRARYSTATUSENTRY']._serialized_start = 401
    _globals['_LIBRARYSTATUSENTRY']._serialized_end = 576
    _globals['_LIBRARYTABLE']._serialized_start = 579
    _globals['_LIBRARYTABLE']._serialized_end = 722
    _globals['_LIBRARYTABLEMUTATIONRESPONSE']._serialized_start = 724
    _globals['_LIBRARYTABLEMUTATIONRESPONSE']._serialized_end = 818
    _globals['_LIBRARYCOMMANDSTATUS']._serialized_start = 821
    _globals['_LIBRARYCOMMANDSTATUS']._serialized_end = 1064
    _globals['_LIBRARYCOMMANDSTATUS_CODE']._serialized_start = 934
    _globals['_LIBRARYCOMMANDSTATUS_CODE']._serialized_end = 1046