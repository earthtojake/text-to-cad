import assert from "node:assert/strict";
import test from "node:test";
import { activateFileSheetTab, clampSplitRatio, defaultFileSheetTabArrangement, kindSupportsSplit, moveFileSheetTab, normalizeFileSheetTabArrangement, readFileSheetTabLayoutStore, resolveFileSheetTabPanes, setFileSheetTabRatio, setFileSheetTabSplit, writeFileSheetTabLayoutStore, FILE_SHEET_TAB_LAYOUT_STORAGE_KEY, MAX_FILE_SHEET_SPLIT_RATIO, MIN_FILE_SHEET_SPLIT_RATIO } from "./fileSheetTabLayout.js";
const sections = ["tree", "motion", "view"];

test("the standard STEP tabs share one full-height strip", () => {
  for (const ids of [["tree", "view"], sections]) {
    const layout = defaultFileSheetTabArrangement("step", ids);
    assert.deepEqual(layout, { split: false, top: ids, bottom: [], ratio: .5 });
    assert.equal(resolveFileSheetTabPanes(layout, "step", ["motion"]).panes[0].activeId, ids.includes("motion") ? "motion" : "tree");
  }
});

test("robot defaults and format-specific splits remain intact", () => {
  for (const kind of ["urdf", "srdf", "sdf"]) {
    assert.equal(kindSupportsSplit(kind), true);
    const ids = ["motion", "components", "view"];
    assert.equal(defaultFileSheetTabArrangement(kind, ids).split, false);
  }
  assert.equal(kindSupportsSplit("mesh"), false);
  assert.deepEqual(defaultFileSheetTabArrangement("dxf", ["material", "bends", "dxfLayers", "view"]), { split: true, top: ["material"], bottom: ["bends", "dxfLayers", "view"], ratio: .5 });
});

test("legacy tabs merge in place and keep unrelated custom splits", () => {
  const stored = { split: true, top: ["animation", "tree"], bottom: ["pose", "metadata", "display", "render"], ratio: .65 };
  const actual = normalizeFileSheetTabArrangement(stored, "step", [...sections, "metadata"]);
  assert.deepEqual(actual, { split: true, top: ["motion", "tree"], bottom: ["metadata", "view"], ratio: .65 });
  const resolved = resolveFileSheetTabPanes(actual, "step", ["pose", "metadata", "render"]);
  assert.deepEqual(resolved.panes.map(p => p.activeId), ["motion", "view"]);
});

test("most recently selected legacy alias stays active after consolidation", () => {
  const layout = defaultFileSheetTabArrangement("step", sections);
  assert.equal(resolveFileSheetTabPanes(layout, "step", ["pose", "display", "animation"]).panes[0].activeId, "motion");
  assert.deepEqual(activateFileSheetTab(["pose", "display"], layout, "step", "top", "motion"), ["motion"]);
});

test("new conditional tabs join render order without moving saved tabs", () => {
  const layout = normalizeFileSheetTabArrangement({ split: false, top: ["tree", "view"], bottom: [], ratio: .5 }, "step", sections);
  assert.deepEqual(layout.top, sections);
  const custom = normalizeFileSheetTabArrangement({ split: true, top: ["tree"], bottom: ["view", "motion"] }, "step", sections);
  assert.deepEqual(custom.bottom, ["view", "motion"]);
});

test("missing tabs drop and duplicate pane entries cannot duplicate controls", () => {
  assert.deepEqual(normalizeFileSheetTabArrangement({ split: true, top: ["features", "tree", "view"], bottom: ["display", "metadata"] }, "step", [...sections, "metadata"]), { split: true, top: sections, bottom: ["metadata"], ratio: .5 });
  assert.deepEqual(normalizeFileSheetTabArrangement({ top: ["materials"] }, "step", []), { split: false, top: [], bottom: [], ratio: .5 });
});

test("explicit split and merge preserve all tabs and ratio", () => {
  const initial = { ...defaultFileSheetTabArrangement("step", sections), ratio: .6 };
  const split = setFileSheetTabSplit(initial, "step", true, sections);
  assert.deepEqual(split, { split: true, top: ["tree"], bottom: ["motion", "view"], ratio: .6 });
  assert.deepEqual(setFileSheetTabSplit(split, "step", false, sections), initial);
  assert.equal(setFileSheetTabSplit(initial, "mesh", true, sections).split, false);
});

test("moving across panes collapses an emptied pane without dropping tabs", () => {
  const initial = { split: true, top: ["tree"], bottom: ["motion", "view"], ratio: .5 };
  assert.deepEqual(moveFileSheetTab(initial, "step", "tree", "bottom", 0), { split: false, top: sections, bottom: [], ratio: .5 });
});

test("dragging lands in the indicated slot for both directions and the end", () => {
  const initial = { split: false, top: sections, bottom: [], ratio: .5 };
  for (const id of sections) for (let slot = 0; slot <= sections.length; slot++) {
    const expected = sections.filter(value => value !== id);
    expected.splice(slot > sections.indexOf(id) ? slot - 1 : slot, 0, id);
    assert.deepEqual(moveFileSheetTab(initial, "step", id, "top", slot).top, expected);
  }
});

test("split ratios clamp to the supported range", () => {
  assert.equal(clampSplitRatio(.05), MIN_FILE_SHEET_SPLIT_RATIO);
  assert.equal(clampSplitRatio(.95), MAX_FILE_SHEET_SPLIT_RATIO);
  assert.equal(clampSplitRatio("bad"), .5);
  assert.equal(setFileSheetTabRatio({}, .7).ratio, .7);
});

test("v5/v6 stores migrate all kinds without resetting custom arrangements", () => {
  for (const version of [5, 6]) {
    const data = { [`cad-viewer:file-sheet-tab-layout:v${version}`]: JSON.stringify({
      step: { split: true, top: ["tree", "animation"], bottom: ["pose", "metadata", "render"], ratio: .7 },
      urdf: { split: false, top: ["joints", "components", "display"], bottom: [], ratio: .4 },
      dxf: { split: true, top: ["material"], bottom: ["bends", "dxfLayers"], ratio: .6 },
    }) };
    const storage = { getItem: key => data[key] ?? null, setItem: (key, value) => { data[key] = value; } };
    const store = readFileSheetTabLayoutStore(storage);
    assert.deepEqual(store.step, { split: true, top: ["tree", "motion"], bottom: ["metadata", "view"], ratio: .7 });
    assert.deepEqual(store.urdf.top, ["motion", "components", "view"]);
    assert.deepEqual(store.dxf.bottom, ["bends", "dxfLayers"]);
    writeFileSheetTabLayoutStore(storage, store);
    assert.ok(data[FILE_SHEET_TAB_LAYOUT_STORAGE_KEY]);
    assert.deepEqual(readFileSheetTabLayoutStore(storage), store);
  }
});

test("consolidation collapses a split whose second pane was only a duplicate", () => {
  const storage = { getItem: key => key.endsWith(":v6") ? JSON.stringify({ step: { split: true, top: ["tree", "pose"], bottom: ["animation"], ratio: .4 } }) : null };
  assert.deepEqual(readFileSheetTabLayoutStore(storage).step, { split: false, top: ["tree", "motion"], bottom: [], ratio: .4 });
});

test("missing or malformed stores fall back without errors", () => {
  assert.deepEqual(readFileSheetTabLayoutStore(null), {});
  assert.deepEqual(readFileSheetTabLayoutStore({ getItem: () => "{bad json" }), {});
});
