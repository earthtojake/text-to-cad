import type { SqliteConnection, StoreHandle } from '@emdash/core/primitives/sqlite-store/api';
import {
  defineDerivedSqliteStore,
  fingerprintDerivedSchema,
  betterSqlite3Driver,
} from '@emdash/core/primitives/sqlite-store/node';
import {
  DEFAULT_PERSISTED_MAX_AGE,
  DEFAULT_PERSISTED_MAX_ENTRIES,
  type MementoModelKey,
  type MementoRow,
} from '@core/primitives/mementos/api';
import type { Subject } from '@core/primitives/subjects/api';

const schemaSql = `
  CREATE TABLE mementos (
    memento_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    version TEXT NOT NULL,
    data TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (memento_id, subject_kind, subject_key)
  ) STRICT;

  CREATE INDEX idx_mementos_subject
    ON mementos (subject_kind, subject_key);

  CREATE INDEX idx_mementos_retention
    ON mementos (memento_id, updated_at DESC);
`;

export const mementosSqliteStore = defineDerivedSqliteStore({
  name: 'mementos',
  driver: betterSqlite3Driver,
  version: fingerprintDerivedSchema(schemaSql),
  createSchema(connection) {
    connection.exec(schemaSql);
  },
});

interface StoredMementoRow {
  memento_id: string;
  subject_kind: string;
  subject_key: string;
  version: string;
  data: string;
  updated_at: number;
}

export interface MementoSweepPolicy {
  readonly mementoId: string;
  readonly maxAge: number;
  readonly maxEntries: number;
}

export interface MementoSnapshotRow extends MementoModelKey, MementoRow {}

export interface DeleteOrphansResult {
  readonly deleted: number;
  readonly orphanKeys: readonly string[];
}

export class MementoPersistenceService {
  constructor(
    private readonly handle: StoreHandle<SqliteConnection> = mementosSqliteStore.open(':memory:')
  ) {}

  static open(databasePath: string): MementoPersistenceService {
    return new MementoPersistenceService(mementosSqliteStore.open(databasePath));
  }

  getRow(key: MementoModelKey): MementoRow | null {
    const row = this.handle.connection.get<StoredMementoRow>(
      `SELECT version, data, updated_at
       FROM mementos
       WHERE memento_id = ? AND subject_kind = ? AND subject_key = ?`,
      [key.mementoId, key.kind, key.key]
    );
    return row ? mapStoredRow(row) : null;
  }

  upsert(key: MementoModelKey, row: MementoRow): void {
    this.handle.connection.run(
      `INSERT INTO mementos (
         memento_id, subject_kind, subject_key, version, data, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT (memento_id, subject_kind, subject_key) DO UPDATE SET
         version = excluded.version,
         data = excluded.data,
         updated_at = excluded.updated_at`,
      [key.mementoId, key.kind, key.key, row.version, row.data, row.updatedAt]
    );
  }

  deleteRow(key: MementoModelKey): boolean {
    const result = this.handle.connection.run(
      `DELETE FROM mementos
       WHERE memento_id = ? AND subject_kind = ? AND subject_key = ?`,
      [key.mementoId, key.kind, key.key]
    );
    return toNumber(result.changes) > 0;
  }

  deleteBySubject(subject: Subject): number {
    const result = this.handle.connection.run(
      'DELETE FROM mementos WHERE subject_kind = ? AND subject_key = ?',
      [subject.kind, subject.key]
    );
    return toNumber(result.changes);
  }

  deleteAll(): number {
    return toNumber(this.handle.connection.run('DELETE FROM mementos').changes);
  }

  deleteOrphans(kind: string, validKeys: readonly string[]): DeleteOrphansResult {
    const valid = new Set(validKeys);
    const orphanKeys = this.handle.connection
      .all<{ subject_key: string }>(
        'SELECT DISTINCT subject_key FROM mementos WHERE subject_kind = ?',
        [kind]
      )
      .map(({ subject_key }) => subject_key)
      .filter((key) => !valid.has(key));

    const deleted = this.handle.transaction(() => {
      let count = 0;
      for (const keys of chunks(orphanKeys, 500)) {
        const placeholders = keys.map(() => '?').join(', ');
        count += toNumber(
          this.handle.connection.run(
            `DELETE FROM mementos
             WHERE subject_kind = ? AND subject_key IN (${placeholders})`,
            [kind, ...keys]
          ).changes
        );
      }
      return count;
    });
    return { deleted, orphanKeys };
  }

  snapshot(subject?: Subject): MementoSnapshotRow[] {
    const rows = subject
      ? this.handle.connection.all<StoredMementoRow>(
          `SELECT memento_id, subject_kind, subject_key, version, data, updated_at
           FROM mementos
           WHERE subject_kind = ? AND subject_key = ?
           ORDER BY memento_id`,
          [subject.kind, subject.key]
        )
      : this.handle.connection.all<StoredMementoRow>(
          `SELECT memento_id, subject_kind, subject_key, version, data, updated_at
           FROM mementos
           ORDER BY memento_id, subject_kind, subject_key`
        );

    return rows.map((row) => ({
      mementoId: row.memento_id,
      kind: row.subject_kind,
      key: row.subject_key,
      ...mapStoredRow(row),
    }));
  }

  sweep(policies: readonly MementoSweepPolicy[], now = Date.now()): number {
    const policyByMemento = new Map(policies.map((policy) => [policy.mementoId, policy]));
    const mementoIds = this.handle.connection
      .all<{ memento_id: string }>('SELECT DISTINCT memento_id FROM mementos')
      .map(({ memento_id }) => memento_id);

    return this.handle.transaction(() => {
      let deleted = 0;
      for (const mementoId of mementoIds) {
        const policy = policyByMemento.get(mementoId) ?? {
          mementoId,
          maxAge: DEFAULT_PERSISTED_MAX_AGE,
          maxEntries: DEFAULT_PERSISTED_MAX_ENTRIES,
        };

        deleted += toNumber(
          this.handle.connection.run(
            'DELETE FROM mementos WHERE memento_id = ? AND updated_at < ?',
            [mementoId, now - policy.maxAge]
          ).changes
        );
        deleted += toNumber(
          this.handle.connection.run(
            `DELETE FROM mementos
             WHERE rowid IN (
               SELECT rowid
               FROM mementos
               WHERE memento_id = ?
               ORDER BY updated_at DESC, subject_kind, subject_key
               LIMIT -1 OFFSET ?
             )`,
            [mementoId, policy.maxEntries]
          ).changes
        );
      }
      return deleted;
    });
  }

  close(): void {
    this.handle.close();
  }
}

function mapStoredRow(row: Pick<StoredMementoRow, 'version' | 'data' | 'updated_at'>): MementoRow {
  return {
    version: row.version,
    data: row.data,
    updatedAt: row.updated_at,
  };
}

function toNumber(value: number | bigint): number {
  const converted = Number(value);
  if (!Number.isSafeInteger(converted)) {
    throw new RangeError(`SQLite change count is outside the safe integer range: ${value}`);
  }
  return converted;
}

function chunks<T>(values: readonly T[], size: number): T[][] {
  const result: T[][] = [];
  for (let index = 0; index < values.length; index += size) {
    result.push(values.slice(index, index + size));
  }
  return result;
}
