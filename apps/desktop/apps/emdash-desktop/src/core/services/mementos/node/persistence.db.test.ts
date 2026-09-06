import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  defineDerivedSqliteStore,
  fingerprintDerivedSchema,
  betterSqlite3Driver,
} from '@emdash/core/primitives/sqlite-store/node';
import { afterEach, describe, expect, it } from 'vitest';
import { z } from 'zod';
import { defineSubject } from '@core/primitives/subjects/api';
import {
  MementoPersistenceService,
  mementosSqliteStore,
  type MementoSnapshotRow,
} from './persistence';

const taskSubject = defineSubject({
  kind: 'task',
  key: z.object({ taskId: z.string() }),
  encode: ({ taskId }) => taskId,
});

describe('MementoPersistenceService', () => {
  let service: MementoPersistenceService | undefined;

  afterEach(() => {
    service?.close();
    service = undefined;
  });

  it('upserts, reads, snapshots, and deletes rows', async () => {
    const handle = await mementosSqliteStore.openTemp();
    service = new MementoPersistenceService(handle);
    const key = { mementoId: 'tasks.drawer', kind: 'task', key: 'task-1' };

    expect(service.getRow(key)).toBeNull();

    service.upsert(key, { version: '1', data: '{"version":"1","open":false}', updatedAt: 10 });
    service.upsert(key, { version: '1', data: '{"version":"1","open":true}', updatedAt: 20 });

    expect(service.getRow(key)).toEqual({
      version: '1',
      data: '{"version":"1","open":true}',
      updatedAt: 20,
    });
    expect(service.snapshot(taskSubject({ taskId: 'task-1' }))).toEqual<MementoSnapshotRow[]>([
      {
        mementoId: 'tasks.drawer',
        kind: 'task',
        key: 'task-1',
        version: '1',
        data: '{"version":"1","open":true}',
        updatedAt: 20,
      },
    ]);
    expect(service.deleteBySubject(taskSubject({ taskId: 'task-1' }))).toBe(1);
    expect(service.getRow(key)).toBeNull();
  });

  it('deletes every persisted memento', async () => {
    const handle = await mementosSqliteStore.openTemp();
    service = new MementoPersistenceService(handle);
    service.upsert(
      { mementoId: 'tasks.drawer', kind: 'task', key: 'task-1' },
      { version: '1', data: '{}', updatedAt: 1 }
    );
    service.upsert(
      { mementoId: 'projects.sidebar', kind: 'project', key: 'project-1' },
      { version: '1', data: '{}', updatedAt: 2 }
    );

    expect(service.deleteAll()).toBe(2);
    expect(service.snapshot()).toEqual([]);
  });

  it('deletes orphaned subject keys in chunks without affecting other kinds', async () => {
    const handle = await mementosSqliteStore.openTemp();
    service = new MementoPersistenceService(handle);
    service.upsert(
      { mementoId: 'tasks.drawer', kind: 'task', key: 'keep' },
      { version: '1', data: '{}', updatedAt: 1 }
    );
    service.upsert(
      { mementoId: 'projects.sidebar', kind: 'project', key: 'project-1' },
      { version: '1', data: '{}', updatedAt: 1 }
    );
    for (let index = 0; index < 501; index++) {
      service.upsert(
        { mementoId: 'tasks.drawer', kind: 'task', key: `orphan-${index}` },
        { version: '1', data: '{}', updatedAt: index + 2 }
      );
    }

    const result = service.deleteOrphans('task', ['keep']);

    expect(result.deleted).toBe(501);
    expect(result.orphanKeys).toHaveLength(501);
    expect(service.snapshot().map(({ kind, key }) => [kind, key])).toEqual([
      ['project', 'project-1'],
      ['task', 'keep'],
    ]);
  });

  it('sweeps stale rows and bounds each memento definition', async () => {
    const handle = await mementosSqliteStore.openTemp();
    service = new MementoPersistenceService(handle);
    for (const [subjectKey, updatedAt] of [
      ['old', 10],
      ['recent-1', 80],
      ['recent-2', 90],
      ['recent-3', 100],
    ] as const) {
      service.upsert(
        { mementoId: 'tasks.drawer', kind: 'task', key: subjectKey },
        { version: '1', data: '{}', updatedAt }
      );
    }

    expect(service.sweep([{ mementoId: 'tasks.drawer', maxAge: 50, maxEntries: 2 }], 110)).toBe(2);
    expect(service.snapshot().map(({ key }) => key)).toEqual(['recent-2', 'recent-3']);
  });

  it('rebuilds the derived database when its schema fingerprint changes', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'emdash-mementos-rebuild-'));
    const databasePath = join(directory, 'mementos.db');
    try {
      const initial = mementosSqliteStore.open(databasePath);
      initial.connection.run(
        `INSERT INTO mementos (
           memento_id, subject_kind, subject_key, version, data, updated_at
         ) VALUES ('tasks.drawer', 'task', 'task-1', '1', '{}', 1)`
      );
      initial.close();

      const replacementSchema = `
        CREATE TABLE replacement (
          id TEXT PRIMARY KEY
        ) STRICT
      `;
      const replacementStore = defineDerivedSqliteStore({
        name: 'mementos-replacement',
        driver: betterSqlite3Driver,
        version: fingerprintDerivedSchema(replacementSchema),
        createSchema(connection) {
          connection.exec(replacementSchema);
        },
      });
      const replacement = replacementStore.open(databasePath);
      expect(
        replacement.connection.get<{ name: string }>(
          "SELECT name FROM sqlite_schema WHERE type = 'table' AND name = 'mementos'"
        )
      ).toBeUndefined();
      expect(
        replacement.connection.get<{ name: string }>(
          "SELECT name FROM sqlite_schema WHERE type = 'table' AND name = 'replacement'"
        )
      ).toEqual({ name: 'replacement' });
      replacement.close();
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
});
