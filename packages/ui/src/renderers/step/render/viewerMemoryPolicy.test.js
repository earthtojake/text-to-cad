import assert from "node:assert/strict";
import test from "node:test";

import {
  createViewerMemoryPolicy,
  ViewerMemoryLimitError,
} from "./viewerMemoryPolicy.js";

test("ledger accounts retained, worker reservations, GPU estimates and fixed headroom", () => {
  const policy = createViewerMemoryPolicy({
    budgetBytes: 1000,
    gpuHeadroomBytes: 100,
  });
  policy.setRetained("displayCpu", 300);
  policy.setRetained("selectors", 40);
  policy.setRetained("bvh", 20);
  policy.setRetained("gpuEstimated", 300);
  policy.setRetained("deformation", 10);
  policy.setRetained("assetCaches", 30);
  policy.setRetained("workerResidentEstimated", 25);
  policy.setRetained("replacementPending", 15);
  const admitted = policy.reserve({ category: "workerInFlight", bytes: 100, label: "component a" });
  assert.equal(admitted.ok, true);
  assert.deepEqual(policy.snapshot().inFlightByCategory, { workerInFlight: 100 });
  assert.equal(policy.snapshot().estimatedOwnedBytes, 840);
  assert.equal(policy.snapshot().availableBytes, 60);
  policy.release(admitted.token);
  assert.equal(policy.snapshot().reservationCount, 0);
});

test("a load's denial preserves the current allocation and reports a bounded limitation", () => {
  const limitations = [];
  const policy = createViewerMemoryPolicy({
    budgetBytes: 500,
    gpuHeadroomBytes: 50,
    onLimitation: (detail) => limitations.push(detail),
  });
  policy.setRetained("displayCpu", 250);
  policy.setRetained("gpuEstimated", 150);
  const denied = policy.reserve({
    category: "workerInFlight",
    bytes: 100,
    kind: "replace",
    label: "gear",
  });
  assert.equal(denied.ok, false);
  assert.equal(denied.detail.preservingCurrentView, true);
  assert.equal(policy.snapshot().estimatedOwnedBytes, 400, "denial allocates nothing");
  assert.equal(limitations.length, 1);
});

test("the policy makes no hard RSS claim", () => {
  const policy = createViewerMemoryPolicy({ budgetBytes: 100, gpuHeadroomBytes: 10 });
  assert.equal(policy.snapshot().hardRssCap, false);
  const error = new ViewerMemoryLimitError("limited", { requestedBytes: 20 });
  assert.equal(error.code, "VIEWER_MEMORY_LIMIT");
});

test("a transient admission miss does not become a stale completed-load limitation", () => {
  const policy = createViewerMemoryPolicy({ budgetBytes: 100, gpuHeadroomBytes: 10 });
  policy.setRetained("displayCpu", 90);
  const transient = policy.reserve({
    category: "workerInFlight",
    bytes: 1,
    recordLimitation: false,
  });
  assert.equal(transient.ok, false);
  assert.equal(policy.snapshot().lastLimitation, null);
  policy.noteLimitation({ requestedBytes: 1, preservingCurrentView: true });
  assert.equal(policy.snapshot().lastLimitation.requestedBytes, 1);
  policy.clearLimitation();
  assert.equal(policy.snapshot().lastLimitation, null);
});

test("live retained providers refresh diagnostics and admission", () => {
  const policy = createViewerMemoryPolicy({ budgetBytes: 300, gpuHeadroomBytes: 50 });
  let workerBytes = 80;
  policy.setRetainedProvider("workerResidentEstimated", () => workerBytes);
  assert.equal(policy.snapshot().retainedByCategory.workerResidentEstimated, 80);

  workerBytes = 240;
  const denied = policy.reserve({ category: "workerInFlight", bytes: 20 });
  assert.equal(denied.ok, false, "admission samples current foreign worker ownership");
  assert.equal(denied.detail.estimatedOwnedBytes, 240);

  workerBytes = 40;
  assert.equal(policy.snapshot().retainedByCategory.workerResidentEstimated, 40);
});
