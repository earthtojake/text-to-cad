import assert from "node:assert/strict";
import test from "node:test";

import { APP_THEME_COLORS } from "./appTheme.js";
import { DEFAULT_VIEWPORT_BACKGROUND, normalizeViewportBackground, resolveViewportTheme } from "./viewportTheme.js";
import { resolveViewSceneSettings } from "../common/sceneSettings.js";

test("the viewport's Background is Light by default, its own whatever the app's theme; the old Follow theme reads as Light", () => {
  assert.equal(DEFAULT_VIEWPORT_BACKGROUND, "light");
  assert.equal(normalizeViewportBackground("purple"), "light");
  assert.deepEqual(resolveViewportTheme(undefined, "dark"), {
    background: "light", scheme: "light", canvas: APP_THEME_COLORS.light.canvas, gradient: ["#f4f5f6", "#dfe2e5"]
  });
  assert.deepEqual(resolveViewportTheme("dark", "light"), { background: "dark", scheme: "dark", canvas: APP_THEME_COLORS.dark.canvas, gradient: null });
  assert.equal(normalizeViewportBackground("theme"), "light");
  assert.deepEqual(resolveViewportTheme("theme", "dark"), resolveViewportTheme("light"));
});

test("a light viewport's scene stands on its gradient: the view's top and bottom are the pair's own colours, the stops past them", () => {
  const { theme } = resolveViewSceneSettings({ appearance: "light", canvas: ["#f4f5f6", "#dfe2e5"] });
  assert.equal(theme.background.type, "linear");
  assert.equal(theme.background.linearAngle, 90);
  assert.equal(theme.background.solidColor, "#dfe2e5");
  // Half a span past each end: the view's middle half runs from the top colour to the bottom one.
  assert.deepEqual([theme.background.linearStart, theme.background.linearEnd], ["#ffffff", "#d5d9dd"]);
  assert.equal(resolveViewSceneSettings({ appearance: "dark", canvas: "#1e1e1e" }).theme.background.type, "solid");
});
