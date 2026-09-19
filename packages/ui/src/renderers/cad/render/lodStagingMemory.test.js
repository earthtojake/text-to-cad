import assert from "node:assert/strict";
import test from "node:test";
import { lodPayloadMemory, setLodStaging, lodStagingBuffers, lodStagingSnapshot, syncSelectorCacheAccounting } from "./lodStagingMemory.js";
import { createViewerMemoryPolicy } from "./viewerMemoryPolicy.js";

test("payload charges full unique backing once, with separately measured mesh GPU inputs", () => {
  const backing = new ArrayBuffer(4096), vertices = new Float32Array(backing, 0, 9), indices = new Uint32Array(backing, 40, 3);
  const mesh = { vertices, indices }, bundle = { face: { positions: new Float32Array(backing, 100, 6) } };
  bundle.loop = bundle;
  const value = lodPayloadMemory({ meshData: { parts: [{ sourceMesh: mesh }, { sourceMesh: mesh }] }, bundle });
  assert.equal(value.cpuBytes, 4096); assert.equal(value.gpuInputBytes, 48); assert.equal(value.buffers.size, 1);
});

test("stage exclusions keep shared buffers until their final owner releases, including cancellation cleanup", () => {
  const first = Symbol(), second = Symbol(), backing = new ArrayBuffer(128), extra = new ArrayBuffer(64);
  const entries = [{ payload: { meshData: { vertices: new Float32Array(backing) }, bundle: { indices: new Uint32Array(extra) } } }];
  setLodStaging(first, entries); setLodStaging(second, entries);
  assert.deepEqual(lodStagingSnapshot(), { owners: 2, buffers: 2, bytes: 192 });
  assert.equal(lodStagingBuffers([backing]).size, 2);
  setLodStaging(first, []); assert.deepEqual(lodStagingSnapshot(), { owners: 1, buffers: 2, bytes: 192 });
  setLodStaging(second, []); setLodStaging(second, []);
  assert.deepEqual(lodStagingSnapshot(), { owners: 0, buffers: 0, bytes: 0 });
});

test("cache-only updates preserve measured picking arrays and cannot mix independent policies", () => {
  const one = createViewerMemoryPolicy(), two = createViewerMemoryPolicy();
  syncSelectorCacheAccounting(one, 200, 700); syncSelectorCacheAccounting(two, 50, 100);
  syncSelectorCacheAccounting(one, 0); syncSelectorCacheAccounting(two, 80);
  assert.equal(one.snapshot().retainedByCategory.selectors, 700);
  assert.equal(two.snapshot().retainedByCategory.selectors, 180);
  syncSelectorCacheAccounting(one, 400); assert.equal(one.snapshot().retainedByCategory.selectors, 1100);
  syncSelectorCacheAccounting(one, 300, 30); assert.equal(one.snapshot().retainedByCategory.selectors, 330);
  one.reset(); syncSelectorCacheAccounting(one, 10); assert.equal(one.snapshot().retainedByCategory.selectors, 10);
});
