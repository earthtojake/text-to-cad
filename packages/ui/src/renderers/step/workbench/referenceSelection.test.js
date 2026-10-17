import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildAssemblyPartCopyText,
  fileRefPrefixForEntry,
  buildNormalizedReferenceState,
  buildReferenceCacheKey,
  buildSelectionCopyPayload,
  buildWholeStepEntryCopyReference,
  canonicalCadRefCopyText,
  computeNextSelectionIds,
  copySelectedReferenceText,
  copyTextLines,
  normalizeReferenceList,
  orderedStringListEqual,
  parseAssemblyPartReferenceSelectionId,
  selectRequestedAssemblyComponents,
  topologyCompositionKeyMatches,
  topologyCompositionServes,
  uniqueStringList,
  withFileRefPrefix
} from "./referenceSelection.js";

const STEP_ENTRY = {
  file: "models/assy.step",
  kind: "part",
  url: "/models/.assy.step.glb",
  hash: "selector-hash",
  bytes: 42
};

// Occurrence tokens of three parts (in the order a sorted copy line lists them) and element
// names: a ref is `<occurrence token>/<element name>`.
const ROOT = "o:1a2b3c4d5e6f";
const BRACKET = "o:2b3c4d5e6f70";
const PRISM = "o:3c4d5e6f7081";
const F1 = "f:base.extrude1.3";
const F4 = "f:base.hole1.1";
const E1 = "e:base.extrude1.5";

// A part's selector table (cadgen selector_table.py, schema 3) as `joinSelectorTable` extends
// it: element rows lead with their name and name no occurrence; the page places them.
function selectorBundle() {
  return {
    manifest: {
      cadRef: "models/assy",
      tables: {
        occurrenceColumns: ["transform", "bbox", "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount", "vertexStart", "vertexCount"],
        shapeColumns: ["ordinal", "kind", "bbox", "center", "area", "faceStart", "faceCount", "edgeStart", "edgeCount"],
        faceColumns: ["name", "ordinal", "shape", "surfaceType", "area", "center", "normal", "bbox", "edgeStart", "edgeCount", "relevance", "flags", "params", "tangentGroup", "triangleStart", "triangleCount"],
        edgeColumns: ["name", "ordinal", "shape", "curveType", "length", "center", "bbox", "faceStart", "faceCount", "vertexStart", "vertexCount", "relevance", "flags", "params", "adjacentFaceCount", "continuity", "dihedralDeg", "visibilityClass", "chain", "segmentStart", "segmentCount"]
      },
      occurrences: [
        [null, null, 0, 1, 0, 1, 0, 1, 0, 0]
      ],
      shapes: [
        [1, "solid", null, [0, 0, 0], 1, 0, 1, 0, 1]
      ],
      faces: [
        [F1, 1, 1, "plane", 4, [0, 0, 0], [0, 0, 1], null, 0, 0, 0, 0, {}, 1, 0, 0]
      ],
      edges: [
        [E1, 1, 1, "line", 2, [1, 0, 0], null, 0, 1, 0, 0, 0, 0, {}, 1, "c0", 90, "feature", 1, 0, 0]
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

  const referenceState = buildNormalizedReferenceState(STEP_ENTRY, selectorBundle(), { occurrenceId: ROOT });
  assert.equal(buildReferenceCacheKey(STEP_ENTRY), "models/assy.step:selector-hash");
  assert.equal(referenceState.fileRef, "models/assy.step");
  assert.equal(referenceState.referenceHash, "models/assy.step:selector-hash");
  // The occurrence, its face and its edge; a solid is a row, never a reference.
  assert.deepEqual(
    referenceState.references.map((reference) => reference.copyText),
    [
      `#${ROOT}`,
      `#${ROOT}/${F1}`,
      `#${ROOT}/${E1}`
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
    references: [{ id: "e1", copyText: `#${ROOT}/${E1}` }],
    parts: [
      { id: "part-b", occurrenceId: BRACKET, name: "Bracket" },
      { occurrenceId: PRISM, name: "triangular_prism" },
      { id: "", name: "Missing selector" }
    ],
    entry: STEP_ENTRY
  });
  assert.deepEqual(payload.lines, [
    `#${ROOT}/${E1},${BRACKET},${PRISM}`
  ]);
  assert.equal(payload.copiedCount, 3);
  assert.deepEqual(payload.missingPartNames, ["Missing selector"]);

  assert.equal(
    buildAssemblyPartCopyText({ id: "part-b", occurrenceId: BRACKET, name: "Bracket" }, STEP_ENTRY),
    `#${BRACKET}`
  );
  assert.equal(
    buildAssemblyPartCopyText({ occurrenceId: PRISM, name: "triangular_prism" }, STEP_ENTRY),
    `#${PRISM}`
  );
  assert.equal(
    buildAssemblyPartCopyText({ id: "internal-node", displaySelector: PRISM, name: "cube_top_pad" }, STEP_ENTRY),
    `#${PRISM}`
  );
  // A name is never a selector, and neither is an id of the old positional grammar.
  assert.equal(
    buildAssemblyPartCopyText({ id: "cube_top_pad", name: "cube_top_pad" }, STEP_ENTRY),
    ""
  );
  assert.equal(
    buildAssemblyPartCopyText({ id: "o1.7.1", occurrenceId: "o1.7.1", name: "cube_top_pad" }, STEP_ENTRY),
    ""
  );
  assert.deepEqual(buildWholeStepEntryCopyReference(STEP_ENTRY), {
    id: "step-entry:whole",
    copyText: "#"
  });
  assert.equal(canonicalCadRefCopyText(`#${ROOT}/${F4} plane area=35`), `#${ROOT}/${F4}`);
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

test("empty lazy topology composition remains a valid exact assembly key", () => {
  assert.equal(topologyCompositionKeyMatches("", ""), true);
  assert.equal(topologyCompositionKeyMatches(undefined, "*"), true);
  assert.equal(topologyCompositionKeyMatches("o1.3", "o1.3"), true);
  assert.equal(topologyCompositionKeyMatches("", "*"), false);
});

test("a composition serves a request that holds every part it loaded", () => {
  const state = { loadedTopologyKey: "o1.1|o1.2", loadedTopologyIds: ["o1.1", "o1.2"] };
  // Exactly its parts, or more of them on the way.
  assert.equal(topologyCompositionServes(state, "o1.1|o1.2", ["o1.2", "o1.1"]), true);
  assert.equal(topologyCompositionServes(state, "o1.1|o1.2|o1.3", ["o1.1", "o1.2", "o1.3"]), true);
  // A part it holds is no longer requested: not until it is composed again without it.
  assert.equal(topologyCompositionServes(state, "o1.1", ["o1.1"]), false);
  // A part file (and a state without loaded ids) serves only its exact key.
  assert.equal(topologyCompositionServes({ loadedTopologyKey: "*", loadedTopologyIds: null }, "*", []), true);
  assert.equal(topologyCompositionServes({ loadedTopologyKey: "o1.1", loadedTopologyIds: null }, "o1.1|o1.2", ["o1.1", "o1.2"]), false);
  assert.equal(topologyCompositionServes(null, "", []), false);
});

test("copy text carries the entry's file prefix", () => {
  const entry = { ...STEP_ENTRY, fileRefPrefix: "models/assy.step" };
  assert.equal(
    buildAssemblyPartCopyText({ occurrenceId: PRISM, name: "prism" }, entry),
    `models/assy.step#${PRISM}`
  );
  assert.equal(buildWholeStepEntryCopyReference(entry).copyText, "models/assy.step#");
  assert.equal(fileRefPrefixForEntry(entry), "models/assy.step");
});


test("an entry with no prefix emits the bare refs it always did", () => {
  // The prefix is opt-in per call site: every existing caller that builds a minimal entry keeps
  // producing exactly the copy text it produced before.
  assert.equal(
    buildAssemblyPartCopyText({ occurrenceId: PRISM, name: "prism" }, STEP_ENTRY),
    `#${PRISM}`
  );
  assert.equal(buildWholeStepEntryCopyReference(STEP_ENTRY).copyText, "#");
  assert.equal(fileRefPrefixForEntry(STEP_ENTRY), "");
});

test("canonical copy text keeps a file prefix instead of dropping the line", () => {
  assert.equal(canonicalCadRefCopyText(`assy.step#${ROOT}/${F4} plane area=35`), `assy.step#${ROOT}/${F4}`);
  assert.equal(canonicalCadRefCopyText(`#${ROOT}/${F4} plane area=35`), `#${ROOT}/${F4}`);
});

test("withFileRefPrefix is idempotent, which is what lets it run at one funnel", () => {
  // Copy text arrives at the funnel from several builders: some already carry a prefix (parts
  // built from the entry), some do not (tree-node selections). Applying this once at
  // the end is only safe because a second application is a no-op.
  assert.equal(withFileRefPrefix(`#${BRACKET}`, "plate.stl"), `plate.stl#${BRACKET}`);
  assert.equal(withFileRefPrefix(`plate.stl#${BRACKET}`, "plate.stl"), `plate.stl#${BRACKET}`);
  assert.equal(withFileRefPrefix(`other.stl#${BRACKET}`, "plate.stl"), `other.stl#${BRACKET}`);
  assert.equal(withFileRefPrefix("#", "plate.stl"), "plate.stl#");
  // No prefix available, or nothing ref-like: leave it exactly as it was.
  assert.equal(withFileRefPrefix(`#${BRACKET}`, ""), `#${BRACKET}`);
  assert.equal(withFileRefPrefix("plain text", "plate.stl"), "plain text");
  assert.equal(withFileRefPrefix("", "plate.stl"), "");
});

test("every copy path shapes its text the one way: canonical refs, each carrying the file prefix", () => {
  // The Copy Reference button, a menu's Copy Reference and a double-click all copy through here,
  // so a tree row's ref is prefixed exactly as the button's is.
  assert.deepEqual(copyTextLines([`#${ROOT}/${F4} plane area=35`, "", `#${BRACKET}`], "planetary.step"),
    [`planetary.step#${ROOT}/${F4}`, `planetary.step#${BRACKET}`]);
  assert.deepEqual(copyTextLines(`#${ROOT}/${F4}\n#${BRACKET}`, "planetary.step"), [`planetary.step#${ROOT}/${F4}`, `planetary.step#${BRACKET}`],
    "a menu's newline-joined copy text reads the same as a list of lines");
  assert.deepEqual(copyTextLines([`planetary.step#${ROOT}`], "planetary.step"), [`planetary.step#${ROOT}`], "an already-prefixed line passes through");
  assert.deepEqual(copyTextLines([`#${ROOT}`], ""), [`#${ROOT}`], "no prefix, the bare ref");
  assert.deepEqual(copyTextLines(["plain text"], "planetary.step"), [], "text that is not a ref is not copied");
  assert.deepEqual(copyTextLines(undefined, "planetary.step"), []);
});
