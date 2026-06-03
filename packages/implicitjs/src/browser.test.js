import assert from "node:assert/strict";
import test from "node:test";

import {
  analyzeImplicitMeshQuality,
  exportImplicitAnimatedGlb,
  exportImplicitModel,
  createImplicitMaterial,
  IMPLICIT_CAD_SCHEMA,
  loadImplicitSource,
  normalizeImplicitDefinition,
  normalizeParameterValue,
  snapshotImplicitCadModel
} from "./browser.js";

test("browser entry exposes editable-source, parameter, model, and render APIs", () => {
  assert.equal(typeof loadImplicitSource, "function");
  assert.equal(IMPLICIT_CAD_SCHEMA, "implicit.js/0.1.0");
  assert.equal(typeof normalizeImplicitDefinition, "function");
  assert.equal(typeof normalizeParameterValue, "function");
  assert.equal(typeof createImplicitMaterial, "function");
  assert.equal(typeof analyzeImplicitMeshQuality, "function");
  assert.equal(typeof snapshotImplicitCadModel, "function");
  assert.equal(typeof exportImplicitModel, "function");
  assert.equal(typeof exportImplicitAnimatedGlb, "function");
});
