import assert from 'node:assert/strict';
import test from 'node:test';
import { MEASURE_FILTER_DEFAULT, edgeEnds, nearestEnd, restrictMeasurePick } from './measureFilter.js';

const edge = { snapKind: 'edge', point: [5, 0, 0], referenceId: 'e1', geometry: { kind: 'line', direction: [1, 0, 0] } };
const face = { snapKind: 'face', point: [5, 5, 0], referenceId: 'f1' };
const onFace = { snapKind: 'face', point: [5, 0.2, 0], referenceId: 'f2' };
const free = { snapKind: 'free', point: [5, 0.2, 0], referenceId: '' };

test('with every kind ticked, an edge near its end is that vertex, and every other pick is kept', () => {
  assert.deepEqual(restrictMeasurePick(edge, MEASURE_FILTER_DEFAULT, { vertex: [0, 0, 0] }),
    { ...edge, snapKind: 'vertex', point: [0, 0, 0], geometry: null });
  assert.equal(restrictMeasurePick(edge, MEASURE_FILTER_DEFAULT), edge);
  assert.equal(restrictMeasurePick(face, MEASURE_FILTER_DEFAULT), face);
  assert.equal(restrictMeasurePick(free, MEASURE_FILTER_DEFAULT), free);
  assert.equal(restrictMeasurePick(null, MEASURE_FILTER_DEFAULT), null);
});

test('an unticked kind falls through to the next the filter allows, else to nothing', () => {
  const fallbacks = { vertex: [0, 0, 0], face: () => onFace };
  // Vertices unticked: the edge stays an edge, wherever its ends are.
  assert.equal(restrictMeasurePick(edge, ['edge', 'face'], fallbacks), edge);
  // Edges unticked: away from an end, the face under the pointer; at an end, the vertex.
  assert.equal(restrictMeasurePick(edge, ['face'], fallbacks), onFace);
  assert.equal(restrictMeasurePick(edge, ['vertex', 'face'], fallbacks).snapKind, 'vertex');
  assert.equal(restrictMeasurePick(edge, ['vertex', 'face'], { ...fallbacks, vertex: null }), onFace);
  // No face under it to fall to, or Faces unticked too: nothing a press can take there.
  assert.equal(restrictMeasurePick(edge, ['face'], { ...fallbacks, face: () => null }), null);
  assert.equal(restrictMeasurePick(face, ['vertex', 'edge'], fallbacks), null);
});

test("an edge's ends are the points that end one segment; a closed edge has none", () => {
  // Two segments in a row, (0,0,0)-(1,0,0)-(2,0,0): its ends are the first and the last point.
  assert.deepEqual(edgeEnds(new Float32Array([0, 0, 0, 1, 0, 0, 1, 0, 0, 2, 0, 0])), [[0, 0, 0], [2, 0, 0]]);
  // A closed triangle of segments: every point ends two of them.
  assert.deepEqual(edgeEnds([0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0]), []);
  assert.deepEqual(edgeEnds(null), []);
});

test('the end taken is the nearest within the snap distance on screen', () => {
  const toScreen = ([x, y]) => ({ x: x * 100, y: y * 100 });
  const ends = [[0, 0, 0], [2, 0, 0]];
  assert.deepEqual(nearestEnd(ends, toScreen, { x: 6, y: 0 }), [0, 0, 0]);
  assert.deepEqual(nearestEnd(ends, toScreen, { x: 195, y: 5 }), [2, 0, 0]);
  assert.equal(nearestEnd(ends, toScreen, { x: 100, y: 0 }), null, 'mid-edge is no vertex');
  assert.equal(nearestEnd(ends, () => null, { x: 0, y: 0 }), null, 'an end off screen is not taken');
});
