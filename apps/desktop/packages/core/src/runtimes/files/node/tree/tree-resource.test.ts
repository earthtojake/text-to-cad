import { mkdir, mkdtemp, realpath, rename, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { ok } from '@emdash/shared';
import { deferred } from '@emdash/shared/testing';
import { snapshot } from '@emdash/wire/state';
import { afterEach, describe, expect, it } from 'vitest';
import { ROOT_RELATIVE_PATH, type PortableRelativePath } from '#primitives/path/api';
import type { FileTreeModel } from '#runtimes/files/api';
import { resolveRootIdentity, treeIdentity } from '#runtimes/files/node/allocation/identity';
import { RootResource } from '#runtimes/files/node/root/root-resource';
import { runtimeRoot } from '#runtimes/files/node/testing/paths';
import type { IWatchService, WatchEvent, WatchOptions } from '#services/fs-watch/api';
import { TreeResource } from './tree-resource';

const cleanups: Array<() => void | Promise<void>> = [];

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup();
});

describe('TreeResource', () => {
  it('eagerly expands one child layer when depth is 2', async () => {
    const { rootPath, tree } = await createHarness({ exclusions: [] });
    await mkdir(path.join(rootPath, 'repo', '.git'), { recursive: true });
    await mkdir(path.join(rootPath, 'plain', 'src'), { recursive: true });

    const diagnostic = tree as unknown as DiagnosticTreeResource;
    const result = await diagnostic.expandPath(ROOT_RELATIVE_PATH, undefined, 2);

    expect(result.success).toBe(true);
    const model = diagnostic.current();
    expect(model.entries.repo?.childrenLoaded).toBe(true);
    expect(model.entries.repo?.children).toContain('repo/.git');
    expect(model.entries.plain?.childrenLoaded).toBe(true);
    expect(model.entries.plain?.children).toContain('plain/src');
    expect(model.entries['repo/.git']?.childrenLoaded).toBe(false);
  });

  it('keeps expand shallow when depth is omitted', async () => {
    const { rootPath, tree } = await createHarness({ exclusions: [] });
    await mkdir(path.join(rootPath, 'repo', '.git'), { recursive: true });

    const diagnostic = tree as unknown as DiagnosticTreeResource;
    const result = await diagnostic.expandPath(ROOT_RELATIVE_PATH);

    expect(result.success).toBe(true);
    const model = diagnostic.current();
    expect(model.entries.repo?.childrenLoaded).toBe(false);
    expect(model.entries.repo?.children).toEqual([]);
  });

  it('filters excluded entries from expanded directories', async () => {
    const { rootPath, tree } = await createHarness({ exclusions: ['generated'] });
    await mkdir(path.join(rootPath, 'src', 'generated'), { recursive: true });
    await writeFile(path.join(rootPath, 'src', 'app.ts'), '');
    await writeFile(path.join(rootPath, 'src', 'generated', 'client.ts'), '');

    const diagnostic = tree as unknown as DiagnosticTreeResource;
    await diagnostic.expandPath(ROOT_RELATIVE_PATH);
    await diagnostic.expandPath(portable('src'));

    expect(diagnostic.current().entries['src/app.ts']).toBeDefined();
    expect(diagnostic.current().entries['src/generated']).toBeUndefined();
    expect(diagnostic.current().entries.src?.children).toEqual(['src/app.ts']);
  });

  it('ignores watcher events under excluded paths', async () => {
    const { rootPath, tree, watcher } = await createHarness({ exclusions: ['generated'] });
    await mkdir(path.join(rootPath, 'src', 'generated'), { recursive: true });
    await writeFile(path.join(rootPath, 'src', 'app.ts'), '');

    const diagnostic = tree as unknown as DiagnosticTreeResource;
    await diagnostic.expandPath(ROOT_RELATIVE_PATH);
    await diagnostic.expandPath(portable('src'));
    await writeFile(path.join(rootPath, 'src', 'generated', 'client.ts'), '');
    watcher.emit([{ kind: 'create', path: path.join(rootPath, 'src', 'generated', 'client.ts') }]);
    await diagnostic.lane;

    expect(diagnostic.current().entries['src/generated']).toBeUndefined();
    expect(diagnostic.current().entries.src?.children).toEqual(['src/app.ts']);
  });

  it('coalesces a resync burst to one active and one trailing rebuild', async () => {
    const { tree, watcher } = await createHarness();
    const diagnostic = tree as unknown as DiagnosticTreeResource;
    const firstStarted = deferred<void>();
    const resumeFirst = deferred<void>();
    let rebuilds = 0;

    diagnostic.resync = async () => {
      rebuilds += 1;
      if (rebuilds !== 1) return;
      firstStarted.resolve();
      await resumeFirst.promise;
    };

    watcher.resync();
    await firstStarted.promise;
    for (let index = 0; index < 10; index += 1) watcher.resync();

    expect(rebuilds).toBe(1);
    resumeFirst.resolve();
    await diagnostic.lane;

    expect(rebuilds).toBe(2);
  });

  it('drops a trailing resync when disposed during the active rebuild', async () => {
    const { tree, watcher } = await createHarness();
    const diagnostic = tree as unknown as DiagnosticTreeResource;
    const firstStarted = deferred<void>();
    const resumeFirst = deferred<void>();
    let rebuilds = 0;

    diagnostic.resync = async () => {
      rebuilds += 1;
      if (rebuilds !== 1) return;
      firstStarted.resolve();
      await resumeFirst.promise;
    };

    watcher.resync();
    await firstStarted.promise;
    watcher.resync();
    const disposal = tree.dispose();
    resumeFirst.resolve();
    await disposal;

    expect(rebuilds).toBe(1);
  });

  it('applies ack-time absolute create changes to loaded parents', async () => {
    const { rootPath, tree } = await createHarness();
    const diagnostic = tree as unknown as DiagnosticTreeResource;
    await diagnostic.expandPath(ROOT_RELATIVE_PATH);

    await writeFile(path.join(rootPath, 'new.ts'), '');
    await tree.applyAbsoluteChanges([
      { kind: 'create', absolutePath: path.join(rootPath, 'new.ts') },
    ]);

    expect(diagnostic.current().entries['new.ts']).toMatchObject({
      path: 'new.ts',
      kind: 'file',
      parentPath: '',
    });
  });

  it('removes deleted subtrees at ack time', async () => {
    const { rootPath, tree } = await createHarness();
    await mkdir(path.join(rootPath, 'src'), { recursive: true });
    await writeFile(path.join(rootPath, 'src', 'app.ts'), '');
    const diagnostic = tree as unknown as DiagnosticTreeResource;
    await diagnostic.expandPath(ROOT_RELATIVE_PATH);
    await diagnostic.expandPath(portable('src'));

    await rm(path.join(rootPath, 'src'), { recursive: true });
    await tree.applyAbsoluteChanges([{ kind: 'delete', absolutePath: path.join(rootPath, 'src') }]);

    expect(diagnostic.current().entries.src).toBeUndefined();
    expect(diagnostic.current().entries['src/app.ts']).toBeUndefined();
    expect(diagnostic.current().entries[''].children).not.toContain('src');
  });

  it('reconciles both sides of an ack-time move across loaded parents', async () => {
    const { rootPath, tree } = await createHarness();
    await mkdir(path.join(rootPath, 'src'), { recursive: true });
    await mkdir(path.join(rootPath, 'dest'), { recursive: true });
    await writeFile(path.join(rootPath, 'src', 'app.ts'), '');
    const diagnostic = tree as unknown as DiagnosticTreeResource;
    await diagnostic.expandPath(ROOT_RELATIVE_PATH);
    await diagnostic.expandPath(portable('src'));
    await diagnostic.expandPath(portable('dest'));

    await rename(path.join(rootPath, 'src', 'app.ts'), path.join(rootPath, 'dest', 'app.ts'));
    await tree.applyAbsoluteChanges([
      { kind: 'delete', absolutePath: path.join(rootPath, 'src', 'app.ts') },
      { kind: 'create', absolutePath: path.join(rootPath, 'dest', 'app.ts') },
    ]);

    expect(diagnostic.current().entries['src/app.ts']).toBeUndefined();
    expect(diagnostic.current().entries['dest/app.ts']).toMatchObject({
      path: 'dest/app.ts',
      parentPath: 'dest',
      kind: 'file',
    });
    expect(diagnostic.current().entries.src?.children).not.toContain('src/app.ts');
    expect(diagnostic.current().entries.dest?.children).toContain('dest/app.ts');
  });

  it('ignores ack-time changes outside this root or under exclusions', async () => {
    const { rootPath, tree } = await createHarness({ exclusions: ['generated'] });
    await mkdir(path.join(rootPath, 'generated'), { recursive: true });
    const diagnostic = tree as unknown as DiagnosticTreeResource;
    await diagnostic.expandPath(ROOT_RELATIVE_PATH);
    const before = snapshot(tree.source()).revision;

    await tree.applyAbsoluteChanges([
      { kind: 'create', absolutePath: path.join(tmpdir(), 'unrelated', 'file.ts') },
      { kind: 'create', absolutePath: path.join(rootPath, 'generated', 'client.ts') },
    ]);

    expect(snapshot(tree.source()).revision).toBe(before);
  });

  it('refreshes loaded directories and preserves expansion', async () => {
    const { rootPath, tree } = await createHarness();
    await mkdir(path.join(rootPath, 'src'), { recursive: true });
    await writeFile(path.join(rootPath, 'src', 'app.ts'), '');
    const diagnostic = tree as unknown as DiagnosticTreeResource;
    await diagnostic.expandPath(ROOT_RELATIVE_PATH);
    await diagnostic.expandPath(portable('src'));
    await writeFile(path.join(rootPath, 'src', 'new.ts'), '');

    const settled: string[] = [];
    const result = await tree.refresh(
      treeContext(tree, undefined, 'refresh-test', async (name) => {
        settled.push(String(name));
      })
    );

    expect(result.success).toBe(true);
    expect(settled).toEqual(['tree']);
    expect(diagnostic.current().entries.src?.childrenLoaded).toBe(true);
    expect(diagnostic.current().entries['src/new.ts']).toMatchObject({
      path: 'src/new.ts',
      parentPath: 'src',
    });
  });

  it('reveals an already visible file without publishing a new tree revision', async () => {
    const { rootPath, tree } = await createHarness();
    await mkdir(path.join(rootPath, 'src'), { recursive: true });
    await writeFile(path.join(rootPath, 'src', 'app.ts'), '');
    const diagnostic = tree as unknown as DiagnosticTreeResource;
    await diagnostic.expandPath(ROOT_RELATIVE_PATH);
    await diagnostic.expandPath(portable('src'));
    const before = snapshot(tree.source()).revision;

    const result = await tree.reveal(
      treeContext(tree, { path: portable('src/app.ts') }, 'reveal-visible-test')
    );

    expect(result.success).toBe(true);
    expect(snapshot(tree.source()).revision).toBe(before);
  });
});

type DiagnosticTreeResource = {
  lane: Promise<void>;
  current(): FileTreeModel;
  expandPath(
    entryPath: PortableRelativePath,
    mutationId?: string,
    depth?: 1 | 2
  ): Promise<{ success: boolean }>;
  resync(previous: FileTreeModel): Promise<void>;
};

class ManualWatcher implements IWatchService {
  private onResync: (() => void) | undefined;
  private onEvents: ((events: WatchEvent[]) => void) | undefined;

  watch(_root: string, onEvents: (events: WatchEvent[]) => void, options: WatchOptions = {}) {
    this.onEvents = onEvents;
    this.onResync = options.onResync;
    return {
      ready: async () => ok(undefined),
      release: async () => {
        this.onEvents = undefined;
        this.onResync = undefined;
      },
    };
  }

  emit(events: WatchEvent[]): void {
    this.onEvents?.(events);
  }

  resync(): void {
    this.onResync?.();
  }

  async dispose(): Promise<void> {
    this.onEvents = undefined;
    this.onResync = undefined;
  }
}

function portable(path: string): PortableRelativePath {
  return path as PortableRelativePath;
}

function treeContext<Input>(
  tree: TreeResource,
  input: Input,
  mutationId: string,
  onObserved: (name: 'tree') => void | Promise<void> = () => {}
) {
  return {
    key: { root: tree.identity.root.root, sessionId: tree.identity.sessionId },
    input,
    mutationId,
    observed: async (name: 'tree', _revision: unknown) => {
      await onObserved(name);
    },
  };
}

async function createHarness(options: { exclusions?: string[] } = {}): Promise<{
  rootPath: string;
  tree: TreeResource;
  watcher: ManualWatcher;
}> {
  const rootPath = await realpath(await mkdtemp(path.join(tmpdir(), 'emdash-tree-resource-')));
  cleanups.push(() => rm(rootPath, { recursive: true, force: true }));

  const resolved = await resolveRootIdentity(runtimeRoot(rootPath));
  if (!resolved.success) throw new Error(`Unable to resolve test root: ${resolved.error.type}`);

  const watcher = new ManualWatcher();
  const root = await RootResource.create({ identity: resolved.data, watcher });
  cleanups.push(() => root.dispose());

  const identity = treeIdentity(resolved.data, {
    root: resolved.data.root,
    sessionId: 'tree-resource-test',
    exclusions: options.exclusions,
  });
  const tree = new TreeResource({ identity, root });
  cleanups.push(() => tree.dispose());
  return { rootPath, tree, watcher };
}
