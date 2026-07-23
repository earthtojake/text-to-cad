import assert from "node:assert/strict";
import { test } from "node:test";
import { BASE_VIEWER_THEME, getViewerThemeValue } from "./stageTheme.js";

test("getViewerThemeValue prefers the viewer theme value when present", () => {
  assert.equal(getViewerThemeValue({ surface: "#ffffff" }, "surface", "#000000"), "#ffffff");
});

test("getViewerThemeValue falls back to the base viewer theme", () => {
  assert.equal(getViewerThemeValue({}, "surface", "#000000"), BASE_VIEWER_THEME.surface);
  assert.equal(getViewerThemeValue(null, "sceneBackground", "#000000"), BASE_VIEWER_THEME.sceneBackground);
});

test("getViewerThemeValue falls back to the provided default when key is unknown", () => {
  assert.equal(getViewerThemeValue({}, "unknownKey", "fallback-value"), "fallback-value");
});
