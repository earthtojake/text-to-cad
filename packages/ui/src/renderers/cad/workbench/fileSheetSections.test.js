import assert from "node:assert/strict";
import test from "node:test";
import { defaultOpenFileSheetSectionIds, renderedFileSheetSectionIds, normalizeFileSheetOpenSectionIds, resolveActiveFileSheetSectionId, shouldOpenFileSheetForSelectionReveal } from "./fileSheetSections.js";

test("STEP shares Model, optional Motion, and View across both viewing modes", () => {
  for (const renderMode of [false, true]) {
    assert.deepEqual(renderedFileSheetSectionIds("step", { renderMode }), ["tree", "display"]);
    for (const options of [{ hasStepPosePanel: true }, { hasStepAnimationPanel: true }, { hasStepPosePanel: true, hasStepAnimationPanel: true }]) {
      assert.deepEqual(renderedFileSheetSectionIds("step", { ...options, renderMode }), ["tree", "kinematics", "display"]);
      assert.deepEqual(defaultOpenFileSheetSectionIds("step", { ...options, renderMode }), ["tree"]);
    }
  }
});

test("format-specific tabs remain available in both viewing modes", () => {
  for (const renderMode of [false, true]) {
    assert.deepEqual(renderedFileSheetSectionIds("dxf", { renderMode, hasDxfBendsPanel: true, hasDxfLayersPanel: true }), ["material", "bends", "dxfLayers", "display"]);
    // Components is the robot's link tree: always there, second after Motion, whatever the meshes name.
    assert.deepEqual(renderedFileSheetSectionIds("urdf", { renderMode }), ["kinematics", "links", "display"]);
    assert.deepEqual(renderedFileSheetSectionIds("srdf", { renderMode }), ["kinematics", "links", "display"]);
    assert.deepEqual(renderedFileSheetSectionIds("sdf", { renderMode }), ["kinematics", "links", "sdf", "display"]);
    assert.deepEqual(renderedFileSheetSectionIds("srdf", { renderMode, showJoints: false }), ["links", "display"]);
    // A mesh has only Display: measurements are the Measure tool's panel.
    assert.deepEqual(renderedFileSheetSectionIds("mesh", { renderMode }), ["display"]);
  }
});

test("defaults retain useful format-specific selections", () => {
  assert.deepEqual(defaultOpenFileSheetSectionIds("dxf"), []);
  assert.deepEqual(defaultOpenFileSheetSectionIds("step", { hasFileStatus: true }), ["status", "tree"]);
  // Motion is the tab every robot lands on; an SDF's metadata tab follows it.
  assert.deepEqual(defaultOpenFileSheetSectionIds("sdf"), ["kinematics"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("srdf"), ["kinematics"]);
  // Motion stays the tab a robot lands on; Components is never the default.
  assert.deepEqual(defaultOpenFileSheetSectionIds("urdf"), ["kinematics"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("mesh"), []);
});

test("an open selection is the last id this format still has; a retired id is simply not open", () => {
  assert.deepEqual(normalizeFileSheetOpenSectionIds(["tree", "kinematics", "display"], ["tree", "kinematics", "display"]), ["display"]);
  // No table of old names: "view", "motion", "pose", "render" mean nothing now.
  assert.deepEqual(normalizeFileSheetOpenSectionIds(["tree", "pose", "view", "motion"], ["tree", "kinematics", "display"]), ["tree"]);
  assert.deepEqual(normalizeFileSheetOpenSectionIds(["joints", "render", "materials"], ["kinematics", "display"]), []);
  assert.deepEqual(normalizeFileSheetOpenSectionIds(null, ["tree"]), []);
});

test("selection reveals keep the host's existing behavior", () => {
  assert.equal(shouldOpenFileSheetForSelectionReveal(), true);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false }), false);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false, source: "tree" }), true);
});

test("one tab is active: the last selected one that exists, else the format's first", () => {
  const tabs = ["tree", "kinematics", "display"];
  assert.equal(resolveActiveFileSheetSectionId(["tree", "display", "kinematics"], tabs), "kinematics");
  assert.equal(resolveActiveFileSheetSectionId(["tree", "render"], tabs), "tree");
  assert.equal(resolveActiveFileSheetSectionId(["retired", "kinematics"], ["tree", "display"]), "tree");
  assert.equal(resolveActiveFileSheetSectionId([], ["material", "bends", "dxfLayers", "display"]), "material");
  assert.equal(resolveActiveFileSheetSectionId(null, []), "");
  assert.deepEqual(tabs, ["tree", "kinematics", "display"]);
});
