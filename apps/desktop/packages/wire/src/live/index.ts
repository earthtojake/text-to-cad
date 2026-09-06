// Public `@emdash/wire/live` entry: the server-side reactivity sources, the
// keyed replica caches consumers hold on the client side, and the resync
// failure policies threaded through their options.
export { eventFromUpdate } from './event-stream/client';
export {
  createEventStreamHost,
  EventStreamSource,
  type EventStreamHost,
  type EventStreamHostOptions,
  type EventStreamSourceOptions,
} from './event-stream/source';
export {
  resyncMarkStale,
  resyncRetry,
  type LiveResyncFailureContext,
  type LiveResyncFailureDecision,
  type LiveResyncFailurePolicy,
} from './follower';
export { LiveJobCancelledError, LiveJobFailedError } from './job/client';
export {
  LiveJobSource,
  type LiveJobContext,
  type LiveJobHandler,
  type LiveJobListEntry,
  type LiveJobSourceOptions,
} from './job/source';
export { createLineLogStore, type LineLogStore, type LineLogStoreOptions } from './log/line-store';
export {
  LIVE_LOG_DEFAULT_MAX_BUFFER_BYTES,
  LiveLogSource,
  type LiveLogSourceOptions,
} from './log/source';
export {
  createLiveJobReplicaCache,
  createPlainJobStore,
  ReplicaJob,
  type JobStore,
  type LiveJobReplicaCache,
  type LiveJobReplicaCacheOptions,
  type ReplicaJobOptions,
  type ReplicaJobState,
} from './replica/job';
export {
  createLiveLogReplicaCache,
  ReplicaLog,
  type LiveLogReplicaCache,
  type LiveLogReplicaCacheOptions,
  type LogSink,
  type LogStore,
  type ReplicaLogOptions,
} from './replica/log';
export { type StateStore } from './replica/store';
