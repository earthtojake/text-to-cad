"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/commands/variant_commands.proto')
_sym_db = _symbol_database.Default()
from ...common.types import base_types_pb2 as common_dot_types_dot_base__types__pb2
from ...common.types import variants_pb2 as common_dot_types_dot_variants__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n&common/commands/variant_commands.proto\x12\x15kiapi.common.commands\x1a\x1dcommon/types/base_types.proto\x1a\x1bcommon/types/variants.proto"F\n\x0bGetVariants\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"\x80\x01\n\x10VariantsResponse\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x123\n\x08variants\x18\x02 \x03(\x0b2!.kiapi.common.types.DesignVariant"}\n\nAddVariant\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x18\n\x0bdescription\x18\x03 \x01(\tH\x00\x88\x01\x01B\x0e\n\x0c_description"V\n\rDeleteVariant\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x0c\n\x04name\x18\x02 \x01(\t"l\n\rRenameVariant\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x10\n\x08old_name\x18\x02 \x01(\t\x12\x10\n\x08new_name\x18\x03 \x01(\t"s\n\x15SetVariantDescription\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x13\n\x0bdescription\x18\x03 \x01(\t"\x9c\x01\n\x0bCopyVariant\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x10\n\x08old_name\x18\x02 \x01(\t\x12\x10\n\x08new_name\x18\x03 \x01(\t\x12\x1c\n\x0fnew_description\x18\x04 \x01(\tH\x00\x88\x01\x01B\x12\n\x10_new_description"h\n\x11SetCurrentVariant\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x11\n\x04name\x18\x02 \x01(\tH\x00\x88\x01\x01B\x07\n\x05_name"L\n\x11GetCurrentVariant\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"4\n\x16CurrentVariantResponse\x12\x11\n\x04name\x18\x01 \x01(\tH\x00\x88\x01\x01B\x07\n\x05_nameb\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.commands.variant_commands_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_GETVARIANTS']._serialized_start = 125
    _globals['_GETVARIANTS']._serialized_end = 195
    _globals['_VARIANTSRESPONSE']._serialized_start = 198
    _globals['_VARIANTSRESPONSE']._serialized_end = 326
    _globals['_ADDVARIANT']._serialized_start = 328
    _globals['_ADDVARIANT']._serialized_end = 453
    _globals['_DELETEVARIANT']._serialized_start = 455
    _globals['_DELETEVARIANT']._serialized_end = 541
    _globals['_RENAMEVARIANT']._serialized_start = 543
    _globals['_RENAMEVARIANT']._serialized_end = 651
    _globals['_SETVARIANTDESCRIPTION']._serialized_start = 653
    _globals['_SETVARIANTDESCRIPTION']._serialized_end = 768
    _globals['_COPYVARIANT']._serialized_start = 771
    _globals['_COPYVARIANT']._serialized_end = 927
    _globals['_SETCURRENTVARIANT']._serialized_start = 929
    _globals['_SETCURRENTVARIANT']._serialized_end = 1033
    _globals['_GETCURRENTVARIANT']._serialized_start = 1035
    _globals['_GETCURRENTVARIANT']._serialized_end = 1111
    _globals['_CURRENTVARIANTRESPONSE']._serialized_start = 1113
    _globals['_CURRENTVARIANTRESPONSE']._serialized_end = 1165