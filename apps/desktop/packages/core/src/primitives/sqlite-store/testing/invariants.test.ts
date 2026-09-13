import { describe, expect, it } from 'vitest';
import { betterSqlite3Driver } from '../node/better-sqlite3-driver';
import {
  assertForeignKeyIntegrity,
  assertSqliteIntegrity,
  assertSqliteStoreInvariants,
} from './invariants';

describe('SQLite invariant helpers', () => {
  it('accepts a valid in-memory database', () => {
    const connection = betterSqlite3Driver.open(':memory:');
    connection.exec('PRAGMA foreign_keys = ON; CREATE TABLE values_table (id INTEGER PRIMARY KEY)');
    expect(() => assertSqliteIntegrity(connection)).not.toThrow();
    expect(() => assertForeignKeyIntegrity(connection)).not.toThrow();
    expect(() => assertSqliteStoreInvariants(connection)).not.toThrow();
    connection.close();
  });

  it('reports foreign-key violations', () => {
    const connection = betterSqlite3Driver.open(':memory:');
    connection.exec(`
      PRAGMA foreign_keys = OFF;
      CREATE TABLE parent (id INTEGER PRIMARY KEY);
      CREATE TABLE child (parent_id INTEGER REFERENCES parent(id));
      INSERT INTO child (parent_id) VALUES (42);
    `);
    expect(() => assertForeignKeyIntegrity(connection)).toThrow('foreign-key check failed');
    connection.close();
  });
});
