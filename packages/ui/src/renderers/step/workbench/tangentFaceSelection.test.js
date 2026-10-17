import { connectedReferenceIds } from './selectionFilter.js';
import assert from 'node:assert/strict';
import test from 'node:test';
import { buildTangentFaceGraph } from './tangentFaceSelection.js';

const face = (id, group, extra = {}) => ({ id, selectorType: 'face', occurrenceId: 'o:3f2a9c1d7e5b', ...extra,
  pickData: { tangentGroup: group } });

test('faces of one tangent group select together; sharp-edged neighbours do not', () => {
  const graph = buildTangentFaceGraph([face('a', 1), face('b', 1), face('c', 1), face('d', 2), face('e', 3),
    { id: 'edge', selectorType: 'edge', pickData: { visibilityClass: 'tangent' } }]);
  assert.deepEqual(new Set(connectedReferenceIds(graph, 'a')), new Set(['a', 'b', 'c']));
  assert.deepEqual(connectedReferenceIds(graph, 'd'), ['d']);
  assert.deepEqual(connectedReferenceIds(graph, 'missing'), []);
});

test('a group id is local to one part and occurrence', () => {
  // cadgen numbers tangent groups within the component, across its solids.
  const graph = buildTangentFaceGraph([face('a', 1), face('other occurrence', 1, { occurrenceId: 'o:a1b2c3d4e5f6' }),
    face('other part', 1, { partId: 'p2' }), face('no group', null)]);
  assert.deepEqual(connectedReferenceIds(graph, 'a'), ['a']);
});
