import type { Result } from '@emdash/shared';
import {
  createConcurrencyLimiter,
  createScope,
  type ConcurrencyLimiter,
  type Scope,
} from '@emdash/shared/concurrency';
import type Database from 'better-sqlite3';
import { DEFAULT_SEARCH_EXCLUDE } from '#primitives/exclusion-policy/api';
import type { EnvSource } from '#primitives/exec/api';
import type { StoreHandle } from '#primitives/sqlite-store/api';
import type {
  ContentSearchError,
  ContentSearchInput,
  ContentSearchResult,
  FileSearchRegisterRootError,
  FileSearchRootInput,
  FileSearchUnregisterRootError,
  PathSearchError,
  PathSearchInput,
  PathSearchResult,
} from '#runtimes/file-search/api';
import type { IWatchService } from '#services/fs-watch/api';
import type { ContentSearchContext } from './content/content-searcher';
import { RipgrepContentSearcher } from './content/ripgrep/ripgrep-content-searcher';
import { searchRootContent } from './content/root-content-search';
import { DefaultFileSearchExclusions } from './exclusions';
import { NodePathScanner } from './path/index/scanner';
import { searchRootPaths } from './path/root-path-search';
import { createRegisteredRoot } from './root/registered-root';
import { NodeFileSearchRootResolver } from './root/root-identity';
import { FileSearchRootRegistry } from './root/root-registry';
import { SqliteFileSearchStore } from './storage/sqlite-file-search-store';
import type { FileSearchDb } from './storage/store';

const DEFAULT_MAX_CONCURRENT_SCANS = 2;
const DEFAULT_MAX_CONCURRENT_CONTENT_SEARCHES = 4;

export type FileSearchRuntimeOptions = Readonly<{
  handle: StoreHandle<FileSearchDb, Database.Database>;
  watcher: IWatchService;
  ripgrepPath?: string;
  env?: EnvSource;
  maxConcurrentScans?: number;
  maxConcurrentContentSearches?: number;
  onError?: (context: string, error: unknown) => void;
}>;

/** Host-scoped composition root for durable root, path, and content search. */
export class FileSearchRuntime {
  private readonly scope: Scope;
  private readonly roots: FileSearchRootRegistry;
  private readonly store: SqliteFileSearchStore;
  private readonly contentLimiter: ConcurrencyLimiter;
  private readonly contentSearcher: RipgrepContentSearcher;
  private disposePromise: Promise<void> | undefined;

  constructor(options: FileSearchRuntimeOptions) {
    const onError = options.onError ?? (() => {});
    this.scope = createScope({
      label: 'file-search-runtime',
      onCleanupError: (error) => onError('file-search cleanup failed', error),
    });
    this.store = new SqliteFileSearchStore(options.handle);

    try {
      const defaultContentExclusions = new DefaultFileSearchExclusions();
      const scanner = new NodePathScanner();
      const scanLimiter = createConcurrencyLimiter(
        options.maxConcurrentScans ?? DEFAULT_MAX_CONCURRENT_SCANS
      );
      this.contentLimiter = createConcurrencyLimiter(
        options.maxConcurrentContentSearches ?? DEFAULT_MAX_CONCURRENT_CONTENT_SEARCHES
      );
      this.contentSearcher = new RipgrepContentSearcher({
        executable: options.ripgrepPath,
        env: options.env ?? (async () => process.env),
        exclusions: defaultContentExclusions,
      });
      this.roots = new FileSearchRootRegistry({
        catalog: this.store,
        resolver: new NodeFileSearchRootResolver(),
        createRoot: (record, scope, rootExclusions, exclusionsFingerprint) =>
          createRegisteredRoot({
            record,
            indexStore: this.store,
            watcher: options.watcher,
            scanner,
            exclusions: rootExclusions,
            exclusionsFingerprint,
            scope,
            scanLimiter,
            onError,
          }),
        compileExclusions: (patterns) => new DefaultFileSearchExclusions({ patterns }),
        defaultExclusionPatterns: DEFAULT_SEARCH_EXCLUDE,
        scope: this.scope,
        onError,
      });
    } catch (error) {
      void this.scope.dispose(error);
      throw error;
    }
  }

  registerRoot(input: FileSearchRootInput): Promise<Result<void, FileSearchRegisterRootError>> {
    return this.roots.registerRoot(input);
  }

  unregisterRoot(input: FileSearchRootInput): Promise<Result<void, FileSearchUnregisterRootError>> {
    return this.roots.unregisterRoot(input);
  }

  async searchPaths(input: PathSearchInput): Promise<Result<PathSearchResult, PathSearchError>> {
    const root = this.roots.resolveRegisteredRoot(input.root);
    return root.success ? searchRootPaths(root.data, input, this.store) : root;
  }

  searchContent(
    input: ContentSearchInput,
    context: ContentSearchContext
  ): Promise<Result<ContentSearchResult, ContentSearchError>> {
    const root = this.roots.resolveRegisteredRoot(input.root);
    return root.success
      ? searchRootContent(root.data, input, context, {
          limiter: this.contentLimiter,
          searcher: this.contentSearcher,
        })
      : Promise.resolve(root);
  }

  dispose(): Promise<void> {
    if (this.disposePromise) return this.disposePromise;
    this.disposePromise = this.disposeInternal();
    return this.disposePromise;
  }

  private async disposeInternal(): Promise<void> {
    try {
      await this.roots.dispose();
    } finally {
      await this.scope.dispose(new Error('File-search runtime disposed'));
    }
  }
}
