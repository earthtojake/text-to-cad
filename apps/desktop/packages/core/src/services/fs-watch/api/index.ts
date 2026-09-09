export {
  fsWatchContract,
  watchEventSchema,
  watchEventsBatchSchema,
  watchKeySchema,
  watchResyncSchema,
  type FsWatchEvent,
  type FsWatchKey,
  type FsWatchStreamEvent,
} from './contract';
export { requireWatchReady } from './models';
export type {
  IWatchService,
  WatchEvent,
  WatchEventKind,
  WatchHandle,
  WatchOptions,
} from './models';

export { fsWatchWorker } from './worker';
