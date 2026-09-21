import assert from "node:assert/strict";
import test from "node:test";

import {
  VIEWPORT_QUALITY_STATE,
  lodSnapshotForFile,
  lodSnapshotForModel,
  viewportQualityStatus
} from "./viewportQualityStatus.js";

const standardSnapshot = {
  componentCount: 2,
  belowMinimum: 0,
  standardSettled: true,
  qualitySettled: true,
  busy: false,
  pendingEvaluation: false,
  unmetTargets: []
};

test("Render high detail requires a settled snapshot for its own quality policy", () => {
  const input = { hasGeometry: true, modelComplete: true, quality: "high", lodExpectedComponentCount: 2 };
  const stale = viewportQualityStatus({ ...input, lodSnapshot: { ...standardSnapshot, quality: "interactive" } });
  assert.equal(stale.state, VIEWPORT_QUALITY_STATE.REFINING);
  assert.equal(stale.standardQualityReady, true);
  assert.equal(stale.highQualityReady, false);
  const refining = viewportQualityStatus({ ...input, lodSnapshot: { ...standardSnapshot, quality: "high", busy: true } });
  assert.equal(refining.state, VIEWPORT_QUALITY_STATE.REFINING);
  const settled = viewportQualityStatus({ ...input, lodSnapshot: { ...standardSnapshot, quality: "high" } });
  assert.equal(settled.state, VIEWPORT_QUALITY_STATE.HIGH);
  assert.equal(settled.label, "High detail");
  assert.equal(settled.highQualityReady, true);
});

test("high quality never claims extra geometry detail for source meshes or memory-limited targets", () => {
  const mesh = viewportQualityStatus({ hasGeometry: true, modelComplete: true, quality: "high" });
  assert.equal(mesh.state, VIEWPORT_QUALITY_STATE.STANDARD);
  assert.equal(mesh.highQualityReady, false);
  const limited = viewportQualityStatus({ hasGeometry: true, modelComplete: true, quality: "high",
    lodSnapshot: { ...standardSnapshot, quality: "high", qualitySettled: false,
      unmetTargets: [{ reason: "memory-denied", targetLevel: 3 }] } });
  assert.equal(limited.label, "Extra detail limited");
  assert.equal(limited.highQualityReady, false);
});

test("first visible coarse geometry is a preview until standard detail settles", () => {
  const status = viewportQualityStatus({
    hasGeometry: true,
    modelComplete: true,
    lodSnapshot: { ...standardSnapshot, belowMinimum: 2, standardSettled: false, pendingEvaluation: true }
  });
  assert.equal(status.state, VIEWPORT_QUALITY_STATE.REFINING);
  assert.equal(status.firstPreviewReady, true);
  assert.equal(status.standardQualityReady, false);
});

test("standard quality is observable independently of further camera refinement", () => {
  const status = viewportQualityStatus({
    hasGeometry: true,
    modelComplete: true,
    lodSnapshot: { ...standardSnapshot, qualitySettled: false, busy: true }
  });
  assert.equal(status.state, VIEWPORT_QUALITY_STATE.REFINING);
  assert.equal(status.standardQualityReady, true);
});

test("a package waits for a scheduler snapshot covering its own components", () => {
  const status = viewportQualityStatus({
    hasGeometry: true,
    modelComplete: true,
    lodExpectedComponentCount: 1,
    lodSnapshot: { componentCount: 0, standardSettled: false, unmetTargets: [] }
  });
  assert.equal(status.state, VIEWPORT_QUALITY_STATE.REFINING);
  assert.equal(status.standardQualityReady, false);
});

test("a final 69-component package cannot inherit a settled 24-component preview", () => {
  const status = viewportQualityStatus({
    hasGeometry: true,
    modelComplete: true,
    lodExpectedComponentCount: 69,
    lodSnapshot: { ...standardSnapshot, componentCount: 24 }
  });
  assert.equal(status.state, VIEWPORT_QUALITY_STATE.REFINING);
  assert.equal(status.standardQualityReady, false);
});

test("a complete mesh with no component refinement is standard detail", () => {
  const status = viewportQualityStatus({ hasGeometry: true, modelComplete: true });
  assert.equal(status.state, VIEWPORT_QUALITY_STATE.STANDARD);
  assert.equal(status.standardQualityReady, true);
});

test("a partial progressive package never claims standard detail", () => {
  const status = viewportQualityStatus({
    hasGeometry: true,
    modelComplete: false,
    lodSnapshot: standardSnapshot
  });
  assert.equal(status.state, VIEWPORT_QUALITY_STATE.PREVIEW);
  assert.equal(status.standardQualityReady, false);
});

test("memory and work failures preserve the displayed geometry's honest state", () => {
  const limited = viewportQualityStatus({
    hasGeometry: true,
    modelComplete: true,
    lodSnapshot: { ...standardSnapshot, standardSettled: false, unmetTargets: [{ reason: "memory-denied" }] }
  });
  const failed = viewportQualityStatus({
    hasGeometry: true,
    modelComplete: true,
    lodSnapshot: { ...standardSnapshot, standardSettled: false, unmetTargets: [{ reason: "load-failed" }] }
  });
  assert.equal(limited.state, VIEWPORT_QUALITY_STATE.LIMITED);
  assert.equal(failed.state, VIEWPORT_QUALITY_STATE.ERROR);
});

test("a clean current snapshot clears a stale memory-limitation event", () => {
  const status = viewportQualityStatus({
    hasGeometry: true,
    modelComplete: true,
    lodSnapshot: standardSnapshot,
    memoryLimitation: { source: "viewportLod", unmetTargets: [{ reason: "memory-denied" }] }
  });
  assert.equal(status.state, VIEWPORT_QUALITY_STATE.STANDARD);
});

test("a current memory target remains reduced detail", () => {
  const status = viewportQualityStatus({
    hasGeometry: true,
    modelComplete: true,
    lodSnapshot: { ...standardSnapshot, standardSettled: false, unmetTargets: [{ reason: "memory-pressure" }] }
  });
  assert.equal(status.state, VIEWPORT_QUALITY_STATE.LIMITED);
});

test("a finished standard level describes an optional-detail limitation plainly", () => {
  const limited = viewportQualityStatus({
    hasGeometry: true,
    modelComplete: true,
    lodSnapshot: { ...standardSnapshot, busy: true, unmetTargets: [{ reason: "memory-denied" }] }
  });
  assert.equal(limited.standardQualityReady, true);
  assert.equal(limited.label, "Extra detail limited");
});

test("a disposed or foreign-file scheduler snapshot never belongs to the current model", () => {
  assert.equal(lodSnapshotForFile({ file: "old.step" }, "new.step"), null);
  assert.equal(lodSnapshotForFile({ file: "same.step", disposed: true }, "same.step"), null);
  assert.deepEqual(lodSnapshotForFile({ file: "same.step" }, "same.step"), { file: "same.step" });
});

test("a new model cannot inherit a prior model's settled scheduler snapshot", () => {
  const prior = { modelKey: "old.step:abc", snapshot: { ...standardSnapshot, file: "old.step", modelKey: "old.step:abc" } };
  assert.equal(lodSnapshotForModel(prior, "new.step:def"), null);
  assert.equal(lodSnapshotForModel(prior, "old.step:abc")?.standardSettled, true);
});

test("a same-file predecessor cannot satisfy a newer render revision", () => {
  const prior = { modelKey: "same.step:old", snapshot: { ...standardSnapshot, file: "same.step", modelKey: "same.step:old" } };
  assert.equal(lodSnapshotForModel(prior, "same.step:new"), null);
});
