import {
  canonicalExclusionPatterns,
  DEFAULT_TREE_EXCLUDE,
} from '@emdash/core/primitives/exclusion-policy/api';
import { encodeResourceUri } from '@emdash/core/primitives/path/api';
import type { FileTreeModel } from '@emdash/core/runtimes/files/api';
import { ok } from '@emdash/shared';
import { waitFor } from '@emdash/shared/testing';
import { defineContract } from '@emdash/wire/rpc';
import { cell, expose } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { observable, runInAction } from 'mobx';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  HARDCORE_TREE_EXCLUDE,
  withHardcoreTreeExclusions,
} from '@core/features/editor/contributions/settings';
import { filesWireContract, type FilesTreeKey } from '@core/features/files/api';
import type {
  ProjectHostAccess,
  ProjectHostAccessState,
} from '@core/features/projects/api/browser/stores/project-context';
import {
  hostFileRefFromNativePath,
  hostPathFromNative,
  portablePath,
} from '@core/primitives/desktop-runtime/api';
import { FilesStore } from './files-store';

const wireClient = vi.hoisted(() => ({ current: undefined as unknown }));
const filesSettingsMeta = vi.hoisted(() => ({ current: undefined as unknown }));

vi.mock('@core/features/files/api/browser/client', () => ({
  getFilesClient: async () => wireClient.current,
}));

vi.mock('@core/features/settings/api/browser/app-settings-client', () => ({
  fetchAppSettingsMeta: async () => filesSettingsMeta.current,
}));

type RecordedMutation = { name: string; key: FilesTreeKey; input: unknown };

function makeEntry(
  path: string,
  kind: 'file' | 'directory',
  children: readonly string[] = []
): FileTreeModel['entries'][string] {
  return {
    path: portablePath(path),
    name: path.split('/').pop() ?? '',
    parentPath:
      path === '' ? null : portablePath(path.slice(0, Math.max(path.lastIndexOf('/'), 0))),
    kind,
    childrenLoaded: kind === 'directory',
    children: children.map((child) => portablePath(child)),
  };
}

function makeTreeModel(root: string): FileTreeModel {
  return {
    root: hostPathFromNative(root),
    entries: {
      '': makeEntry('', 'directory', ['README.md', 'src']),
      'README.md': makeEntry('README.md', 'file'),
      src: makeEntry('src', 'directory', ['src/index.ts']),
      'src/index.ts': makeEntry('src/index.ts', 'file'),
    },
  };
}

function setup(
  options: {
    treeSessionId?: string;
    sshConnectionId?: string;
    hostAccess?: ProjectHostAccess;
  } = {}
) {
  const treeCell = cell<FileTreeModel>(makeTreeModel('/repo'));
  const stateKeys: FilesTreeKey[] = [];
  const mutationCalls: RecordedMutation[] = [];
  const fsCalls: Array<{ name: string; input: unknown }> = [];

  const touch = async (
    name: string,
    context: {
      key: FilesTreeKey;
      input?: unknown;
      mutationId: string;
      observed(state: 'tree', revision: ReturnType<typeof treeCell.update>): Promise<void>;
    }
  ) => {
    mutationCalls.push({ name, key: context.key, input: context.input });
    const revision = treeCell.update((previous) => ({ ...previous }), {
      mutationIds: [context.mutationId],
    });
    await context.observed('tree', revision);
    return ok(undefined);
  };

  const provider = expose(
    filesWireContract.tree.model,
    {
      tree: (key) => {
        stateKeys.push(key);
        return treeCell;
      },
    },
    {
      mutations: {
        expand: (context) => touch('expand', context),
        reveal: (context) => touch('reveal', context),
        refresh: (context) => touch('refresh', context),
      },
    }
  );

  const testContract = defineContract({ tree: filesWireContract.tree });
  const wire = createTestWire(testContract, { tree: { model: provider } });
  const recordFsCall = (name: string) => async (input: unknown) => {
    fsCalls.push({ name, input });
    return ok(undefined);
  };
  // The write verbs are stateless fs procedures; the tree updates arrive
  // through the live model after the runtime's ack-time republish.
  wireClient.current = {
    ...wire.client,
    fs: {
      createFile: recordFsCall('createFile'),
      createDirectory: recordFsCall('createDirectory'),
      rename: recordFsCall('rename'),
      move: recordFsCall('move'),
      copy: recordFsCall('copy'),
      delete: recordFsCall('delete'),
    },
  };

  const store = new FilesStore(
    options.treeSessionId ?? 'task-1',
    'workspace-1',
    '/repo',
    options.sshConnectionId,
    options.hostAccess
  );
  return { store, stateKeys, mutationCalls, fsCalls };
}

let disposeStore: (() => void) | null = null;

afterEach(() => {
  disposeStore?.();
  disposeStore = null;
  wireClient.current = undefined;
  filesSettingsMeta.current = undefined;
});

describe('FilesStore', () => {
  it('binds the files domain tree model with task-scoped expansion state', async () => {
    const { store, stateKeys, mutationCalls } = setup();
    disposeStore = () => store.dispose();

    await store.start();

    expect(stateKeys[0]).toEqual({
      root: encodeResourceUri(hostFileRefFromNativePath('/repo')),
      sessionId: 'task-1',
      exclusions: canonicalExclusionPatterns(withHardcoreTreeExclusions(DEFAULT_TREE_EXCLUDE)),
    });
    expect(mutationCalls).toContainEqual({
      name: 'expand',
      key: stateKeys[0],
      input: { path: '' },
    });

    await waitFor(() => store.rootNodes.length === 2);
    expect(store.rootNodes.map((node) => node.path)).toEqual(['/repo/src', '/repo/README.md']);
    expect(store.isLoading).toBe(false);
  });

  it('keeps generated CAD folders excluded when callers provide older saved settings', async () => {
    const { store, stateKeys } = setup();
    disposeStore = () => store.dispose();

    store.setExclusions(['.git']);
    await store.start();

    expect(stateKeys[0]?.exclusions).toEqual(
      canonicalExclusionPatterns(['.git', ...HARDCORE_TREE_EXCLUDE])
    );
  });

  it('keeps generated CAD folders excluded when persisted settings omit them', async () => {
    filesSettingsMeta.current = { value: { treeExclude: ['.git'] } };
    const { store, stateKeys } = setup();
    disposeStore = () => store.dispose();

    await store.start();

    expect(stateKeys[0]?.exclusions).toEqual(
      canonicalExclusionPatterns(['.git', ...HARDCORE_TREE_EXCLUDE])
    );
  });

  it('does not share the tree session between tasks using the same workspace', async () => {
    const { store, stateKeys } = setup({ treeSessionId: 'task-2' });
    disposeStore = () => store.dispose();

    await store.start();

    expect(stateKeys[0]?.sessionId).toBe('task-2');
    expect(stateKeys[0]?.sessionId).not.toBe('workspace-1');
  });

  it('carries the workspace host into the tree key for remote workspaces', async () => {
    const { store, stateKeys } = setup({ sshConnectionId: 'ssh-1' });
    disposeStore = () => store.dispose();

    await store.start();

    expect(stateKeys[0]?.root).toEqual(
      encodeResourceUri(hostFileRefFromNativePath('/repo', 'ssh-1'))
    );
  });

  it('routes write operations through the stateless fs verbs keyed by ResourceUri', async () => {
    const { store, fsCalls } = setup();
    disposeStore = () => store.dispose();
    await store.start();

    await expect(store.createFile('/repo/src/new.ts')).resolves.toEqual(ok(undefined));
    await expect(store.createDirectory('/repo/src/lib')).resolves.toEqual(ok(undefined));
    await expect(store.rename('/repo/README.md', 'README2.md')).resolves.toEqual(ok(undefined));
    await expect(store.move('/repo/README.md', '/repo/src')).resolves.toEqual(ok(undefined));
    await expect(store.deleteEntry('/repo/src/index.ts', true)).resolves.toEqual(ok(undefined));

    const uri = (path: string) => encodeResourceUri(hostFileRefFromNativePath(path));
    const named = (name: string) => fsCalls.filter((call) => call.name === name);
    expect(named('createFile')[0]?.input).toEqual({ uri: uri('/repo/src/new.ts') });
    expect(named('createDirectory')[0]?.input).toEqual({ uri: uri('/repo/src/lib') });
    expect(named('rename')[0]?.input).toEqual({
      from: uri('/repo/README.md'),
      to: uri('/repo/README2.md'),
    });
    expect(named('move')[0]?.input).toEqual({
      from: uri('/repo/README.md'),
      to: uri('/repo/src/README.md'),
    });
    expect(named('delete')[0]?.input).toEqual({
      uri: uri('/repo/src/index.ts'),
      recursive: true,
    });
  });

  it('reveals files through the tree model and reports ancestor directories', async () => {
    const { store, mutationCalls } = setup();
    disposeStore = () => store.dispose();
    await store.start();

    await expect(store.revealFile('/repo/src/index.ts')).resolves.toEqual(ok(['/repo/src']));
    expect(mutationCalls.filter((call) => call.name === 'reveal')[0]?.input).toEqual({
      path: 'src/index.ts',
    });
  });

  it('retains the observed tree as stale and blocks writes while offline', async () => {
    const state = observable.box<ProjectHostAccessState>({
      kind: 'ready',
      hostGeneration: 1,
    });
    const hostAccess = {
      get state() {
        return state.get();
      },
      get liveAction() {
        const current = state.get();
        return current.kind === 'ready'
          ? ({ kind: 'enabled' } as const)
          : ({ kind: 'disabled', state: current } as const);
      },
    } as ProjectHostAccess;
    const { store, fsCalls } = setup({ hostAccess });
    disposeStore = () => store.dispose();
    await store.start();
    await waitFor(() => store.rootNodes.length === 2);
    const refresh = vi.spyOn(
      (
        store as unknown as {
          treeModel: { states: { tree: { refresh(): Promise<void> } } };
        }
      ).treeModel.states.tree,
      'refresh'
    );

    runInAction(() =>
      state.set({
        kind: 'degraded',
        situation: 'offline',
        recovery: 'automatic',
      })
    );

    expect(store.observation.kind).toBe('stale');
    expect(store.rootNodes.map((node) => node.path)).toEqual(['/repo/src', '/repo/README.md']);
    await expect(store.createFile('/repo/offline.ts')).resolves.toMatchObject({
      success: false,
      error: { type: 'unavailable' },
    });
    expect(fsCalls).toEqual([]);

    runInAction(() => state.set({ kind: 'ready', hostGeneration: 2 }));
    await vi.waitFor(() => expect(refresh).toHaveBeenCalledOnce());
    expect(store.observation.kind).toBe('live');
    expect(store.rootNodes.map((node) => node.path)).toEqual(['/repo/src', '/repo/README.md']);
  });

  it('reports a never-observed offline tree unavailable without contacting Files', async () => {
    const state: ProjectHostAccessState = {
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    };
    const hostAccess = {
      state,
      liveAction: { kind: 'disabled', state },
    } as ProjectHostAccess;
    const { store, stateKeys } = setup({ hostAccess });
    disposeStore = () => store.dispose();

    await store.start();

    expect(store.observation).toEqual({ kind: 'unavailable' });
    expect(store.isLoading).toBe(false);
    expect(stateKeys).toEqual([]);
  });
});
