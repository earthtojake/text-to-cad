import assert from "node:assert/strict";
import test from "node:test";

import { footprintMatrix, modelMatrix, placePoint } from "./partPlacement.js";

const close = (actual, expected) => assert.deepEqual(actual.map(value => Math.round(value * 1e6) / 1e6 + 0), expected);

test("a front part's model stands on the front face at the part's sheet point, y negated", () => {
  const part = { at: [10, 20], rotation: 0, side: "top" };
  close(placePoint(modelMatrix(part, {}, 1.6), [0, 0, 0]), [10, -20, 0]);
  // Up out of the model is up out of the front face; its +x is the sheet's +x.
  close(placePoint(modelMatrix(part, {}, 1.6), [1, 0, 2]), [11, -20, 2]);
});

test("a back part's model hangs under the back face, turned over about its x axis", () => {
  const part = { at: [10, 20], rotation: 0, side: "bottom" };
  close(placePoint(modelMatrix(part, {}, 1.6), [0, 0, 0]), [10, -20, -1.6]);
  // The model's height goes down from the back; its +x stays the sheet's +x, its +y is mirrored.
  close(placePoint(modelMatrix(part, {}, 1.6), [1, 1, 2]), [11, -21, -3.6]);
});

test("a turned part's model is turned counter-clockwise seen from the top", () => {
  const part = { at: [0, 0], rotation: 90, side: "top" };
  close(placePoint(footprintMatrix(part), [1, 0, 0]), [0, 1, 0]);
  close(placePoint(modelMatrix({ ...part, side: "bottom" }, {}, 2), [1, 0, 0]), [0, 1, -2]);
});

test("a model's offset, rotation and scale apply in the footprint's frame, as KiCad applies them", () => {
  const part = { at: [5, 5], rotation: 90, side: "top" };
  // Offset 1 mm along the footprint's x, which the part's quarter turn points along the world's y.
  close(placePoint(modelMatrix(part, { offset: [1, 0, 0] }), [0, 0, 0]), [5, -4, 0]);
  // KiCad's rotate is applied negated: z by 90 takes the model's +x to the footprint's -y.
  close(placePoint(modelMatrix({ ...part, rotation: 0 }, { rotate: [0, 0, 90] }), [1, 0, 0]), [5, -6, 0]);
  // About x by -90 (a VRML model's usual turn): the model's +y becomes the footprint's +z.
  close(placePoint(modelMatrix({ ...part, rotation: 0 }, { rotate: [-90, 0, 0] }), [0, 1, 0]), [5, -5, 1]);
  close(placePoint(modelMatrix({ ...part, rotation: 0 }, { scale: [2, 3, 4] }), [1, 1, 1]), [7, -2, 4]);
});
