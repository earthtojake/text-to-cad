// The canvas is one colour from one definition, the `--canvas` token: core's written-out copy
// (`lib/appTheme.js`), the 2D views' colours (a board's palette, a drawing's fallback) and the
// 3D tools view's scene background all resolve to what the stylesheet declares, in each theme.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { APP_THEME_COLORS } from "@cad/core/lib/appTheme.js";
import { resolveViewSceneSettings } from "@cad/core/common/sceneSettings.js";
import { boardPalette } from "@cad/core/lib/plot2d/index.js";
import { cssColorToHex, resolveCanvasColor } from "../renderers/kit/look/canvasColor.js";
import { readDrawingThemeColors } from "../renderers/dxf/themeColors.js";

const tokens = await readFile(new URL("./tokens.css", import.meta.url), "utf8");
const declared = (selector) => {
  const block = tokens.slice(tokens.indexOf(`${selector} {`));
  return cssColorToHex(/--canvas:\s*([^;]+);/u.exec(block.slice(0, block.indexOf("}")))?.[1] ?? "");
};

for (const [scheme, selector] of [["light", ":root"], ["dark", ".dark"]]) {
  test(`in the ${scheme} theme every view's canvas is the --canvas token`, () => {
    const canvas = declared(selector);
    assert.match(canvas ?? "", /^#[0-9a-f]{6}$/u, `${selector} declares --canvas`);
    assert.equal(APP_THEME_COLORS[scheme].canvas, canvas, "core's written-out copy");
    assert.equal(boardPalette(scheme).background, canvas, "a board's canvas");
    assert.equal(readDrawingThemeColors(null, scheme).background, canvas, "a drawing's, with no token to read");
    const scene = resolveCanvasColor({ prefersDark: scheme === "dark" });
    assert.equal(scene, canvas, "the 3D canvas, with no token to read");
    assert.equal(resolveViewSceneSettings({ appearance: scheme, canvas: scene }).theme.background.solidColor, canvas,
      "the 3D tools view's scene");
  });
}
