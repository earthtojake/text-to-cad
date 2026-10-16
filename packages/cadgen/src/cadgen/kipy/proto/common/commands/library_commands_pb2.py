"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/commands/library_commands.proto')
_sym_db = _symbol_database.Default()
from ...common.types import base_types_pb2 as common_dot_types_dot_base__types__pb2
from ...common.types import library_types_pb2 as common_dot_types_dot_library__types__pb2
from google.protobuf import any_pb2 as google_dot_protobuf_dot_any__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n&common/commands/library_commands.proto\x12\x15kiapi.common.commands\x1a\x1dcommon/types/base_types.proto\x1a common/types/library_types.proto\x1a\x19google/protobuf/any.proto"\x8b\x01\n\x0fGetLibraryTable\x12-\n\x04type\x18\x01 \x01(\x0e2\x1f.kiapi.common.types.LibraryType\x124\n\x05scope\x18\x02 \x01(\x0e2%.kiapi.common.types.LibraryTableScope\x12\x13\n\x0bsubstituted\x18\x03 \x01(\x08"|\n\x14LibraryTableResponse\x12/\n\x05table\x18\x01 \x01(\x0b2 .kiapi.common.types.LibraryTable\x123\n\x04rows\x18\x02 \x03(\x0b2%.kiapi.common.types.LibraryTableEntry"\x82\x01\n\x14AddLibraryTableEntry\x124\n\x05entry\x18\x01 \x01(\x0b2%.kiapi.common.types.LibraryTableEntry\x124\n\x05scope\x18\x02 \x01(\x0e2%.kiapi.common.types.LibraryTableScope"\x85\x01\n\x17UpdateLibraryTableEntry\x124\n\x05entry\x18\x01 \x01(\x0b2%.kiapi.common.types.LibraryTableEntry\x124\n\x05scope\x18\x02 \x01(\x0e2%.kiapi.common.types.LibraryTableScope"\x90\x01\n\x17DeleteLibraryTableEntry\x12-\n\x04type\x18\x01 \x01(\x0e2\x1f.kiapi.common.types.LibraryType\x12\x10\n\x08nickname\x18\x02 \x01(\t\x124\n\x05scope\x18\x03 \x01(\x0e2%.kiapi.common.types.LibraryTableScope"z\n\x12GetLibraryStatuses\x12.\n\x05types\x18\x01 \x03(\x0e2\x1f.kiapi.common.types.LibraryType\x124\n\x05scope\x18\x02 \x01(\x0e2%.kiapi.common.types.LibraryTableScope"R\n\x15LibraryStatusResponse\x129\n\tlibraries\x18\x01 \x03(\x0b2&.kiapi.common.types.LibraryStatusEntry"\x86\x01\n\rReloadLibrary\x12-\n\x04type\x18\x01 \x01(\x0e2\x1f.kiapi.common.types.LibraryType\x124\n\x05scope\x18\x02 \x01(\x0e2%.kiapi.common.types.LibraryTableScope\x12\x10\n\x08nickname\x18\x03 \x03(\t"A\n\x10LoadAllLibraries\x12-\n\x04type\x18\x01 \x03(\x0e2\x1f.kiapi.common.types.LibraryType"R\n\x0fGetLibraryItems\x12-\n\x04type\x18\x01 \x01(\x0e2\x1f.kiapi.common.types.LibraryType\x12\x10\n\x08nickname\x18\x02 \x03(\t"L\n\x14LibraryItemsResponse\x124\n\x05items\x18\x01 \x03(\x0b2%.kiapi.common.types.LibraryIdentifier"\xb6\x01\n\x13GetItemsFromLibrary\x12-\n\x04type\x18\x01 \x01(\x0e2\x1f.kiapi.common.types.LibraryType\x127\n\x08document\x18\x02 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x127\n\x08item_ids\x18\x03 \x03(\x0b2%.kiapi.common.types.LibraryIdentifier"O\n\x0fSearchLibraries\x12-\n\x04type\x18\x01 \x01(\x0e2\x1f.kiapi.common.types.LibraryType\x12\r\n\x05query\x18\x02 \x01(\t"O\n\x17SearchLibrariesResponse\x124\n\x05items\x18\x01 \x03(\x0b2%.kiapi.common.types.LibraryIdentifier"n\n\x18PlaceFromLibraryResponse\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x12"\n\x04item\x18\x02 \x01(\x0b2\x14.google.protobuf.Anyb\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.commands.library_commands_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_GETLIBRARYTABLE']._serialized_start = 158
    _globals['_GETLIBRARYTABLE']._serialized_end = 297
    _globals['_LIBRARYTABLERESPONSE']._serialized_start = 299
    _globals['_LIBRARYTABLERESPONSE']._serialized_end = 423
    _globals['_ADDLIBRARYTABLEENTRY']._serialized_start = 426
    _globals['_ADDLIBRARYTABLEENTRY']._serialized_end = 556
    _globals['_UPDATELIBRARYTABLEENTRY']._serialized_start = 559
    _globals['_UPDATELIBRARYTABLEENTRY']._serialized_end = 692
    _globals['_DELETELIBRARYTABLEENTRY']._serialized_start = 695
    _globals['_DELETELIBRARYTABLEENTRY']._serialized_end = 839
    _globals['_GETLIBRARYSTATUSES']._serialized_start = 841
    _globals['_GETLIBRARYSTATUSES']._serialized_end = 963
    _globals['_LIBRARYSTATUSRESPONSE']._serialized_start = 965
    _globals['_LIBRARYSTATUSRESPONSE']._serialized_end = 1047
    _globals['_RELOADLIBRARY']._serialized_start = 1050
    _globals['_RELOADLIBRARY']._serialized_end = 1184
    _globals['_LOADALLLIBRARIES']._serialized_start = 1186
    _globals['_LOADALLLIBRARIES']._serialized_end = 1251
    _globals['_GETLIBRARYITEMS']._serialized_start = 1253
    _globals['_GETLIBRARYITEMS']._serialized_end = 1335
    _globals['_LIBRARYITEMSRESPONSE']._serialized_start = 1337
    _globals['_LIBRARYITEMSRESPONSE']._serialized_end = 1413
    _globals['_GETITEMSFROMLIBRARY']._serialized_start = 1416
    _globals['_GETITEMSFROMLIBRARY']._serialized_end = 1598
    _globals['_SEARCHLIBRARIES']._serialized_start = 1600
    _globals['_SEARCHLIBRARIES']._serialized_end = 1679
    _globals['_SEARCHLIBRARIESRESPONSE']._serialized_start = 1681
    _globals['_SEARCHLIBRARIESRESPONSE']._serialized_end = 1760
    _globals['_PLACEFROMLIBRARYRESPONSE']._serialized_start = 1762
    _globals['_PLACEFROMLIBRARYRESPONSE']._serialized_end = 1872