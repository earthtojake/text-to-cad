// The host's half of references (docs/file-view.md, "References and
// captures"): what `onReference` is handed for a copied line, and how a
// selector a host names (`selectReference`) maps onto the surface's own
// selection ids.
import assert from "node:assert/strict";
import test from "node:test";

import {
  findStepTreeNodeForSelector,
  referenceFromCopyText,
  referencesFromCopyText,
  resolveSelectorSelection,
} from "./hostReference.js";

test("referenceFromCopyText: the full file, the selector without its #, the text as copied", () => {
  assert.deepEqual(referenceFromCopyText("bracket.step#o1.2", "models/STEP/bracket.step"), {
    file: "models/STEP/bracket.step",
    selector: "o1.2",
    text: "bracket.step#o1.2",
  });
  assert.deepEqual(referenceFromCopyText("#f45,e3", "a.step"), { file: "a.step", selector: "f45,e3", text: "#f45,e3" });
  assert.deepEqual(referenceFromCopyText("bracket#label.f45", "src/bracket.step.py"), {
    file: "src/bracket.step.py",
    selector: "label.f45",
    text: "bracket#label.f45",
  });
  // A whole-file line has no selector; a path with no `#` is one too.
  assert.deepEqual(referenceFromCopyText("bracket.step#", "bracket.step"), { file: "bracket.step", selector: "", text: "bracket.step#" });
  assert.deepEqual(referenceFromCopyText("STEP/bracket.step", "STEP/bracket.step"), { file: "STEP/bracket.step", selector: "", text: "STEP/bracket.step" });
});

test("referencesFromCopyText: one per line, blanks dropped", () => {
  assert.deepEqual(
    referencesFromCopyText("a.step#o1\n\n a.step#o2 \n", "a.step").map((reference) => reference.selector),
    ["o1", "o2"],
  );
});

const TREE = {
  id: "root",
  occurrenceId: "o1",
  name: "assembly",
  children: [
    { id: "o1.1", occurrenceId: "o1.1", name: "bracket", label: "bracket", children: [] },
    {
      id: "o1.2",
      occurrenceId: "o1.2",
      name: "shaft",
      children: [
        { id: "topology-face:o1.2.f3", nodeType: "topology-face", topologyReferenceId: "o1.2.f3", displaySelector: "f3", children: [] },
      ],
    },
  ],
};

test("findStepTreeNodeForSelector: by occurrence id, name, label and topology id", () => {
  assert.equal(findStepTreeNodeForSelector(TREE, "o1.1")?.name, "bracket");
  assert.equal(findStepTreeNodeForSelector(TREE, "bracket")?.id, "o1.1");
  assert.equal(findStepTreeNodeForSelector(TREE, "shaft")?.id, "o1.2");
  assert.equal(findStepTreeNodeForSelector(TREE, "o1.2.f3")?.nodeType, "topology-face");
  assert.equal(findStepTreeNodeForSelector(TREE, "o9"), null);
  assert.equal(findStepTreeNodeForSelector(null, "o1"), null);
});

test("resolveSelectorSelection: reference map first, then the tree, then a labelled entity", () => {
  const referenceMap = new Map([
    ["o1.2.f7", { id: "ref:o1.2.f7" }],
    ["f7", { id: "ref:o1.2.f7" }],
    ["o1.1.f45", { id: "ref:o1.1.f45" }],
  ]);
  const options = { referenceMap, treeRoot: TREE };
  assert.deepEqual(resolveSelectorSelection("o1.2.f7", options), { kind: "reference", id: "ref:o1.2.f7" });
  assert.deepEqual(resolveSelectorSelection("o1.2", options), { kind: "part", id: "o1.2" });
  assert.deepEqual(resolveSelectorSelection("bracket", options), { kind: "part", id: "o1.1" });
  assert.deepEqual(resolveSelectorSelection("o1.2.f3", options), { kind: "reference", id: "o1.2.f3" });
  // `bracket.f45`: the labelled node's occurrence, then its entity in the map.
  assert.deepEqual(resolveSelectorSelection("bracket.f45", options), { kind: "reference", id: "ref:o1.1.f45" });
  // A list selects its first member; nothing known is null, not a guess.
  assert.deepEqual(resolveSelectorSelection("o1.1,o1.2", options), { kind: "part", id: "o1.1" });
  assert.equal(resolveSelectorSelection("o7.f1", options), null);
  assert.equal(resolveSelectorSelection("", options), null);
  assert.equal(resolveSelectorSelection("o1", {}), null);
});
