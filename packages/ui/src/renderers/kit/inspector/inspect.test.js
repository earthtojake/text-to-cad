import assert from 'node:assert/strict';
import test from 'node:test';
import { nextActivePick, pickRows } from './inspect.js';

// Several picks: the Selected pane draws one, the active one (Blender's active object).
test('a pick added is the active one, the last of those added; let go of, the nearest pick left takes over', () => {
  assert.equal(nextActivePick([], ['a'], ''), 'a', 'the first pick');
  assert.equal(nextActivePick(['a'], ['a', 'b'], 'a'), 'b', 'a pick added (Shift) is the active one');
  assert.equal(nextActivePick(['a', 'b'], ['c', 'd'], 'b'), 'd', 'several at once (a box, a block): the last of them');
  assert.equal(nextActivePick(['a', 'b', 'c'], ['a', 'b', 'c'], 'a'), 'a', 'one chosen in the switcher stays');
  assert.equal(nextActivePick(['a', 'b', 'c'], ['a', 'c'], 'b'), 'c', 'let go of: the one after it');
  assert.equal(nextActivePick(['a', 'b', 'c'], ['a', 'b'], 'c'), 'b', 'the last let go of: the one before it');
  assert.equal(nextActivePick(['a', 'b', 'c'], ['b', 'c'], 'b'), 'b', 'another let go of: it stays');
  assert.equal(nextActivePick(['a', 'b'], [], 'a'), '', 'nothing picked');
});

test('the switcher lists the picks the view describes, in the order they were picked: each its glyph, name and short kind', () => {
  const describe = id => (id === 'gone' ? null : { id: `d:${id}`, pick: id, kind: 'solid', title: id.toUpperCase(), tip: id === 'u1' ? 'RP2040' : undefined, facts: [] });
  assert.deepEqual(pickRows(['u1', 'gone', 'r1'], describe), [
    { id: 'u1', kind: 'solid', label: 'U1', detail: 'RP2040' }, { id: 'r1', kind: 'solid', label: 'R1', detail: '' }]);
});
