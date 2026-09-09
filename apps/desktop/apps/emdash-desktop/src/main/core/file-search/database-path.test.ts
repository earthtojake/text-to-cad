import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { resolveFileSearchDatabasePath } from './database-path';

describe('resolveFileSearchDatabasePath', () => {
  it('keeps the private index beside and scoped to the app database', () => {
    expect(resolveFileSearchDatabasePath(path.join('/tmp', 'scratch.db'))).toBe(
      path.join('/tmp', 'scratch-file-search.db')
    );
  });

  it('adds a database extension when the app database has none', () => {
    expect(resolveFileSearchDatabasePath(path.join('/tmp', 'scratch'))).toBe(
      path.join('/tmp', 'scratch-file-search.db')
    );
  });
});
