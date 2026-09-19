import assert from "node:assert/strict";
import test from "node:test";

import {
  DXF_MM_TO_GLB_SCALE,
  dxfPreviewPositions,
  dxfSoupToGlbPositions,
} from "./previewGlb.js";

// One triangle in the mesher's frame: x/z in the sheet, y out of it.
const SOUP = Float32Array.from([
  0, 0.5, 0,
  10, 0.5, 0,
  10, 0.5, 20,
]);

// Float32 storage, so compare at single precision rather than exactly.
function assertClose(actual, expected, message) {
  assert.equal(actual.length, expected.length, message);
  for (let index = 0; index < expected.length; index += 1) {
    assert.ok(
      Math.abs(actual[index] - expected[index]) < 1e-7,
      `${message}: [${index}] ${actual[index]} != ${expected[index]}`,
    );
  }
}

test("the soup converter applies the mesher's Y-up -> CAD Z-up map and the mm scale", () => {
  // (x, y, z) -> (x, z, -y), all scaled to glTF metres.
  assertClose(dxfSoupToGlbPositions(SOUP), [
    0, 0, -0.0005,
    0.01, 0, -0.0005,
    0.01, 0.02, -0.0005,
  ], "axis map");
});

test("prism and overlay ride the SAME conversion, so they land on one axis", () => {
  // The overlay used to be handed to writeGlb unconverted, which put the sheet
  // and its markings on different axes at a thousand times the scale. Pinning
  // them against each other is what makes that impossible to reintroduce.
  const meshData = {
    vertices: SOUP,
    indices: Uint32Array.from([0, 1, 2]),
  };
  assert.deepEqual(
    Array.from(dxfPreviewPositions(meshData)),
    Array.from(dxfSoupToGlbPositions(SOUP)),
  );
});

test("the scale is overridable for the client path, which works in millimetres", () => {
  assertClose(dxfSoupToGlbPositions(SOUP, { scale: 1 }).slice(0, 3), [0, 0, -0.5], "mm scale");
  assert.equal(DXF_MM_TO_GLB_SCALE, 0.001);
});

test("an empty or absent soup converts to an empty soup", () => {
  assert.equal(dxfSoupToGlbPositions(new Float32Array(0)).length, 0);
  assert.equal(dxfSoupToGlbPositions(null).length, 0);
});
