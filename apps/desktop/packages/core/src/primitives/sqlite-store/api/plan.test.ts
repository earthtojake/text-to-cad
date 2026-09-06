import { describe, expect, it } from 'vitest';
import { computePendingMigrations, validateMigrationManifest, verifyAppliedHashes } from './plan';
import type { BundledMigration } from './types';

const migrations: BundledMigration[] = [
  { idx: 0, tag: '0000_first', when: 1, hash: 'hash-0', sql: 'SELECT 0;' },
  { idx: 1, tag: '0001_second', when: 2, hash: 'hash-1', sql: 'SELECT 1;' },
  { idx: 2, tag: '0002_third', when: 3, hash: 'hash-2', sql: 'SELECT 2;' },
];

describe('SQLite migration planning', () => {
  it('computes missing migrations by tag in index order', () => {
    expect(
      computePendingMigrations(
        [
          { tag: '0002_third', hash: 'hash-2' },
          { tag: '0000_first', hash: 'hash-0' },
        ],
        migrations
      ).map(({ tag }) => tag)
    ).toEqual(['0001_second']);
  });

  it('ignores applied migrations from newer application versions', () => {
    expect(() =>
      verifyAppliedHashes(
        [
          { tag: '0000_first', hash: 'hash-0' },
          { tag: '9999_future', hash: 'future-hash' },
        ],
        migrations
      )
    ).not.toThrow();
  });

  it('rejects modified applied migrations', () => {
    expect(() =>
      verifyAppliedHashes([{ tag: '0000_first', hash: 'different' }], migrations)
    ).toThrow('Migration 0000_first was modified after it was applied');
  });

  it('rejects duplicate tags and indices', () => {
    expect(() => validateMigrationManifest([...migrations, { ...migrations[0], idx: 3 }])).toThrow(
      'Duplicate migration tag'
    );
    expect(() =>
      validateMigrationManifest([...migrations, { ...migrations[0], tag: 'other' }])
    ).toThrow('Duplicate migration index');
  });
});
