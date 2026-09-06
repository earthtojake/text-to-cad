import type Database from 'better-sqlite3';
import { afterEach, describe, expect, it } from 'vitest';
import type { PortableRelativePath } from '#primitives/path/api';
import type { StoreHandle } from '#primitives/sqlite-store/api';
import { relativePath as relative } from '../testing/paths';
import { SqliteFileSearchStore } from './sqlite-file-search-store';
import { fileSearchStore, type FileSearchDb } from './store';

const handles: Array<StoreHandle<FileSearchDb, Database.Database>> = [];

afterEach(() => {
  for (const handle of handles.splice(0)) handle.close();
});

describe('SqliteFileSearchStore', () => {
  it('persists canonical roots idempotently and rejects conflicting identity rows', () => {
    const store = createStore();
    const created = store.upsertRoot({ rootKey: 'root-key', rootPath: '/workspace' });

    expect(created.kind).toBe('created');
    expect(store.upsertRoot({ rootKey: 'root-key', rootPath: '/workspace' }).kind).toBe(
      'unchanged'
    );
    publish(store, created.root.id, [{ path: relative('src/index.ts'), kind: 'file' }]);
    expect(store.searchPaths('root-key', '', ['file'], 20)).toMatchObject({ kind: 'ready' });

    expect(() =>
      store.upsertRoot({ rootKey: 'root-key', rootPath: '/canonical-workspace' })
    ).toThrow('Corrupt file-search root identity');
    expect(store.listRoots()).toEqual([
      { id: created.root.id, rootKey: 'root-key', rootPath: '/workspace' },
    ]);

    store.deleteRoot('root-key');
    store.deleteRoot('root-key');
    expect(store.listRoots()).toEqual([]);
  });

  it('keeps the published generation visible until a complete replacement is published', () => {
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath: '/workspace' }).root;
    publish(store, root.id, [{ path: relative('old.ts'), kind: 'file' }]);

    const replacement = store.beginBuild(root.id);
    replacement.append([{ path: relative('new.ts'), kind: 'file' }]);
    expect(store.searchPaths('root-key', '', ['file'], 20)).toEqual({
      kind: 'ready',
      hits: [{ path: 'old.ts', kind: 'file' }],
    });

    replacement.publish([]);
    expect(store.searchPaths('root-key', '', ['file'], 20)).toEqual({
      kind: 'ready',
      hits: [{ path: 'new.ts', kind: 'file' }],
    });

    const discarded = store.beginBuild(root.id);
    discarded.append([{ path: relative('discarded.ts'), kind: 'file' }]);
    discarded.discard();
    discarded.discard();
    expect(store.searchPaths('root-key', '', ['file'], 20)).toEqual({
      kind: 'ready',
      hits: [{ path: 'new.ts', kind: 'file' }],
    });
  });

  it('applies file and subtree patches atomically to the published generation', () => {
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath: '/workspace' }).root;
    publish(store, root.id, [
      { path: relative('src'), kind: 'directory' },
      { path: relative('src/old.ts'), kind: 'file' },
      { path: relative('keep.ts'), kind: 'file' },
    ]);

    store.applyPublishedPatches(root.id, [
      {
        kind: 'replace-subtree',
        path: relative('src'),
        entries: [
          { path: relative('src'), kind: 'directory' },
          { path: relative('src/new.ts'), kind: 'file' },
        ],
      },
      { kind: 'upsert', entry: { path: relative('added.ts'), kind: 'file' } },
      { kind: 'delete-subtree', path: relative('keep.ts') },
    ]);

    expect(store.searchPaths('root-key', '', ['file', 'directory'], 20)).toEqual({
      kind: 'ready',
      hits: [
        { path: 'added.ts', kind: 'file' },
        { path: 'src', kind: 'directory' },
        { path: 'src/new.ts', kind: 'file' },
      ],
    });
  });

  it('uses path ordering for empty text, substring fallback for short text, and FTS for terms', () => {
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath: '/workspace' }).root;
    publish(store, root.id, [
      { path: relative('packages/core/src/ButtonManager.ts'), kind: 'file' },
      { path: relative('packages/core/src/manager.ts'), kind: 'file' },
      { path: relative('packages/chat-ui/src/button.tsx'), kind: 'file' },
      { path: relative('packages/core/src/components'), kind: 'directory' },
    ]);

    expect(store.searchPaths('root-key', '', ['directory'], 20)).toEqual({
      kind: 'ready',
      hits: [{ path: 'packages/core/src/components', kind: 'directory' }],
    });
    expect(store.searchPaths('root-key', 'BU', ['file'], 20)).toEqual({
      kind: 'ready',
      hits: [
        { path: 'packages/chat-ui/src/button.tsx', kind: 'file' },
        { path: 'packages/core/src/ButtonManager.ts', kind: 'file' },
      ],
    });
    expect(store.searchPaths('root-key', 'core button', ['file'], 20)).toEqual({
      kind: 'ready',
      hits: [{ path: 'packages/core/src/ButtonManager.ts', kind: 'file' }],
    });
    expect(store.searchPaths('root-key', 'core bu', ['file'], 20)).toEqual({
      kind: 'ready',
      hits: [{ path: 'packages/core/src/ButtonManager.ts', kind: 'file' }],
    });

    expect(() => store.searchPaths('root-key', 'core"button', ['file'], 20)).not.toThrow();
    expect(() => store.searchPaths('root-key', 'NEAR(core)', ['file'], 20)).not.toThrow();
    expect(() => store.searchPaths('root-key', 'core*', ['file'], 20)).not.toThrow();
  });

  it('escapes wildcard characters when deleting a subtree', () => {
    const store = createStore();
    const root = store.upsertRoot({ rootKey: 'root-key', rootPath: '/workspace' }).root;
    publish(store, root.id, [
      { path: relative('wild%'), kind: 'directory' },
      { path: relative('wild%/deleted.ts'), kind: 'file' },
      { path: relative('wild-card'), kind: 'directory' },
      { path: relative('wild-card/kept.ts'), kind: 'file' },
    ]);

    store.applyPublishedPatches(root.id, [{ kind: 'delete-subtree', path: relative('wild%') }]);
    expect(store.searchPaths('root-key', '', ['file', 'directory'], 20)).toEqual({
      kind: 'ready',
      hits: [
        { path: 'wild-card', kind: 'directory' },
        { path: 'wild-card/kept.ts', kind: 'file' },
      ],
    });
  });
});

function createStore(): SqliteFileSearchStore {
  const handle = fileSearchStore.open(':memory:');
  handles.push(handle);
  return new SqliteFileSearchStore(handle);
}

function publish(
  store: SqliteFileSearchStore,
  rootId: number,
  entries: Array<{ path: PortableRelativePath; kind: 'file' | 'directory' }>
): void {
  const build = store.beginBuild(rootId);
  build.append(entries);
  build.publish([]);
}
