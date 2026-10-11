import test from 'node:test';
import assert from 'node:assert/strict';
import { buildEdgeChainGraph } from './edgeChainSelection.js';
import { connectedReferenceIds, filterSelectionReferences, toggleReferenceGroupSelection } from './selectionFilter.js';
const edge = (id, chain, extra = {}) => ({ id, selectorType: 'edge', occurrenceId: 'o1', shapeId: 'o1.s1', ...extra,
  pickData: { chain, ...extra.pickData } });
const chain = (refs, seed = 'a') => new Set(connectedReferenceIds(buildEdgeChainGraph(refs), seed));

test('edges of one chain select together, whichever is picked; other chains stay apart', () => {
  const refs = [edge('a', 1), edge('b', 1), edge('c', 1), edge('d', 2)];
  assert.deepEqual(chain(refs), new Set(['a', 'b', 'c']));
  assert.deepEqual(chain(refs, 'c'), new Set(['a', 'b', 'c']));
  assert.deepEqual(chain(refs, 'd'), new Set(['d']));
  assert.deepEqual(toggleReferenceGroupSelection(['a', 'b'], ['a', 'b'], true), []);
  assert.deepEqual(filterSelectionReferences([...refs, { id: 'face', selectorType: 'face' }], 'edges'), refs);
});

test('a chain id is local to one part, occurrence and solid; an edge without one stands alone', () => {
  const a = edge('a', 1);
  for (const extra of [{ shapeId: 'o1.s2' }, { occurrenceId: 'o2' }, { partId: 'other' }, { pickData: { chain: null } }]) {
    assert.deepEqual(chain([a, edge('b', 1, extra)]), new Set(['a']));
  }
  assert.deepEqual(chain([edge('a', null), edge('b', null)]), new Set(['a']));
  assert.deepEqual(connectedReferenceIds(buildEdgeChainGraph([a]), 'missing'), []);
});
