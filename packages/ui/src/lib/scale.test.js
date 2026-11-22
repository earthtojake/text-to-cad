import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

import { DESKTOP_SCALE, PHONE_SCALE } from "./scale.js";

// The script's numbers are the stylesheet's tokens: a desktop's `:root`, and the ONE phone switch.
test("the scale's numbers in script are the stylesheet's tokens, a desktop's and a phone's", () => {
  const css = readFileSync(new URL("../styles/globals.css", import.meta.url), "utf8");
  const block = selector => css.slice(css.indexOf(selector)).split("}")[0];
  const desktop = block(":root {\n  --cad-text-tiny"), phone = block(':root:has([data-viewer-layout="mobile"]:not([data-offscreen-picture] *)) {');
  const names = { control: "control", iconButton: "icon-button", row: "row", rowSm: "row-sm", glyph: "glyph", glyphSm: "glyph-sm", pad: "pad", step: "step", radiusControl: "radius-control",
    switchH: "switch-h", switchW: "switch-w", thumb: "thumb", check: "check" };
  for (const [scale, text] of [[DESKTOP_SCALE, desktop], [PHONE_SCALE, phone]]) {
    for (const [key, name] of Object.entries(names)) {
      const match = new RegExp(`--cad-${name}: (\\d+)px;`).exec(text);
      assert.ok(match, `--cad-${name} is set`);
      assert.equal(Number(match[1]), scale[key], `--cad-${name}`);
    }
    // Its text sizes: the type scale's steps (a desktop's in rem at 16px).
    const sizes = [...text.matchAll(/--cad-text-\w+: ([\d.]+)(px|rem);/g)].map(([, value, unit]) => Number(value) * (unit === "rem" ? 16 : 1));
    assert.deepEqual([...new Set(sizes)].sort((a, b) => a - b), [...scale.text], "the text sizes");
  }
});
