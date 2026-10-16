"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 29, 4, '', 'common/commands/editor_commands.proto')
_sym_db = _symbol_database.Default()
from google.protobuf import any_pb2 as google_dot_protobuf_dot_any__pb2
from ...common.types import base_types_pb2 as common_dot_types_dot_base__types__pb2
from ...common.types import enums_pb2 as common_dot_types_dot_enums__pb2
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n%common/commands/editor_commands.proto\x12\x15kiapi.common.commands\x1a\x19google/protobuf/any.proto\x1a\x1dcommon/types/base_types.proto\x1a\x18common/types/enums.proto"=\n\rRefreshEditor\x12,\n\x05frame\x18\x01 \x01(\x0e2\x1d.kiapi.common.types.FrameType"|\n\x0fOpenLibraryItem\x12.\n\x04type\x18\x01 \x01(\x0e2 .kiapi.common.types.DocumentType\x129\n\nidentifier\x18\x02 \x01(\x0b2%.kiapi.common.types.LibraryIdentifier"B\n\x10GetOpenDocuments\x12.\n\x04type\x18\x01 \x01(\x0e2 .kiapi.common.types.DocumentType"T\n\x18GetOpenDocumentsResponse\x128\n\tdocuments\x18\x01 \x03(\x0b2%.kiapi.common.types.DocumentSpecifier"S\n\x18GetDocumentModifiedState\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"_\n GetDocumentModifiedStateResponse\x12;\n\x05state\x18\x01 \x01(\x0e2,.kiapi.common.commands.DocumentModifiedState"9\n\x0bSaveOptions\x12\x11\n\toverwrite\x18\x01 \x01(\x08\x12\x17\n\x0finclude_project\x18\x02 \x01(\x08"\x90\x01\n\x12SaveCopyOfDocument\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x0c\n\x04path\x18\x02 \x01(\t\x123\n\x07options\x18\x03 \x01(\x0b2".kiapi.common.commands.SaveOptions"I\n\x0eRevertDocument\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"\x1b\n\tRunAction\x12\x0e\n\x06action\x18\x01 \x01(\t"K\n\x11RunActionResponse\x126\n\x06status\x18\x01 \x01(\x0e2&.kiapi.common.commands.RunActionStatus"=\n\x0bBeginCommit\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader";\n\x13BeginCommitResponse\x12$\n\x02id\x18\x01 \x01(\x0b2\x18.kiapi.common.types.KIID"\xa7\x01\n\tEndCommit\x12$\n\x02id\x18\x01 \x01(\x0b2\x18.kiapi.common.types.KIID\x123\n\x06action\x18\x02 \x01(\x0e2#.kiapi.common.commands.CommitAction\x12\x0f\n\x07message\x18\x03 \x01(\t\x12.\n\x06header\x18\x04 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader"\x13\n\x11EndCommitResponse"\x8f\x01\n\x0bCreateItems\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x12#\n\x05items\x18\x02 \x03(\x0b2\x14.google.protobuf.Any\x12+\n\tcontainer\x18\x03 \x01(\x0b2\x18.kiapi.common.types.KIID"X\n\nItemStatus\x123\n\x04code\x18\x01 \x01(\x0e2%.kiapi.common.commands.ItemStatusCode\x12\x15\n\rerror_message\x18\x02 \x01(\t"k\n\x12ItemCreationResult\x121\n\x06status\x18\x01 \x01(\x0b2!.kiapi.common.commands.ItemStatus\x12"\n\x04item\x18\x02 \x01(\x0b2\x14.google.protobuf.Any"\xbe\x01\n\x13CreateItemsResponse\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x125\n\x06status\x18\x02 \x01(\x0e2%.kiapi.common.types.ItemRequestStatus\x12@\n\rcreated_items\x18\x03 \x03(\x0b2).kiapi.common.commands.ItemCreationResult"n\n\x08GetItems\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x122\n\x05types\x18\x02 \x03(\x0e2#.kiapi.common.types.KiCadObjectType"g\n\x0cGetItemsById\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x12\'\n\x05items\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID"\x9e\x01\n\x10GetItemsResponse\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x125\n\x06status\x18\x02 \x01(\x0e2%.kiapi.common.types.ItemRequestStatus\x12#\n\x05items\x18\x03 \x03(\x0b2\x14.google.protobuf.Any"b\n\x0bUpdateItems\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x12#\n\x05items\x18\x02 \x03(\x0b2\x14.google.protobuf.Any"i\n\x10ItemUpdateResult\x121\n\x06status\x18\x01 \x01(\x0b2!.kiapi.common.commands.ItemStatus\x12"\n\x04item\x18\x02 \x01(\x0b2\x14.google.protobuf.Any"\xbc\x01\n\x13UpdateItemsResponse\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x125\n\x06status\x18\x02 \x01(\x0e2%.kiapi.common.types.ItemRequestStatus\x12>\n\rupdated_items\x18\x03 \x03(\x0b2\'.kiapi.common.commands.ItemUpdateResult"i\n\x0bDeleteItems\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x12*\n\x08item_ids\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID"u\n\x12ItemDeletionResult\x12$\n\x02id\x18\x01 \x01(\x0b2\x18.kiapi.common.types.KIID\x129\n\x06status\x18\x02 \x01(\x0e2).kiapi.common.commands.ItemDeletionStatus"\xbe\x01\n\x13DeleteItemsResponse\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x125\n\x06status\x18\x02 \x01(\x0e2%.kiapi.common.types.ItemRequestStatus\x12@\n\rdeleted_items\x18\x03 \x03(\x0b2).kiapi.common.commands.ItemDeletionResult"\x9f\x01\n\x0eGetBoundingBox\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x12\'\n\x05items\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID\x124\n\x04mode\x18\x03 \x01(\x0e2&.kiapi.common.commands.BoundingBoxMode"j\n\x16GetBoundingBoxResponse\x12\'\n\x05items\x18\x01 \x03(\x0b2\x18.kiapi.common.types.KIID\x12\'\n\x05boxes\x18\x02 \x03(\x0b2\x18.kiapi.common.types.Box2"r\n\x0cGetSelection\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x122\n\x05types\x18\x02 \x03(\x0e2#.kiapi.common.types.KiCadObjectType"8\n\x11SelectionResponse\x12#\n\x05items\x18\x01 \x03(\x0b2\x14.google.protobuf.Any"i\n\x0eAddToSelection\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x12\'\n\x05items\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID"n\n\x13RemoveFromSelection\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x12\'\n\x05items\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID"@\n\x0eClearSelection\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader"\xae\x01\n\x0cFocusOnItems\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\'\n\x05items\x18\x02 \x03(\x0b2\x18.kiapi.common.types.KIID\x121\n\x06margin\x18\x03 \x01(\x0b2\x1c.kiapi.common.types.DistanceH\x00\x88\x01\x01B\t\n\x07_margin"\xa1\x01\n\x07HitTest\x12.\n\x06header\x18\x01 \x01(\x0b2\x1e.kiapi.common.types.ItemHeader\x12$\n\x02id\x18\x02 \x01(\x0b2\x18.kiapi.common.types.KIID\x12-\n\x08position\x18\x03 \x01(\x0b2\x1b.kiapi.common.types.Vector2\x12\x11\n\ttolerance\x18\x04 \x01(\x05"G\n\x0fHitTestResponse\x124\n\x06result\x18\x01 \x01(\x0e2$.kiapi.common.commands.HitTestResult"L\n\x11GetTitleBlockInfo\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"\x85\x01\n\x11SetTitleBlockInfo\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x127\n\x0btitle_block\x18\x02 \x01(\x0b2".kiapi.common.types.TitleBlockInfo"J\n\x0fGetPageSettings\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"\x83\x01\n\x0fSetPageSettings\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x127\n\rpage_settings\x18\x02 \x01(\x0b2 .kiapi.common.types.PageSettings"O\n\x14SaveDocumentToString\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier"b\n\x15SavedDocumentResponse\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x10\n\x08contents\x18\x02 \x01(\t"\x17\n\x15SaveSelectionToString"Q\n\x16SavedSelectionResponse\x12%\n\x03ids\x18\x01 \x03(\x0b2\x18.kiapi.common.types.KIID\x12\x10\n\x08contents\x18\x02 \x01(\t"j\n\x1dParseAndCreateItemsFromString\x127\n\x08document\x18\x01 \x01(\x0b2%.kiapi.common.types.DocumentSpecifier\x12\x10\n\x08contents\x18\x02 \x01(\t*N\n\x15DocumentModifiedState\x12\x0f\n\x0bDMS_UNKNOWN\x10\x00\x12\x12\n\x0eDMS_UNMODIFIED\x10\x01\x12\x10\n\x0cDMS_MODIFIED\x10\x02*W\n\x0fRunActionStatus\x12\x0f\n\x0bRAS_UNKNOWN\x10\x00\x12\n\n\x06RAS_OK\x10\x01\x12\x0f\n\x0bRAS_INVALID\x10\x02\x12\x16\n\x12RAS_FRAME_NOT_OPEN\x10\x03*=\n\x0cCommitAction\x12\x0f\n\x0bCMA_UNKNOWN\x10\x00\x12\x0e\n\nCMA_COMMIT\x10\x01\x12\x0c\n\x08CMA_DROP\x10\x02*\x93\x01\n\x0eItemStatusCode\x12\x0f\n\x0bISC_UNKNOWN\x10\x00\x12\n\n\x06ISC_OK\x10\x01\x12\x14\n\x10ISC_INVALID_TYPE\x10\x02\x12\x10\n\x0cISC_EXISTING\x10\x03\x12\x13\n\x0fISC_NONEXISTENT\x10\x04\x12\x11\n\rISC_IMMUTABLE\x10\x05\x12\x14\n\x10ISC_INVALID_DATA\x10\x07*Y\n\x12ItemDeletionStatus\x12\x0f\n\x0bIDS_UNKNOWN\x10\x00\x12\n\n\x06IDS_OK\x10\x01\x12\x13\n\x0fIDS_NONEXISTENT\x10\x02\x12\x11\n\rIDS_IMMUTABLE\x10\x03*R\n\x0fBoundingBoxMode\x12\x0f\n\x0bBBM_UNKNOWN\x10\x00\x12\x11\n\rBBM_ITEM_ONLY\x10\x01\x12\x1b\n\x17BBM_ITEM_AND_CHILD_TEXT\x10\x02*=\n\rHitTestResult\x12\x0f\n\x0bHTR_UNKNOWN\x10\x00\x12\x0e\n\nHTR_NO_HIT\x10\x01\x12\x0b\n\x07HTR_HIT\x10\x02b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'common.commands.editor_commands_pb2', _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_DOCUMENTMODIFIEDSTATE']._serialized_start = 5072
    _globals['_DOCUMENTMODIFIEDSTATE']._serialized_end = 5150
    _globals['_RUNACTIONSTATUS']._serialized_start = 5152
    _globals['_RUNACTIONSTATUS']._serialized_end = 5239
    _globals['_COMMITACTION']._serialized_start = 5241
    _globals['_COMMITACTION']._serialized_end = 5302
    _globals['_ITEMSTATUSCODE']._serialized_start = 5305
    _globals['_ITEMSTATUSCODE']._serialized_end = 5452
    _globals['_ITEMDELETIONSTATUS']._serialized_start = 5454
    _globals['_ITEMDELETIONSTATUS']._serialized_end = 5543
    _globals['_BOUNDINGBOXMODE']._serialized_start = 5545
    _globals['_BOUNDINGBOXMODE']._serialized_end = 5627
    _globals['_HITTESTRESULT']._serialized_start = 5629
    _globals['_HITTESTRESULT']._serialized_end = 5690
    _globals['_REFRESHEDITOR']._serialized_start = 148
    _globals['_REFRESHEDITOR']._serialized_end = 209
    _globals['_OPENLIBRARYITEM']._serialized_start = 211
    _globals['_OPENLIBRARYITEM']._serialized_end = 335
    _globals['_GETOPENDOCUMENTS']._serialized_start = 337
    _globals['_GETOPENDOCUMENTS']._serialized_end = 403
    _globals['_GETOPENDOCUMENTSRESPONSE']._serialized_start = 405
    _globals['_GETOPENDOCUMENTSRESPONSE']._serialized_end = 489
    _globals['_GETDOCUMENTMODIFIEDSTATE']._serialized_start = 491
    _globals['_GETDOCUMENTMODIFIEDSTATE']._serialized_end = 574
    _globals['_GETDOCUMENTMODIFIEDSTATERESPONSE']._serialized_start = 576
    _globals['_GETDOCUMENTMODIFIEDSTATERESPONSE']._serialized_end = 671
    _globals['_SAVEOPTIONS']._serialized_start = 673
    _globals['_SAVEOPTIONS']._serialized_end = 730
    _globals['_SAVECOPYOFDOCUMENT']._serialized_start = 733
    _globals['_SAVECOPYOFDOCUMENT']._serialized_end = 877
    _globals['_REVERTDOCUMENT']._serialized_start = 879
    _globals['_REVERTDOCUMENT']._serialized_end = 952
    _globals['_RUNACTION']._serialized_start = 954
    _globals['_RUNACTION']._serialized_end = 981
    _globals['_RUNACTIONRESPONSE']._serialized_start = 983
    _globals['_RUNACTIONRESPONSE']._serialized_end = 1058
    _globals['_BEGINCOMMIT']._serialized_start = 1060
    _globals['_BEGINCOMMIT']._serialized_end = 1121
    _globals['_BEGINCOMMITRESPONSE']._serialized_start = 1123
    _globals['_BEGINCOMMITRESPONSE']._serialized_end = 1182
    _globals['_ENDCOMMIT']._serialized_start = 1185
    _globals['_ENDCOMMIT']._serialized_end = 1352
    _globals['_ENDCOMMITRESPONSE']._serialized_start = 1354
    _globals['_ENDCOMMITRESPONSE']._serialized_end = 1373
    _globals['_CREATEITEMS']._serialized_start = 1376
    _globals['_CREATEITEMS']._serialized_end = 1519
    _globals['_ITEMSTATUS']._serialized_start = 1521
    _globals['_ITEMSTATUS']._serialized_end = 1609
    _globals['_ITEMCREATIONRESULT']._serialized_start = 1611
    _globals['_ITEMCREATIONRESULT']._serialized_end = 1718
    _globals['_CREATEITEMSRESPONSE']._serialized_start = 1721
    _globals['_CREATEITEMSRESPONSE']._serialized_end = 1911
    _globals['_GETITEMS']._serialized_start = 1913
    _globals['_GETITEMS']._serialized_end = 2023
    _globals['_GETITEMSBYID']._serialized_start = 2025
    _globals['_GETITEMSBYID']._serialized_end = 2128
    _globals['_GETITEMSRESPONSE']._serialized_start = 2131
    _globals['_GETITEMSRESPONSE']._serialized_end = 2289
    _globals['_UPDATEITEMS']._serialized_start = 2291
    _globals['_UPDATEITEMS']._serialized_end = 2389
    _globals['_ITEMUPDATERESULT']._serialized_start = 2391
    _globals['_ITEMUPDATERESULT']._serialized_end = 2496
    _globals['_UPDATEITEMSRESPONSE']._serialized_start = 2499
    _globals['_UPDATEITEMSRESPONSE']._serialized_end = 2687
    _globals['_DELETEITEMS']._serialized_start = 2689
    _globals['_DELETEITEMS']._serialized_end = 2794
    _globals['_ITEMDELETIONRESULT']._serialized_start = 2796
    _globals['_ITEMDELETIONRESULT']._serialized_end = 2913
    _globals['_DELETEITEMSRESPONSE']._serialized_start = 2916
    _globals['_DELETEITEMSRESPONSE']._serialized_end = 3106
    _globals['_GETBOUNDINGBOX']._serialized_start = 3109
    _globals['_GETBOUNDINGBOX']._serialized_end = 3268
    _globals['_GETBOUNDINGBOXRESPONSE']._serialized_start = 3270
    _globals['_GETBOUNDINGBOXRESPONSE']._serialized_end = 3376
    _globals['_GETSELECTION']._serialized_start = 3378
    _globals['_GETSELECTION']._serialized_end = 3492
    _globals['_SELECTIONRESPONSE']._serialized_start = 3494
    _globals['_SELECTIONRESPONSE']._serialized_end = 3550
    _globals['_ADDTOSELECTION']._serialized_start = 3552
    _globals['_ADDTOSELECTION']._serialized_end = 3657
    _globals['_REMOVEFROMSELECTION']._serialized_start = 3659
    _globals['_REMOVEFROMSELECTION']._serialized_end = 3769
    _globals['_CLEARSELECTION']._serialized_start = 3771
    _globals['_CLEARSELECTION']._serialized_end = 3835
    _globals['_FOCUSONITEMS']._serialized_start = 3838
    _globals['_FOCUSONITEMS']._serialized_end = 4012
    _globals['_HITTEST']._serialized_start = 4015
    _globals['_HITTEST']._serialized_end = 4176
    _globals['_HITTESTRESPONSE']._serialized_start = 4178
    _globals['_HITTESTRESPONSE']._serialized_end = 4249
    _globals['_GETTITLEBLOCKINFO']._serialized_start = 4251
    _globals['_GETTITLEBLOCKINFO']._serialized_end = 4327
    _globals['_SETTITLEBLOCKINFO']._serialized_start = 4330
    _globals['_SETTITLEBLOCKINFO']._serialized_end = 4463
    _globals['_GETPAGESETTINGS']._serialized_start = 4465
    _globals['_GETPAGESETTINGS']._serialized_end = 4539
    _globals['_SETPAGESETTINGS']._serialized_start = 4542
    _globals['_SETPAGESETTINGS']._serialized_end = 4673
    _globals['_SAVEDOCUMENTTOSTRING']._serialized_start = 4675
    _globals['_SAVEDOCUMENTTOSTRING']._serialized_end = 4754
    _globals['_SAVEDDOCUMENTRESPONSE']._serialized_start = 4756
    _globals['_SAVEDDOCUMENTRESPONSE']._serialized_end = 4854
    _globals['_SAVESELECTIONTOSTRING']._serialized_start = 4856
    _globals['_SAVESELECTIONTOSTRING']._serialized_end = 4879
    _globals['_SAVEDSELECTIONRESPONSE']._serialized_start = 4881
    _globals['_SAVEDSELECTIONRESPONSE']._serialized_end = 4962
    _globals['_PARSEANDCREATEITEMSFROMSTRING']._serialized_start = 4964
    _globals['_PARSEANDCREATEITEMSFROMSTRING']._serialized_end = 5070