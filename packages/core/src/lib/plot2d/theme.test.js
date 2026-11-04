import assert from "node:assert/strict";
import test from "node:test";

import { BOARD_PALETTES, boardPalette, itemColor, layerColor } from "./theme.js";

// sRGB to linear light, OKLab's hue, and WCAG's contrast ratio: what the light palette is chosen by.
const channels = (hex) => [1, 3, 5].map((at) => Number.parseInt(hex.slice(at, at + 2), 16) / 255);
const linear = (value) => (value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4);
const luminance = (hex) => { const [r, g, b] = channels(hex).map(linear); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const contrast = (a, b) => { const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
function hue(hex) {
  const [r, g, b] = channels(hex).map(linear);
  const [l, m, s] = [0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b, 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
    0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b].map(Math.cbrt);
  const a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s;
  const bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
  return { hue: (Math.atan2(bb, a) * 180 / Math.PI + 360) % 360, chroma: Math.hypot(a, bb) };
}
const OPAQUE = /^#[0-9a-f]{6}$/i;
// Every layer a board names, both coppers, the inner ones and what goes through the board.
const LAYERS = ["F.Cu", "B.Cu", ...Array.from({ length: 30 }, (_, at) => `In${at + 1}.Cu`), "F.SilkS", "B.SilkS", "F.Fab", "B.Fab",
  "F.CrtYd", "B.CrtYd", "F.Adhes", "B.Adhes", "Edge.Cuts", "Margin", "Dwgs.User", "Cmts.User", "Eco1.User", "Eco2.User",
  ...Array.from({ length: 9 }, (_, at) => `User.${at + 1}`), "vias", "drills"];

test("each theme draws on the app's own canvas: the light one on white, the dark one on its neutral grey", () => {
  assert.equal(boardPalette("light").background, "#FFFFFF");
  assert.equal(boardPalette("dark").background, "#292929");
  // Anything but light is dark, and without a theme the board is KiCad's own colours.
  assert.equal(boardPalette(undefined), BOARD_PALETTES.dark);
  assert.equal(layerColor("F.SilkS"), BOARD_PALETTES.dark.layer("F.SilkS"));
  assert.equal(itemColor("F.Cu", { t: "path" }), "#C83434");
});

test("the light palette is KiCad's, every opaque colour reading at 3:1 on white with its hue kept, the copper as it is", () => {
  const light = boardPalette("light"), dark = boardPalette("dark");
  for (const id of LAYERS) {
    const [was, is] = [dark.layer(id), light.layer(id)];
    assert.ok(OPAQUE.test(was) && OPAQUE.test(is), id);
    assert.ok(contrast(is, light.background) >= 3, `${id} ${is} reads on white: ${contrast(is, light.background).toFixed(2)}`);
    // A colour that already read is kept; one that did not keeps its hue (a grey has none to keep).
    if (contrast(was, "#FFFFFF") >= 3) assert.equal(is, was, `${id} already read on white`);
    else if (hue(was).chroma > 0.02) assert.ok(Math.abs(hue(is).hue - hue(was).hue) < 3, `${id} keeps its hue: ${hue(was).hue.toFixed(0)} -> ${hue(is).hue.toFixed(0)}`);
  }
  assert.deepEqual([light.layer("F.Cu"), light.layer("B.Cu")], ["#C83434", "#4D7FC4"], "KiCad's copper, red and blue");
  // The silkscreen's yellow turns ochre rather than vanishing.
  assert.ok(contrast(dark.layer("F.SilkS"), "#FFFFFF") < 1.5 && contrast(light.layer("F.SilkS"), "#FFFFFF") >= 3);
  for (const hole of Object.values(light.holes)) for (const color of [hole.fill, hole.wall].filter(Boolean)) {
    assert.ok(contrast(color, light.background) >= 3, `a hole's ${color} reads on white`);
  }
});

test("names on copper are light or dark against each theme's own copper", () => {
  for (const palette of Object.values(BOARD_PALETTES)) {
    for (const id of ["F.Cu", "B.Cu", "In1.Cu", "In8.Cu"]) {
      const light = palette.netname(id).startsWith("rgba(255");
      const [r, g, b] = channels(palette.layer(id));
      assert.equal(light, r * 0.299 + g * 0.587 + b * 0.117 <= 0.5, `${palette.scheme} ${id}`);
    }
  }
});
