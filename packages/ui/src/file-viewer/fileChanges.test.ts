import { expect, test } from 'vitest';
import { reconcileFileTree } from './fileChanges.js';
const directory = (path: string) => ({ path, name: path.split('/').pop()!, kind: 'directory' as const });
const file = (path: string) => ({ ...directory(path), kind: 'file' as const });

test('directory moves retain every cached descendant and deletion removes its subtree', () => {
  const listings = { '': [directory('old'), file('keep')], old: [directory('old/deep')], 'old/deep': [file('old/deep/note')] };
  const moved = reconcileFileTree(listings, ['', 'old', 'old/deep'], [{ kind: 'moved', from: 'old', to: 'new', entryKind: 'directory' }]);
  expect(moved.expanded).toEqual(['', 'new', 'new/deep']);
  expect(moved.listings['new/deep']).toEqual([file('new/deep/note')]);
  expect(moved.listings['']).toEqual([directory('new'), file('keep')]);
  expect(listings['old/deep']).toEqual([file('old/deep/note')]);
  const deleted = reconcileFileTree(moved.listings, moved.expanded, [{ kind: 'deleted', path: 'new', entryKind: 'directory' }]);
  expect(deleted).toEqual({ listings: { '': [file('keep')] }, expanded: [''] });
});
