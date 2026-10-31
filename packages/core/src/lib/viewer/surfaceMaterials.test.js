import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import { createMaterialFillColor, readSourceColor, shapeSourceColor } from "./surfaceMaterials.js";

const EPSILON = 1e-6;

function assertNear(actual, expected, message = "") {
  assert.ok(Math.abs(actual - expected) < EPSILON, `${message} expected ${expected}, received ${actual}`);
}

function assertColorNear(color, expected, message = "") {
  assertNear(color.r, expected[0], `${message} r`);
  assertNear(color.g, expected[1], `${message} g`);
  assertNear(color.b, expected[2], `${message} b`);
}

test("source color helpers read and shape source colors consistently", () => {
  assert.equal(readSourceColor(THREE, "#abc").getHexString(), "aabbcc");
  assert.equal(readSourceColor(THREE, "not-a-color"), null);

  const source = new THREE.Color(0.2, 0.4, 0.6);
  const shaped = shapeSourceColor(THREE, source, {
    tintStrength: 0,
    saturation: 1,
    contrast: 1,
    brightness: 0.5
  });
  assertColorNear(shaped, [0.1, 0.2, 0.3], "shaped");
});

test("source color shaping preserves explicit zero-valued controls", () => {
  const source = new THREE.Color(0.2, 0.4, 0.6);
  const black = shapeSourceColor(THREE, source, { brightness: 0 });
  assertColorNear(black, [0, 0, 0], "zero brightness");

  const neutralContrast = shapeSourceColor(THREE, source, { contrast: 0 });
  assertColorNear(neutralContrast, [0.5, 0.5, 0.5], "zero contrast");

  const desaturated = shapeSourceColor(THREE, source, { saturation: 0 });
  assertNear(desaturated.r, desaturated.g, "zero saturation red/green");
  assertNear(desaturated.g, desaturated.b, "zero saturation green/blue");
});

test("a fill colour is the palette's at the part's place", () => {
  assert.equal(createMaterialFillColor(THREE, {
    defaultColor: "#445566",
    fillColors: ["#112233", "#aabbcc"],
    cycleColors: true
  }, 1).getHexString(), "aabbcc");
});
