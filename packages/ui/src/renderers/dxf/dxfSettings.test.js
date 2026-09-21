import assert from "node:assert/strict";
import test from "node:test";

import {
  dxfFormatLength, dxfMaterialPreset, dxfParseLengthToMm, dxfSettingsRecord, dxfUnitOption,
  normalizeDxfBendRadiusMm, normalizeDxfKFactor, normalizeDxfOrientation, normalizeDxfThicknessMm,
  readDxfSettings, resetDxfModel
} from "./dxfSettings.js";

test("an empty record is the defaults: flat, millimetres, no stock, curved corners, 3D", () => {
  assert.deepEqual(readDxfSettings(null, 0), {
    thicknessMm: 0, bends: [], bendStyle: "curved", bendRadiusMm: 0, kFactor: 0.5,
    hiddenLayers: [], units: "mm", orientation: { x: 0, y: 0, z: 0 }, material: "none", view: "3d"
  });
});

test("a record is restored exactly, and nonsense in it is the default rather than an error", () => {
  const stored = {
    thicknessMm: 6, bends: [{ angleDeg: 90, direction: "down" }], bendStyle: "boxed", bendRadiusMm: 3,
    kFactor: 0.44, hiddenLayers: ["BEND"], units: "in", orientation: { x: 1, y: 0, z: 2 }, material: "brass", view: "2d"
  };
  assert.deepEqual(dxfSettingsRecord(readDxfSettings(stored, 1)), stored);
  const salvaged = readDxfSettings({ thicknessMm: "thick", bendStyle: "rounded", kFactor: 12, units: "furlongs", view: "4d" }, 0);
  assert.deepEqual([salvaged.thicknessMm, salvaged.bendStyle, salvaged.kFactor, salvaged.units, salvaged.view],
    [0, "curved", 0.9, "mm", "3d"]);
});

test("the bend rows are sized to the FILE, not to what the record remembers", () => {
  const stored = { bends: [{ angleDeg: 90, direction: "down" }, { angleDeg: 45, direction: "up" }] };
  assert.deepEqual(readDxfSettings(stored, 3).bends, [
    { angleDeg: 90, direction: "down" }, { angleDeg: 45, direction: "up" }, { angleDeg: 0, direction: "up" }
  ], "a bend the file gained opens flat");
  assert.deepEqual(readDxfSettings(stored, 1).bends, [{ angleDeg: 90, direction: "down" }]);
});

test("values are clamped to their ranges", () => {
  assert.deepEqual([normalizeDxfThicknessMm(-1), normalizeDxfThicknessMm(999), normalizeDxfThicknessMm(6.25)], [0, 25, 6.25]);
  assert.deepEqual([normalizeDxfBendRadiusMm(-2), normalizeDxfBendRadiusMm(99)], [0, 20]);
  assert.deepEqual([normalizeDxfKFactor(0), normalizeDxfKFactor(1)], [0.1, 0.9]);
  assert.deepEqual(normalizeDxfOrientation({ x: -1, y: 5, z: "2" }), { x: 3, y: 1, z: 2 });
});

test("Units convert at the input boundary only: the state stays millimetres", () => {
  const inches = dxfUnitOption("in");
  assert.equal(dxfFormatLength(25.4, inches), "1.00 in");
  assert.equal(Math.round(dxfParseLengthToMm("2 in", inches, 0) * 100) / 100, 50.8);
  assert.equal(dxfParseLengthToMm("nonsense", inches, 7), 7, "an unreadable entry keeps what was there");
});

test("Reset model restores the geometry, and leaves how it is being looked at alone", () => {
  const state = readDxfSettings({
    thicknessMm: 6, bends: [{ angleDeg: 90, direction: "down" }], hiddenLayers: ["CUT"],
    orientation: { x: 1, y: 2, z: 3 }, units: "in", material: "brass", view: "2d", bendStyle: "boxed"
  }, 1);
  const reset = resetDxfModel(state);
  assert.deepEqual([reset.thicknessMm, reset.bends, reset.hiddenLayers, reset.orientation],
    [0, [{ angleDeg: 0, direction: "up" }], [], { x: 0, y: 0, z: 0 }]);
  assert.deepEqual([reset.units, reset.material, reset.view, reset.bendStyle], ["in", "brass", "2d", "boxed"]);
});

test("a material preset carries the tint the sheet wears; None carries none", () => {
  assert.equal(dxfMaterialPreset("brass").colorHex, "#c9a94f");
  assert.equal(dxfMaterialPreset("none").colorHex, null);
  assert.equal(dxfMaterialPreset("not-a-material").value, "none");
});
