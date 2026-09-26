import assert from "node:assert/strict";
import test from "node:test";
import { CAD_EDGE_COVERAGE_GLSL, CAD_EDGE_FEATHER_PIXELS } from "./cadEdgeCoverage.js";

// Execute the scalar expression actually embedded in both shaders. This keeps
// the numerical regression tied to the shader, rather than a second formula.
const body = CAD_EDGE_COVERAGE_GLSL.match(/float cadEdgeCoverage\(float distancePixels, float halfWidth\) \{([\s\S]*?)\}/)?.[1];
assert.ok(body);
const evaluate = new Function("distancePixels", "halfWidth", "smoothstep", body);
function smoothstep(low, high, value) {
  const t = Math.max(0, Math.min(1, (value - low) / (high - low)));
  return t * t * (3 - 2 * t);
}
function coverage(distance, width) {
  return evaluate(distance, width / 2, smoothstep);
}
function integratedInk(width) {
  const extent = width / 2 + CAD_EDGE_FEATHER_PIXELS;
  const samples = 10000;
  const step = 2 * extent / samples;
  let sum = 0;
  for (let index = 0; index < samples; index++) {
    sum += coverage(-extent + (index + 0.5) * step, width) * step;
  }
  return sum;
}

test("analytic line coverage preserves nominal ink, including subpixel classes", () => {
  for (const width of [0, 0.01, 0.1, 0.65, 0.8, 1, 1.15, 2, 3, 6]) {
    assert.ok(Math.abs(integratedInk(width) - width) < 1e-6, `${width} device px must integrate to its nominal width`);
    for (const dpr of [1, 2, 3]) {
      assert.ok(Math.abs(integratedInk(width) / dpr - width / dpr) < 1e-6);
    }
  }
});

test("zero-width lines have no residual ink and subpixel lines have a soft centre", () => {
  for (const distance of [-2, -0.75, -0.1, 0, 0.1, 0.75, 2]) {
    assert.equal(coverage(distance, 0), 0);
  }
  for (const width of [0.01, 0.1, 0.65, 0.8, 1]) {
    const peak = coverage(0, width);
    assert.ok(peak > 0 && peak < 1, `${width} px must not force an opaque centre`);
    for (let distance = 0; distance <= 2; distance += 0.05) {
      const alpha = coverage(distance, width);
      assert.ok(alpha >= 0 && alpha <= peak);
      assert.ok(Math.abs(alpha - coverage(-distance, width)) < 1e-12);
    }
    assert.equal(coverage(width / 2 + CAD_EDGE_FEATHER_PIXELS, width), 0);
  }
});
