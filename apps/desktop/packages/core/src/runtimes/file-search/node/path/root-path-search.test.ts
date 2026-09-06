import { ok } from '@emdash/shared';
import { createConcurrencyLimiter, createScope } from '@emdash/shared/concurrency';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { HostAbsolutePath } from '#primitives/path/api';
import type { IWatchService } from '#services/fs-watch/api';
import { DefaultFileSearchExclusions } from '../exclusions';
import { createRegisteredRoot } from '../root/registered-root';
import { hostPath as absolute } from '../testing/paths';
import type {
  PathIndexBuild,
  PathIndexEntry,
  PathIndexStore,
  PathIndexStoreSearchResult,
} from './index/path-index-store';
import type { PathScanner } from './index/scanner';
import { searchRootPaths } from './root-path-search';

const cleanups: Array<() => void | Promise<void>> = [];

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup();
});

describe('searchRootPaths', () => {
  it('maps expected scan and store failures while throwing invariant failures', async () => {
    const root = absolute('/workspace');
    const missing = Object.assign(new Error('gone'), { code: 'ENOENT' });
    const failedScan = createRoot('/workspace', { scanner: new FailingScanner(missing) });
    await vi.waitFor(() => {
      expect(searchRootPaths(failedScan.root, pathInput(root), failedScan.store)).toMatchObject({
        success: false,
        error: { type: 'root-unavailable', reason: 'not-found' },
      });
    });

    const busy = Object.assign(new Error('database busy'), { code: 'SQLITE_BUSY' });
    const busyStore = new FakePathIndexStore(() => {
      throw busy;
    });
    const busyRoot = createRoot('/workspace', { store: busyStore }).root;
    await waitForPublished(busyStore);
    expect(searchRootPaths(busyRoot, pathInput(root), busyStore)).toMatchObject({
      success: false,
      error: { type: 'io' },
    });

    const invariant = new Error('path-index invariant failed');
    const brokenStore = new FakePathIndexStore(() => {
      throw invariant;
    });
    const brokenRoot = createRoot('/workspace', { store: brokenStore }).root;
    await waitForPublished(brokenStore);
    expect(() => searchRootPaths(brokenRoot, pathInput(root), brokenStore)).toThrow(invariant);
  });
});

class FakePathIndexStore implements PathIndexStore {
  published = false;

  constructor(
    private readonly search: () => PathIndexStoreSearchResult = () => ({
      kind: 'ready',
      hits: [],
    })
  ) {}

  beginBuild(): PathIndexBuild {
    return {
      append: () => {},
      publish: () => {
        this.published = true;
      },
      discard: () => {},
    };
  }

  applyPublishedPatches(): void {}

  searchPaths(): PathIndexStoreSearchResult {
    return this.search();
  }
}

class EmptyScanner implements PathScanner {
  async *scan(): AsyncIterable<PathIndexEntry> {
    yield* [];
  }
}

class FailingScanner implements PathScanner {
  constructor(private readonly failure: unknown) {}

  async *scan(): AsyncIterable<PathIndexEntry> {
    yield* [];
    throw this.failure;
  }
}

class NoopWatchService implements IWatchService {
  watch() {
    return { ready: async () => ok(undefined), release: async () => {} };
  }

  async dispose(): Promise<void> {}
}

function createRoot(
  rootPath: string,
  options: { store?: FakePathIndexStore; scanner?: PathScanner } = {}
) {
  const scope = createScope({ label: 'root-path-search-test' });
  cleanups.push(() => scope.dispose());
  const store = options.store ?? new FakePathIndexStore();
  const root = createRegisteredRoot({
    record: { id: 1, rootKey: 'root-key', rootPath },
    indexStore: store,
    watcher: new NoopWatchService(),
    scanner: options.scanner ?? new EmptyScanner(),
    exclusions: new DefaultFileSearchExclusions({ caseSensitive: true }),
    exclusionsFingerprint: '[]',
    scope,
    scanLimiter: createConcurrencyLimiter(1),
  });
  return { root, store };
}

async function waitForPublished(store: FakePathIndexStore): Promise<void> {
  await vi.waitFor(() => expect(store.published).toBe(true));
}

function pathInput(root: HostAbsolutePath) {
  return { root, query: '', kinds: ['file' as const] };
}
