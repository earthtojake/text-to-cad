import assert from "node:assert/strict";
import test from "node:test";

import {
  defaultOpenFileSheetSectionIds,
  renderedFileSheetSectionIds,
  shouldOpenFileSheetForSelectionReveal
} from "./fileSheetSections.js";

test("file sheet section defaults match current sheet behavior", () => {
  assert.deepEqual(defaultOpenFileSheetSectionIds("dxf"), ["plate", "bends"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("gcode"), ["toolpath"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("step"), ["tree"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("step", { hasFileStatus: true }), ["status", "tree"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("step", { hasStepModulePanel: true }), ["tree", "parameters"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("mesh", { hasFileStatus: true }), ["status"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("implicit", { hasFileStatus: true }), ["status"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("implicit"), []);
  assert.deepEqual(defaultOpenFileSheetSectionIds("implicit", { hasImplicitParameterPanel: true }), ["parameters"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("srdf", { motionEnabled: true }), ["motion", "joints"]);
  assert.deepEqual(defaultOpenFileSheetSectionIds("sdf"), ["sdf", "joints"]);
});

test("rendered file sheet sections include closed-by-default sections", () => {
  assert.deepEqual(renderedFileSheetSectionIds("gcode", { hasFileStatus: true }), [
    "status",
    "toolpath",
    "features",
    "stats",
    "bounds",
    "display",
    "appearance",
    "metadata"
  ]);
  assert.deepEqual(renderedFileSheetSectionIds("step", { hasFileStatus: true, hasStepModulePanel: true }), [
    "status",
    "tree",
    "parameters",
    "display",
    "appearance",
    "metadata"
  ]);
  assert.deepEqual(renderedFileSheetSectionIds("mesh"), ["display", "appearance", "metadata"]);
  assert.deepEqual(renderedFileSheetSectionIds("implicit"), ["graphics", "display", "appearance", "metadata"]);
  assert.deepEqual(renderedFileSheetSectionIds("implicit", { hasImplicitParameterPanel: true }), ["parameters", "graphics", "display", "appearance", "metadata"]);
});

test("viewer-origin selection reveals do not open the file sheet on mobile", () => {
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: true, source: "viewer" }), true);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false, source: "viewer" }), false);
  assert.equal(shouldOpenFileSheetForSelectionReveal({ isDesktop: false, source: "tree" }), true);
});
