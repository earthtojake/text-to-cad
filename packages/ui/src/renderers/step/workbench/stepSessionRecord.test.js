import assert from "node:assert/strict";
import test from "node:test";

import { readStepRecord, restoredPoseValues, stepRecordInputs, stepRecordSignatures, writeStepRecord } from "./stepSessionRecord.js";

const entry = { file: "hinge.step", kind: "assembly", hash: "h1" };
const tree = { selectedReferenceIds: ["o1.1.f3"], selectedPartIds: [], expandedStepTreeNodeIds: ["o1.1"], hiddenPartIds: ["o1.2"] };
const animationState = { activeClipId: "swing", enabled: false, playing: false, elapsedSec: 1.5, speed: 2, loopEnabled: false };

test("the record is written from the surface as it stands, and reads back against the same file", () => {
  const signatures = stepRecordSignatures(entry);
  const inputs = stepRecordInputs({ tree, parameterValues: { hinge: 30 }, animationState, clockTime: () => 9,
    largeFileState: { selectableTopologyEnabled: true }, signatures });
  assert.equal(inputs.animation.elapsedSec, 1.5, "a paused clip's time is React state's");
  const record = writeStepRecord(inputs);
  const restored = readStepRecord(record, signatures);
  assert.deepEqual(restored.tree, tree);
  assert.deepEqual(restored.pose, { parameterValues: { hinge: 30 } });
  assert.equal(restored.largeFile.selectableTopologyEnabled, true);
  // A rebuilt model is not the model the tree was written against.
  assert.deepEqual(readStepRecord(record, stepRecordSignatures({ ...entry, hash: "h2" })).tree.selectedReferenceIds, []);
});

test("while a clip plays its time is the clock's", () => {
  const inputs = stepRecordInputs({ tree, parameterValues: {}, animationState: { ...animationState, enabled: true, playing: true },
    clockTime: () => 3.25, largeFileState: { selectableTopologyEnabled: false }, signatures: stepRecordSignatures(entry) });
  assert.equal(inputs.animation.elapsedSec, 3.25);
});

test("a routine that owned the pose wins: its record restores no Position values", () => {
  assert.equal(restoredPoseValues({ pose: null, animation: null }), null);
  assert.deepEqual(restoredPoseValues({ pose: { parameterValues: { hinge: 30 } }, animation: null }), { hinge: 30 });
  assert.deepEqual(restoredPoseValues({ pose: { parameterValues: { hinge: 30 } }, animation: { enabled: false, activeClipId: "swing" } }), { hinge: 30 });
  assert.deepEqual(restoredPoseValues({ pose: { parameterValues: { hinge: 30 } }, animation: { enabled: true, activeClipId: "swing" } }), {});
});
