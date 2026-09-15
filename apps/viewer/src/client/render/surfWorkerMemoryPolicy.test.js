import assert from "node:assert/strict";
import test from "node:test";

import { createViewerMemoryPolicy } from "./viewerMemoryPolicy.js";
import {
  installSurfWorkerMemoryProvider,
  workerResidentBytesFromStats,
} from "./surfWorkerMemoryPolicy.js";

test("worker resident accounting uses the exact live slot sum", () => {
  assert.equal(workerResidentBytesFromStats({
    residentSlots: 3,
    usedSlots: 2,
    residentEstimateBytes: 192 * 1024 * 1024,
  }), 192 * 1024 * 1024);
  assert.equal(workerResidentBytesFromStats({ residentEstimateBytes: 0 }), 0);
});

test("full and partial pool changes are reflected without a completion heuristic", () => {
  const policy = createViewerMemoryPolicy({
    budgetBytes: 1024 * 1024 * 1024,
    gpuHeadroomBytes: 0,
  });
  let stats = { residentSlots: 2, usedSlots: 2, residentEstimateBytes: 500 * 1024 * 1024 };
  installSurfWorkerMemoryProvider(policy, () => stats);
  assert.equal(policy.snapshot().retainedByCategory.workerResidentEstimated, 500 * 1024 * 1024);

  stats = { residentSlots: 1, usedSlots: 1, residentEstimateBytes: 250 * 1024 * 1024 };
  assert.equal(policy.snapshot().retainedByCategory.workerResidentEstimated, 250 * 1024 * 1024);

  stats = { residentSlots: 0, usedSlots: 0, residentEstimateBytes: 0 };
  assert.equal(policy.snapshot().retainedByCategory.workerResidentEstimated, 0);
});
