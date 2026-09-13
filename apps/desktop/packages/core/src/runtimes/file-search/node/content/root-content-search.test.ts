import { mkdtemp, realpath, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { ok } from '@emdash/shared';
import { createConcurrencyLimiter, createScope } from '@emdash/shared/concurrency';
import { deferred } from '@emdash/shared/testing';
import { afterEach, describe, expect, it } from 'vitest';
import type { ContentSearchResult } from '#runtimes/file-search/api';
import type { RegisteredRoot } from '../root/registered-root';
import { hostPath as absolute } from '../testing/paths';
import type {
  ContentSearchContext,
  FileContentSearcher,
  ResolvedContentSearchInput,
} from './content-searcher';
import { searchRootContent } from './root-content-search';

const cleanups: Array<() => void | Promise<void>> = [];

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup();
});

describe('searchRootContent', () => {
  it('runs independently of path-index readiness and applies resolved defaults', async () => {
    const rootPath = await createDirectory();
    const root = registeredRoot(rootPath);
    const searcher = new RecordingContentSearcher();

    await expect(
      searchRootContent(
        root,
        { root: absolute(rootPath), query: 'term' },
        { signal: new AbortController().signal, onProgress: () => {} },
        { limiter: createConcurrencyLimiter(1), searcher }
      )
    ).resolves.toEqual({ success: true, data: emptyContentResult() });
    expect(searcher.inputs).toEqual([
      expect.objectContaining({ rootPath, searchPath: rootPath, limit: 1_000 }),
    ]);
  });

  it('cancels and awaits root-scoped work when the registration scope closes', async () => {
    const rootPath = await createDirectory();
    const root = registeredRoot(rootPath);
    const searcher = new BlockingContentSearcher();
    const search = searchRootContent(
      root,
      { root: absolute(rootPath), query: 'term' },
      { signal: new AbortController().signal, onProgress: () => {} },
      { limiter: createConcurrencyLimiter(1), searcher }
    );
    void search.catch(() => {});
    await searcher.started.promise;

    const disposal = root.scope.dispose(new Error('root unregistered'));
    await searcher.cancelled.promise;
    await expect(search).rejects.toBeDefined();
    await disposal;
  });
});

class RecordingContentSearcher implements FileContentSearcher {
  readonly inputs: ResolvedContentSearchInput[] = [];

  async search(input: ResolvedContentSearchInput, _context: ContentSearchContext) {
    this.inputs.push(input);
    return ok(emptyContentResult());
  }
}

class BlockingContentSearcher implements FileContentSearcher {
  readonly started = deferred<void>();
  readonly cancelled = deferred<void>();

  search(
    _input: ResolvedContentSearchInput,
    context: ContentSearchContext
  ): Promise<ReturnType<typeof successResult>> {
    this.started.resolve();
    return new Promise((_resolve, reject) => {
      const cancel = (): void => {
        this.cancelled.resolve();
        reject(context.signal.reason);
      };
      if (context.signal.aborted) cancel();
      else context.signal.addEventListener('abort', cancel, { once: true });
    });
  }
}

function registeredRoot(rootPath: string): RegisteredRoot {
  const scope = createScope({ label: 'root-content-search-test' });
  cleanups.push(() => scope.dispose());
  return {
    record: { id: 1, rootKey: 'root-key', rootPath },
    index: {} as RegisteredRoot['index'],
    scope,
    exclusionsFingerprint: '[]',
  };
}

async function createDirectory(): Promise<string> {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'emdash-root-content-search-'));
  cleanups.push(() => rm(directory, { recursive: true, force: true }));
  return realpath(directory);
}

function successResult() {
  return { success: true as const, data: emptyContentResult() };
}

function emptyContentResult(): ContentSearchResult {
  return { files: [], complete: true };
}
