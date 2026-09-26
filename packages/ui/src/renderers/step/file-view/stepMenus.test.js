import assert from "node:assert/strict";
import test from "node:test";

import { modelMenuDescriptor, partMenuDescriptor, topologyMenuDescriptor } from "./stepMenus.js";

const entry = { file: "hinge.step", kind: "assembly" };
const root = { id: "root", name: "hinge", children: [
  { id: "o1.1", name: "base", nodeType: "part", children: [] },
  { id: "o1.2", name: "arm", nodeType: "part", children: [] }
] };
const common = { root, isAssemblyView: true, expandedIds: [], loadableIds: ["o1.1", "o1.2"], copyReferenceMap: new Map(), entry };

test("the model menu offers Show all only with something hidden, and frames the selection only with one", () => {
  const none = modelMenuDescriptor({ ...common, hiddenCount: 0, zoomSelectionAvailable: false });
  assert.equal(none.global, true);
  assert.equal(none.showShowAll, false);
  assert.equal(none.zoomSelectionAvailable, false);
  assert.equal(none.collapseAllDisabled, true, "nothing is open to collapse");
  const some = modelMenuDescriptor({ ...common, expandedIds: ["o1.1"], hiddenCount: 2, zoomSelectionAvailable: true });
  assert.deepEqual([some.showShowAll, some.zoomSelectionAvailable, some.collapseAllDisabled], [true, true, false]);
});

test("a lone part's model menu carries the whole part's reference; an assembly's carries none", () => {
  const lone = modelMenuDescriptor({ ...common, isAssemblyView: false, entry: { ...entry, kind: "part", fileRefPrefix: "hinge.step" },
    hiddenCount: 0, zoomSelectionAvailable: false });
  assert.equal(lone.copyText, "hinge.step#", "Add to prompt and Copy Reference name the whole file");
  assert.equal(modelMenuDescriptor({ ...common, isAssemblyView: false, hiddenCount: 0, zoomSelectionAvailable: false }).copyText, "#");
  assert.equal(modelMenuDescriptor({ ...common, hiddenCount: 0, zoomSelectionAvailable: false }).copyText, "",
    "empty space in an assembly names no part");
});

test("a part menu acts on the whole selection with the node, and says what the node is", () => {
  const menu = partMenuDescriptor({ ...common, nodeId: " o1.2 ", renderPartId: "", node: root.children[1], leafIds: ["o1.2"],
    hiddenPartIds: [], focusedNodeIds: [], selectedPartIds: ["o1.1"], zoomSelectionAvailable: true });
  assert.equal(menu.nodeId, "o1.2");
  assert.equal(menu.renderPartId, "o1.2", "a tree row is its own node");
  assert.equal(menu.label, "arm");
  assert.deepEqual(menu.actionNodeIds, ["o1.1", "o1.2"]);
  assert.equal(menu.actionCount, 2);
  assert.equal(menu.selected, false);
  assert.equal(menu.copyText, "#o1.2", "Copy Reference copies the node's own reference");
  const hidden = partMenuDescriptor({ ...common, nodeId: "o1.2", node: root.children[1], leafIds: ["o1.2"],
    hiddenPartIds: ["o1.2"], focusedNodeIds: ["o1.2"], selectedPartIds: [], zoomSelectionAvailable: false });
  assert.deepEqual([hidden.hidden, hidden.selectDisabled, hidden.focused, hidden.showVisibility, hidden.hideOtherDisabled], [true, true, true, false, true]);
  assert.equal(partMenuDescriptor({ ...common, nodeId: "", node: null, leafIds: [], hiddenPartIds: [], focusedNodeIds: [], selectedPartIds: [] }), null);
});

test("a topology menu takes the selected faces with the picked ones, and opens empty while a row loads", () => {
  const referenceMap = new Map([["o1.1.f3", { id: "o1.1.f3", selectorType: "face", copyText: "#o1.1.f3" }],
    ["o1.1.f4", { id: "o1.1.f4", selectorType: "face", copyText: "#o1.1.f4" }]]);
  const menu = topologyMenuDescriptor({ referenceIds: ["o1.1.f4"], label: "Top", selectedReferenceIds: ["o1.1.f3"], referenceMap,
    copyReferenceMap: new Map(), entry, zoomSelectionAvailable: true });
  assert.deepEqual(menu.referenceIds, ["o1.1.f3", "o1.1.f4"]);
  assert.equal(menu.label, "Top");
  assert.equal(menu.selected, false);
  assert.equal(menu.showIsolate, false);
  assert.equal(menu.copyText, "#o1.1.f3,o1.1.f4", "one reference that names every face it acts on");
  const loading = topologyMenuDescriptor({ referenceIds: [], selectedReferenceIds: ["o1.1.f3"], referenceMap, copyReferenceMap: new Map(), entry, zoomSelectionAvailable: false });
  assert.deepEqual([loading.referenceIds, loading.copyText, loading.actionCount], [[], "", 1]);
});
