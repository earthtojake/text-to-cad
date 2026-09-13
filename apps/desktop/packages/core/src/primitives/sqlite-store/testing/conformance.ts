import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { rmSync } from 'node:fs';
import type { SqliteDriver } from '../api';

function quoteSqliteString(value: string): string {
  return `'${value.replaceAll("'", "''")}'`;
}

/**
 * Runs the driver behaviors required by the store primitive.
 *
 * The caller owns cleanup of `path`. Keeping this independent of a test runner
 * lets consumers reuse it without adding Vitest as a runtime dependency.
 */
export function runSqliteDriverConformance(driver: SqliteDriver, path: string): void {
  const connection = driver.open(path);
  const vacuumPath = `${path}.vacuum-${randomUUID()}`;
  try {
    connection.exec(`
      CREATE TABLE conformance_values (
        id INTEGER PRIMARY KEY,
        text_value TEXT,
        integer_value INTEGER,
        blob_value BLOB,
        null_value TEXT
      );
      CREATE INDEX conformance_text_idx ON conformance_values(text_value);
    `);

    const inserted = connection.run(
      `INSERT INTO conformance_values
       (id, text_value, integer_value, blob_value, null_value)
       VALUES (?, ?, ?, ?, ?)`,
      [1, 'hello', Number.MAX_SAFE_INTEGER, new Uint8Array([1, 2, 3]), null]
    );
    assert.equal(Number(inserted.changes), 1);

    const row = connection.get<{
      blob_value: Uint8Array;
      id: number;
      integer_value: number;
      null_value: null;
      text_value: string;
    }>(
      `SELECT id, text_value, integer_value, blob_value, null_value
       FROM conformance_values
       WHERE id = ?`,
      [1]
    );
    assert.ok(row);
    assert.equal(row.id, 1);
    assert.equal(row.text_value, 'hello');
    assert.equal(row.integer_value, Number.MAX_SAFE_INTEGER);
    assert.deepEqual([...row.blob_value], [1, 2, 3]);
    assert.equal(row.null_value, null);
    assert.deepEqual(
      connection.all<{ id: number }>('SELECT id FROM conformance_values ORDER BY id'),
      [{ id: 1 }]
    );

    connection.exec('PRAGMA user_version = 42');
    assert.equal(connection.get<{ user_version: number }>('PRAGMA user_version')?.user_version, 42);

    connection.exec('PRAGMA busy_timeout = 1234');
    assert.equal(connection.get<{ timeout: number }>('PRAGMA busy_timeout')?.timeout, 1234);

    connection.exec('BEGIN IMMEDIATE');
    connection.run(
      `INSERT INTO conformance_values
       (id, text_value, integer_value, blob_value, null_value)
       VALUES (?, ?, ?, ?, ?)`,
      [2, 'committed', 2, new Uint8Array(), null]
    );
    connection.exec('COMMIT');
    connection.exec('BEGIN IMMEDIATE');
    connection.run(
      `INSERT INTO conformance_values
       (id, text_value, integer_value, blob_value, null_value)
       VALUES (?, ?, ?, ?, ?)`,
      [3, 'rolled back', 3, new Uint8Array(), null]
    );
    connection.exec('ROLLBACK');
    assert.deepEqual(
      connection.all<{ id: number }>('SELECT id FROM conformance_values ORDER BY id'),
      [{ id: 1 }, { id: 2 }]
    );

    connection.exec(`
      CREATE TABLE conformance_parent (id INTEGER PRIMARY KEY);
      CREATE TABLE conformance_child (
        id INTEGER PRIMARY KEY,
        parent_id INTEGER REFERENCES conformance_parent(id)
      );
      PRAGMA foreign_keys = ON;
    `);
    assert.equal(connection.get<{ foreign_keys: number }>('PRAGMA foreign_keys')?.foreign_keys, 1);
    assert.throws(() =>
      connection.run('INSERT INTO conformance_child (id, parent_id) VALUES (1, 999)')
    );

    connection.exec('PRAGMA foreign_keys = OFF');
    connection.run('INSERT INTO conformance_child (id, parent_id) VALUES (2, 999)');
    connection.run('DELETE FROM conformance_child WHERE id = 2');
    connection.exec('PRAGMA foreign_keys = ON');

    connection.exec('BEGIN IMMEDIATE');
    try {
      connection.exec('PRAGMA foreign_keys = OFF');
      assert.equal(
        connection.get<{ foreign_keys: number }>('PRAGMA foreign_keys')?.foreign_keys,
        1
      );
      assert.throws(() =>
        connection.run('INSERT INTO conformance_child (id, parent_id) VALUES (3, 999)')
      );
    } finally {
      connection.exec('ROLLBACK');
    }

    const unsafeInteger = BigInt(Number.MAX_SAFE_INTEGER) + 1n;
    connection.run(
      `INSERT INTO conformance_values
       (id, text_value, integer_value, blob_value, null_value)
       VALUES (?, ?, ?, ?, ?)`,
      [4, 'bigint', unsafeInteger, new Uint8Array(), null]
    );
    assert.equal(
      connection.get<{ integer_value: bigint }>(
        'SELECT integer_value FROM conformance_values WHERE id = 4'
      )?.integer_value,
      unsafeInteger
    );

    connection.exec(`VACUUM INTO ${quoteSqliteString(vacuumPath)}`);
    const vacuumConnection = driver.open(vacuumPath);
    try {
      assert.deepEqual(
        vacuumConnection.all<{ id: number }>('SELECT id FROM conformance_values ORDER BY id'),
        [{ id: 1 }, { id: 2 }, { id: 4 }]
      );
    } finally {
      vacuumConnection.close();
    }
  } finally {
    connection.close();
    for (const suffix of ['', '-wal', '-shm']) {
      rmSync(`${vacuumPath}${suffix}`, { force: true });
    }
  }
}
