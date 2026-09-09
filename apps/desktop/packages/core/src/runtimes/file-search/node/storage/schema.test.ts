import type Database from 'better-sqlite3';
import { eq } from 'drizzle-orm';
import { afterEach, describe, expect, it } from 'vitest';
import type { StoreHandle } from '#primitives/sqlite-store/api';
import { pathEntries, registeredRoots } from './schema';
import { fileSearchStore, type FileSearchDb } from './store';

const handles: Array<StoreHandle<FileSearchDb, Database.Database>> = [];

afterEach(() => {
  for (const handle of handles.splice(0)) handle.close();
});

describe('fileSearchStore schema', () => {
  it('creates the Drizzle tables and native FTS objects together', () => {
    const handle = createDatabase();
    const objects = handle.connection.native
      .prepare(
        `SELECT name
         FROM sqlite_schema
         WHERE name IN (
           'registered_roots',
           'path_entries',
           'path_entries_fts',
           'path_entries_after_insert',
           'path_entries_after_delete',
           'path_entries_after_update'
         )
         ORDER BY name`
      )
      .all() as Array<{ name: string }>;

    expect(objects.map(({ name }) => name)).toEqual([
      'path_entries',
      'path_entries_after_delete',
      'path_entries_after_insert',
      'path_entries_after_update',
      'path_entries_fts',
      'registered_roots',
    ]);

    const rootColumns = handle.connection.native
      .prepare('PRAGMA table_info(registered_roots)')
      .all() as Array<{ name: string }>;
    const entryColumns = handle.connection.native
      .prepare('PRAGMA table_info(path_entries)')
      .all() as Array<{ name: string }>;

    expect(rootColumns.map(({ name }) => name)).toEqual([
      'id',
      'root_key',
      'root_path',
      'current_generation',
    ]);
    expect(entryColumns.map(({ name }) => name)).toEqual([
      'id',
      'root_id',
      'generation',
      'relative_path',
      'name',
      'kind',
    ]);
  });

  it('keeps the FTS index synchronized with Drizzle writes', () => {
    const handle = createDatabase();
    const rootId = insertRoot(handle);
    const inserted = handle.db
      .insert(pathEntries)
      .values({
        rootId,
        generation: 1,
        relativePath: 'src/index.ts',
        name: 'index.ts',
        kind: 'file',
      })
      .returning({ id: pathEntries.id })
      .get();
    handle.db
      .insert(pathEntries)
      .values({
        rootId,
        generation: 1,
        relativePath: 'src/components',
        name: 'components',
        kind: 'directory',
      })
      .run();

    expect(search(handle, 'index')).toEqual([{ path: 'src/index.ts', kind: 'file' }]);
    expect(search(handle, 'components')).toEqual([{ path: 'src/components', kind: 'directory' }]);

    handle.db
      .update(pathEntries)
      .set({ relativePath: 'src/main.ts', name: 'main.ts' })
      .where(eq(pathEntries.id, inserted.id))
      .run();

    expect(search(handle, 'index')).toEqual([]);
    expect(search(handle, 'main')).toEqual([{ path: 'src/main.ts', kind: 'file' }]);

    handle.db.delete(pathEntries).where(eq(pathEntries.id, inserted.id)).run();
    expect(search(handle, 'main')).toEqual([]);

    handle.db
      .insert(pathEntries)
      .values({
        rootId,
        generation: 1,
        relativePath: 'src/worker.ts',
        name: 'worker.ts',
        kind: 'file',
      })
      .run();
    handle.db.delete(registeredRoots).where(eq(registeredRoots.id, rootId)).run();

    expect(search(handle, 'worker')).toEqual([]);
  });

  it('enforces path-entry constraints for native writes', () => {
    const handle = createDatabase();
    const rootId = insertRoot(handle);

    expect(() =>
      handle.connection.native
        .prepare(
          `INSERT INTO path_entries (root_id, generation, relative_path, name, kind)
           VALUES (?, 1, ?, ?, ?)`
        )
        .run(rootId, 'src/link', 'link', 'symlink')
    ).toThrow();
  });
});

function createDatabase(): StoreHandle<FileSearchDb, Database.Database> {
  const handle = fileSearchStore.open(':memory:');
  handles.push(handle);
  return handle;
}

function insertRoot(
  handle: StoreHandle<FileSearchDb, Database.Database>,
  currentGeneration: number | null = null
): number {
  return handle.db
    .insert(registeredRoots)
    .values({ rootKey: '/workspace', rootPath: '/workspace', currentGeneration })
    .returning({ id: registeredRoots.id })
    .get().id;
}

function search(
  handle: StoreHandle<FileSearchDb, Database.Database>,
  query: string
): Array<{ path: string; kind: string }> {
  const rows = handle.connection.native
    .prepare(
      `SELECT relative_path, kind
       FROM path_entries_fts
       WHERE path_entries_fts MATCH ?
       ORDER BY relative_path`
    )
    .all(query) as Array<{ relative_path: string; kind: string }>;

  return rows.map(({ relative_path, kind }) => ({ path: relative_path, kind }));
}
