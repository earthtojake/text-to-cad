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

test("this renderer holds a sheet for STEP alone; every other family has its own renderer", () => {
  for (const renderMode of [false, true]) {
    for (const kind of ["dxf", "mesh", "urdf", "srdf", "sdf"]) assert.deepEqual(renderedFileSheetSectionIds(kind, { renderMode }), []);
  }
});

test("defaults retain useful format-specific selections", () => {
  assert.deepEqual(defaultOpenFileSheetSectionIds("step", { hasFileStatus: true }), ["status", "tree"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("urdf"), []);
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
  assert.equal(resolveActiveFileSheetSectionId([], ["features", "kinematics", "display"]), "features");
  assert.equal(resolveActiveFileSheetSectionId(null, []), "");
  assert.deepEqual(tabs, ["tree", "kinematics", "display"]);
});
