import assert from "node:assert/strict";
import test from "node:test";
import { isCompletePublication, isRequestedDetailComplete, recordMeshCostRampSample } from "./completion.mjs";

const completeCost = {
  final: true,
  loadedComponents: 866,
  totalComponents: 866,
  componentCount: 866,
  occurrenceCount: 1220,
  at: 100.4,
};
const completeScene = {
  modelKey: "hand",
  renderMemoryProbe: { occurrences: 1220 },
  sceneSync: { atMs: 101, records: 1220 },
};

test("a partial model never becomes fully loaded when failure or retry clears its probe", () => {
  const visible = { modelKey: "hand" };
  assert.equal(isCompletePublication({ ...visible, meshCost: { final: false, loadedComponents: 56, totalComponents: 866 } }), false);
  assert.equal(isCompletePublication({ ...visible, meshCost: null }), false);
  assert.equal(isCompletePublication({ ...visible, meshCost: { final: false, loadedComponents: 866, totalComponents: 866 } }), false);
  assert.equal(isCompletePublication({ ...visible, meshCost: { final: true, loadedComponents: 56, totalComponents: 866 } }), false);
  assert.equal(isCompletePublication({ ...visible, meshCost: { final: true, loadedComponents: 866, totalComponents: 866, componentCount: 849 } }), false);
  assert.equal(isCompletePublication({ modelKey: "", meshCost: { final: true, loadedComponents: 866, totalComponents: 866 } }), false);
});

test("a final publication cannot certify an old partial scene", () => {
  assert.equal(isCompletePublication({
    ...completeScene,
    meshCost: completeCost,
    renderMemoryProbe: { occurrences: 56 },
    sceneSync: { atMs: 101, records: 56 },
  }), false);
});

test("a complete publication succeeds only after matching render and scene counts", () => {
  assert.equal(isCompletePublication({ ...completeScene, meshCost: completeCost }), true);
});

test("canonical completion requires every leaf and a settled requested detail floor", () => {
  const probe = { ...completeScene, meshCost: completeCost };
  assert.equal(isRequestedDetailComplete(probe, 0), true);
  assert.equal(isRequestedDetailComplete(probe, 1), false);
  const lod = { minimumLevel: 1, componentCount: 866, belowMinimum: 0, busy: false, pendingEvaluation: false };
  assert.equal(isRequestedDetailComplete({ ...probe, viewportLod: lod }, 1), true);
  for (const change of [{ componentCount: 865 }, { belowMinimum: 1 }, { busy: true }, { pendingEvaluation: true }]) {
    assert.equal(isRequestedDetailComplete({ ...probe, viewportLod: { ...lod, ...change } }, 1), false);
  }
});

test("scene sync must complete at or after the final publication", () => {
  assert.equal(isCompletePublication({
    ...completeScene,
    meshCost: completeCost,
    sceneSync: { atMs: 99, records: 1220 },
  }), false);
  assert.equal(isCompletePublication({
    ...completeScene,
    meshCost: { ...completeCost, at: 100.9 },
    sceneSync: { atMs: 100, records: 1220 },
  }), true, "scene timestamps are integer-rounded, so compare against the publication floor");
});

test("ramp records a null clear and the same publication after restart", () => {
  const state = { entries: [], lastKey: "", seenPublication: false };
  recordMeshCostRampSample(state, null, 1);
  recordMeshCostRampSample(state, { loadedComponents: 8 }, 2);
  recordMeshCostRampSample(state, { loadedComponents: 8 }, 3);
  recordMeshCostRampSample(state, null, 4);
  recordMeshCostRampSample(state, { loadedComponents: 8 }, 5);
  assert.deepEqual(state.entries, [
    { atMs: 2, cost: { loadedComponents: 8 } },
    { atMs: 4, cost: null },
    { atMs: 5, cost: { loadedComponents: 8 } },
  ]);
});
