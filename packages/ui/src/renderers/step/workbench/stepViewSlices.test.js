import assert from "node:assert/strict";
import test from "node:test";

import { readFileView, writeFileView } from "../../kit/shell/fileView.js";
import { NO_TREE, readStepView, stepViewSignatures, stepViewSlices } from "./stepViewSlices.js";

const entry = { file: "hinge.step", kind: "assembly", hash: "h1" };
const tree = { expandedStepTreeNodeIds: ["o1.1"], hiddenPartIds: ["o1.2"], isolatedAssemblyNodeIds: ["o1"] };

test("the slices are written from the surface as it stands, and read back against the same file", () => {
  const signatures = stepViewSignatures(entry);
  const slices = stepViewSlices({ tree, parameterValues: { hinge: 30 }, largeFileState: { selectableTopologyEnabled: true } });
  assert.deepEqual(Object.keys(slices), ["tree", "pose", "largeFile", "annotations"]);
  const stored = JSON.parse(JSON.stringify(writeFileView({ renderer: slices, signatures })));
  const restored = readStepView(readFileView(stored, signatures).renderer);
  assert.deepEqual(restored.tree, tree);
  assert.deepEqual(restored.pose, { parameterValues: { hinge: 30 } });
  assert.equal(restored.largeFile.selectableTopologyEnabled, true);
  // A rebuilt model is not the model the tree was written against: the tree and the large-file
  // choice go, the pose (the sidecar's) stays.
  const rebuilt = readStepView(readFileView(stored, stepViewSignatures({ ...entry, hash: "h2", stepModule: undefined })).renderer);
  assert.deepEqual(rebuilt.tree, NO_TREE);
  assert.equal(rebuilt.largeFile.selectableTopologyEnabled, false);
  assert.equal(rebuilt.pose, null, "the sidecar's signature carries the file hash too");
});

test("annotations come back whatever the model has become, and malformed ones are dropped", () => {
  const note = { id: "a1", references: [{ selector: "o1.2", label: "Arm" }], text: "make a hole", anchor: { point: [1, 2, 3], normal: null } };
  const signatures = stepViewSignatures(entry);
  const slices = stepViewSlices({ tree, parameterValues: {}, largeFileState: null, annotations: [note, { id: "bad" }] });
  assert.deepEqual(slices.annotations, { items: [note] });
  const stored = JSON.parse(JSON.stringify(writeFileView({ renderer: slices, signatures })));
  const rebuilt = readStepView(readFileView(stored, stepViewSignatures({ ...entry, hash: "h2" })).renderer);
  assert.deepEqual(rebuilt.annotations, [note], "a note is the person's, not the geometry's");
  assert.deepEqual(readStepView({}).annotations, []);
});

test("a slice holds view state only: no selection, no routine, and ids are strings without duplicates", () => {
  const slices = stepViewSlices({ tree: { ...tree, selectedReferenceIds: ["o1.f1"], expandedStepTreeNodeIds: ["o1", "o1", 7, ""] },
    parameterValues: null, largeFileState: null });
  assert.deepEqual(slices.tree, { expandedStepTreeNodeIds: ["o1", "7"], hiddenPartIds: ["o1.2"], isolatedAssemblyNodeIds: ["o1"] });
  assert.equal("selectedReferenceIds" in slices.tree, false);
  assert.deepEqual(slices.pose, { parameterValues: {} });
  assert.equal(slices.largeFile.selectableTopologyEnabled, false);
  assert.deepEqual(readStepView(undefined), { tree: NO_TREE, pose: null, largeFile: { selectableTopologyEnabled: false }, annotations: [] });
});
