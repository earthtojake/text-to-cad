import assert from "node:assert/strict";
import test from "node:test";

import {
  cadWebGlRendererAttributes,
  fallbackCadWebGlRendererAttributes
} from "./webglRenderer.js";

test("shared CAD WebGL renderer attributes match viewer depth defaults", () => {
  assert.deepEqual(cadWebGlRendererAttributes(), {
    alpha: true,
    antialias: true,
    powerPreference: "high-performance",
    preserveDrawingBuffer: false,
    logarithmicDepthBuffer: true
  });
  assert.equal(cadWebGlRendererAttributes({ preserveDrawingBuffer: true }).preserveDrawingBuffer, true);
});

test("shared CAD WebGL renderer fallback preserves snapshot/viewer compatibility knobs", () => {
  assert.deepEqual(fallbackCadWebGlRendererAttributes(), {
    alpha: true,
    antialias: false,
    powerPreference: "default",
    preserveDrawingBuffer: false,
    logarithmicDepthBuffer: false
  });
});
