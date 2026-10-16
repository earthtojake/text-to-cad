"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/commands/cross_probe_commands.proto')
_sym_db = _symbol_database.Default()
from ...common.types import base_types_pb2 as common_dot_types_dot_base__types__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n*common/commands/cross_probe_commands.proto\x12\x15kiapi.common.commands\x1a\x1dcommon/types/base_types.proto"o\n\x12CrossProbeAnnounce\x121\n\nframe_type\x18\x01 \x01(\x0e2\x1d.kiapi.common.types.FrameType\x12\x13\n\x0bsocket_path\x18\x02 \x01(\t\x12\x11\n\tapi_token\x18\x03 \x01(\t"f\n\x1aCrossProbeAnnounceResponse\x127\n\x06status\x18\x01 \x01(\x0e2\'.kiapi.common.commands.CrossProbeStatus\x12\x0f\n\x07message\x18\x02 \x01(\t"+\n\x16FootprintSelectionSpec\x12\x11\n\treference\x18\x01 \x01(\t"5\n\x10PadSelectionSpec\x12\x11\n\treference\x18\x01 \x01(\t\x12\x0e\n\x06number\x18\x02 \x01(\t"\xc8\x01\n\rSelectionSpec\x12B\n\tfootprint\x18\x01 \x01(\x0b2-.kiapi.common.commands.FootprintSelectionSpecH\x00\x126\n\x03pad\x18\x02 \x01(\x0b2\'.kiapi.common.commands.PadSelectionSpecH\x00\x123\n\nsheet_path\x18\x03 \x01(\x0b2\x1d.kiapi.common.types.SheetPathH\x00B\x06\n\x04spec"\xf4\x01\n\rSyncSelection\x12<\n\x07context\x18\x01 \x01(\x0e2+.kiapi.common.commands.SyncSelectionContext\x126\n\x04mode\x18\x02 \x01(\x0e2(.kiapi.common.commands.SyncSelectionMode\x128\n\nfocus_item\x18\x03 \x01(\x0b2$.kiapi.common.commands.SelectionSpec\x123\n\x05items\x18\x04 \x03(\x0b2$.kiapi.common.commands.SelectionSpec"a\n\x15SyncSelectionResponse\x127\n\x06status\x18\x01 \x01(\x0e2\'.kiapi.common.commands.CrossProbeStatus\x12\x0f\n\x07message\x18\x02 \x01(\t"!\n\rHighlightNets\x12\x10\n\x08net_name\x18\x01 \x03(\t"a\n\x15HighlightNetsResponse\x127\n\x06status\x18\x01 \x01(\x0e2\'.kiapi.common.commands.CrossProbeStatus\x12\x0f\n\x07message\x18\x02 \x01(\t"G\n\x0bFocusOnItem\x128\n\nfocus_item\x18\x01 \x01(\x0b2$.kiapi.common.commands.SelectionSpec"_\n\x13FocusOnItemResponse\x127\n\x06status\x18\x01 \x01(\x0e2\'.kiapi.common.commands.CrossProbeStatus\x12\x0f\n\x07message\x18\x02 \x01(\t*i\n\x10CrossProbeStatus\x12\x13\n\x0fCPS_UNSPECIFIED\x10\x00\x12\n\n\x06CPS_OK\x10\x01\x12\x11\n\rCPS_NOT_FOUND\x10\x02\x12\x0f\n\x0bCPS_INVALID\x10\x03\x12\x10\n\x0cCPS_DISABLED\x10\x04*P\n\x11SyncSelectionMode\x12\x0f\n\x0bSSM_UNKNOWN\x10\x00\x12\x12\n\x0eSSM_ITEMS_ONLY\x10\x01\x12\x16\n\x12SSM_ITEMS_AND_NETS\x10\x02*K\n\x14SyncSelectionContext\x12\x0f\n\x0bSSC_UNKNOWN\x10\x00\x12\x10\n\x0cSSC_IMPLICIT\x10\x01\x12\x10\n\x0cSSC_EXPLICIT\x10\x02b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.commands.cross_probe_commands_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_CROSSPROBESTATUS']._serialized_start = 1270
    _globals['_CROSSPROBESTATUS']._serialized_end = 1375
    _globals['_SYNCSELECTIONMODE']._serialized_start = 1377
    _globals['_SYNCSELECTIONMODE']._serialized_end = 1457
    _globals['_SYNCSELECTIONCONTEXT']._serialized_start = 1459
    _globals['_SYNCSELECTIONCONTEXT']._serialized_end = 1534
    _globals['_CROSSPROBEANNOUNCE']._serialized_start = 100
    _globals['_CROSSPROBEANNOUNCE']._serialized_end = 211
    _globals['_CROSSPROBEANNOUNCERESPONSE']._serialized_start = 213
    _globals['_CROSSPROBEANNOUNCERESPONSE']._serialized_end = 315
    _globals['_FOOTPRINTSELECTIONSPEC']._serialized_start = 317
    _globals['_FOOTPRINTSELECTIONSPEC']._serialized_end = 360
    _globals['_PADSELECTIONSPEC']._serialized_start = 362
    _globals['_PADSELECTIONSPEC']._serialized_end = 415
    _globals['_SELECTIONSPEC']._serialized_start = 418
    _globals['_SELECTIONSPEC']._serialized_end = 618
    _globals['_SYNCSELECTION']._serialized_start = 621
    _globals['_SYNCSELECTION']._serialized_end = 865
    _globals['_SYNCSELECTIONRESPONSE']._serialized_start = 867
    _globals['_SYNCSELECTIONRESPONSE']._serialized_end = 964
    _globals['_HIGHLIGHTNETS']._serialized_start = 966
    _globals['_HIGHLIGHTNETS']._serialized_end = 999
    _globals['_HIGHLIGHTNETSRESPONSE']._serialized_start = 1001
    _globals['_HIGHLIGHTNETSRESPONSE']._serialized_end = 1098
    _globals['_FOCUSONITEM']._serialized_start = 1100
    _globals['_FOCUSONITEM']._serialized_end = 1171
    _globals['_FOCUSONITEMRESPONSE']._serialized_start = 1173
    _globals['_FOCUSONITEMRESPONSE']._serialized_end = 1268