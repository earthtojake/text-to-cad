import assert from "node:assert/strict";
import test from "node:test";

import {
  IMPLICIT_GRAPHICS_LIMITS,
  normalizeImplicitGraphicsSettings
} from "./implicitGraphicsSettings.js";

test("implicit graphics settings allow wider quality ranges", () => {
  assert.deepEqual(IMPLICIT_GRAPHICS_LIMITS.resolutionScale, { min: 0.5, max: 5, step: 0.05 });
  assert.deepEqual(IMPLICIT_GRAPHICS_LIMITS.interactionResolutionScale, { min: 0.25, max: 4, step: 0.05 });
  assert.deepEqual(IMPLICIT_GRAPHICS_LIMITS.detail, { min: 0.25, max: 8, step: 0.05 });
  assert.deepEqual(IMPLICIT_GRAPHICS_LIMITS.normalSmoothing, { min: 0.25, max: 5, step: 0.05 });
});

test("implicit graphics settings clamp to expanded ranges", () => {
  assert.deepEqual(normalizeImplicitGraphicsSettings({
    resolutionScale: 99,
    interactionResolutionScale: -1,
    detail: 9,
    normalSmoothing: 10
  }), {
    resolutionScale: 5,
    interactionResolutionScale: 0.25,
    detail: 8,
    normalSmoothing: 5,
    modelColors: true,
    shadows: true,
    ambientOcclusion: true,
    rimLight: true
  });
});
