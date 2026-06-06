import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildAssemblyPartCopyText,
  buildNormalizedReferenceState,
  buildReferenceCacheKey,
  buildSelectionCopyButtonLabel,
  buildSelectionCopyPayload,
  buildWholeStepEntryCopyReference,
  cadRefQueryHasKnownEntry,
  collectCadRefSelectionRequest,
  computeNextSelectionIds,
  copySelectedReferenceText,
  normalizeReferenceList,
  orderedStringListEqual,
  parseAssemblyPartReferenceSelectionId,
  resolveCadRefSelection,
  resolveTopologyRelativeFile,
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
      "#o1 Root",
      "#s1 solid volume=1",
      "#f1 plane area=4",
      "#e1 line length=2"
    ]
  );
});

test("copy helpers merge selector refs and keep plain fallback lines", () => {
  const copyResult = copySelectedReferenceText([
    { id: "f2", copyText: "#f2" },
    { id: "f1", copyText: "#f1" },
    { id: "f1-duplicate", copyText: "#f1" },
    { id: "plain", copyText: "plain reference" }
  ]);
  assert.equal(copyResult.text, "#f1,f2\nplain reference");

  const payload = buildSelectionCopyPayload({
    references: [{ id: "e1", copyText: "#e1" }],
    parts: [
      { id: "part-b", occurrenceId: "o1.2", name: "Bracket" },
      { id: "", name: "Missing selector" }
    ],
    entry: STEP_ENTRY
  });
  assert.deepEqual(payload.lines, [
    "#e1,o1.2"
  ]);
  assert.equal(payload.copiedCount, 2);
  assert.deepEqual(payload.missingPartNames, ["Missing selector"]);

  assert.equal(
    buildAssemblyPartCopyText({ id: "part-b", occurrenceId: "o1.2", name: "Bracket" }, STEP_ENTRY),
    '#o1.2 Assembly part "Bracket"'
  );
  assert.deepEqual(buildWholeStepEntryCopyReference(STEP_ENTRY), {
    id: "step-entry:whole",
    copyText: "# STEP file"
  });
  assert.equal(buildSelectionCopyButtonLabel(payload.lines, { count: payload.copiedCount }), "Copy [2 refs] #e1,o1.2");
  assert.equal(buildSelectionCopyButtonLabel([]), "Copy refs");
});

test("selector ref query helpers classify and resolve selected references and parts", () => {
  const assemblyEntry = {
    ...STEP_ENTRY,
    kind: "assembly"
  };
  const cadRefs = [
    "#o1.2,f1"
  ];
  assert.equal(cadRefQueryHasKnownEntry(cadRefs, [assemblyEntry]), false);
  assert.deepEqual(collectCadRefSelectionRequest(cadRefs, assemblyEntry), {
    hasMatchingToken: true,
    hasWholeEntryToken: false,
    selectors: ["o1.2", "o1.2.f1"],
    needsParts: true,
    needsReferences: true
  });

  const resolved = resolveCadRefSelection({
    cadRefs,
    entry: assemblyEntry,
    isAssemblyView: true,
    references: [
      {
        id: "ref-face-1",
        partId: "part-a",
        copyText: "#o1.2.f1",
        displaySelector: "o1.2.f1",
        normalizedSelector: "o1.2.f1"
      }
    ],
    assemblyParts: [
      { id: "root", children: [{ id: "part-b", occurrenceId: "o1.2" }] },
      { id: "part-b", occurrenceId: "o1.2" }
    ]
  });
  assert.equal(resolved.hasMatchingToken, true);
  assert.deepEqual(resolved.selectedReferenceIds, ["ref-face-1"]);
  assert.deepEqual(resolved.selectedPartIds, ["part-b"]);
  assert.equal(resolved.inspectedAssemblyNodeId, "");
  assert.deepEqual(resolved.expandedAssemblyPartIds, ["part-b", "part-a"]);
});

test("selector ref query resolves nested occurrence selection without entering focus", () => {
  const assemblyEntry = {
    ...STEP_ENTRY,
    kind: "assembly"
  };
  const resolved = resolveCadRefSelection({
    cadRefs: ["#o1.2.3"],
    entry: assemblyEntry,
    isAssemblyView: true,
    assemblyParts: [
      { id: "root", children: [{ id: "module", occurrenceId: "o1.2" }] },
      { id: "module", occurrenceId: "o1.2", children: [{ id: "part-c", occurrenceId: "o1.2.3" }] },
      { id: "part-c", occurrenceId: "o1.2.3" }
    ]
  });

  assert.deepEqual(resolved.selectedPartIds, ["part-c"]);
  assert.equal(resolved.inspectedAssemblyNodeId, "");
  assert.deepEqual(resolved.expandedAssemblyPartIds, ["part-c"]);
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
