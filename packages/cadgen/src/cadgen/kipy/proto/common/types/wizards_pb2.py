"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/types/wizards.proto')
_sym_db = _symbol_database.Default()
from google.protobuf import any_pb2 as google_dot_protobuf_dot_any__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1acommon/types/wizards.proto\x12\x12kiapi.common.types\x1a\x19google/protobuf/any.proto"\x8c\x01\n\x12WizardIntParameter\x12\r\n\x05value\x18\x01 \x01(\x05\x12\x0f\n\x07default\x18\x02 \x01(\x05\x12\x10\n\x03min\x18\x03 \x01(\x05H\x00\x88\x01\x01\x12\x10\n\x03max\x18\x04 \x01(\x05H\x01\x88\x01\x01\x12\x15\n\x08multiple\x18\x05 \x01(\x05H\x02\x88\x01\x01B\x06\n\x04_minB\x06\n\x04_maxB\x0b\n\t_multiple"i\n\x13WizardRealParameter\x12\r\n\x05value\x18\x01 \x01(\x01\x12\x0f\n\x07default\x18\x02 \x01(\x01\x12\x10\n\x03min\x18\x03 \x01(\x01H\x00\x88\x01\x01\x12\x10\n\x03max\x18\x04 \x01(\x01H\x01\x88\x01\x01B\x06\n\x04_minB\x06\n\x04_max"5\n\x13WizardBoolParameter\x12\r\n\x05value\x18\x01 \x01(\x08\x12\x0f\n\x07default\x18\x02 \x01(\x08"k\n\x15WizardStringParameter\x12\r\n\x05value\x18\x01 \x01(\t\x12\x0f\n\x07default\x18\x02 \x01(\t\x12\x1d\n\x10validation_regex\x18\x03 \x01(\tH\x00\x88\x01\x01B\x13\n\x11_validation_regex"5\n\x10WizardEnumChoice\x12\x12\n\nidentifier\x18\x01 \x01(\t\x12\r\n\x05label\x18\x02 \x01(\t"l\n\x13WizardEnumParameter\x12\r\n\x05value\x18\x01 \x01(\x05\x12\x0f\n\x07default\x18\x02 \x01(\x05\x125\n\x07choices\x18\x03 \x03(\x0b2$.kiapi.common.types.WizardEnumChoice"N\n\x13WizardParameterList\x127\n\nparameters\x18\x01 \x03(\x0b2#.kiapi.common.types.WizardParameter"\xea\x03\n\x0fWizardParameter\x12\x12\n\nidentifier\x18\x01 \x01(\t\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x13\n\x0bdescription\x18\x03 \x01(\t\x12=\n\x08category\x18\x04 \x01(\x0e2+.kiapi.common.types.WizardParameterCategory\x129\n\x04type\x18\x05 \x01(\x0e2+.kiapi.common.types.WizardParameterDataType\x125\n\x03int\x18\x06 \x01(\x0b2&.kiapi.common.types.WizardIntParameterH\x00\x127\n\x04real\x18\x07 \x01(\x0b2\'.kiapi.common.types.WizardRealParameterH\x00\x127\n\x04bool\x18\x08 \x01(\x0b2\'.kiapi.common.types.WizardBoolParameterH\x00\x12;\n\x06string\x18\t \x01(\x0b2).kiapi.common.types.WizardStringParameterH\x00\x127\n\x04enum\x18\n \x01(\x0b2\'.kiapi.common.types.WizardEnumParameterH\x00B\x07\n\x05value"w\n\nWizardInfo\x120\n\x04meta\x18\x01 \x01(\x0b2".kiapi.common.types.WizardMetaInfo\x127\n\nparameters\x18\x02 \x03(\x0b2#.kiapi.common.types.WizardParameter"\x87\x01\n\x0eWizardMetaInfo\x12\x12\n\nidentifier\x18\x01 \x01(\t\x12\x0c\n\x04name\x18\x02 \x01(\t\x12\x13\n\x0bdescription\x18\x03 \x01(\t\x12>\n\x0ftypes_generated\x18\x04 \x03(\x0e2%.kiapi.common.types.WizardContentType"\x92\x01\n\x16WizardGeneratedContent\x12:\n\x06status\x18\x01 \x01(\x0e2*.kiapi.common.types.WizardGenerationStatus\x12%\n\x07content\x18\x02 \x01(\x0b2\x14.google.protobuf.Any\x12\x15\n\rerror_message\x18\x03 \x01(\t*\xcd\x01\n\x17WizardParameterDataType\x12\x10\n\x0cWPDT_UNKNOWN\x10\x00\x12\x11\n\rWPDT_DISTANCE\x10\x01\x12\r\n\tWPDT_AREA\x10\x02\x12\x0f\n\x0bWPDT_VOLUME\x10\x03\x12\r\n\tWPDT_TIME\x10\x04\x12\x0e\n\nWPDT_ANGLE\x10\x05\x12\x0f\n\x0bWPDT_STRING\x10\x06\x12\x10\n\x0cWPDT_INTEGER\x10\x07\x12\r\n\tWPDT_REAL\x10\x08\x12\r\n\tWPDT_BOOL\x10\t\x12\r\n\tWPDT_ENUM\x10\n*{\n\x17WizardParameterCategory\x12\x0f\n\x0bWPC_UNKNOWN\x10\x00\x12\x0f\n\x0bWPC_PACKAGE\x10\x01\x12\x0c\n\x08WPC_PADS\x10\x02\x12\x0f\n\x0bWPC_3DMODEL\x10\x03\x12\x10\n\x0cWPC_METADATA\x10\x04\x12\r\n\tWPC_RULES\x10\x05*G\n\x11WizardContentType\x12\x0f\n\x0bWCT_UNKNOWN\x10\x00\x12\x0e\n\nWCT_SYMBOL\x10\x01\x12\x11\n\rWCT_FOOTPRINT\x10\x02*D\n\x16WizardGenerationStatus\x12\x0f\n\x0bWGS_UNKNOWN\x10\x00\x12\n\n\x06WGS_OK\x10\x01\x12\r\n\tWGS_ERROR\x10\x02b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.types.wizards_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_WIZARDPARAMETERDATATYPE']._serialized_start = 1638
    _globals['_WIZARDPARAMETERDATATYPE']._serialized_end = 1843
    _globals['_WIZARDPARAMETERCATEGORY']._serialized_start = 1845
    _globals['_WIZARDPARAMETERCATEGORY']._serialized_end = 1968
    _globals['_WIZARDCONTENTTYPE']._serialized_start = 1970
    _globals['_WIZARDCONTENTTYPE']._serialized_end = 2041
    _globals['_WIZARDGENERATIONSTATUS']._serialized_start = 2043
    _globals['_WIZARDGENERATIONSTATUS']._serialized_end = 2111
    _globals['_WIZARDINTPARAMETER']._serialized_start = 78
    _globals['_WIZARDINTPARAMETER']._serialized_end = 218
    _globals['_WIZARDREALPARAMETER']._serialized_start = 220
    _globals['_WIZARDREALPARAMETER']._serialized_end = 325
    _globals['_WIZARDBOOLPARAMETER']._serialized_start = 327
    _globals['_WIZARDBOOLPARAMETER']._serialized_end = 380
    _globals['_WIZARDSTRINGPARAMETER']._serialized_start = 382
    _globals['_WIZARDSTRINGPARAMETER']._serialized_end = 489
    _globals['_WIZARDENUMCHOICE']._serialized_start = 491
    _globals['_WIZARDENUMCHOICE']._serialized_end = 544
    _globals['_WIZARDENUMPARAMETER']._serialized_start = 546
    _globals['_WIZARDENUMPARAMETER']._serialized_end = 654
    _globals['_WIZARDPARAMETERLIST']._serialized_start = 656
    _globals['_WIZARDPARAMETERLIST']._serialized_end = 734
    _globals['_WIZARDPARAMETER']._serialized_start = 737
    _globals['_WIZARDPARAMETER']._serialized_end = 1227
    _globals['_WIZARDINFO']._serialized_start = 1229
    _globals['_WIZARDINFO']._serialized_end = 1348
    _globals['_WIZARDMETAINFO']._serialized_start = 1351
    _globals['_WIZARDMETAINFO']._serialized_end = 1486
    _globals['_WIZARDGENERATEDCONTENT']._serialized_start = 1489
    _globals['_WIZARDGENERATEDCONTENT']._serialized_end = 1635