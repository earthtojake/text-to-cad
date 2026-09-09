import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import {
  CAD_EDGE_FEATHER_PIXELS,
  CAD_EDGE_INSTANCE_TEXELS,
  CadEdgeInstances,
  buildCadEdgeSegmentTexture
} from "./cadEdgeInstances.js";
import { screenSpaceLineDeviceResolution } from "./renderEdges.js";

// One horizontal segment, classed `feature`.
function oneSegment() {
  return buildCadEdgeSegmentTexture(THREE, {
    positions: new Float32Array([0, 0, 0, 1, 0, 0]),
    indices: new Uint32Array([0, 1])
  }, [{ classId: "feature", segmentStart: 0, segmentCount: 1 }]);
}

function instanceSet(classStyles, options = {}) {
  return new CadEdgeInstances(THREE, {
    segments: oneSegment(),
    classStyles,
    ...options
  });
}

const FEATURE = [{ classId: "feature", color: new THREE.Color("#132232"), opacity: 1, thickness: 1.15 }];

// The coverage ramp, read back OUT of the shader source so a changed ramp changes
// the numbers this file integrates.
function featherRamp(source, halfWidthName) {
  const match = source.match(new RegExp(
    `1\\.0 - smoothstep\\(\\s*max\\(${halfWidthName} - ([0-9.]+), 0\\.0\\),\\s*${halfWidthName} \\+ ([0-9.]+),`
  ));
  assert.ok(match, `no analytic feather in the shader (looked for a smoothstep around ${halfWidthName})`);
  return { inner: Number(match[1]), outer: Number(match[2]) };
}

// Ink in device pixels: twice the integral of coverage from the centreline out.
// A smoothstep integrates to its midpoint, so the total is inner + outer edge.
function featherInk(thickness, { inner, outer }) {
  const halfWidth = thickness / 2;
  return Math.max(halfWidth - inner, 0) + (halfWidth + outer);
}

test("the segment texture packs endpoints and the class index", () => {
  const segments = oneSegment();
  assert.equal(segments.segmentCount, 1);
  assert.equal(segments.width, 2);
  assert.equal(segments.height, 1);
  const data = segments.texture.image.data;
  assert.deepEqual(Array.from(data.subarray(0, 4)), [0, 0, 0, 0]);   // start.xyz + class 0 (feature)
  assert.deepEqual(Array.from(data.subarray(4, 7)), [1, 0, 0]);      // end.xyz
  assert.equal(buildCadEdgeSegmentTexture(THREE, { positions: new Float32Array(), indices: new Uint32Array() }, []), null);
});

test("instanced CAD edges carry per-class colour, opacity and thickness", () => {
  const set = instanceSet([
    { classId: "feature", color: new THREE.Color("#132232"), opacity: 1, thickness: 1.15 },
    { classId: "tangent", color: new THREE.Color("#445566"), opacity: 0.5, thickness: 0.8 },
    { classId: "seam", color: new THREE.Color("#778899"), opacity: 0.85, thickness: 2 }
    // degenerate: absent, so it draws at width 0 and opacity 0.
  ], { depthBias: 0.0045 });

  const width = set.uniforms.cadClassWidth.value;
  assert.equal(width.x, 1.15);
  assert.equal(width.y, 0.8);
  assert.equal(width.z, 2);
  assert.equal(width.w, 0);

  const colors = set.uniforms.cadClassColor.value.elements;
  assert.equal(colors[3], 1);      // feature opacity
  assert.equal(colors[7], 0.5);    // tangent opacity
  assert.equal(colors[11], 0.85);  // seam opacity
  assert.equal(colors[15], 0);     // degenerate: not drawn

  // Depth bias rides the material as fixed-function polygon offset.
  assert.equal(set.material.polygonOffset, true);
  assert.equal(set.material.polygonOffsetUnits < 0, true);
  set.dispose();
});

test("the instanced edge shader extrudes a FULL width in device pixels", () => {
  const set = instanceSet(FEATURE, { resolution: { width: 800, height: 600 } });
  const source = set.material.vertexShader;

  // `thickness` is the full width of the ink, so the quad spans +-halfWidth ...
  assert.match(source, /float halfWidth = lineWidth \* 0\.5;/);
  // ... plus the feather's room on each side, and offset is a UNIT perpendicular,
  // so the scale that puts each side at the padded half width is 2x it.
  const padding = source.match(/float paddedHalfWidth = halfWidth \+ ([0-9.]+);/);
  assert.ok(padding, "the vertex shader does not pad the quad for a feather");
  assert.equal(Number(padding[1]), CAD_EDGE_FEATHER_PIXELS);
  assert.match(source, /offset \*= paddedHalfWidth \* 2\.0;\n\s*offset \/= resolution\.y;/);

  // `resolution` is the drawing buffer, which is what makes that a DEVICE pixel:
  // the extrusion normalises by resolution.y and lands in NDC, so the ink is
  // lineWidth * drawingBufferHeight / resolution.y.
  assert.equal(set.uniforms.resolution.value.x, 800);
  assert.equal(set.uniforms.resolution.value.y, 600);
  const widthDevicePx = 1.15 * 600 / set.uniforms.resolution.value.y;
  assert.equal(widthDevicePx, 1.15);

  set.setResolution(1200, 900);
  assert.equal(set.material.resolution.x, 1200);
  assert.equal(set.material.resolution.y, 900);
  assert.equal(set.highlightMaterial.resolution.y, 900);   // both passes, one uniform
  set.dispose();
});

test("the instanced edge shader antialiases with an analytic feather", () => {
  const set = instanceSet(FEATURE);
  const fragment = set.material.fragmentShader;

  // Coverage MULTIPLIES the per-class alpha rather than replacing it, so a
  // tangent edge at opacity 0.5 stays half strength across its whole width.
  assert.match(fragment, /vColor\.a \* opacity \* coverage/);
  const ramp = featherRamp(fragment, "halfWidth");
  assert.equal(ramp.inner, CAD_EDGE_FEATHER_PIXELS);
  assert.equal(ramp.outer, CAD_EDGE_FEATHER_PIXELS);

  // The distance is exact in device pixels, taken from the interpolated cross
  // coordinate — no derivative, no alpha-to-coverage, no sample-count dependence.
  assert.match(fragment, /float distancePixels = abs\(vCadEdge\.x\) \* \(halfWidth \+ [0-9.]+\);/);
  assert.equal(fragment.includes("fwidth"), false);
  assert.equal(set.material.alphaToCoverage, false);
  assert.equal(set.material.transparent, true);

  // The weight is the retired surface shader's, to the digit: 1.325 device px at
  // the 1.15 default, and exactly `thickness` once the ink outweighs the feather.
  assert.equal(featherInk(1.15, ramp), 1.325);
  assert.equal(featherInk(2, ramp), 2);
  assert.equal(featherInk(3, ramp), 3);
  set.dispose();
});

// The ink a viewport actually paints, in CSS pixels. The shader extrudes
// `lineWidth / resolution.y` into NDC and NDC y spans the whole drawing buffer,
// so the ink is `lineWidth * drawingBufferHeight / resolution.y` device pixels —
// and a device pixel is 1/dpr of a CSS one.
function inkCssPixels(set, thickness, { cssHeight, dpr }) {
  const devicePixels = thickness * (cssHeight * dpr) / set.uniforms.resolution.value.y;
  return devicePixels / dpr;
}

// Widths are floats through two divisions; a sub-picopixel is not a regression.
function assertPixels(actual, expected) {
  assert.ok(Math.abs(actual - expected) < 1e-12, `expected ${expected} px of ink, got ${actual}`);
}

test("a CAD edge thickness paints the same ink at dpr 1, 2 and 3", () => {
  const set = instanceSet(FEATURE);
  const syncViewport = (dpr) => {
    const { width, height } = screenSpaceLineDeviceResolution({ getPixelRatio: () => dpr }, 800, 600);
    set.setResolution(width, height);
  };

  // `thickness` is 1.15 DEVICE pixels at every ratio — the weight the retired
  // surface shader drew, whose `fwidth` derivative was a drawing-buffer pixel.
  syncViewport(1);
  assert.equal(set.uniforms.resolution.value.y, 600);
  assertPixels(inkCssPixels(set, 1.15, { cssHeight: 600, dpr: 1 }), 1.15);
  syncViewport(2);
  assert.equal(set.uniforms.resolution.value.y, 1200);
  assertPixels(inkCssPixels(set, 1.15, { cssHeight: 600, dpr: 2 }), 1.15 / 2);
  syncViewport(3);
  assertPixels(inkCssPixels(set, 1.15, { cssHeight: 600, dpr: 3 }), 1.15 / 3);

  // The regression this replaces, stated in numbers: hand the shader the CSS
  // size and the buffer's pixel ratio never cancels, so `thickness` becomes a
  // CSS-pixel width — 1.15 CSS px at every ratio, which is twice the authored
  // weight at dpr 2 and three times it at dpr 3.
  set.setResolution(800, 600);
  assertPixels(inkCssPixels(set, 1.15, { cssHeight: 600, dpr: 2 }), 1.15);
  assertPixels(inkCssPixels(set, 1.15, { cssHeight: 600, dpr: 3 }), 1.15);
  set.dispose();
});

test("an instance slot keeps its own matrix, style, visibility and highlight", () => {
  const set = instanceSet(FEATURE);
  assert.equal(set.instanceData.length % CAD_EDGE_INSTANCE_TEXELS, 0);

  const slot = set.allocate();
  assert.deepEqual(set.readSlot(slot), {
    matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    color: null,
    opacity: 1,
    visible: true,
    highlighted: false
  });
  assert.equal(set.geometry.instanceCount, 1);

  set.setMatrix(slot, new THREE.Matrix4().makeTranslation(2, 3, 4));
  set.setStyle(slot, { color: new THREE.Color("#ff0000"), opacity: 0.25 });
  set.setVisible(slot, false);
  set.setHighlighted(slot, true);
  const read = set.readSlot(slot);
  assert.deepEqual(read.color, [1, 0, 0]);
  assert.equal(read.opacity, 0.25);
  assert.equal(read.visible, false);
  assert.equal(read.highlighted, true);
  assert.equal(set.highlightObject.visible, true);

  // Dropping the class override restores the class colours at a scaled opacity.
  set.setStyle(slot, { opacityScale: 0.5 });
  assert.equal(set.readSlot(slot).color, null);
  assert.equal(set.readSlot(slot).opacity, 0.5);

  set.setHighlighted(slot, false);
  set.release(slot);
  assert.equal(set.geometry.instanceCount, 0);
  assert.equal(set.highlightObject.visible, false);
  set.dispose();
});
