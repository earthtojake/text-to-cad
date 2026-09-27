import { connectedReferenceIds } from './selectionFilter.js';
import assert from 'node:assert/strict';
import test from 'node:test';
import { buildTangentFaceGraph } from './tangentFaceSelection.js';

const face = (id, occurrence = 'o1') => ({ id, displaySelector: id, selectorType: 'face', occurrenceId: occurrence, shapeId: `${occurrence}.s1` });
const edge = (id, faces, visibilityClass = 'tangent') => ({ id, selectorType: 'edge', pickData: { adjacentSelectors: faces, visibilityClass } });

test('follows tangent chains and cycles while stopping at sharp, boundary and unclassified edges', () => {
  const references = ['a', 'b', 'c', 'd', 'e'].map(id => face(id));
  const graph = buildTangentFaceGraph([...references,
    edge('ab', ['a', 'b']), edge('bc', ['b', 'c']), edge('ca', ['c', 'a']),
    edge('cd', ['c', 'd'], 'feature'), edge('ce', ['c', 'e'], null), edge('boundary', ['a']),
  ]);
  assert.deepEqual(new Set(connectedReferenceIds(graph, 'a')), new Set(['a', 'b', 'c']));
  assert.deepEqual(connectedReferenceIds(graph, 'd'), ['d']);
  assert.deepEqual(connectedReferenceIds(graph, 'missing'), []);
});

test('does not cross occurrences, nonmanifold edges, or partially loaded adjacency', () => {
  const graph = buildTangentFaceGraph([face('a'), face('b'), face('c'), face('other', 'o2'),
    edge('nonmanifold', ['a', 'b', 'c']), edge('missing', ['a', 'unloaded']), edge('cross', ['a', 'other']),
  ]);
  assert.deepEqual(connectedReferenceIds(graph, 'a'), ['a']);
});


test('ambiguous display selectors cannot connect to the wrong face', () => {
  const graph=buildTangentFaceGraph([face('a'),face('b'),{...face('other'),displaySelector:'b'},edge('ab',['a','b'])]);
  assert.deepEqual(connectedReferenceIds(graph,'a'),['a']);
});
