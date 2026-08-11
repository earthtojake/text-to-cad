import assert from "node:assert/strict";
import test from "node:test";

import {
  activateFileSheetTab,
  clampSplitRatio,
  defaultFileSheetTabArrangement,
  kindSupportsSplit,
  moveFileSheetTab,
  normalizeFileSheetTabArrangement,
  readFileSheetTabLayoutStore,
  resolveFileSheetTabPanes,
  setFileSheetTabRatio,
  setFileSheetTabSplit,
  writeFileSheetTabLayoutStore,
  FILE_SHEET_TAB_PANES,
  MAX_FILE_SHEET_SPLIT_RATIO,
  MIN_FILE_SHEET_SPLIT_RATIO
} from "./fileSheetTabLayout.js";

const STEP_SECTIONS = ["tree", "parameters", "display", "theme", "metadata"];

test("only step supports the split", () => {
  assert.equal(kindSupportsSplit("step"), true);
  assert.equal(kindSupportsSplit("dxf"), true);
  assert.equal(kindSupportsSplit("urdf"), false);
});

test("default step arrangement puts the tree on top and everything else on the bottom", () => {
  const arrangement = defaultFileSheetTabArrangement("step", STEP_SECTIONS);
  assert.equal(arrangement.split, true);
  assert.deepEqual(arrangement.top, ["tree"]);
  assert.deepEqual(arrangement.bottom, ["parameters", "display", "theme", "metadata"]);
  assert.equal(arrangement.ratio, 0.5);
});

test("parameters sits between reference and display in the bottom pane", () => {
  const arrangement = defaultFileSheetTabArrangement(
    "step",
    ["tree", "reference", "parameters", "display"]
  );
  assert.deepEqual(arrangement.top, ["tree"]);
  assert.deepEqual(arrangement.bottom, ["reference", "parameters", "display"]);
});

test("default non-split-kind arrangement is a single strip", () => {
  const arrangement = defaultFileSheetTabArrangement("urdf", ["joints", "display", "metadata"]);
  assert.equal(arrangement.split, false);
  assert.deepEqual(arrangement.top, ["joints", "display", "metadata"]);
  assert.deepEqual(arrangement.bottom, []);
});

test("default dxf arrangement keeps Material on top, conditional tabs below", () => {
  const arrangement = defaultFileSheetTabArrangement("dxf", ["material", "bends", "dxfLayers"]);
  assert.equal(arrangement.split, true);
  assert.deepEqual(arrangement.top, ["material"]);
  assert.deepEqual(arrangement.bottom, ["bends", "dxfLayers"]);
});

test("dxf with only Material collapses to a single strip", () => {
  const arrangement = defaultFileSheetTabArrangement("dxf", ["material"]);
  assert.equal(arrangement.split, false);
  assert.deepEqual(arrangement.top, ["material"]);
});

test("step with only a tree collapses to a single strip", () => {
  const arrangement = defaultFileSheetTabArrangement("step", ["tree"]);
  assert.equal(arrangement.split, false);
  assert.deepEqual(arrangement.top, ["tree"]);
});

test("normalize drops missing tabs and slots new ones into their default pane", () => {
  const stored = { split: true, top: ["tree"], bottom: ["display", "theme"], ratio: 0.6 };
  const normalized = normalizeFileSheetTabArrangement(stored, "step", STEP_SECTIONS);
  // parameters + metadata are newly rendered; both default to the bottom pane and
  // land at their render-order position (parameters before display, metadata last).
  assert.deepEqual(normalized.top, ["tree"]);
  assert.deepEqual(normalized.bottom, ["parameters", "display", "theme", "metadata"]);
  assert.equal(normalized.ratio, 0.6);
});

test("issues and parameters slot into render order when they first appear", () => {
  // Stored from a plain STEP file; the next one has both issues and parameters.
  const stored = { split: true, top: ["tree"], bottom: ["reference", "display"] };
  const normalized = normalizeFileSheetTabArrangement(
    stored,
    "step",
    ["status", "tree", "reference", "parameters", "display"]
  );
  // Issues leads, parameters sits between reference and display — not appended.
  assert.deepEqual(normalized.bottom, ["status", "reference", "parameters", "display"]);
  // Leftmost is the pane fallback, so Issues is what you land on.
  assert.equal(resolveFileSheetTabPanes(normalized, "step", []).panes[1].activeId, "status");
});

test("a tab the user dragged keeps its stored position", () => {
  const stored = { split: true, top: ["tree"], bottom: ["reference", "status", "display"] };
  const normalized = normalizeFileSheetTabArrangement(
    stored,
    "step",
    ["status", "tree", "reference", "display"]
  );
  assert.deepEqual(normalized.bottom, ["reference", "status", "display"]);
});

test("normalize de-dupes a tab present in both panes (top wins)", () => {
  const stored = { split: true, top: ["tree", "display"], bottom: ["display", "metadata"] };
  const normalized = normalizeFileSheetTabArrangement(stored, "step", ["tree", "display", "metadata"]);
  assert.deepEqual(normalized.top, ["tree", "display"]);
  assert.deepEqual(normalized.bottom, ["metadata"]);
});

test("normalize re-derives the default split when a requested split has an empty pane", () => {
  const stored = { split: true, top: ["tree", "parameters", "display", "theme", "metadata"], bottom: [] };
  const normalized = normalizeFileSheetTabArrangement(stored, "step", STEP_SECTIONS);
  assert.equal(normalized.split, true);
  assert.deepEqual(normalized.top, ["tree"]);
  assert.deepEqual(normalized.bottom, ["parameters", "display", "theme", "metadata"]);
});

test("normalize forces a single strip for non-split kinds", () => {
  const stored = { split: true, top: ["joints"], bottom: ["display"] };
  const normalized = normalizeFileSheetTabArrangement(stored, "urdf", ["joints", "display", "metadata"]);
  assert.equal(normalized.split, false);
  assert.deepEqual(normalized.top, ["joints", "display", "metadata"]);
  assert.deepEqual(normalized.bottom, []);
});

test("moving a tab across panes updates assignment", () => {
  const arrangement = defaultFileSheetTabArrangement("step", STEP_SECTIONS);
  const next = moveFileSheetTab(arrangement, "step", "display", FILE_SHEET_TAB_PANES.TOP, 1);
  assert.deepEqual(next.top, ["tree", "display"]);
  assert.deepEqual(next.bottom, ["parameters", "theme", "metadata"]);
  assert.equal(next.split, true);
});

test("moving the last tab out of a pane collapses the split", () => {
  const arrangement = { split: true, top: ["tree"], bottom: ["display", "metadata"], ratio: 0.5 };
  const next = moveFileSheetTab(arrangement, "step", "tree", FILE_SHEET_TAB_PANES.BOTTOM, 0);
  assert.equal(next.split, false);
  assert.deepEqual(next.top, ["tree", "display", "metadata"]);
  assert.deepEqual(next.bottom, []);
});

test("toggling the split off merges panes, on restores the default split", () => {
  const arrangement = defaultFileSheetTabArrangement("step", STEP_SECTIONS);
  const merged = setFileSheetTabSplit(arrangement, "step", false, STEP_SECTIONS);
  assert.equal(merged.split, false);
  assert.deepEqual(merged.top, ["tree", "parameters", "display", "theme", "metadata"]);

  const reSplit = setFileSheetTabSplit(merged, "step", true, STEP_SECTIONS);
  assert.equal(reSplit.split, true);
  assert.deepEqual(reSplit.top, ["tree"]);
  assert.deepEqual(reSplit.bottom, ["parameters", "display", "theme", "metadata"]);
});

test("split ratio is clamped", () => {
  assert.equal(clampSplitRatio(0.05), MIN_FILE_SHEET_SPLIT_RATIO);
  assert.equal(clampSplitRatio(0.95), MAX_FILE_SHEET_SPLIT_RATIO);
  assert.equal(clampSplitRatio("nope"), 0.5);
  assert.equal(setFileSheetTabRatio({ top: [], bottom: [] }, 0.7).ratio, 0.7);
});

test("resolve panes: each pane defaults to its leftmost tab", () => {
  const sections = ["tree", "reference", "parameters", "display", "theme", "metadata"];
  const arrangement = defaultFileSheetTabArrangement("step", sections);
  const resolved = resolveFileSheetTabPanes(arrangement, "step", []);
  assert.equal(resolved.split, true);
  assert.equal(resolved.panes[0].activeId, "tree");
  assert.equal(resolved.panes[1].activeId, "reference");

  // Reorder the bottom pane and the default follows the new leftmost tab, rather
  // than staying pinned to a hardcoded preference.
  const reordered = moveFileSheetTab(arrangement, "step", "display", FILE_SHEET_TAB_PANES.BOTTOM, 0);
  assert.equal(resolveFileSheetTabPanes(reordered, "step", []).panes[1].activeId, "display");
});

test("resolve panes: an open id activates its tab (last in pane wins)", () => {
  const arrangement = defaultFileSheetTabArrangement("step", STEP_SECTIONS);
  const resolved = resolveFileSheetTabPanes(arrangement, "step", ["tree", "metadata"]);
  assert.equal(resolved.panes[1].activeId, "metadata");
});

test("resolve panes: single strip for non-step uses first tab by default", () => {
  const arrangement = defaultFileSheetTabArrangement("urdf", ["motion", "joints", "display"]);
  const resolved = resolveFileSheetTabPanes(arrangement, "urdf", []);
  assert.equal(resolved.split, false);
  assert.equal(resolved.panes.length, 1);
  assert.equal(resolved.panes[0].activeId, "motion");
});

test("activating a tab prunes pane siblings from the open list", () => {
  const arrangement = defaultFileSheetTabArrangement("step", STEP_SECTIONS);
  let open = ["tree", "display"];
  open = activateFileSheetTab(open, arrangement, "step", FILE_SHEET_TAB_PANES.BOTTOM, "metadata");
  // display (a bottom sibling) is dropped; metadata appended.
  assert.deepEqual(open, ["tree", "metadata"]);
  // tree (top pane) is untouched.
  const resolved = resolveFileSheetTabPanes(arrangement, "step", open);
  assert.equal(resolved.panes[0].activeId, "tree");
  assert.equal(resolved.panes[1].activeId, "metadata");
});

test("layout store round-trips through storage", () => {
  const data = {};
  const storage = {
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => { data[key] = value; }
  };
  assert.deepEqual(readFileSheetTabLayoutStore(storage), {});
  writeFileSheetTabLayoutStore(storage, { step: { split: true, top: ["tree"], bottom: ["display"], ratio: 0.4 } });
  const restored = readFileSheetTabLayoutStore(storage);
  assert.deepEqual(restored.step.top, ["tree"]);
  assert.equal(restored.step.ratio, 0.4);
});

test("layout store tolerates missing storage and bad json", () => {
  assert.deepEqual(readFileSheetTabLayoutStore(null), {});
  const storage = { getItem: () => "{not json", setItem: () => {} };
  assert.deepEqual(readFileSheetTabLayoutStore(storage), {});
});
