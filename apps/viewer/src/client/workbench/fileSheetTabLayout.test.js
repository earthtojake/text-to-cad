import assert from "node:assert/strict";
import test from "node:test";

import {
  activateFileSheetTab,
  clampSplitRatio,
  defaultFileSheetTabArrangement,
  defaultRenderFileSheetTabArrangement,
  kindSupportsSplit,
  moveFileSheetTab,
  normalizeFileSheetTabArrangement,
  readFileSheetTabLayoutStore,
  renderFileSheetTabArrangementForScope,
  resolveFileSheetTabPanes,
  setFileSheetTabRatio,
  setFileSheetTabSplit,
  writeFileSheetTabLayoutStore,
  FILE_SHEET_TAB_PANES,
  MAX_FILE_SHEET_SPLIT_RATIO,
  MIN_FILE_SHEET_SPLIT_RATIO
} from "./fileSheetTabLayout.js";

const STEP_SECTIONS = ["tree", "pose", "display", "metadata"];

test("step, dxf and the robot kinds support the split; a plain mesh does not", () => {
  assert.equal(kindSupportsSplit("step"), true);
  assert.equal(kindSupportsSplit("dxf"), true);
  // Robots gained a split when Components arrived: the inventory sits above the
  // Reference/Joints readouts, the same shape as STEP's Tree.
  assert.equal(kindSupportsSplit("urdf"), true);
  assert.equal(kindSupportsSplit("srdf"), true);
  assert.equal(kindSupportsSplit("sdf"), true);
  // A plain mesh has one readout strip and nothing to promote above it.
  assert.equal(kindSupportsSplit("mesh"), false);
});

test("a robot opens as one strip on Joints, Components beside it", () => {
  // No robot tab claims the top pane, so the default is one strip and the first
  // tab wins: Joints, the reason the file was opened. Components is one click
  // away, and selecting a component jumps to it (CadWorkspace.selectRobotComponent).
  for (const kind of ["urdf", "srdf", "sdf"]) {
    const arrangement = defaultFileSheetTabArrangement(kind, ["joints", "components", "display"]);
    assert.equal(arrangement.split, false, `${kind} should not split by default`);
    const resolved = resolveFileSheetTabPanes(arrangement, kind, []);
    assert.equal(resolved.split, false, `${kind} should resolve to one pane`);
    assert.deepEqual(resolved.panes[0].tabs, ["joints", "components", "display"], `${kind} tabs`);
    assert.equal(resolved.panes[0].activeId, "joints", `${kind} lands on Joints`);
  }
});

test("Components joins a stored robot split at its render-order position", () => {
  // The user dragged Joints up on a robot with no named objects; the next robot has
  // some. Components belongs to no pane by default, so it lands in the bottom one —
  // before Display, which renders after it, rather than appended past it.
  const stored = { split: true, top: ["joints"], bottom: ["display"] };
  const normalized = normalizeFileSheetTabArrangement(stored, "urdf", ["joints", "components", "display"]);
  assert.deepEqual(normalized.top, ["joints"]);
  assert.deepEqual(normalized.bottom, ["components", "display"]);
  assert.equal(normalized.split, true);
});

test("a robot with no named components opens as one strip, and can still be split", () => {
  // Making robots splittable must not hand every existing robot a split it never
  // had: with no Components tab there is no designated top-pane tab, so the
  // default stays the single strip these files have always shown.
  for (const [kind, sections] of [
    ["urdf", ["joints", "display"]],
    ["srdf", ["motion", "joints", "display"]],
    ["sdf", ["sdf", "joints", "display"]]
  ]) {
    const arrangement = defaultFileSheetTabArrangement(kind, sections);
    assert.equal(arrangement.split, false, `${kind} should not split by default`);
    assert.deepEqual(arrangement.top, sections, `${kind} single strip`);
    assert.deepEqual(arrangement.bottom, []);

    // The split toggle is still honoured — it just is not the default.
    const split = setFileSheetTabSplit(arrangement, kind, true, sections);
    assert.equal(split.split, true, `${kind} split toggle`);
    assert.deepEqual(split.top, sections.slice(0, 1));
    assert.deepEqual(split.bottom, sections.slice(1));
  }
});

test("default step arrangement puts the tree on top and everything else on the bottom", () => {
  const arrangement = defaultFileSheetTabArrangement("step", STEP_SECTIONS);
  assert.equal(arrangement.split, true);
  assert.deepEqual(arrangement.top, ["tree"]);
  assert.deepEqual(arrangement.bottom, ["pose", "display", "metadata"]);
  assert.equal(arrangement.ratio, 0.5);
});

test("Render starts Studio-first in one row and supports transient tab interaction", () => {
  const entered = defaultRenderFileSheetTabArrangement(["render", "animation"]);
  let resolved = resolveFileSheetTabPanes(entered, "step", []);
  assert.equal(resolved.split, false);
  assert.deepEqual(resolved.panes[0].tabs, ["render", "animation"]);
  assert.equal(resolved.panes[0].activeId, "render");

  const animationOpen = activateFileSheetTab([], entered, "step", FILE_SHEET_TAB_PANES.TOP, "animation");
  resolved = resolveFileSheetTabPanes(entered, "step", animationOpen);
  assert.equal(resolved.panes[0].activeId, "animation");

  const splitVisit = moveFileSheetTab(
    entered,
    "step",
    "animation",
    FILE_SHEET_TAB_PANES.BOTTOM,
    0
  );
  assert.equal(splitVisit.split, true);
  assert.deepEqual(splitVisit.top, ["render"]);
  assert.deepEqual(splitVisit.bottom, ["animation"]);

  // Re-entering Render derives a fresh transient arrangement rather than
  // carrying the prior visit's split or changing CAD's durable layout.
  assert.deepEqual(
    defaultRenderFileSheetTabArrangement(["render", "animation"]),
    entered
  );
});

test("deriving a Render arrangement leaves the saved CAD arrangement unchanged", () => {
  const cad = {
    split: true,
    top: ["tree", "display"],
    bottom: ["reference", "measurements"],
    ratio: 0.65
  };
  const before = structuredClone(cad);

  defaultRenderFileSheetTabArrangement(["render", "animation"]);

  assert.deepEqual(cad, before);
  assert.deepEqual(
    normalizeFileSheetTabArrangement(cad, "step", ["tree", "reference", "measurements", "display"]),
    cad
  );
});

test("switching models within Render starts the next model in one Studio-first row", () => {
  const splitForA = {
    scope: "assembly-a.step",
    arrangement: {
      split: true,
      top: ["render"],
      bottom: ["animation"],
      ratio: 0.7
    }
  };

  assert.equal(
    renderFileSheetTabArrangementForScope(
      splitForA,
      "assembly-a.step",
      "step",
      ["render", "animation"]
    ).split,
    true
  );
  assert.deepEqual(
    renderFileSheetTabArrangementForScope(
      splitForA,
      "assembly-b.step",
      "step",
      ["render", "animation"]
    ),
    defaultRenderFileSheetTabArrangement(["render", "animation"])
  );
});

test("pose sits between reference and display in the bottom pane", () => {
  const arrangement = defaultFileSheetTabArrangement(
    "step",
    ["tree", "reference", "pose", "display"]
  );
  assert.deepEqual(arrangement.top, ["tree"]);
  assert.deepEqual(arrangement.bottom, ["reference", "pose", "display"]);
});

test("pose and animation are two bottom-pane tabs, in render order", () => {
  // The split's two systems land side by side under the tree; neither is
  // promoted to the top pane, and Animation follows Pose.
  const arrangement = defaultFileSheetTabArrangement(
    "step",
    ["tree", "reference", "pose", "animation", "measurements", "display"]
  );
  assert.deepEqual(arrangement.top, ["tree"]);
  assert.deepEqual(arrangement.bottom, ["reference", "pose", "animation", "measurements", "display"]);
  // A model with clips but no mates renders Animation alone — it must not
  // inherit Pose's slot rules by being appended somewhere else.
  const clipsOnly = defaultFileSheetTabArrangement(
    "step",
    ["tree", "reference", "animation", "measurements", "display"]
  );
  assert.deepEqual(clipsOnly.bottom, ["reference", "animation", "measurements", "display"]);
});

test("a stored strip picks up animation at its render-order slot", () => {
  // Stored from a model with mates only; the next one also ships clips.
  const stored = { split: true, top: ["tree"], bottom: ["reference", "pose", "display"] };
  const normalized = normalizeFileSheetTabArrangement(
    stored,
    "step",
    ["tree", "reference", "pose", "animation", "display"]
  );
  assert.deepEqual(normalized.bottom, ["reference", "pose", "animation", "display"]);
});

test("default non-split-kind arrangement is a single strip", () => {
  const arrangement = defaultFileSheetTabArrangement("mesh", ["measurements", "display", "metadata"]);
  assert.equal(arrangement.split, false);
  assert.deepEqual(arrangement.top, ["measurements", "display", "metadata"]);
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
  const stored = { split: true, top: ["tree"], bottom: ["display"], ratio: 0.6 };
  const normalized = normalizeFileSheetTabArrangement(stored, "step", STEP_SECTIONS);
  // pose + metadata are newly rendered; both default to the bottom pane and
  // land at their render-order position (pose before display, metadata last).
  assert.deepEqual(normalized.top, ["tree"]);
  assert.deepEqual(normalized.bottom, ["pose", "display", "metadata"]);
  assert.equal(normalized.ratio, 0.6);
});

test("pose slots into render order when it first appears", () => {
  // Stored from a plain STEP file; the next one declares mates, so pose renders.
  const stored = { split: true, top: ["tree"], bottom: ["reference", "display"] };
  const normalized = normalizeFileSheetTabArrangement(
    stored,
    "step",
    ["tree", "reference", "pose", "display"]
  );
  // Pose sits between reference and display — not appended after it.
  assert.deepEqual(normalized.bottom, ["reference", "pose", "display"]);
  // Leftmost is the pane fallback, so reference is what you land on.
  assert.equal(resolveFileSheetTabPanes(normalized, "step", []).panes[1].activeId, "reference");
});

test("a tab the user dragged keeps its stored position", () => {
  const stored = { split: true, top: ["tree"], bottom: ["reference", "pose", "display"] };
  const normalized = normalizeFileSheetTabArrangement(
    stored,
    "step",
    ["tree", "reference", "pose", "display"]
  );
  assert.deepEqual(normalized.bottom, ["reference", "pose", "display"]);
});

test("normalize de-dupes a tab present in both panes (top wins)", () => {
  const stored = { split: true, top: ["tree", "display"], bottom: ["display", "metadata"] };
  const normalized = normalizeFileSheetTabArrangement(stored, "step", ["tree", "display", "metadata"]);
  assert.deepEqual(normalized.top, ["tree", "display"]);
  assert.deepEqual(normalized.bottom, ["metadata"]);
});

test("normalize re-derives the default split when a requested split has an empty pane", () => {
  const stored = { split: true, top: ["tree", "pose", "display", "metadata"], bottom: [] };
  const normalized = normalizeFileSheetTabArrangement(stored, "step", STEP_SECTIONS);
  assert.equal(normalized.split, true);
  assert.deepEqual(normalized.top, ["tree"]);
  assert.deepEqual(normalized.bottom, ["pose", "display", "metadata"]);
});

test("normalize forces a single strip for non-split kinds", () => {
  const stored = { split: true, top: ["measurements"], bottom: ["display"] };
  const normalized = normalizeFileSheetTabArrangement(stored, "mesh", ["measurements", "display", "metadata"]);
  assert.equal(normalized.split, false);
  assert.deepEqual(normalized.top, ["measurements", "display", "metadata"]);
  assert.deepEqual(normalized.bottom, []);
});

test("moving a tab across panes updates assignment", () => {
  const arrangement = defaultFileSheetTabArrangement("step", STEP_SECTIONS);
  const next = moveFileSheetTab(arrangement, "step", "display", FILE_SHEET_TAB_PANES.TOP, 1);
  assert.deepEqual(next.top, ["tree", "display"]);
  assert.deepEqual(next.bottom, ["pose", "metadata"]);
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
  assert.deepEqual(merged.top, ["tree", "pose", "display", "metadata"]);

  const reSplit = setFileSheetTabSplit(merged, "step", true, STEP_SECTIONS);
  assert.equal(reSplit.split, true);
  assert.deepEqual(reSplit.top, ["tree"]);
  assert.deepEqual(reSplit.bottom, ["pose", "display", "metadata"]);
});

test("split ratio is clamped", () => {
  assert.equal(clampSplitRatio(0.05), MIN_FILE_SHEET_SPLIT_RATIO);
  assert.equal(clampSplitRatio(0.95), MAX_FILE_SHEET_SPLIT_RATIO);
  assert.equal(clampSplitRatio("nope"), 0.5);
  assert.equal(setFileSheetTabRatio({ top: [], bottom: [] }, 0.7).ratio, 0.7);
});

test("resolve panes: each pane defaults to its leftmost tab", () => {
  const sections = ["tree", "reference", "pose", "display", "metadata"];
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
  const arrangement = defaultFileSheetTabArrangement("mesh", ["animation", "measurements", "display"]);
  const resolved = resolveFileSheetTabPanes(arrangement, "mesh", []);
  assert.equal(resolved.split, false);
  assert.equal(resolved.panes.length, 1);
  assert.equal(resolved.panes[0].activeId, "animation");
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

test("measurements defaults to the bottom pane, after reference", () => {
  const arrangement = defaultFileSheetTabArrangement("step", [
    "tree",
    "reference",
    "measurements",
    "display"
  ]);
  assert.equal(arrangement.split, true);
  assert.deepEqual(arrangement.top, ["tree"]);
  assert.deepEqual(arrangement.bottom, ["reference", "measurements", "display"]);
});

test("activating measurements makes it the bottom pane's live tab", () => {
  const arrangement = defaultFileSheetTabArrangement("step", ["tree", "reference", "measurements"]);
  const opened = activateFileSheetTab(["tree", "reference"], arrangement, "step", "bottom", "measurements");
  const resolved = resolveFileSheetTabPanes(arrangement, "step", opened);
  const top = resolved.panes.find((pane) => pane.pane === "top");
  const bottom = resolved.panes.find((pane) => pane.pane === "bottom");
  assert.equal(bottom.activeId, "measurements");
  // Activating it must not disturb whatever the other pane was showing.
  assert.equal(top.activeId, "tree");
});

test("a drop lands where the indicator promised, including the last slot", () => {
  // The drop index counts slots in the strip AS DISPLAYED, which still shows the tab being
  // dragged. moveFileSheetTab removes it before splicing, so every slot right of where it
  // started has shifted left by one. Reading the index literally moved a rightward drag one
  // slot too far, and the end-of-strip clamp hid it at the only position with nowhere to
  // overshoot to -- which is why it surfaced as "drag to the last spot, land second-last".
  const tabs = ["tree", "reference", "pose", "measurements", "display"];
  const arrangement = { split: false, top: [...tabs], bottom: [], ratio: 0.5 };

  for (const id of tabs) {
    for (let slot = 0; slot <= tabs.length; slot += 1) {
      const want = tabs.filter((value) => value !== id);
      const from = tabs.indexOf(id);
      want.splice(slot > from ? slot - 1 : slot, 0, id);
      const got = moveFileSheetTab(arrangement, "step", id, FILE_SHEET_TAB_PANES.TOP, slot).top;
      assert.deepEqual(got, want, `dragging ${id} to slot ${slot}`);
    }
  }
});

test("dropping any tab past the last slot puts it last", () => {
  const tabs = ["tree", "reference", "pose", "measurements", "display"];
  const arrangement = { split: false, top: [...tabs], bottom: [], ratio: 0.5 };
  for (const id of tabs) {
    const top = moveFileSheetTab(arrangement, "step", id, FILE_SHEET_TAB_PANES.TOP, tabs.length).top;
    assert.equal(top[top.length - 1], id, `${id} should land last`);
    assert.equal(top.length, tabs.length, "no tab lost or duplicated");
  }
});
