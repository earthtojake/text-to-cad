// Public `@emdash/wire/rpc` entry: contracts and endpoint factories, the
// client/serve/controller surface, transports, protocol vocabulary, provider
// seam types, blob surface, validation, and instrumentation seam types.
export {
  blobSourceFromBytes,
  isDownloadFileOpenResult,
  type BlobDownloadHandle,
  type BlobSource,
  type DownloadFileOpen,
  type FileLike,
  type ReadableStreamLike,
  type UploadFileValue,
  type WireFile,
} from '../api/blob-channel';
export {
  createMutationId,
  type EventStreamSnapshotData,
  type LiveAttachmentErrorContext,
  type LiveCursor,
  type LiveCursorEntry,
  type LiveLogSnapshotData,
  type LiveMutationInput,
  type LiveMutationResult,
  type LiveMutationSuccess,
  type LiveSnapshot,
  type LiveSource,
  type LiveSubscribeOptions,
  type LiveUpdate,
  type Mutator,
} from '../api/channel';
export {
  type ClientOptions,
  type ContractClient,
  type EventStreamClientHandle,
  type EventStreamSubscribeOptions,
  type FileUploadCallOptions,
  type LiveClientHandle,
  type LiveJobClientHandle,
  type LiveJobStateFor,
  type LiveLogClientHandle,
  type LiveModelClientHandle,
  type MutationCallOptions,
  type ProcedureCallOptions,
} from '../api/client';
export {
  connect,
  type AttachOptions,
  type CallOptions,
  type Connection,
  type ConnectOptions,
} from '../api/connect';
export { type CallMeta, type Controller, type ProcedureHandler } from '../api/controller';
export {
  defineContract,
  downloadFile,
  eventStream,
  fallible,
  liveJob,
  liveLog,
  liveModel,
  liveState,
  mutation,
  procedure,
  resourcedStream,
  uploadFile,
  type Contract,
  type ContractDefinitions,
  type ContractEntry,
  type DownloadFileEndpointDef,
  type DownloadFileError,
  type DownloadFileInput,
  type DownloadFileMeta,
  type EndpointDef,
  type EndpointInput,
  type EndpointOutput,
  type EventStreamEndpointDef,
  type EventStreamEvent,
  type EventStreamKey,
  type JobError,
  type JobInput,
  type JobProgress,
  type JobResult,
  type LiveJobEndpointDef,
  type LiveLogEndpointDef,
  type LiveLogKey,
  type LiveModelDef,
  type LiveModelKey,
  type LiveModelMutationCtx,
  type LiveModelMutationHandler,
  type LiveModelMutations,
  type LiveModelStates,
  type LiveStateData,
  type LiveStateDef,
  type LiveStateKey,
  type MutationData,
  type MutationDef,
  type MutationError,
  type MutationInput,
  type ProcedureDef,
  type UploadFileEndpointDef,
  type UploadFileError,
  type UploadFileInput,
  type UploadFileResult,
} from '../api/define';
export {
  type WireBatchDroppedEvent,
  type WireCallEndEvent,
  type WireCallStartEvent,
  type WireCancelEvent,
  type WireCursorTranslationTimeoutEvent,
  type WireInstrumentation,
  type WireMutationDedupedEvent,
  type WireResyncEvent,
  type WireResyncFailedEvent,
  type WireResyncReason,
  type WireScopeCleanupErrorEvent,
  type WireSnapshotEvent,
  type WireTopicAttachEvent,
  type WireTopicDetachEvent,
  type WireTransportEvent,
} from '../api/instrumentation';
export {
  WireError,
  type WireErrorCode,
  type WireFileMeta,
  type WireMessage,
  type WireTransport,
} from '../api/protocol';
export { serve, type ServeOptions } from '../api/serve';
export { createWireSessionHub, type WireSessionHub } from '../api/sessions';
export { encodeTopic } from '../api/topics';
export { domPortTransport, type DomPortLike } from '../api/transports/dom-port';
export {
  awaitWirePort,
  exposeWireToWindows,
  requestWirePort,
  type ExposeWireOptions,
  type IpcMainInvokeEventLike,
  type IpcMainLike,
  type IpcRendererLike,
  type MessageChannelFactory,
  type MessagePortMainLike,
  type WebContentsLike,
  type WindowLike,
} from '../api/transports/electron';
export { memoryTransportPair, type MemoryTransportPair } from '../api/transports/memory';
export { type PortLike } from '../api/transports/port';
export {
  reconnectingTransport,
  type ReconnectFailureContext,
  type ReconnectingTransport,
  type ReconnectingTransportOptions,
} from '../api/transports/reconnecting';
export { streamTransport } from '../api/transports/stream';
export { applyValidation, type ValidatePolicy } from '../api/validation';
export { type LeasedLiveModelProvider } from '../live/replica/leased-provider';
export { type LiveModelMutationEnvelope, type LiveModelProvider } from '../live/replica/provider';
export { client } from './client';
export { queuedClient } from './queued-client';
export { createController, type ContractImpl, type CreateControllerOptions } from './controller';
export { forwardContractImpl, forwardController } from './forward';
export {
  createInProcessWire,
  type CreateInProcessWireOptions,
  type InProcessWire,
} from './in-process-wire';
