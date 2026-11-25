import assert from 'node:assert/strict';
import test from 'node:test';

import { treeKey } from './tree-keys.js';

// A tree as drawn: an open assembly with a shut subassembly and an open one, a part under the open one, and a part
// at the root.
const ROWS = [
  { depth: 0, branch: true, open: true },   // 0 assembly
  { depth: 1, branch: true, open: false },  // 1 shut subassembly
  { depth: 1, branch: true, open: true },   // 2 open subassembly
  { depth: 2, branch: false, open: false }, // 3 its part
  { depth: 0, branch: false, open: false }, // 4 a part at the root
];

test('Down and Up walk the rows on screen, Home and End go to the ends, and nothing walks past them', () => {
  assert.deepEqual(treeKey('ArrowDown', ROWS, 0), { focus: 1 });
  assert.deepEqual(treeKey('ArrowUp', ROWS, 3), { focus: 2 });
  assert.equal(treeKey('ArrowDown', ROWS, 4), null);
  assert.equal(treeKey('ArrowUp', ROWS, 0), null, 'Up from the first row is the tree\'s owner\'s (a filter above it)');
  assert.deepEqual(treeKey('Home', ROWS, 3), { focus: 0 });
  assert.deepEqual(treeKey('End', ROWS, 1), { focus: 4 });
  assert.equal(treeKey('Home', ROWS, 0), null);
});

test('Right opens a shut branch and goes into an open one; Left shuts an open branch and goes up from anything else', () => {
  assert.deepEqual(treeKey('ArrowRight', ROWS, 1), { toggle: 1 });
  assert.deepEqual(treeKey('ArrowRight', ROWS, 2), { focus: 3 });
  assert.equal(treeKey('ArrowRight', ROWS, 3), null, 'a leaf has nothing to open');
  assert.deepEqual(treeKey('ArrowLeft', ROWS, 2), { toggle: 2 });
  assert.deepEqual(treeKey('ArrowLeft', ROWS, 3), { focus: 2 }, 'a part goes to the row it hangs from');
  assert.deepEqual(treeKey('ArrowLeft', ROWS, 1), { focus: 0 }, 'so does a shut branch');
  assert.equal(treeKey('ArrowLeft', ROWS, 4), null, 'a root has nothing above it');
  // An open branch with nothing drawn under it (all of it filtered away) has no first row to go to.
  assert.equal(treeKey('ArrowRight', [{ depth: 0, branch: true, open: true }, { depth: 0, branch: false, open: false }], 0), null);
});

test('from outside the rows, Down goes to the first and every other key is left alone; Enter and Space are the row\'s own', () => {
  assert.deepEqual(treeKey('ArrowDown', ROWS, -1), { focus: 0 });
  for (const key of ['ArrowUp', 'Home', 'End', 'ArrowLeft', 'ArrowRight']) assert.equal(treeKey(key, ROWS, -1), null, key);
  for (const key of ['Enter', ' ', 'a', 'Tab']) assert.equal(treeKey(key, ROWS, 2), null, key);
  assert.equal(treeKey('ArrowDown', [], -1), null);
});
