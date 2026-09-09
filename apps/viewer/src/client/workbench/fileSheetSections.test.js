import assert from "node:assert/strict";
import test from "node:test";

import {
  defaultOpenFileSheetSectionIds,
  renderedFileSheetSectionIds,
  shouldOpenFileSheetForSelectionReveal
} from "./fileSheetSections.js";

test("file sheet section defaults match current sheet behavior", () => {
  // A DXF opens no tab by default: Material is the pane's leftmost tab and the tab
  // layout resolves it as active, so this list stays empty.
  assert.deepEqual(defaultOpenFileSheetSectionIds("dxf"), []);
  assert.deepEqual(defaultOpenFileSheetSectionIds("step"), ["tree"]);
  // In the tabbed layout the Tree is the only default-open section; Display is
  // the default-active bottom tab, resolved by the tab layout, not this list.
  assert.deepEqual(
    defaultOpenFileSheetSectionIds("step", { hasStepPosePanel: true, hasStepAnimationPanel: true }),
    ["tree"]
  );
  assert.deepEqual(defaultOpenFileSheetSectionIds("mesh"), ["measurements"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("srdf"), ["joints"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("srdf", { motionEnabled: true }), ["motion", "joints"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("sdf"), ["sdf", "joints"]);
});

test("a robot's sheet does not advertise a Tree tab it cannot render", () => {
  // Robot links ARE selectable parts in the viewport as of R1, but the Tree PANEL still
  // lives inside StepFileSheet. Listing "tree" here without a section to render would put
  // an id in the rendered list that no sheet answers. See R1b.
  assert.deepEqual(renderedFileSheetSectionIds("urdf"), ["joints"]);
  assert.deepEqual(renderedFileSheetSectionIds("sdf"), ["sdf", "joints"]);
});

test("rendered file sheet sections include closed-by-default sections", () => {
  // A drawing has controls of its own: thickness and bends are render-time parameters on the
  // cached prism, so they steer the viewport without touching the package.
  // One stacked surface: Material over Bends, no tab switch between them.
  assert.deepEqual(renderedFileSheetSectionIds("dxf"), ["material"]);
  assert.deepEqual(
    renderedFileSheetSectionIds("dxf", { hasDxfBendsPanel: true, hasDxfLayersPanel: true }),
    ["material", "bends", "dxfLayers"]
  );
  assert.deepEqual(renderedFileSheetSectionIds("step", {
    hasStepPosePanel: true,
    hasStepAnimationPanel: true
  }), [
    "tree",
    "reference",
    // Pose sits directly after Reference: it is the one tab in this strip that MOVES
    // the geometry, so it takes the position nearest the default rather than trailing
    // the readouts. Animation follows it.
    "pose",
    "animation",
    "measurements",
    "display"
  ]);
  // The two systems are gated independently: a model may declare mates without
  // shipping clips, ship clips without declaring mates, or do neither.
  assert.deepEqual(renderedFileSheetSectionIds("step", { hasStepPosePanel: true }), [
    "tree",
    "reference",
    "pose",
    "measurements",
    "display"
  ]);
  assert.deepEqual(renderedFileSheetSectionIds("step", { hasStepAnimationPanel: true }), [
    "tree",
    "reference",
    "animation",
    "measurements",
    "display"
  ]);
  assert.deepEqual(renderedFileSheetSectionIds("step"), [
    "tree",
    "reference",
    "measurements",
    "display"
  ]);
  assert.deepEqual(renderedFileSheetSectionIds("srdf"), ["joints"]);
  assert.deepEqual(renderedFileSheetSectionIds("mesh"), ["measurements"]);
});

test("viewer-origin selection reveals do not open the file sheet on mobile", () => {
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: true, source: "viewer" }), true);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false, source: "viewer" }), false);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false, source: "tree" }), true);
});
