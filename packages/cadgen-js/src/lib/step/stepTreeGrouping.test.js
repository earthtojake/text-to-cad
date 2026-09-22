import assert from "node:assert/strict";
import { test } from "node:test";

import { groupRepeatedStepTreeRows } from "./stepTree.js";

// Rows as flattenVisibleStepTreeRows emits them: pre-order, depth-tagged.
const row = (id, label, depth, { hasChildren = false, leafPartIds = [id] } = {}) =>
  ({ id, label, depth, hasChildren, leafPartIds, detail: "", nodeType: "part" });

// A deck with six identical planters, two unlike column pieces and a handle.
const DECK = [
  row("o1", "deck_module", 0, { hasChildren: true, leafPartIds: [] }),
  row("o1.1", "hatch_handle", 1),
  row("o1.2", "column_1_deck_socket", 1),
  row("o1.3", "column_1_module_1", 1),
  row("o1.4", "plant_1_01", 1),
  row("o1.5", "plant_1_02", 1),
  row("o1.6", "plant_1_03", 1)
];
// Planters share a component; the column pieces are different geometry.
const COMPONENTS = new Map([
  ["o1.1", "c-handle"],
  ["o1.2", "c-socket"],
  ["o1.3", "c-module"],
  ["o1.4", "c-planter"],
  ["o1.5", "c-planter"],
  ["o1.6", "c-planter"]
]);

const labels = (rows) => rows.map((r) => r.label);

test("folds rows that share a component and leaves the rest alone", () => {
  const out = groupRepeatedStepTreeRows(DECK, COMPONENTS);
  assert.deepEqual(labels(out),
    ["deck_module", "hatch_handle", "column_1_deck_socket", "column_1_module_1", "plant_1"]);
  const group = out[4];
  assert.equal(group.groupCount, 3);
  assert.ok(group.isGroup);
  assert.ok(group.hasChildren, "it opens to its instances");
});

test("names the group by what its members share, not by one of them", () => {
  const out = groupRepeatedStepTreeRows(DECK, COMPONENTS);
  assert.equal(out[4].label, "plant_1", "not plant_1_01, which names one and counts three");
});

test("a group stands where its first member stood", () => {
  const out = groupRepeatedStepTreeRows(DECK, COMPONENTS);
  assert.equal(out.indexOf(out.find((r) => r.isGroup)), 4, "assembly order survives");
});

test("selecting or hiding the group means every instance", () => {
  const out = groupRepeatedStepTreeRows(DECK, COMPONENTS);
  assert.deepEqual(out[4].leafPartIds, ["o1.4", "o1.5", "o1.6"]);
});

test("every instance stays reachable when the group opens", () => {
  const collapsed = groupRepeatedStepTreeRows(DECK, COMPONENTS);
  const groupId = collapsed[4].id;
  const opened = groupRepeatedStepTreeRows(DECK, COMPONENTS, [groupId]);
  assert.deepEqual(labels(opened).slice(4), ["plant_1", "plant_1_01", "plant_1_02", "plant_1_03"]);
  assert.equal(opened[5].depth, opened[4].depth + 1, "instances nest under the group");
  assert.equal(opened[5].inGroup, groupId);
});

test("two unlike parts never fold, however alike their names", () => {
  // column_1_deck_socket and column_1_module_1 share a prefix and nothing else.
  const out = groupRepeatedStepTreeRows(DECK, COMPONENTS);
  assert.ok(labels(out).includes("column_1_deck_socket"));
  assert.ok(labels(out).includes("column_1_module_1"));
});

test("identical names with different geometry stay apart", () => {
  const rows = [row("a", "bolt_01", 0), row("b", "bolt_02", 0)];
  const differing = new Map([["a", "c-m3"], ["b", "c-m4"]]);
  assert.equal(groupRepeatedStepTreeRows(rows, differing).length, 2);
});

test("a sub-assembly is not folded, because the tree is the structure", () => {
  const rows = [
    row("s1", "column_1", 0, { hasChildren: true }),
    row("s2", "column_2", 0, { hasChildren: true })
  ];
  const shared = new Map([["s1", "c-column"], ["s2", "c-column"]]);
  assert.equal(groupRepeatedStepTreeRows(rows, shared).length, 2);
});

test("same depth under different parents does not fold across them", () => {
  const rows = [
    row("p1", "left", 0, { hasChildren: true }),
    row("p1.1", "bolt", 1),
    row("p2", "right", 0, { hasChildren: true }),
    row("p2.1", "bolt", 1)
  ];
  const shared = new Map([["p1.1", "c-bolt"], ["p2.1", "c-bolt"]]);
  assert.deepEqual(labels(groupRepeatedStepTreeRows(rows, shared)),
    ["left", "bolt", "right", "bolt"], "one bolt each, not a group of two");
});

test("rows without a component id are passed through", () => {
  assert.deepEqual(groupRepeatedStepTreeRows(DECK, new Map()), DECK);
  assert.deepEqual(groupRepeatedStepTreeRows(DECK, null), DECK);
  assert.deepEqual(groupRepeatedStepTreeRows([], COMPONENTS), []);
});

test("a component appearing once is left as itself", () => {
  const out = groupRepeatedStepTreeRows(DECK, COMPONENTS);
  assert.ok(!out.find((r) => r.label === "hatch_handle").isGroup);
});
