import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { parseSurf } from '../surf/container.js';
import { buildSelectorBundleFromSurf } from '../surf/surfSelectorBundle.js';
import { buildSelectorRuntime, composeSelectorRuntimes } from '../selectors/runtime.js';
import { recognizeStepFeatures } from './recognizeFeatures.js';

// Extracted AFTER exporting and reimporting recognition_fixture.py's STEP.
// No model recipe, inferred history, Python runtime or mesh proxy is available
// to recognition. The fixture includes an exterior boss to catch false holes.
const bytes = readFileSync(new URL('../../../../../models/examples/STEP/recognition-fixture.surf', import.meta.url));
const { index, floats } = parseSurf(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
const bundle = buildSelectorBundleFromSurf(index, floats);
const makeRuntime = options => buildSelectorRuntime(bundle, { copyCadPath: 'recognition-fixture.step', ...options });
const dimensions = group => group.dimensions.map(d => Math.round(d.value * 1e6) / 1e6);

test('imported STEP recognizes only hole/slot walls and measured dimensions', () => {
  const runtime = makeRuntime();
  const before = JSON.stringify(runtime);
  const result = recognizeStepFeatures(runtime);
  assert.equal(result.status, 'ready');
  assert.deepEqual(result.groups.map(g => g.kind), ['hole', 'slot']);
  assert.deepEqual(result.groups[0].faceIds, ['f11']);
  assert.deepEqual(result.groups[1].faceIds, ['f10', 'f7', 'f8', 'f9']);
  assert.deepEqual(dimensions(result.groups[0]), [6, 6]);
  assert.deepEqual(dimensions(result.groups[1]), [30, 8, 6]);
  assert.equal(runtime.referenceMap.get('f12').pickData.inwardCylinder, false);
  assert.equal(JSON.stringify(runtime), before, 'recognition must not mutate geometry or runtime');
});

test('transformed assembly occurrences keep groups, dimensions and selectors separate', () => {
  const first = makeRuntime({ partId: 'bracketA', remapOccurrenceId: 'o2' });
  const second = makeRuntime({ partId: 'bracketB', remapOccurrenceId: 'o3', transform: [1,0,0,0, 0,0,1,0, 0,-1,0,0, 100,20,30,1] });
  const runtime = composeSelectorRuntimes([first, second]);
  for (const partId of ['bracketA', 'bracketB']) {
    const result = recognizeStepFeatures(runtime, { partId });
    assert.equal(result.groups.length, 2);
    assert.deepEqual(dimensions(result.groups[1]), [30, 8, 6]);
    assert.ok(result.groups.every(g => g.partId === partId));
    assert.ok(result.groups.every(g => g.faceIds.every(id => runtime.referenceMap.get(id).partId === partId)));
  }
  assert.equal(recognizeStepFeatures(runtime).groups.length, 4);
});

test('incomplete curved walls and missing orientation do not invent holes', () => {
  const runtime = makeRuntime();
  runtime.referenceMap.get('f11').pickData.area /= 2;
  runtime.referenceMap.get('f8').pickData.inwardCylinder = null;
  assert.deepEqual(recognizeStepFeatures(runtime).groups, []);
});

test('unsupported/freeform slot wall is not presented as a recognized slot', () => {
  const runtime = makeRuntime();
  runtime.referenceMap.get('f7').pickData.surfaceType = 'bspline';
  assert.deepEqual(recognizeStepFeatures(runtime).groups.map(g => g.kind), ['hole']);
});

test('missing part and excessive topology yield explicit non-results', () => {
  const runtime = makeRuntime();
  assert.equal(recognizeStepFeatures(runtime, { partId: 'absent' }).status, 'unavailable');
  assert.equal(recognizeStepFeatures(runtime, { maxFaces: 2 }).status, 'too-large');
  assert.equal(recognizeStepFeatures(null).status, 'unavailable');
});
