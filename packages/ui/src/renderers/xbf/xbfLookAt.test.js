import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import test from 'node:test';
import * as THREE from 'three';
import { loadXbfDocument } from '@text-to-cad/core/lib/xbf/xbfDocument.js';
import { createXbfScene } from '@text-to-cad/core/lib/xbf/xbfScene.js';

import { lookAtFor } from '../kit/camera/lookAt.js';
import { xbfLookSubject } from './xbfLookAt.js';

/** An engine document's face or edge as what a double-click looks at: its kind from its surface or polyline, where it stands. */

// Core's bracket: a 40 x 20 x 4 plate on z = -2..2 with a Ø8 hole at the origin, two Ø6 pegs at x = ±12.
const FIXTURES = path.join(path.dirname(createRequire(import.meta.url).resolve('@text-to-cad/core/lib/xbf/xbfDocument.js')), '__fixtures__');
const read = file => fs.readFileSync(path.join(FIXTURES, file));
const ENVIRONMENT = new Uint8Array([...new TextEncoder().encode('#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y 1 +X 1\n'), 255, 255, 255, 128]).buffer;
async function bracket() {
  const fetch = async (url) => {
    if (url.endsWith('/api/look')) return new Response(read('look.json'));
    if (url.endsWith('/api/look/environment')) return new Response(ENVIRONMENT);
    const part = /\/part\/([^/]+)$/.exec(url);
    return new Response(part ? read(`bracket/${part[1]}.xbm`) : read('bracket/structure.json'));
  };
  return createXbfScene(THREE, await loadXbfDocument('http://127.0.0.1:9/api/doc/bracket', { fetch }));
}
const rounded = values => values.map(value => Math.round(value * 1000) / 1000 + 0);

test("a planar face is a plane by its normal; a cylinder's side a cylinder by its axis, origin and radius; any other face free", async () => {
  const scene = await bracket();
  const top = xbfLookSubject(scene, 'i0/face/2');
  assert.deepEqual([top.kind, rounded(top.normal), rounded(top.origin)], ['plane', [0, 0, 1], [0, 0, 2]]);
  assert.ok(top.points.length > 4 && top.points.every(point => Math.abs(point[2] - 2) < 1e-6), 'its nodes, on it');
  // Seen from up and off to the front-left, a double-click on it looks straight down at its middle, framed.
  const look = lookAtFor(top, [-0.6, -0.6, 0.53]);
  assert.deepEqual([rounded(look.direction), rounded(look.point)], [[0, 0, 1], [0, 0, 2]]);
  const hole = xbfLookSubject(scene, 'i0/face/11');
  assert.deepEqual([hole.kind, rounded(hole.axis.map(Math.abs)), rounded(hole.origin), Math.round(hole.radius * 1e6) / 1e6], ['cylinder', [0, 0, 1], [0, 0, 0], 4]);
  const surface = { elementGeometry: () => ({ kind: 'face', surface: { type: 'surface' }, points: [[0, 0, 0], [1, 0, 0], [0, 1, 1]] }) };
  assert.equal(xbfLookSubject(surface, 'i0/face/1').kind, 'free');
  assert.equal(xbfLookSubject(scene, 'i0/face/99'), null, 'no such face');
  scene.dispose();
});

test('a straight edge is a line, a circle a circle by its axis and centre, read off its polyline; any other curve free', async () => {
  const scene = await bracket();
  const line = xbfLookSubject(scene, 'i0/edge/7');
  assert.deepEqual([line.kind, rounded(line.direction.map(Math.abs)), line.points], ['line', [1, 0, 0], [[-18, -10, 2], [18, -10, 2]]]);
  const rim = xbfLookSubject(scene, 'i0/edge/12');
  assert.deepEqual([rim.kind, rounded(rim.axis.map(Math.abs)), rounded(rim.center)], ['circle', [0, 0, 1], [0, 0, 2]]);
  const wave = { elementGeometry: () => ({ kind: 'edge', points: [[0, 0, 0], [1, 1, 0], [2, 0, 0], [3, 1, 0], [4, 0, 0]] }) };
  assert.equal(xbfLookSubject(wave, 'i0/edge/1').kind, 'free');
  scene.dispose();
});

test('a face is looked at where its instance stands: Explode moves it with its part', async () => {
  const scene = await bracket();
  const before = xbfLookSubject(scene, 'i1/face/2');
  scene.setExplode(1);
  const after = xbfLookSubject(scene, 'i1/face/2');
  assert.equal(after.kind, 'plane');
  assert.notDeepEqual(rounded(after.origin), rounded(before.origin), 'the peg moved, and its top with it');
  const box = scene.selectionBounds(['i1/face/2']);
  assert.ok(after.points.every(point => point.every((value, axis) => value >= box.min[axis] - 1e-6 && value <= box.max[axis] + 1e-6)),
    'where the view draws it');
  scene.dispose();
});
