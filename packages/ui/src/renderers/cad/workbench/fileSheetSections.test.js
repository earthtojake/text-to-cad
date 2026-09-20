import assert from "node:assert/strict";
import test from "node:test";
import { defaultOpenFileSheetSectionIds, renderedFileSheetSectionIds, normalizeFileSheetOpenSectionIds, resolveActiveFileSheetSectionId, shouldOpenFileSheetForSelectionReveal } from "./fileSheetSections.js";

test("STEP shares Model, optional Motion, and View across both viewing modes", () => {
  for (const renderMode of [false, true]) {
    assert.deepEqual(renderedFileSheetSectionIds("step", { renderMode }), ["tree", "view"]);
    for (const options of [{ hasStepPosePanel: true }, { hasStepAnimationPanel: true }, { hasStepPosePanel: true, hasStepAnimationPanel: true }]) {
      assert.deepEqual(renderedFileSheetSectionIds("step", { ...options, renderMode }), ["tree", "motion", "view"]);
      assert.deepEqual(defaultOpenFileSheetSectionIds("step", { ...options, renderMode }), ["tree"]);
    }
  }
});

test("format-specific tabs remain available in both viewing modes", () => {
  for (const renderMode of [false, true]) {
    assert.deepEqual(renderedFileSheetSectionIds("dxf", { renderMode, hasDxfBendsPanel: true, hasDxfLayersPanel: true }), ["material", "bends", "dxfLayers", "view"]);
    // Components is the robot's link tree: always there, second after Motion, whatever the meshes name.
    assert.deepEqual(renderedFileSheetSectionIds("urdf", { renderMode }), ["motion", "components", "view"]);
    assert.deepEqual(renderedFileSheetSectionIds("srdf", { renderMode }), ["motion", "components", "view"]);
    assert.deepEqual(renderedFileSheetSectionIds("sdf", { renderMode }), ["sdf", "motion", "components", "view"]);
    assert.deepEqual(renderedFileSheetSectionIds("srdf", { renderMode, showJoints: false }), ["components", "view"]);
    // A mesh has only View: measurements are the Measure tool's panel, a GLB clip the Animate tool's bar.
    assert.deepEqual(renderedFileSheetSectionIds("mesh", { renderMode }), ["view"]);
    assert.deepEqual(renderedFileSheetSectionIds("mesh", { renderMode, hasEmbeddedGlbAnimationPanel: true }), ["view"]);
  }
});

test("defaults retain useful format-specific selections", () => {
  assert.deepEqual(defaultOpenFileSheetSectionIds("dxf"), []);
  assert.deepEqual(defaultOpenFileSheetSectionIds("step", { hasFileStatus: true }), ["status", "tree"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("sdf"), ["sdf", "motion"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("srdf"), ["motion"]);
  // Motion stays the tab a robot lands on; Components is never the default.
  assert.deepEqual(defaultOpenFileSheetSectionIds("urdf"), ["motion"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("mesh", { hasEmbeddedGlbAnimationPanel: true }), []);
  assert.deepEqual(defaultOpenFileSheetSectionIds("mesh"), []);
});

test("legacy open selections migrate without losing the most recent tab", () => {
  assert.deepEqual(normalizeFileSheetOpenSectionIds(["tree", "pose", "display", "animation"], ["tree", "motion", "view"]), ["motion"]);
  assert.deepEqual(normalizeFileSheetOpenSectionIds(["joints", "render", "materials"], ["motion", "view"]), ["view"]);
  assert.deepEqual(normalizeFileSheetOpenSectionIds(null, ["tree"]), []);
});

test("selection reveals keep the host's existing behavior", () => {
  assert.equal(shouldOpenFileSheetForSelectionReveal(), true);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false }), false);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false, source: "tree" }), true);
});

test("a single active tab restores legacy split selections without rearranging sections", () => {
  const tabs = ["tree", "motion", "view"];
  assert.equal(resolveActiveFileSheetSectionId(["tree", "pose", "display", "animation"], tabs), "motion");
  assert.equal(resolveActiveFileSheetSectionId(["tree", "render"], tabs), "view");
  assert.equal(resolveActiveFileSheetSectionId(["retired", "motion"], ["tree", "view"]), "tree");
  assert.equal(resolveActiveFileSheetSectionId([], ["material", "bends", "dxfLayers", "view"]), "material");
  assert.equal(resolveActiveFileSheetSectionId(null, []), "");
  assert.deepEqual(tabs, ["tree", "motion", "view"]);
});
