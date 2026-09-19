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
  assert.deepEqual(defaultOpenFileSheetSectionIds("step", { hasFileStatus: true }), ["status", "tree"]);
  // Geometry is the default-open section; Display lives in the toolbar.
  assert.deepEqual(
    defaultOpenFileSheetSectionIds("step", { hasStepPosePanel: true, hasStepAnimationPanel: true }),
    ["tree"]
  );
  assert.deepEqual(defaultOpenFileSheetSectionIds("mesh"), ["measurements"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("mesh", {
    hasEmbeddedGlbAnimationPanel: true,
    measurementAvailable: false
  }), ["animation"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("srdf"), ["joints"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("srdf", { motionEnabled: true }), ["motion", "joints"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("sdf"), ["sdf", "joints"]);
});

test("a robot's sheet does not advertise a Tree tab it cannot render", () => {
  // Robot links ARE selectable parts in the viewport as of R1, but the Tree PANEL still
  // lives inside StepFileSheet. Listing "tree" here without a section to render would put
  // an id in the rendered list that no sheet answers. See R1b.
  assert.deepEqual(renderedFileSheetSectionIds("urdf"), ["joints", "display"]);
  assert.deepEqual(renderedFileSheetSectionIds("sdf"), ["sdf", "joints", "display"]);
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
    // Pose sits directly after Model: it is the one tab in this strip that MOVES
    // the geometry, so it takes the position nearest the default rather than trailing
    // the readouts. Animation follows it.
    "pose",
    "animation"
  ]);
  // The two systems are gated independently: a model may declare mates without
  // shipping clips, ship clips without declaring mates, or do neither.
  assert.deepEqual(renderedFileSheetSectionIds("step", { hasStepPosePanel: true }), [
    "tree",
    "pose"
  ]);
  assert.deepEqual(renderedFileSheetSectionIds("step", { hasStepAnimationPanel: true }), [
    "tree",
    "animation"
  ]);
  assert.deepEqual(renderedFileSheetSectionIds("step"), [
    "tree",
  ]);
  assert.deepEqual(renderedFileSheetSectionIds("srdf"), ["joints", "display"]);
  assert.deepEqual(renderedFileSheetSectionIds("mesh"), ["measurements", "display"]);
  assert.deepEqual(renderedFileSheetSectionIds("mesh", {
    hasEmbeddedGlbAnimationPanel: true,
    measurementAvailable: false
  }), ["animation", "display"]);
});

test("named robot objects add Components after Joints, and no Reference tab", () => {
  // Joints MOVES the robot and is what a URDF is opened for, so it leads and the
  // sheet lands on it. Components is the inventory of named objects inside the
  // linked meshes, and it carries the reference for whatever is selected at its
  // own foot — a Reference tab would stand empty until something was picked.
  assert.deepEqual(
    renderedFileSheetSectionIds("urdf", { hasRobotComponents: true }),
    ["joints", "components", "display"]
  );
  assert.deepEqual(
    renderedFileSheetSectionIds("srdf", { hasRobotComponents: true, motionEnabled: true }),
    ["motion", "joints", "components", "display"]
  );
  assert.deepEqual(
    renderedFileSheetSectionIds("sdf", { hasRobotComponents: true }),
    ["sdf", "joints", "components", "display"]
  );

  // Without named objects — an STL-only robot, or meshes whose objects are all
  // unnamed — neither tab is advertised, and the strip is exactly what main shows.
  assert.deepEqual(renderedFileSheetSectionIds("urdf", { hasRobotComponents: false }), ["joints", "display"]);
  assert.deepEqual(renderedFileSheetSectionIds("srdf"), ["joints", "display"]);
  assert.deepEqual(renderedFileSheetSectionIds("sdf"), ["sdf", "joints", "display"]);

  // Components is an Inspect-only inventory: Render mode still opens Studio alone.
  assert.deepEqual(
    renderedFileSheetSectionIds("urdf", { renderMode: true, hasRobotComponents: true }),
    ["render"]
  );
  // The default open set is unchanged — the tab layout activates Components as the
  // top pane's leftmost tab, so it is not listed here.
  assert.deepEqual(defaultOpenFileSheetSectionIds("urdf", { hasRobotComponents: true }), ["joints"]);
});

test("Render mode orders Studio, Kinematics and Animation when authored", () => {
  assert.deepEqual(renderedFileSheetSectionIds("step", {
    renderMode: true,
    hasStepPosePanel: true,
    hasStepAnimationPanel: true
  }), ["render", "pose", "animation"]);
  assert.deepEqual(renderedFileSheetSectionIds("step", { renderMode: true }), ["render"]);
  assert.deepEqual(renderedFileSheetSectionIds("mesh", { renderMode: true }), ["render"]);
  assert.deepEqual(renderedFileSheetSectionIds("mesh", {
    renderMode: true,
    hasEmbeddedGlbAnimationPanel: true
  }), ["render", "animation"]);
  assert.deepEqual(renderedFileSheetSectionIds("dxf", { renderMode: true }), ["render"]);
  assert.deepEqual(renderedFileSheetSectionIds("sdf", { renderMode: true }), ["render"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("step", {
    renderMode: true,
    hasStepAnimationPanel: true
  }), ["render"]);
});

test("viewer-origin selection reveals do not open the file sheet on mobile", () => {
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: true, source: "viewer" }), true);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false, source: "viewer" }), false);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false, source: "tree" }), true);
});
