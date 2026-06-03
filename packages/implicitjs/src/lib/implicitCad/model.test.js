import assert from "node:assert/strict";
import test from "node:test";

import {
  IMPLICIT_CAD_SCHEMA,
  normalizeImplicitCadDefinition,
  normalizeImplicitCadModel,
  pathIsImplicitCadSource
} from "./model.js";

test("pathIsImplicitCadSource recognizes explicit implicit CAD module suffixes", () => {
  assert.equal(pathIsImplicitCadSource("models/demo.implicit.js"), true);
  assert.equal(pathIsImplicitCadSource("models/demo.implicit.mjs?v=123"), true);
  assert.equal(pathIsImplicitCadSource("models/implicit-cad.mjs"), false);
  assert.equal(pathIsImplicitCadSource("models/demo.js"), false);
});

test("normalizeImplicitCadModel accepts default exports and computes bounds metadata", () => {
  const model = normalizeImplicitCadModel({
    default: {
      schema: IMPLICIT_CAD_SCHEMA,
      name: "Orb",
      bounds: [[-2, -4, -6], [2, 4, 6]],
      glsl: `
float sdf(vec3 p) { return length(p) - 1.0; }
vec3 color(vec3 p, vec3 normal) { return vec3(0.9, 0.2, 0.1); }
`
    }
  }, { sourceUrl: "/models/orb.implicit.js" });
  assert.equal(model.name, "Orb");
  assert.equal(model.sourceUrl, "/models/orb.implicit.js");
  assert.deepEqual(model.center, [0, 0, 0]);
  assert.deepEqual(model.size, [4, 8, 12]);
  assert.equal(model.stepScale, 0.45);
  assert.equal(model.maxDistance, model.radius * 8);
  assert.ok(model.maxStep > 0);
  assert.match(model.glslSource, /float sdf/);
  assert.match(model.colorSource, /vec3 color/);
});

test("normalizeImplicitCadDefinition builds runtime models from params", () => {
  const model = normalizeImplicitCadDefinition({
    name: "Parametric orb",
    params: {
      radius: { type: "number", min: 0.5, max: 4, default: 1.25 },
      tint: { type: "color", default: "#336699" }
    },
    animations: {
      pulse: {
        duration: 2,
        update({ progress, set }) {
          set("radius", 1 + progress);
        }
      }
    },
    glsl: `
float sdf(vec3 p) { return length(p) - radius; }
vec3 color(vec3 p, vec3 normal) { return tint; }
`
  }, { sourceUrl: "/models/parametric-orb.implicit.js" });

  assert.equal(model.definition.parameters.length, 2);
  assert.equal(model.definition.defaultParameterValues.radius, 1.25);
  assert.match(model.glslSource, /radius/);

  const runtimeModel = model.definition.buildModel({ radius: 2.5, tint: "#ff0000" });
  assert.equal(runtimeModel.glslSource, model.glslSource);
  assert.equal(runtimeModel.uniforms.radius.value, 2.5);
  assert.deepEqual(runtimeModel.uniforms.tint.value, [1, 0, 0]);
});

test("normalizeImplicitCadDefinition auto-generates parameter uniforms", () => {
  const model = normalizeImplicitCadDefinition({
    name: "Uniform orb",
    params: {
      radius: { type: "number", min: 0.5, max: 4, default: 1.25 },
      tint: { type: "color", default: "#336699" }
    },
    glsl: `
float sdf(vec3 p) { return length(p) - radius; }
vec3 color(vec3 p, vec3 normal) { return tint; }
`
  });

  assert.equal(model.uniforms.radius.type, "float");
  assert.equal(model.uniforms.radius.value, 1.25);
  assert.equal(model.uniforms.tint.type, "vec3");
  assert.deepEqual(model.uniforms.tint.value, [0.2, 0.4, 0.6]);
  assert.equal(model.uniformSignature, "radius:float;tint:vec3");

  const runtimeModel = model.definition.buildModel({ radius: 2.5, tint: "#ff0000" });
  assert.equal(runtimeModel.glslSource, model.glslSource);
  assert.equal(runtimeModel.uniforms.radius.value, 2.5);
  assert.deepEqual(runtimeModel.uniforms.tint.value, [1, 0, 0]);
  assert.equal(runtimeModel.uniformSignature, model.uniformSignature);
});

test("normalizeImplicitCadDefinition evaluates dynamic bounds and render fields once per build", () => {
  let renderCount = 0;
  const model = normalizeImplicitCadDefinition({
    params: {
      half: { type: "number", min: 1, max: 5, default: 2 }
    },
    bounds: ({ half }) => [[-half, -half, -half], [half, half, half]],
    render: () => {
      renderCount += 1;
      return { steps: 64 };
    },
    glsl: "float sdf(vec3 p) { return length(p) - half; }"
  });

  assert.equal(model.maxSteps, 64);
  assert.deepEqual(model.bounds.min, [-2, -2, -2]);
  assert.equal(renderCount, 1);
});

test("normalizeImplicitCadModel accepts raymarch render controls", () => {
  const model = normalizeImplicitCadModel({
    glsl: "float sdf(vec3 p) { return length(p) - 1.0; }",
    render: {
      stepScale: 0.25,
      maxStep: 0.5
    }
  });
  assert.equal(model.stepScale, 0.25);
  assert.equal(model.maxStep, 0.5);
});

test("normalizeImplicitCadModel estimates bounds when omitted", () => {
  const model = normalizeImplicitCadModel({
    params: {
      radius: { type: "number", min: 1, max: 8, default: 3 }
    },
    glsl: "float sdf(vec3 p) { return length(p) - radius; }"
  });

  assert.equal(model.boundsSource, "auto");
  assert.ok(model.bounds.min[0] < -2.5);
  assert.ok(model.bounds.max[0] > 2.5);
  assert.ok(model.radius < 20);

  const larger = model.definition.buildModel({ radius: 6 });
  assert.equal(larger.boundsSource, "auto");
  assert.ok(larger.bounds.max[0] > model.bounds.max[0]);
});

test("normalizeImplicitCadModel rejects modules without distance code", () => {
  assert.throws(
    () => normalizeImplicitCadModel({ default: { bounds: [[0, 0, 0], [1, 1, 1]] } }),
    /GLSL code/
  );
});
