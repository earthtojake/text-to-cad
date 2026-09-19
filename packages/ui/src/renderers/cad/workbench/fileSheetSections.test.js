import assert from "node:assert/strict";
import test from "node:test";
import { defaultOpenFileSheetSectionIds, renderedFileSheetSectionIds, normalizeFileSheetOpenSectionIds, shouldOpenFileSheetForSelectionReveal } from "./fileSheetSections.js";

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
    assert.deepEqual(renderedFileSheetSectionIds("urdf", { renderMode, hasRobotComponents: true }), ["motion", "components", "view"]);
    assert.deepEqual(renderedFileSheetSectionIds("sdf", { renderMode }), ["sdf", "motion", "view"]);
    assert.deepEqual(renderedFileSheetSectionIds("srdf", { renderMode, showJoints: false, hasRobotComponents: true }), ["components", "view"]);
    assert.deepEqual(renderedFileSheetSectionIds("mesh", { renderMode }), ["measurements", "view"]);
    assert.deepEqual(renderedFileSheetSectionIds("mesh", { renderMode, hasEmbeddedGlbAnimationPanel: true, measurementAvailable: false }), ["motion", "view"]);
  }
});

test("defaults retain useful format-specific selections", () => {
  assert.deepEqual(defaultOpenFileSheetSectionIds("dxf"), []);
  assert.deepEqual(defaultOpenFileSheetSectionIds("step", { hasFileStatus: true }), ["status", "tree"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("sdf"), ["sdf", "motion"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("srdf"), ["motion"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("mesh", { hasEmbeddedGlbAnimationPanel: true }), ["motion"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("mesh", { measurementAvailable: false }), []);
});

test("legacy open selections migrate without losing the most recent tab", () => {
  assert.deepEqual(normalizeFileSheetOpenSectionIds(["tree", "pose", "display", "animation"], ["tree", "motion", "view"]), ["tree", "view", "motion"]);
  assert.deepEqual(normalizeFileSheetOpenSectionIds(["joints", "render", "materials"], ["motion", "view"]), ["motion", "view"]);
  assert.deepEqual(normalizeFileSheetOpenSectionIds(null, ["tree"]), []);
});

test("selection reveals keep the host's existing behavior", () => {
  assert.equal(shouldOpenFileSheetForSelectionReveal(), true);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false }), false);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false, source: "tree" }), true);
});
