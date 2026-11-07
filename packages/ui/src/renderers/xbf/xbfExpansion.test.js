import assert from 'node:assert/strict';
import test from 'node:test';

import { NO_EXPANSION, openAllRows, openRows, personsExpansion, personsRows, shutOpenedBy, shutRows, toggleRow } from './xbfExpansion.js';

// The Model tree's open rows and who opened them: the person, a pick's reveal, an isolation.

test("a reveal and an isolation open shut rows as theirs, and a row already open stays whose it was", () => {
  let tree = toggleRow(NO_EXPANSION, 'a');
  tree = openRows(tree, ['a', 'b'], 'reveal');
  tree = openRows(tree, ['b', 'c', 'd'], 'isolation');
  assert.deepEqual(tree, { open: ['a', 'b', 'c', 'd'], by: { b: 'reveal', c: 'isolation', d: 'isolation' } });
  assert.equal(openRows(tree, ['a', 'c'], 'reveal'), tree, 'nothing shut: the same expansion');
});

test("the file's view keeps the person's rows alone, and a row they open or shut is theirs from then on", () => {
  let tree = openRows(personsExpansion(['a']), ['b', 'c'], 'reveal');
  assert.deepEqual(personsRows(tree), ['a']);
  tree = toggleRow(toggleRow(tree, 'b'), 'b');
  assert.deepEqual(personsRows(tree), ['a', 'b']);
  // Expand all: every row the person's.
  assert.deepEqual(openAllRows(tree, ['c', 'e']), { open: ['a', 'c', 'b', 'e'], by: {} });
});

test("leaving isolation shuts what it opened, all of it or one isolation's under a row, and nothing else", () => {
  const tree = openRows(openRows(personsExpansion(['a']), ['r'], 'reveal'), ['i1', 'i2', 'owner'], 'isolation');
  assert.deepEqual(shutOpenedBy(tree, 'isolation'), { open: ['a', 'r'], by: { r: 'reveal' } });
  assert.deepEqual(shutOpenedBy(tree, 'isolation', new Set(['i1'])), { open: ['a', 'r', 'i2', 'owner'], by: { r: 'reveal', i2: 'isolation', owner: 'isolation' } });
  // A row the isolation opened that the person shut and opened again is theirs, and stays.
  assert.deepEqual(shutOpenedBy(toggleRow(toggleRow(tree, 'owner'), 'owner'), 'isolation').open, ['a', 'r', 'owner']);
  assert.deepEqual(shutRows(tree, ['r', 'i1']), { open: ['a', 'i2', 'owner'], by: { i2: 'isolation', owner: 'isolation' } });
});
