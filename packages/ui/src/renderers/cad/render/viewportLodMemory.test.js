import assert from "node:assert/strict";
import test from "node:test";

import { estimateViewportLodMemory } from "./viewportLodMemory.js";

test("LOD admission and worker ownership share one concrete mesh estimate", () => {
  const estimate = estimateViewportLodMemory({ meshBytes: 1000, currentLevel: 1, level: 2 });
  assert.deepEqual(estimate, {
    currentBytes: 1000,
    nextMeshBytes: 3000,
    replacementBytes: 7500,
    workerTemporaryBytes: 6000,
    heldPreviousBytes: 2500,
    admissionBytes: 16000,
  });
});

test("canonical refinement includes the coarse tier's relaxed angular criterion", () => {
  const estimate = estimateViewportLodMemory({ meshBytes: 1000, currentLevel: 0, level: 1 });
  assert.equal(estimate.nextMeshBytes, 4000);
  assert.equal(estimate.admissionBytes, 20500);
});
