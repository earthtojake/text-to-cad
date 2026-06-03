import assert from "node:assert/strict";
import test from "node:test";

import {
  IMPLICIT_EXPORT_FORMATS,
  exportImplicitAnimatedGlb,
  exportImplicitModel,
  normalizeImplicitExportFormat,
} from "./index.js";

test("root entry exposes concise export aliases", () => {
  assert.deepEqual(IMPLICIT_EXPORT_FORMATS, ["glb", "stl", "3mf"]);
  assert.equal(normalizeImplicitExportFormat("gltf"), "glb");
  assert.equal(typeof exportImplicitModel, "function");
  assert.equal(typeof exportImplicitAnimatedGlb, "function");
});
