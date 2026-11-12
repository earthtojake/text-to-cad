import assert from "node:assert/strict";
import test from "node:test";

import { MASK_OPACITY, boardFinish, finishColor } from "./stackup.js";

// The stack-up of a black-and-gold board, as the plot's index carries it (the file's words).
const STACKUP = {
  layers: [
    { name: "F.SilkS", type: "Top Silk Screen", color: "White" },
    { name: "F.Mask", type: "Top Solder Mask", color: "Black", thickness: 0.01 },
    { name: "F.Cu", type: "copper", thickness: 0.035 },
    { name: "dielectric 1", type: "core", thickness: 1.51, material: "FR4" },
    { name: "B.Cu", type: "copper", thickness: 0.035 },
    { name: "B.Mask", type: "Bottom Solder Mask", color: "Red" }
  ],
  finish: "ENIG"
};

test("a stack-up's named colours are KiCad's 3D viewer's: black mask at its opacity, white silk, an ENIG board's gold", () => {
  const finish = boardFinish(STACKUP);
  assert.deepEqual(finish.sides.top, { mask: { color: "rgb(11, 11, 11)", opacity: MASK_OPACITY }, silk: "rgb(245, 245, 245)" });
  // The back names a red mask and no silkscreen layer: no silk is printed there.
  assert.deepEqual(finish.sides.bottom, { mask: { color: "rgb(181, 19, 21)", opacity: MASK_OPACITY }, silk: null });
  assert.equal(finish.copper, "rgb(178, 156, 0)");
  // The core names no colour: KiCad's default board body.
  assert.equal(finish.substrate, "rgb(110, 115, 77)");
});

test("a board that names no colour and no finish, or has no stack-up, is not drawn as made", () => {
  assert.equal(boardFinish(null), null);
  assert.equal(boardFinish({ layers: [{ name: "F.Mask", type: "Top Solder Mask" }, { name: "F.Cu", type: "copper" }] }), null);
  // A finish alone is enough: the rest takes KiCad's defaults (a green mask, near-white silk).
  const plain = boardFinish({ layers: [{ name: "F.Mask" }, { name: "F.SilkS" }], finish: "HAL SnPb" });
  assert.deepEqual(plain.sides.top, { mask: { color: "rgb(20, 51, 36)", opacity: MASK_OPACITY }, silk: "rgb(240, 240, 240)" });
  assert.equal(plain.sides.bottom.mask, null, "a side with no mask layer is bare");
  assert.equal(plain.copper, "rgb(160, 160, 160)");
});

test("colours written as #RRGGBBAA keep their own opacity, and dielectrics mix as KiCad mixes them", () => {
  const finish = boardFinish({ layers: [{ name: "F.Mask", color: "#1E3C8080" }, { name: "dielectric 1", color: "FR4 natural" },
    { name: "dielectric 2", color: "#FFFFFFFF" }] });
  assert.equal(finish.sides.top.mask.color, "rgb(30, 60, 128)");
  assert.ok(Math.abs(finish.sides.top.mask.opacity - 128 / 255) < 1e-9);
  // FR4 natural, then an opaque white over it by its transparency (none): the first stays, KiCad's Mix.
  assert.equal(finish.substrate, "rgb(109, 116, 75)");
});

test("the copper finish reads as KiCad reads its name", () => {
  assert.deepEqual(["ENIG", "ENEPIG", "Hard gold", "Immersion gold", "OSP", "HT_OSP", "HAL lead-free", "Immersion tin", "Immersion nickel",
    "Immersion silver", "None", null].map(finishColor), [
    "rgb(178, 156, 0)", "rgb(178, 156, 0)", "rgb(178, 156, 0)", "rgb(178, 156, 0)", "rgb(184, 115, 50)", "rgb(184, 115, 50)",
    "rgb(160, 160, 160)", "rgb(160, 160, 160)", "rgb(160, 160, 160)", "rgb(213, 213, 213)", "rgb(191, 156, 59)", "rgb(191, 156, 59)"]);
});
