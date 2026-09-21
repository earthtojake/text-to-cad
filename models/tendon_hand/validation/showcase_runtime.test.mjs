import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

// Exercise the authored runtime template without generated routes or a CAD build.
const runtime = readFileSync(new URL('./showcase_runtime.js', import.meta.url), 'utf8');
const numbers = [0, 0, 0, 10, 0, 0, 10, 10, 0, 20, 10, 0];
const context = vm.createContext({
  ROPE_BASE: [numbers], ROPE_TEMPLATES: [['bezier']], ROPE_NORMALS: [[0, 0, 1]],
  ROPE_VARYING: [[3, 7, 10]], ROPE_NAMES: ['cord'], MOTIONS: [], ACTUATOR_SAMPLES: [],
});
vm.runInContext(runtime.replace('export const clips', 'const clips'), context);
const { interpolate, applyTendons, blendedPose } = vm.runInContext(
  '({interpolate, applyTendons, blendedPose})', context,
);

test('equal interpolation endpoints remain exact through a hold', () => {
  for (const value of [0, 0.1, -0.1, 123.456789, -234.567891]) {
    for (let step = 0; step <= 1000; step++) {
      assert.equal(interpolate(value, value, step / 1000), value);
    }
  }
});

test('moving endpoints preserve the original interpolation at endpoints and between them', () => {
  for (const [low, high] of [[0.1, 0.2], [-234.567891, 123.456789], [4, -8]]) {
    for (let step = 0; step <= 1000; step++) {
      const alpha = step / 1000;
      assert.equal(interpolate(low, high, alpha), low * (1 - alpha) + high * alpha);
    }
  }
});

test('held tendon paths and poses retain exact values and observe mutated author data', () => {
  const low = {v: [10.123456, 10.234567, 10.345678], pose: {bend: 0.1}};
  const high = structuredClone(low);
  const run = alpha => {
    let result;
    applyTendons({get: () => ({deformTube(spec) { result = spec; }})}, low, high, alpha);
    return JSON.parse(JSON.stringify(result));
  };
  const first = run(0);
  for (let step = 0; step <= 100; step++) {
    assert.deepEqual(run(step / 100), first);
    assert.equal(blendedPose(low, high, step / 100).bend, 0.1);
  }
  high.v[0] += 1;
  assert.notDeepEqual(run(0.5), first);
  assert.deepEqual(first.path.segments[0].points[1], [10.123456, 0, 0]);
  assert.deepEqual(run(0), first);
});
