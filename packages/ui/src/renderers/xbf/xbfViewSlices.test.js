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
