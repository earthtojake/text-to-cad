import assert from "node:assert/strict";
import test from "node:test";
import { readFileView, writeFileView } from "../kit/shell/fileView.js";
import { NO_TREE, readXbfView, xbfViewSignatures, xbfViewSlices } from "./xbfViewSlices.js";

// A hinge and a pin, as the engine serves the structure, and the hinge's mechanism.
const structure = {
  tree: { name: "fixture", children: [
    { name: "hinge", children: [{ name: "base", prototype: 0, instance: 0 }, { name: "arm", prototype: 1, instance: 1 }] },
    { name: "pin", prototype: 2, instance: 2 }
  ] },
  instances: [{ prototype: 0, path: "fixture/hinge/base" }, { prototype: 1, path: "fixture/hinge/arm" }, { prototype: 2, path: "fixture/pin" }]
};
const kinematics = { pairs: [{ label: "hinge", type: "revolute" }], configurations: { open: { hinge: 90 } }, asBuilt: { hinge: 0 } };

test("an engine document's tree and pose come back from the file's view while the document is the one they were written against", () => {
  const signatures = xbfViewSignatures(structure, kinematics);
  const slices = xbfViewSlices({
    tree: { expanded: ["n0.0", "n0.0"], hidden: ["i2"], isolated: ["n0.0"] },
    pose: { preset: "__none__", given: { hinge: [25] }, couplings: null }
  });
  assert.deepEqual(slices, { tree: { expanded: ["n0.0"], hidden: ["i2"], isolated: ["n0.0"] },
    pose: { preset: "__none__", given: { hinge: [25] }, couplings: null } });
  const record = writeFileView({ display: { mode: "solid" }, renderer: slices, signatures });
  // A reload: the record read back against the same document gives both slices whole.
  assert.deepEqual(readXbfView(readFileView(record, xbfViewSignatures(structure, kinematics)).renderer), slices);

  // A rebuild that moved the parts: the instances are numbered afresh, so the tree is not the
  // document's any more; the pose is, while the mechanism is the same.
  const moved = { ...structure, instances: [...structure.instances].reverse() };
  const afterMove = readXbfView(readFileView(record, xbfViewSignatures(moved, kinematics)).renderer);
  assert.deepEqual([afterMove.tree, afterMove.pose], [NO_TREE, slices.pose]);
  // A changed mechanism: the pose is dropped, the tree kept.
  const rejointed = readXbfView(readFileView(record, xbfViewSignatures(structure, { ...kinematics, configurations: {} })).renderer);
  assert.deepEqual([rejointed.tree, rejointed.pose], [slices.tree, null]);
});

test("a document with no mechanism keeps no pose, and a stored slice is read as far as it can be", () => {
  assert.deepEqual(Object.keys(xbfViewSignatures(structure, null)), ["tree"]);
  assert.equal(xbfViewSignatures(null, kinematics), null, "no structure yet: nothing can come back");
  assert.deepEqual(xbfViewSlices({ tree: {} }), { tree: { expanded: [], hidden: [], isolated: [] } });
  assert.deepEqual(readXbfView(null), { tree: NO_TREE, pose: null });
  // Ids are text, once each; a pose's values are numbers, or the values are left out.
  assert.deepEqual(readXbfView({ tree: { expanded: ["a", 7, "", "a"], hidden: "i1" }, pose: { preset: "open", given: { hinge: "x" } } }),
    { tree: { expanded: ["a", "7"], hidden: [], isolated: [] }, pose: { preset: "open", given: null, couplings: null } });
});

test("what of a document's PMI is hidden comes back across a rebuild of the same parts, while it has PMI", () => {
  const annotated = { ...structure, prototypes: [{ name: "base" }, { name: "arm" }, { name: "pin" }], pmi: [{ id: "A", part: 0 }, { id: "top-flat", part: 0 }] };
  const slices = xbfViewSlices({ tree: {}, pmi: { hidden: ["0:top-flat", "0:top-flat"], off: true } });
  assert.deepEqual(slices.pmi, { hidden: ["0:top-flat"], off: true });
  const record = writeFileView({ display: { mode: "solid" }, renderer: slices, signatures: xbfViewSignatures(annotated, null) });
  // A rebuild that moved the parts keeps it: an annotation is its part's and its author's id.
  const moved = { ...annotated, instances: [...annotated.instances].reverse() };
  assert.deepEqual(readXbfView(readFileView(record, xbfViewSignatures(moved, null)).renderer).pmi, { hidden: ["0:top-flat"], off: true });
  // One that renumbered the parts has other parts under those numbers: what was hidden is not.
  const renumbered = { ...annotated, prototypes: [...annotated.prototypes].reverse() };
  assert.equal(readXbfView(readFileView(record, xbfViewSignatures(renumbered, null)).renderer).pmi, undefined);
  // A document with no PMI has nothing of it to keep.
  assert.equal(xbfViewSignatures(structure, null).pmi, undefined);
  assert.equal(readXbfView(readFileView(record, xbfViewSignatures(structure, null)).renderer).pmi, undefined);
});
