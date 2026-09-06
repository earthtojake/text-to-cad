import { describe, expect, it } from 'vitest';
import { fileSearchComponent, fileSearchComponentConfigSchema } from './component';

describe('fileSearchComponentConfigSchema', () => {
  it('defines a file-search worker component with its runtime dependencies', () => {
    expect(fileSearchComponent.id).toBe('file-search');
    expect(Object.keys(fileSearchComponent.requirements)).toEqual(['watcher', 'userEnv']);
  });

  it('requires a database path and accepts optional search-engine configuration', () => {
    expect(
      fileSearchComponentConfigSchema.parse({
        databasePath: '/tmp/file-search.db',
        ripgrepPath: 'rg',
        maxConcurrentScans: 2,
        maxConcurrentContentSearches: 4,
      })
    ).toEqual({
      databasePath: '/tmp/file-search.db',
      ripgrepPath: 'rg',
      maxConcurrentScans: 2,
      maxConcurrentContentSearches: 4,
    });
    expect(() => fileSearchComponentConfigSchema.parse({ databasePath: '' })).toThrow();
    expect(() => fileSearchComponentConfigSchema.parse({ databasePath: 'file-search.db' })).toThrow(
      'must be absolute'
    );
    expect(() =>
      fileSearchComponentConfigSchema.parse({
        databasePath: '/tmp/file-search.db',
        ripgrepPath: '',
      })
    ).toThrow();
    expect(() =>
      fileSearchComponentConfigSchema.parse({
        databasePath: '/tmp/file-search.db',
        maxConcurrentContentSearches: 0,
      })
    ).toThrow();
  });
});
