import {
  DEFAULT_SEARCH_EXCLUDE,
  DEFAULT_TREE_EXCLUDE,
  DEFAULT_WATCHER_EXCLUDE,
} from '@emdash/core/primitives/exclusion-policy/api';
import { describe, expect, it } from 'vitest';
import {
  filesSettingsContribution,
  HARDCORE_TREE_EXCLUDE,
  withHardcoreTreeExclusions,
} from './settings';

describe('filesSettingsContribution', () => {
  it('uses core exclusion defaults for tree, search, and watcher settings', () => {
    expect(filesSettingsContribution.defaults).toEqual({
      treeExclude: [...DEFAULT_TREE_EXCLUDE, ...HARDCORE_TREE_EXCLUDE],
      searchExclude: [...DEFAULT_SEARCH_EXCLUDE],
      watcherExclude: [...DEFAULT_WATCHER_EXCLUDE],
    });
  });

  it('validates non-empty string pattern lists', () => {
    expect(
      filesSettingsContribution.schema.parse({
        treeExclude: ['.git'],
        searchExclude: ['node_modules'],
        watcherExclude: ['**/node_modules/**'],
      })
    ).toEqual({
      treeExclude: ['.git', ...HARDCORE_TREE_EXCLUDE],
      searchExclude: ['node_modules'],
      watcherExclude: ['**/node_modules/**'],
    });
  });

  it('adds generated CAD folders to persisted exclusion lists without duplicates', () => {
    expect(withHardcoreTreeExclusions(['.git', '__cadgen__'])).toEqual([
      '.git',
      ...HARDCORE_TREE_EXCLUDE,
    ]);
  });
});
