"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'board/board.proto')
_sym_db = _symbol_database.Default()
from ..common.types import base_types_pb2 as common_dot_types_dot_base__types__pb2
from ..board import board_types_pb2 as board_dot_board__types__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x11board/board.proto\x12\x0bkiapi.board\x1a\x1dcommon/types/base_types.proto\x1a\x17board/board_types.proto" \n\x0bBoardFinish\x12\x11\n\ttype_name\x18\x01 \x01(\t".\n\x15BoardImpedanceControl\x12\x15\n\ris_controlled\x18\x01 \x01(\x08"\x14\n\x0cCastellationJ\x04\x08\x01\x10\x02"G\n\x12BoardEdgeConnector\x121\n\x04type\x18\x01 \x01(\x0e2#.kiapi.board.BoardEdgeConnectorType"\'\n\x0bEdgePlating\x12\x18\n\x10has_edge_plating\x18\x01 \x01(\x08"\xa3\x01\n\x11BoardEdgeSettings\x122\n\tconnector\x18\x01 \x01(\x0b2\x1f.kiapi.board.BoardEdgeConnector\x12/\n\x0ccastellation\x18\x02 \x01(\x0b2\x19.kiapi.board.Castellation\x12)\n\x07plating\x18\x03 \x01(\x0b2\x18.kiapi.board.EdgePlating"\x95\x02\n BoardStackupDielectricProperties\x12\x11\n\tepsilon_r\x18\x01 \x01(\x01\x12\x14\n\x0closs_tangent\x18\x02 \x01(\x01\x12\x15\n\rmaterial_name\x18\x03 \x01(\t\x12/\n\tthickness\x18\x04 \x01(\x0b2\x1c.kiapi.common.types.Distance\x12\x18\n\x10thickness_locked\x18\x05 \x01(\x08\x12\x1b\n\x0espec_frequency\x18\x06 \x01(\x01H\x00\x88\x01\x01\x126\n\x10dielectric_model\x18\x07 \x01(\x0e2\x1c.kiapi.board.DielectricModelB\x11\n\x0f_spec_frequency"\x92\x01\n\x1bBoardStackupDielectricLayer\x12<\n\x05layer\x18\x01 \x03(\x0b2-.kiapi.board.BoardStackupDielectricProperties\x125\n\x04type\x18\x02 \x01(\x0e2\'.kiapi.board.BoardStackupDielectricType"\x8e\x01\n\x1bBoardStackupSoldermaskLayer\x12\x11\n\tepsilon_r\x18\x01 \x01(\x01\x12\x14\n\x0closs_tangent\x18\x02 \x01(\x01\x12\x15\n\rmaterial_name\x18\x03 \x01(\t\x12/\n\tthickness\x18\x04 \x01(\x0b2\x1c.kiapi.common.types.Distance"4\n\x1bBoardStackupSilkscreenLayer\x12\x15\n\rmaterial_name\x18\x01 \x01(\t"\xd4\x03\n\x11BoardStackupLayer\x12/\n\tthickness\x18\x01 \x01(\x0b2\x1c.kiapi.common.types.Distance\x12,\n\x05layer\x18\x02 \x01(\x0e2\x1d.kiapi.board.types.BoardLayer\x12\x0f\n\x07enabled\x18\x03 \x01(\x08\x120\n\x04type\x18\x04 \x01(\x0e2".kiapi.board.BoardStackupLayerType\x12>\n\ndielectric\x18\x05 \x01(\x0b2(.kiapi.board.BoardStackupDielectricLayerH\x00\x12>\n\nsoldermask\x18\t \x01(\x0b2(.kiapi.board.BoardStackupSoldermaskLayerH\x00\x12>\n\nsilkscreen\x18\n \x01(\x0b2(.kiapi.board.BoardStackupSilkscreenLayerH\x00\x12(\n\x05color\x18\x06 \x01(\x0b2\x19.kiapi.common.types.Color\x12\x15\n\rmaterial_name\x18\x07 \x01(\t\x12\x11\n\tuser_name\x18\x08 \x01(\tB\t\n\x07details"\xcd\x01\n\x0cBoardStackup\x12(\n\x06finish\x18\x01 \x01(\x0b2\x18.kiapi.board.BoardFinish\x125\n\timpedance\x18\x02 \x01(\x0b2".kiapi.board.BoardImpedanceControl\x12,\n\x04edge\x18\x03 \x01(\x0b2\x1e.kiapi.board.BoardEdgeSettings\x12.\n\x06layers\x18\x04 \x03(\x0b2\x1e.kiapi.board.BoardStackupLayer"\xb1\x01\n\x1aBoardLayerGraphicsDefaults\x12+\n\x05layer\x18\x01 \x01(\x0e2\x1c.kiapi.board.BoardLayerClass\x120\n\x04text\x18\x02 \x01(\x0b2".kiapi.common.types.TextAttributes\x124\n\x0eline_thickness\x18\x03 \x01(\x0b2\x1c.kiapi.common.types.Distance"K\n\x10GraphicsDefaults\x127\n\x06layers\x18\x01 \x03(\x0b2\'.kiapi.board.BoardLayerGraphicsDefaults"I\n\rBoardSettings\x128\n\x11graphics_defaults\x18\x01 \x01(\x0b2\x1d.kiapi.board.GraphicsDefaults*[\n\x16BoardEdgeConnectorType\x12\x10\n\x0cBECT_UNKNOWN\x10\x00\x12\r\n\tBECT_NONE\x10\x01\x12\x0e\n\nBECT_PLAIN\x10\x02\x12\x10\n\x0cBECT_BEVELED\x10\x03*^\n\x1aBoardStackupDielectricType\x12\x10\n\x0cBSDT_UNKNOWN\x10\x00\x12\r\n\tBSDT_NONE\x10\x01\x12\r\n\tBSDT_CORE\x10\x02\x12\x10\n\x0cBSDT_PREPREG\x10\x03*L\n\x0fDielectricModel\x12\x0e\n\nDM_UNKNOWN\x10\x00\x12\x0f\n\x0bDM_CONSTANT\x10\x01\x12\x18\n\x14DM_DJORDJEVIC_SARKAR\x10\x02*\xa3\x01\n\x15BoardStackupLayerType\x12\x10\n\x0cBSLT_UNKNOWN\x10\x00\x12\x0f\n\x0bBSLT_COPPER\x10\x01\x12\x13\n\x0fBSLT_DIELECTRIC\x10\x02\x12\x13\n\x0fBSLT_SILKSCREEN\x10\x03\x12\x13\n\x0fBSLT_SOLDERMASK\x10\x04\x12\x14\n\x10BSLT_SOLDERPASTE\x10\x05\x12\x12\n\x0eBSLT_UNDEFINED\x10\x07*\x8c\x01\n\x0fBoardLayerClass\x12\x0f\n\x0bBLC_UNKNOWN\x10\x00\x12\x12\n\x0eBLC_SILKSCREEN\x10\x01\x12\x0e\n\nBLC_COPPER\x10\x02\x12\r\n\tBLC_EDGES\x10\x03\x12\x11\n\rBLC_COURTYARD\x10\x04\x12\x13\n\x0fBLC_FABRICATION\x10\x05\x12\r\n\tBLC_OTHER\x10\x06b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'board.board_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_BOARDEDGECONNECTORTYPE']._serialized_start = 2113
    _globals['_BOARDEDGECONNECTORTYPE']._serialized_end = 2204
    _globals['_BOARDSTACKUPDIELECTRICTYPE']._serialized_start = 2206
    _globals['_BOARDSTACKUPDIELECTRICTYPE']._serialized_end = 2300
    _globals['_DIELECTRICMODEL']._serialized_start = 2302
    _globals['_DIELECTRICMODEL']._serialized_end = 2378
    _globals['_BOARDSTACKUPLAYERTYPE']._serialized_start = 2381
    _globals['_BOARDSTACKUPLAYERTYPE']._serialized_end = 2544
    _globals['_BOARDLAYERCLASS']._serialized_start = 2547
    _globals['_BOARDLAYERCLASS']._serialized_end = 2687
    _globals['_BOARDFINISH']._serialized_start = 90
    _globals['_BOARDFINISH']._serialized_end = 122
    _globals['_BOARDIMPEDANCECONTROL']._serialized_start = 124
    _globals['_BOARDIMPEDANCECONTROL']._serialized_end = 170
    _globals['_CASTELLATION']._serialized_start = 172
    _globals['_CASTELLATION']._serialized_end = 192
    _globals['_BOARDEDGECONNECTOR']._serialized_start = 194
    _globals['_BOARDEDGECONNECTOR']._serialized_end = 265
    _globals['_EDGEPLATING']._serialized_start = 267
    _globals['_EDGEPLATING']._serialized_end = 306
    _globals['_BOARDEDGESETTINGS']._serialized_start = 309
    _globals['_BOARDEDGESETTINGS']._serialized_end = 472
    _globals['_BOARDSTACKUPDIELECTRICPROPERTIES']._serialized_start = 475
    _globals['_BOARDSTACKUPDIELECTRICPROPERTIES']._serialized_end = 752
    _globals['_BOARDSTACKUPDIELECTRICLAYER']._serialized_start = 755
    _globals['_BOARDSTACKUPDIELECTRICLAYER']._serialized_end = 901
    _globals['_BOARDSTACKUPSOLDERMASKLAYER']._serialized_start = 904
    _globals['_BOARDSTACKUPSOLDERMASKLAYER']._serialized_end = 1046
    _globals['_BOARDSTACKUPSILKSCREENLAYER']._serialized_start = 1048
    _globals['_BOARDSTACKUPSILKSCREENLAYER']._serialized_end = 1100
    _globals['_BOARDSTACKUPLAYER']._serialized_start = 1103
    _globals['_BOARDSTACKUPLAYER']._serialized_end = 1571
    _globals['_BOARDSTACKUP']._serialized_start = 1574
    _globals['_BOARDSTACKUP']._serialized_end = 1779
    _globals['_BOARDLAYERGRAPHICSDEFAULTS']._serialized_start = 1782
    _globals['_BOARDLAYERGRAPHICSDEFAULTS']._serialized_end = 1959
    _globals['_GRAPHICSDEFAULTS']._serialized_start = 1961
    _globals['_GRAPHICSDEFAULTS']._serialized_end = 2036
    _globals['_BOARDSETTINGS']._serialized_start = 2038
    _globals['_BOARDSETTINGS']._serialized_end = 2111