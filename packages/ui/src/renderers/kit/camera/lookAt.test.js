import assert from 'node:assert/strict';
import test from 'node:test';

import { boundsAbout, lineOfPoints, lookAtFor, planeOfPoints, planeThroughLine } from './lookAt.js';

/** A double-click under Select turns the view square to what it is on: where, by what it is. */

const rounded = values => values.map(value => Math.round(value * 1000) / 1000 + 0);
// The camera now: up and off to the front-left of the model.
const iso = [-0.6, -0.6, 0.53];
const ring = (center, radius, plane = 'xy', count = 16) => Array.from({ length: count }, (_, index) => {
  const angle = (index / count) * Math.PI * 2, a = radius * Math.cos(angle), b = radius * Math.sin(angle);
  return plane === 'xy' ? [center[0] + a, center[1] + b, center[2]] : [center[0] + a, center[1], center[2] + b];
});

test('a planar face: square to it, from the side the camera is on, its middle on its plane, framed', () => {
  const top = [[-60, -40, 8], [60, -40, 8], [60, 40, 8], [-60, 40, 8]];
  const look = lookAtFor({ kind: 'plane', normal: [0, 0, -1], points: top }, iso);
  assert.deepEqual(rounded(look.direction), [0, 0, 1], 'toward the camera, whatever way the face says it faces');
  assert.deepEqual(look.point, [0, 0, 8]);
  assert.deepEqual(look.fit, { min: [-60, -40, 8], max: [60, 40, 8] });
  assert.deepEqual(rounded(lookAtFor({ kind: 'plane', normal: [0.001, -1, 0.002], points: top }, iso).direction), [0, -1, 0], 'a hair off an axis is that axis');
});

test("a cylinder's side: from the side, along the radius toward the camera; its zero point the circumference's nearest point", () => {
  // A boss on the plate: axis +z through (20, 10), radius 5, z 8 to 20.
  const side = [...ring([20, 10, 8], 5), ...ring([20, 10, 20], 5)];
  const look = lookAtFor({ kind: 'cylinder', axis: [0, 0, 1], origin: [20, 10, 0], radius: 5, points: side }, iso);
  assert.deepEqual(rounded(look.direction), rounded([-Math.SQRT1_2, -Math.SQRT1_2, 0]), 'level, toward the camera');
  assert.deepEqual(rounded(look.point), rounded([20 - 5 * Math.SQRT1_2, 10 - 5 * Math.SQRT1_2, 14]), 'on the circumference, halfway up');
  assert.ok(look.fit);
  // Looking straight down its axis there is no side nearest: any side will do, but a side.
  const fromAbove = lookAtFor({ kind: 'cylinder', axis: [0, 0, 1], origin: [20, 10, 0], radius: 5, points: side }, [0, 0, 1]);
  assert.equal(Math.round(fromAbove.direction[2] * 1000), 0);
});

test('a circular edge: down its axis, toward the camera, its centre framed', () => {
  const rim = ring([20, 10, 20], 5);
  const look = lookAtFor({ kind: 'circle', axis: [0, 0, -1], center: [20, 10, 20], points: rim }, iso);
  assert.deepEqual(rounded(look.direction), [0, 0, 1]);
  assert.deepEqual(look.point, [20, 10, 20]);
});

test('a straight edge: of the views square to it, the one nearest the camera now; its middle', () => {
  const edge = [[-60, -40, 8], [60, -40, 8]];
  const look = lookAtFor({ kind: 'line', direction: [1, 0, 0], points: edge }, iso);
  assert.deepEqual(rounded(look.direction), rounded([0, -0.6 / Math.hypot(0.6, 0.53), 0.53 / Math.hypot(0.6, 0.53)]));
  assert.ok(Math.abs(look.direction[0]) < 1e-9, 'square to the edge');
  assert.deepEqual(look.point, [0, -40, 8]);
  const endOn = lookAtFor({ kind: 'line', direction: [1, 0, 0], points: edge }, [1, 0, 0]);
  assert.ok(Math.abs(endOn.direction[0]) < 1e-9, 'looking along it: still square to it');
});

test('anything else: the view as it is, its zero point its point nearest the camera, the zoom as it is', () => {
  const dome = [[0, 0, 30], [10, 0, 20], [-10, 0, 20], [0, 10, 20], [0, -10, 20]];
  const look = lookAtFor({ kind: 'free', points: dome }, [0, 0, 1]);
  assert.deepEqual(look, { direction: [0, 0, 1], point: [0, 0, 30], fit: null });
  assert.deepEqual(lookAtFor({ kind: 'free', points: dome }, [0, -1, 0]).point, [0, -10, 20]);
});

test('the plane points lie in, and a box about a point that holds another', () => {
  assert.deepEqual(rounded(planeOfPoints([[0, 0, 8], [10, 0, 8], [10, 10, 8], [0, 10, 8]], 0.01).normal.map(Math.abs)), [0, 0, 1]);
  assert.equal(planeOfPoints([[0, 0, 0], [5, 0, 0], [10, 0, 0]], 0.01), null, 'a line lies in many');
  assert.equal(planeOfPoints([[0, 0, 0], [10, 0, 0], [10, 10, 5], [0, 10, 0]], 0.01), null, 'not flat');
  assert.deepEqual(boundsAbout([0, 0, 0], { min: [-1, 2, 0], max: [3, 4, 1] }), { min: [-3, -4, -1], max: [3, 4, 1] });
});

test("a plane's origin, where given, is exactly on it: points lifted off it for a highlight do not move the zero point", () => {
  const lifted = [[-60, -40, 8.05], [60, -40, 8.05], [60, 40, 8.05], [-60, 40, 8.05]];
  assert.deepEqual(lookAtFor({ kind: 'plane', normal: [0, 0, 1], origin: [-60, -40, 8], points: lifted }, iso).point, [0, 0, 8]);
});

test("a straight line of ink sets the plane through it, as square to the view as it can be: a line on the plate's top stands a plane up", () => {
  // A centre line drawn on a plate's top, along x, a little wobbly as a hand draws it.
  const line = [[-20, 0, 8], [-5, 0.3, 8], [10, -0.2, 8], [20, 0, 8]];
  const found = lineOfPoints(line, 2);
  assert.deepEqual(rounded(found.direction), [1, 0, 0]);
  assert.deepEqual(rounded(found.origin), [0, 0, 8]);
  // Seen from the front, a little from above: the upright plane through it, facing the front.
  assert.deepEqual(rounded(planeThroughLine(found.direction, [0, -0.95, 0.31])), [0, -1, 0]);
  const look = lookAtFor({ kind: 'plane', normal: planeThroughLine(found.direction, [0, -0.95, 0.31]), origin: found.origin, points: line }, [0, -0.95, 0.31]);
  // The view turns square to it, from the front; its zero point is on the line.
  assert.deepEqual(rounded(look.direction), [0, -1, 0]);
  assert.equal(look.point[1], 0);
  // Seen from well above (60° up): the plane leans to the view, square to it as it can be.
  const steep = planeThroughLine(found.direction, [0, -0.5, 0.866]);
  assert.ok(steep[2] > 0.8 && Math.abs(steep[0]) < 1e-9, `${steep}`);
  // Looking straight down the line: the upright plane through it.
  assert.deepEqual(rounded(planeThroughLine([1, 0, 0], [1, 0, 0])), [0, -1, 0]);
  // What is not straight is no line: a rectangle's corner.
  assert.equal(lineOfPoints([[0, 0, 0], [10, 0, 0], [10, 10, 0]], 1), null);
});
