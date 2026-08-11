import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildAssemblyPartCopyText,
  buildAssemblyMateCopyText,
  buildNormalizedReferenceState,
  buildReferenceCacheKey,
  buildSelectionCopyButtonLabel,
  buildSelectionCopyPayload,
  buildWholeStepEntryCopyReference,
  canonicalCadRefCopyText,
  computeNextSelectionIds,
  copySelectedReferenceText,
  normalizeReferenceList,
  orderedStringListEqual,
  parseAssemblyPartReferenceSelectionId,
  resolveTopologyRelativeFile,
  selectRequestedAssemblyComponents,
  uniqueStringList
} from "./referenceSelection.js";

const STEP_ENTRY = {
  file: "models/assy.step",
  kind: "part",
  url: "/models/.assy.step.glb",
  hash: "selector-hash",
  bytes: 42
};

function selectorBundle() {
  return {
    manifest: {
      cadRef: "models/assy",
      tables: {
        occurrenceColumns: ["id", "path", "name", "sourceName", "parentId", "transform", "bbox", "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        shapeColumns: ["id", "occurrenceId", "ordinal", "kind", "bbox", "center", "area", "volume", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        faceColumns: ["id", "occurrenceId", "shapeId", "ordinal", "surfaceType", "area", "center", "normal", "bbox", "edgeStart", "edgeCount", "relevance", "flags", "params", "triangleStart", "triangleCount"],
        edgeColumns: ["id", "occurrenceId", "shapeId", "ordinal", "curveType", "length", "center", "bbox", "faceStart", "faceCount", "relevance", "flags", "params", "segmentStart", "segmentCount"]
      },
      occurrences: [
        ["o1", "1", "Root", null, null, null, null, 0, 1, 0, 1, 0, 1]
      ],
      shapes: [
        ["o1.s1", "o1", 1, "solid", null, [0, 0, 0], 1, 1, 0, 1, 0, 1]
      ],
      faces: [
        ["o1.f1", "o1", "o1.s1", 1, "plane", 4, [0, 0, 0], [0, 0, 1], null, 0, 0, 0, 0, {}, 0, 0]
      ],
      edges: [
        ["o1.e1", "o1", "o1.s1", 1, "line", 2, [1, 0, 0], null, 0, 1, 0, 0, {}, 0, 0]
      ]
    },
    buffers: {}
  };
}

test("reference state normalization trims reference metadata and preserves cache keys", () => {
  assert.deepEqual(normalizeReferenceList([
    null,
    {
      id: "  f1  ",
      summary: " face ",
      copyText: " #f1 ",
      partId: " part-a ",
      entityType: " face ",
      selectorType: " face ",
      normalizedSelector: " f1 ",
      displaySelector: " f1 "
    },
    { id: "   " }
  ]), [
    {
      id: "f1",
      label: "f1",
      summary: "face",
      shortSummary: "face",
      copyText: "#f1",
      partId: "part-a",
      entityType: "face",
      selectorType: "face",
      normalizedSelector: "f1",
      displaySelector: "f1"
    }
  ]);

  const referenceState = buildNormalizedReferenceState(STEP_ENTRY, selectorBundle());
  assert.equal(buildReferenceCacheKey(STEP_ENTRY), "models/assy.step:selector-hash");
  assert.equal(referenceState.fileRef, "models/assy.step");
  assert.equal(referenceState.referenceHash, "models/assy.step:selector-hash");
  assert.equal(referenceState.stepHash, "selector-hash");
  assert.deepEqual(referenceState.counts, { faces: 1, edges: 1 });
  assert.deepEqual(
    referenceState.references.map((reference) => reference.copyText),
    [
      "#o1",
      "#s1",
      "#f1",
      "#e1"
    ]
  );
});

test("copy helpers merge selector refs and keep plain fallback lines", () => {
  const copyResult = copySelectedReferenceText([
    { id: "f2", copyText: "#f2 plane area=12" },
    { id: "f1", copyText: "#f1" },
    { id: "f1-duplicate", copyText: "#f1" },
    { id: "plain", copyText: "plain reference" }
  ]);
  assert.equal(copyResult.text, "#f1,f2\nplain reference");

  const payload = buildSelectionCopyPayload({
    references: [{ id: "e1", copyText: "#e1" }],
    parts: [
      { id: "part-b", occurrenceId: "o1.2", name: "Bracket" },
      { occurrenceId: "o1.6", name: "triangular_prism" },
      { id: "", name: "Missing selector" }
    ],
    entry: STEP_ENTRY
  });
  assert.deepEqual(payload.lines, [
    "#e1,o1.2,o1.6"
  ]);
  assert.equal(payload.copiedCount, 3);
  assert.deepEqual(payload.missingPartNames, ["Missing selector"]);

  assert.equal(
    buildAssemblyPartCopyText({ id: "part-b", occurrenceId: "o1.2", name: "Bracket" }, STEP_ENTRY),
    "#o1.2"
  );
  assert.equal(
    buildAssemblyPartCopyText({ occurrenceId: "o1.6", name: "triangular_prism" }, STEP_ENTRY),
    "#o1.6"
  );
  assert.equal(
    buildAssemblyPartCopyText({ id: "internal-node", displaySelector: "o1.7.1.s1", name: "cube_top_pad" }, STEP_ENTRY),
    "#o1.7.1.s1"
  );
  assert.equal(
    buildAssemblyPartCopyText({ id: "cube_top_pad", name: "cube_top_pad" }, STEP_ENTRY),
    ""
  );
  assert.deepEqual(buildWholeStepEntryCopyReference(STEP_ENTRY), {
    id: "step-entry:whole",
    copyText: "#"
  });
  assert.equal(buildSelectionCopyButtonLabel(payload.lines, { count: payload.copiedCount }), "Copy #e1,o1.2,o1.6");
  assert.equal(buildSelectionCopyButtonLabel(["#o1.7.1.s1 cube_top_pad solid volume=490"]), "Copy #o1.7.1.s1");
  assert.equal(canonicalCadRefCopyText("#o1.7.1.f4 plane area=35"), "#o1.7.1.f4");
  assert.equal(buildSelectionCopyButtonLabel([]), "Copy refs");
});

test("assembly mate refs copy as selector lines", () => {
  const assemblyEntry = {
    ...STEP_ENTRY,
    kind: "assembly"
  };
  const mate = {
    id: "m1",
    label: "m1",
    sourceLabel: "block mate",
    type: "face_to_face",
    fixed: "block_pocket_floor:offset",
    moving: "bottom_center"
  };
  const mateCopyText = buildAssemblyMateCopyText(mate, assemblyEntry);
  assert.equal(
    mateCopyText,
    "#m1"
  );

  const payload = buildSelectionCopyPayload({
    mates: [mate],
    entry: assemblyEntry
  });
  assert.deepEqual(payload.lines, [
    "#m1"
  ]);
  assert.equal(payload.copiedCount, 1);
});

test("selection utility helpers preserve list and topology path behavior", () => {
  assert.deepEqual(parseAssemblyPartReferenceSelectionId("assembly-part:part-a"), { partId: "part-a" });
  assert.deepEqual(parseAssemblyPartReferenceSelectionId("topology|part-b|face|f1"), { partId: "part-b" });
  assert.equal(parseAssemblyPartReferenceSelectionId("f1"), null);

  assert.equal(orderedStringListEqual(["a", "b"], ["a", "b"]), true);
  assert.equal(orderedStringListEqual(["a", "b"], ["b", "a"]), false);
  assert.deepEqual(uniqueStringList([" a ", "", "b", "a", " b "]), ["a", "b"]);
  assert.deepEqual(computeNextSelectionIds(["a"], "a"), []);
  assert.deepEqual(computeNextSelectionIds(["a"], "b"), ["b"]);
  assert.deepEqual(computeNextSelectionIds(["a"], "b", { multiSelect: true }), ["a", "b"]);
  assert.deepEqual(computeNextSelectionIds(["a", "b"], "a", { multiSelect: true }), ["b"]);

  assert.equal(
    resolveTopologyRelativeFile({ file: "models/assy.step" }, "../parts/part.step"),
    "models/parts/part.step"
  );
});

test("selectRequestedAssemblyComponents loads only the expanded occurrences' components", () => {
  const descriptor = {
    kind: "assembly-package",
    components: { cidA: { glb: "a.glb" }, cidB: { glb: "b.glb" }, cidC: { glb: "c.glb" } },
    occurrences: [
      { id: "o1", name: "root" }, // subassembly: no component
      { id: "o1.1", component: "cidA" },
      { id: "o1.2", component: "cidB" },
      { id: "o1.3", component: "cidA" } // shares cidA with o1.1
    ]
  };

  // Expanding ONE leaf node loads only that occurrence's component — not the whole assembly.
  const one = selectRequestedAssemblyComponents(descriptor, ["o1.2"]);
  assert.deepEqual(one.occurrencesToLoad.map((occ) => occ.id), ["o1.2"]);
  assert.deepEqual(one.neededCids, ["cidB"]);
  assert.equal(one.loadedTopologyKey, "o1.2");

  // Expanding more re-uses a shared component cid → deduped to a single fetch; key is order-stable.
  const two = selectRequestedAssemblyComponents(descriptor, ["o1.3", "o1.1"]);
  assert.deepEqual(two.occurrencesToLoad.map((occ) => occ.id), ["o1.1", "o1.3"]);
  assert.deepEqual(two.neededCids, ["cidA"]);
  assert.equal(two.loadedTopologyKey, "o1.1|o1.3");

  // An empty requested set (nothing expanded) loads nothing.
  const none = selectRequestedAssemblyComponents(descriptor, []);
  assert.equal(none.occurrencesToLoad.length, 0);
  assert.equal(none.neededCids.length, 0);
  assert.equal(none.loadedTopologyKey, "");

  // A single-component part has no tree, so it loads every referenced component regardless.
  const part = selectRequestedAssemblyComponents(descriptor, [], { singleComponentPart: true });
  assert.deepEqual(part.neededCids, ["cidA", "cidB"]);
  assert.equal(part.loadedTopologyKey, "*");
});
