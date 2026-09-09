import { mkdtemp, realpath, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { afterEach, describe, expect, it } from 'vitest';
import { RootWatchError } from '../path/index/errors';
import { hostPath as absolute } from '../testing/paths';
import type { RegisteredRoot, StoredFileSearchRoot } from './registered-root';
import { NodeFileSearchRootResolver } from './root-identity';
import { FileSearchRootRegistry, type RootCatalogStore } from './root-registry';

const cleanups: Array<() => void | Promise<void>> = [];

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup();
});

describe('FileSearchRootRegistry.resolveRegisteredRoot', () => {
  it('maps idle and starting roots as unregistered, then resolves the ready root', async () => {
    const rootPath = await createRootDirectory();
    const root = absolute(rootPath);
    const { registry } = createRegistry();

    expect(resolveRoot(registry, root)).toMatchObject({
      success: false,
      error: { type: 'root-not-registered' },
    });

    const registration = registry.registerRoot({ root });
    expect(resolveRoot(registry, root)).toMatchObject({
      success: false,
      error: { type: 'root-not-registered' },
    });

    await expect(registration).resolves.toMatchObject({ success: true });
    expect(resolveRoot(registry, root)).toMatchObject({ success: true });
  });

  it('preserves start failures and maps stopping roots as unregistered', async () => {
    const rootPath = await createRootDirectory();
    const root = absolute(rootPath);
    const failure = Object.assign(new Error('root disappeared'), { code: 'ENOENT' });
    const failed = createRegistry({
      createRoot: (_record, _scope, _exclusions, _fingerprint) => {
        throw new RootWatchError('watcher attach failed', failure);
      },
    }).registry;

    await expect(failed.registerRoot({ root })).resolves.toMatchObject({ success: false });
    expect(resolveRoot(failed, root)).toMatchObject({
      success: false,
      error: { type: 'root-unavailable', reason: 'not-found' },
    });

    const { registry } = createRegistry();
    await registry.registerRoot({ root });
    const unregister = registry.unregisterRoot({ root });
    expect(resolveRoot(registry, root)).toMatchObject({
      success: false,
      error: { type: 'root-not-registered' },
    });
    await expect(unregister).resolves.toMatchObject({ success: true });
  });

  it('keeps stop-failed resources available and rejects access after disposal', async () => {
    const rootPath = await createRootDirectory();
    const root = absolute(rootPath);
    const catalog = new MemoryCatalog();
    const { registry } = createRegistry({ catalog });
    await registry.registerRoot({ root });
    catalog.deleteFailure = Object.assign(new Error('database busy'), { code: 'SQLITE_BUSY' });

    await expect(registry.unregisterRoot({ root })).resolves.toMatchObject({ success: false });
    expect(resolveRoot(registry, root)).toMatchObject({ success: true });

    catalog.deleteFailure = undefined;
    await registry.dispose();
    expect(() => resolveRoot(registry, root)).toThrow('disposed');
  });
});

class MemoryCatalog implements RootCatalogStore {
  readonly roots = new Map<string, StoredFileSearchRoot>();
  deleteFailure: unknown | undefined;
  private nextId = 1;

  listRoots(): StoredFileSearchRoot[] {
    return [...this.roots.values()];
  }

  upsertRoot(input: { rootKey: string; rootPath: string }) {
    const existing = this.roots.get(input.rootKey);
    if (existing) return { kind: 'unchanged' as const, root: existing };
    const root = { id: this.nextId++, ...input };
    this.roots.set(root.rootKey, root);
    return { kind: 'created' as const, root };
  }

  deleteRoot(rootKey: string): void {
    if (this.deleteFailure !== undefined) throw this.deleteFailure;
    this.roots.delete(rootKey);
  }
}

function createRegistry(
  options: {
    catalog?: MemoryCatalog;
    createRoot?: (
      record: StoredFileSearchRoot,
      scope: Scope,
      exclusions: unknown,
      fingerprint: string
    ) => RegisteredRoot;
  } = {}
): { registry: FileSearchRootRegistry; scope: Scope } {
  const scope = createScope({ label: 'root-registry-resolution-test' });
  const registry = new FileSearchRootRegistry({
    catalog: options.catalog ?? new MemoryCatalog(),
    resolver: new NodeFileSearchRootResolver(),
    createRoot:
      options.createRoot ??
      ((record, rootScope, _exclusions, fingerprint) => fakeRoot(record, rootScope, fingerprint)),
    compileExclusions: () => ({
      excludes: () => false,
      ripgrepGlobs: () => [],
      watchIgnoreGlobs: () => [],
    }),
    defaultExclusionPatterns: [],
    scope,
  });
  cleanups.push(async () => {
    await registry.dispose();
    await scope.dispose();
  });
  return { registry, scope };
}

function fakeRoot(
  record: StoredFileSearchRoot,
  scope: Scope,
  exclusionsFingerprint = '[]'
): RegisteredRoot {
  return { record, scope, index: {} as RegisteredRoot['index'], exclusionsFingerprint };
}

function resolveRoot(registry: FileSearchRootRegistry, root: ReturnType<typeof absolute>) {
  return registry.resolveRegisteredRoot(root);
}

async function createRootDirectory(): Promise<string> {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'emdash-root-registry-resolution-'));
  cleanups.push(() => rm(directory, { recursive: true, force: true }));
  return realpath(directory);
}
