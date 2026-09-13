import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { migrateLegacyUserData } from './user-data-migration';

describe('migrateLegacyUserData', () => {
  it('copies the legacy profile and every SQLite family member without deleting the source', () => {
    const root = mkdtempSync(join(tmpdir(), 'hardcore-user-data-migration-'));
    const legacy = join(root, 'emdash-dev');
    const destination = join(root, 'hardcore-dev');
    mkdirSync(legacy);
    writeFileSync(join(legacy, 'emdash4.db'), 'main');
    writeFileSync(join(legacy, 'emdash4.db-wal'), 'wal');
    writeFileSync(join(legacy, 'emdash4-file-search.db'), 'search');
    writeFileSync(join(legacy, 'mementos.db'), 'mementos');

    migrateLegacyUserData(root, destination);

    expect(readFileSync(join(destination, 'hardcore4.db'), 'utf8')).toBe('main');
    expect(readFileSync(join(destination, 'hardcore4.db-wal'), 'utf8')).toBe('wal');
    expect(readFileSync(join(destination, 'hardcore4-file-search.db'), 'utf8')).toBe('search');
    expect(readFileSync(join(destination, 'mementos.db'), 'utf8')).toBe('mementos');
    expect(readFileSync(join(legacy, 'emdash4.db'), 'utf8')).toBe('main');
  });
});
