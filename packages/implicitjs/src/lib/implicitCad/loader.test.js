import assert from "node:assert/strict";
import test from "node:test";

import {
  loadImplicitModuleFromSource,
  loadImplicitSource,
  normalizeImplicitModel
} from "../../index.js";

test("loadImplicitModuleFromSource normalizes editable implicit source strings", async () => {
  const model = await loadImplicitModuleFromSource(`
    export default {
      schema: "implicit.js/0.1.0",
      name: "inline sphere",
      params: {
        radius: { type: "number", min: 1, max: 8, default: 4 }
      },
      bounds: ({ params }) => params.radius + 1,
      glsl: "float sdf(vec3 p) { return length(p) - radius; }"
    };
  `);

  assert.equal(model.name, "inline sphere");
  assert.equal(model.parameterValues.radius, 4);
  assert.equal(model.bounds.max[0], 5);
  assert.equal(loadImplicitSource, loadImplicitModuleFromSource);
});

test("implicit aliases point at the normalized model API", () => {
  const model = normalizeImplicitModel({
    glsl: "float sdf(vec3 p) { return length(p) - 1.0; }"
  });

  assert.equal(model.kind, "implicit");
  assert.equal(model.name, "Implicit CAD");
});
