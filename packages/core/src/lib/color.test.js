import assert from "node:assert/strict";
import test from "node:test";

import { linearChannelToSrgbByte, linearRgbToHex, linearToSrgb, srgbToLinear } from "./color.js";

test("linearToSrgb and srgbToLinear are inverses", () => {
  for (let i = 0; i <= 100; i += 1) {
    const value = i / 100;
    assert.ok(Math.abs(srgbToLinear(linearToSrgb(value)) - value) < 1e-9, `linear ${value}`);
    assert.ok(Math.abs(linearToSrgb(srgbToLinear(value)) - value) < 1e-9, `srgb ${value}`);
  }
});

test("0 and 1 are fixed points -- which is why primaries hid the encoding bug", () => {
  assert.equal(linearChannelToSrgbByte(0), 0);
  assert.equal(linearChannelToSrgbByte(1), 255);
  assert.equal(linearRgbToHex([1, 0, 0, 1]), "#ff0000");
  // Everything between them moves. Naive round(value * 255) gives 0x80 here.
  assert.equal(linearChannelToSrgbByte(0.5), 188);
  assert.equal(linearRgbToHex([0.5, 0.5, 0.5]), "#bcbcbc");
});

test("linearRgbToHex clamps, drops alpha, and rejects short input", () => {
  assert.equal(linearRgbToHex([2, -1, 0.5, 0.25]), "#ff00bc");
  assert.equal(linearRgbToHex([0.5, 0.5]), null);
  assert.equal(linearRgbToHex(null), null);
});
