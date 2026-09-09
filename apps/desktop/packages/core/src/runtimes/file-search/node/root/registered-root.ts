import type { ConcurrencyLimiter, Scope } from '@emdash/shared/concurrency';
import type { IWatchService } from '#services/fs-watch/api';
import type { FileSearchExclusions } from '../exclusions';
import type { PathIndexStore } from '../path/index/path-index-store';
import { RootIndex } from '../path/index/root-index';
import type { PathScanner } from '../path/index/scanner';

export type StoredFileSearchRoot = Readonly<{
  id: number;
  rootKey: string;
  rootPath: string;
}>;

export type RegisteredRoot = Readonly<{
  record: StoredFileSearchRoot;
  index: RootIndex;
  scope: Scope;
  /** Stable identity string for the exclusion set used to build this root's index. */
  exclusionsFingerprint: string;
}>;

export type CreateRegisteredRootOptions = Readonly<{
  record: StoredFileSearchRoot;
  indexStore: PathIndexStore;
  watcher: IWatchService;
  scanner: PathScanner;
  exclusions: FileSearchExclusions;
  exclusionsFingerprint: string;
  scope: Scope;
  scanLimiter: ConcurrencyLimiter;
  onError?: (context: string, error: unknown) => void;
}>;

/** Builds one registered root and starts its path-index reconciliation in the background. */
export function createRegisteredRoot(options: CreateRegisteredRootOptions): RegisteredRoot {
  const index = new RootIndex({
    root: options.record,
    store: options.indexStore,
    watcher: options.watcher,
    scanner: options.scanner,
    exclusions: options.exclusions,
    scope: options.scope,
    runScan: (signal, operation) => options.scanLimiter.run(signal, operation),
    onError: options.onError,
  });
  void index.reconcile().catch((error: unknown) => {
    if (!options.scope.signal.aborted) {
      options.onError?.('file-search reconciliation failed', error);
    }
  });
  return {
    record: options.record,
    index,
    scope: options.scope,
    exclusionsFingerprint: options.exclusionsFingerprint,
  };
}
