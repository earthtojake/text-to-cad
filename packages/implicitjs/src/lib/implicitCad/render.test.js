import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  createImplicitCadMaterial,
  implicitCadCameraState,
  implicitCadModelShaderKey,
  implicitCadFragmentShader,
  normalizeImplicitCadGlslFloatLiterals,
  resolveImplicitCadAppearanceSettings,
  updateImplicitCadAppearanceUniforms,
  updateImplicitCadGraphicsUniforms
} from "./render.js";
import { normalizeImplicitCadModel } from "./model.js";

test("normalizes integer literals in float shader expressions", () => {
  assert.equal(
    normalizeImplicitCadGlslFloatLiterals("length(p) - 22"),
    "length(p) - 22.0"
  );
  assert.equal(
    normalizeImplicitCadGlslFloatLiterals("smoothstep(-18, 18, p.z)"),
    "smoothstep(-18.0, 18.0, p.z)"
  );
});

test("keeps integer control-flow and array-index literals intact", () => {
  assert.equal(
    normalizeImplicitCadGlslFloatLiterals("for (int i = 0; i < 4; i++) { value += points[i]; value += weights[0]; }"),
    "for (int i = 0; i < 4; i++) { value += points[i]; value += weights[0]; }"
  );
  assert.equal(
    normalizeImplicitCadGlslFloatLiterals("for (int i = 0; i < LIMIT; i += 1) { value += points[i]; }"),
    "for (int i = 0; i < LIMIT; i += 1) { value += points[i]; }"
  );
});

test("fragment shader accepts ordinary JS integer template output", () => {
  const shader = implicitCadFragmentShader({
    glslSource: `
float sdf(vec3 p) { return length(p) - 22; }
vec3 color(vec3 p, vec3 normal) { return vec3(1, 0, 0); }
`,
    maxSteps: 64
  });

  assert.match(shader, /length\(p\) - 22\.0/);
  assert.match(shader, /vec3\(1\.0, 0\.0, 0\.0\)/);
});

test("fragment shader caps raymarch steps for thin procedural fields", () => {
  const shader = implicitCadFragmentShader({
    glslSource: "float sdf(vec3 p) { return length(p) - 1.0; }",
    maxSteps: 64
  });

  assert.match(shader, /uniform float uStepScale;/);
  assert.match(shader, /uniform float uMaxStep;/);
  assert.match(shader, /t \+= min\(stepDistance, uMaxStep\);/);
});

test("fragment shader exposes graphics lighting controls", () => {
  const shader = implicitCadFragmentShader({
    glslSource: "float sdf(vec3 p) { return length(p) - 1.0; }",
    maxSteps: 64
  });

  assert.match(shader, /uniform float uShadowStrength;/);
  assert.match(shader, /uniform float uAmbientOcclusionStrength;/);
  assert.match(shader, /uniform float uRimStrength;/);
  assert.match(shader, /clamp\(uShadowStrength, 0\.0, 1\.0\)/);
});

test("fragment shader declares parameter uniforms", () => {
  const shader = implicitCadFragmentShader({
    glslSource: `
float sdf(vec3 p) { return length(p) - radius; }
vec3 color(vec3 p, vec3 normal) { return tint; }
`,
    maxSteps: 64,
    uniforms: {
      radius: { type: "float", value: 2.5 },
      tint: { type: "vec3", value: [1, 0, 0] }
    }
  });

  assert.match(shader, /uniform float radius;/);
  assert.match(shader, /uniform vec3 tint;/);
  assert.match(shader, /length\(p\) - radius/);
});

test("shader key is stable for uniform-only parameter changes", () => {
  const base = {
    params: {
      radius: { type: "number", min: 1, max: 10, default: 2 }
    },
    glsl: "float sdf(vec3 p) { return length(p) - radius; }"
  };
  const first = implicitCadModelShaderKey(base);
  const second = implicitCadModelShaderKey({
    ...base,
    values: { radius: 8 }
  });
  const changedSource = implicitCadModelShaderKey({
    ...base,
    glsl: "float sdf(vec3 p) { return length(p) - radius + 0.1; }"
  });

  assert.equal(first, second);
  assert.notEqual(first, changedSource);
});

test("fragment shader uses a zero-direction-safe ray bounds intersection", () => {
  const shader = implicitCadFragmentShader({
    glslSource: "float sdf(vec3 p) { return length(p) - 1.0; }",
    maxSteps: 64
  });

  assert.match(shader, /vec2 implicit_ray_slab/);
  assert.match(shader, /abs\(direction\) < 1\.0e-8/);
});

test("camera objects support explicit CAD snapshot-style controls", () => {
  const state = implicitCadCameraState(
    normalizeImplicitCadModel({
      glsl: "float sdf(vec3 p) { return length(p) - 1.0; }",
      bounds: { min: [-1, -1, -1], max: [1, 1, 1] }
    }),
    {
      position: [4, -5, 3],
      target: [0.5, 0, -0.25],
      up: [0, 0, 1],
      zoom: 1.8
    }
  );

  assert.deepEqual(state.position, [4, -5, 3]);
  assert.deepEqual(state.target, [0.5, 0, -0.25]);
  assert.deepEqual(state.up, [0, 0, 1]);
  assert.equal(state.zoom, 1.8);
});

test("camera framing samples SDF bounds when declared bounds are roomy", () => {
  const state = implicitCadCameraState(
    normalizeImplicitCadModel({
      glsl: "float sdf(vec3 p) { return length(p) - 1.0; }",
      bounds: { min: [-10, -10, -10], max: [10, 10, 10] }
    }),
    "iso",
    { width: 1200, height: 900, zoom: 1 }
  );
  const distance = Math.hypot(
    state.position[0] - state.target[0],
    state.position[1] - state.target[1],
    state.position[2] - state.target[2]
  );

  assert.ok(state.frameBounds.min[0] > -5, `expected sampled min, got ${state.frameBounds.min[0]}`);
  assert.ok(state.frameBounds.max[0] < 5, `expected sampled max, got ${state.frameBounds.max[0]}`);
  assert.ok(distance < 30, `expected a camera fit to sampled geometry, got ${distance}`);
});

test("camera framing honors a larger frame margin for safer snapshots", () => {
  const model = normalizeImplicitCadModel({
    glsl: "float sdf(vec3 p) { return length(p) - 1.0; }",
    bounds: { min: [-1, -1, -1], max: [1, 1, 1] }
  });
  const compact = implicitCadCameraState(model, "iso", {
    width: 1200,
    height: 900,
    zoom: 1,
    frameMargin: 1.05
  });
  const padded = implicitCadCameraState(model, "iso", {
    width: 1200,
    height: 900,
    zoom: 1,
    frameMargin: 1.7
  });
  const compactDistance = Math.hypot(
    compact.position[0] - compact.target[0],
    compact.position[1] - compact.target[1],
    compact.position[2] - compact.target[2]
  );
  const paddedDistance = Math.hypot(
    padded.position[0] - padded.target[0],
    padded.position[1] - padded.target[1],
    padded.position[2] - padded.target[2]
  );

  assert.ok(paddedDistance > compactDistance, `expected padded camera to stand farther back than ${compactDistance}, got ${paddedDistance}`);
});

test("camera framing falls back to declared bounds when CPU SDF sampling cannot evaluate GLSL", () => {
  const state = implicitCadCameraState(
    normalizeImplicitCadModel({
      glsl: `
float sdf(vec3 p) {
  for (int i = 0; i < 2; i += 1) {
    break;
  }
  return length(p) - 1.0;
}
`,
      bounds: { min: [-10, -10, -10], max: [10, 10, 10] }
    }),
    "iso",
    { width: 1200, height: 900, zoom: 1 }
  );

  assert.deepEqual(state.frameBounds, { min: [-10, -10, -10], max: [10, 10, 10] });
});

test("workbench appearance and graphics update the shared shader uniforms", () => {
  const model = normalizeImplicitCadModel({
    glsl: `
float sdf(vec3 p) { return length(p) - 1.0; }
vec3 color(vec3 p, vec3 normal) { return vec3(0.1, 0.8, 1.0); }
`,
    material: { color: "#ff3366" }
  });
  const material = createImplicitCadMaterial(THREE, model);

  const themeSettings = updateImplicitCadAppearanceUniforms(THREE, material, model, {
    appearance: "workbench",
    graphicsSettings: { modelColors: false }
  });
  const graphicsSettings = updateImplicitCadGraphicsUniforms(material, model, {
    detail: 4,
    normalSmoothing: 2,
    stepBudget: 24,
    shadows: false,
    ambientOcclusion: false,
    rimLight: false
  });

  assert.equal(material.uniforms.uUseProceduralColor.value, 0);
  assert.equal(material.uniforms.uShadowStrength.value, 0);
  assert.equal(material.uniforms.uAmbientOcclusionStrength.value, 0);
  assert.equal(material.uniforms.uRimStrength.value, 0);
  assert.equal(material.uniforms.uStepBudget.value, 24);
  assert.equal(graphicsSettings.detail, 4);
  assert.ok(material.uniforms.uHitEpsilon.value < model.epsilon);
  assert.equal(resolveImplicitCadAppearanceSettings({ appearance: "workbench" }).background.type, themeSettings.background.type);

  material.dispose();
});
