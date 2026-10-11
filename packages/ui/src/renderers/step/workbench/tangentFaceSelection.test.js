import { connectedReferenceIds } from './selectionFilter.js';
import assert from 'node:assert/strict';
import test from 'node:test';
import { buildTangentFaceGraph } from './tangentFaceSelection.js';

const face = (id, group, extra = {}) => ({ id, selectorType: 'face', occurrenceId: 'o1', shapeId: 'o1.s1', ...extra,
  pickData: { tangentGroup: group } });

test('faces of one tangent group select together; sharp-edged neighbours do not', () => {
  const graph = buildTangentFaceGraph([face('a', 1), face('b', 1), face('c', 1), face('d', 2), face('e', 3),
    { id: 'edge', selectorType: 'edge', pickData: { visibilityClass: 'tangent' } }]);
  assert.deepEqual(new Set(connectedReferenceIds(graph, 'a')), new Set(['a', 'b', 'c']));
  assert.deepEqual(connectedReferenceIds(graph, 'd'), ['d']);
  assert.deepEqual(connectedReferenceIds(graph, 'missing'), []);
});

test('a group id is local to one part, occurrence and solid', () => {
  const graph = buildTangentFaceGraph([face('a', 1), face('other occurrence', 1, { occurrenceId: 'o2' }),
    face('other solid', 1, { shapeId: 'o1.s2' }), face('other part', 1, { partId: 'p2' }), face('no group', null)]);
  assert.deepEqual(connectedReferenceIds(graph, 'a'), ['a']);
});
