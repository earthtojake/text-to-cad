import assert from "node:assert/strict";
import test from "node:test";

import {
  cloneThemePresetSettings,
  DEFAULT_FLOOR_GRID_SETTINGS,
  DEFAULT_THEME_PRESET_ID,
  DEFAULT_THEME_SETTINGS,
  getThemePresetIdForSettings,
  MAX_FLOOR_GRID_DENSITY,
  THEME_COLOR_MODES,
  THEME_FLOOR_MODES,
  THEME_PRESETS,
  MAX_THEME_FILL_COLORS,
  normalizeThemeFillColors,
  normalizeThemeSettings,
  resolveThemeFillColor,
  resolveThemeSettingsForColorMode,
  resolveSystemThemePresetId,
  themeSettingsSupportsSystemColorMode,
  SNAPSHOT_THEME_ID,
  normalizeThemePresetId,
  getThemePresetById
} from "./themeSettings.js";

const WORKBENCH_FILL_COLORS = Object.freeze([
  "#b6c4ce",
  "#f4a7a7",
  "#f8c77e",
  "#f7e38d",
  "#b9e88f",
  "#8fe3c0",
  "#92d7f5",
  "#a9b8ff",
  "#c7a8ff",
  "#f2a7d9"
]);

test("workbench ships as split light and dark presets", () => {
  assert.equal(DEFAULT_THEME_PRESET_ID, "workbench-light");
  assert.equal(THEME_PRESETS[0]?.id, "workbench-light");
  assert.equal(THEME_PRESETS[0]?.label, "Light");
  assert.equal(THEME_PRESETS[1]?.id, "workbench-dark");
  assert.equal(THEME_PRESETS[1]?.label, "Dark");
  assert.deepEqual(THEME_PRESETS.map((preset) => preset.id), ["workbench-light", "workbench-dark"]);
  assert.equal(getThemePresetIdForSettings(DEFAULT_THEME_SETTINGS), "workbench-light");
  // Only the preset ids themselves resolve; anything else falls to the default.
  assert.equal(normalizeThemePresetId("workbench"), "");
  assert.equal(normalizeThemePresetId("light"), "");
  assert.equal(normalizeThemePresetId("dark"), "");
  for (const retired of ["cinematic", "vibrant", "blue", "pink", "clay-sunrise", "terminal"]) {
    assert.equal(normalizeThemePresetId(retired), "", retired);
  }
});

test("workbench-light preset uses neutral material treatment while preserving source colors", () => {
  const light = cloneThemePresetSettings("workbench-light");

  assert.equal(light.colorMode, THEME_COLOR_MODES.LIGHT);
  assert.equal(light.materials.defaultColor, "#b6c4ce");
  assert.deepEqual(light.materials.fillColors, WORKBENCH_FILL_COLORS);
  assert.equal(light.materials.cycleColors, false);
  assert.equal(resolveThemeFillColor(light.materials, 3), "#b6c4ce");
  assert.equal(light.materials.overrideSourceColors, false);
  assert.equal(light.materials.tintMode, "blend");
  assert.equal(light.materials.tintStrength, 0);
  assert.equal(light.materials.saturation, 1.18);
  assert.equal(light.materials.contrast, 1.12);
  assert.equal(light.materials.brightness, 1.02);
  assert.equal(light.materials.roughness, 0.58);
  assert.equal(light.materials.clearcoat, 0.12);
  assert.equal(light.materials.opacity, 1);
  assert.equal(light.materials.envMapIntensity, 0.42);
  assert.equal(light.materials.emissiveIntensity, 0.02);
  assert.equal(Object.hasOwn(light, "edges"), false);
  assert.equal(light.environment.enabled, false);
  assert.equal(light.environment.intensity, 0.32);
  assert.equal(light.background.type, "solid");
  assert.equal(light.background.solidColor, "#f0f4f9");
  assert.equal(light.background.linearStart, "#f0f4f9");
  assert.equal(light.background.linearEnd, "#f0f4f9");
  assert.equal(light.floor.mode, THEME_FLOOR_MODES.STAGE);
  assert.equal(light.floor.enabled, false);
  assert.equal(Object.hasOwn(light.floor, "grid"), false);
  assert.equal(Object.hasOwn(light.floor, "axis"), false);
  // followModel is coupled to the floor: with the workbench stage floor
  // disabled it normalizes to false, so the grid stays the true z=0 plane.
  assert.equal(light.floor.followModel, false);
  assert.equal(light.floor.reflectivity, 0.14);
  assert.equal(light.lighting.toneMappingExposure, 1.16);
  assert.equal(light.lighting.ambient.intensity, 0.4);
  assert.equal(light.lighting.hemisphere.intensity, 1.12);
  // Flat theme: light and dark mode-color slots are identical (no per-variable split).
  assert.equal(light.modeColors.light.background.linearStart, "#f0f4f9");
  assert.equal(light.modeColors.dark.background.linearStart, "#f0f4f9");
  assert.equal(light.modeColors.dark.floor.color, "#e2e9f0");
});

test("workbench-dark changes the backdrop while preserving model materials and lighting", () => {
  const dark = cloneThemePresetSettings("workbench-dark");

  assert.equal(THEME_PRESETS.some((preset) => preset.id === "dark"), false);
  assert.equal(dark.colorMode, THEME_COLOR_MODES.DARK);
  assert.equal(dark.materials.defaultColor, "#b6c4ce");
  assert.deepEqual(dark.materials.fillColors, WORKBENCH_FILL_COLORS);
  assert.equal(dark.materials.cycleColors, false);
  assert.equal(resolveThemeFillColor(dark.materials, 3), "#b6c4ce");
  assert.equal(Object.hasOwn(dark, "edges"), false);
  assert.equal(dark.background.type, "solid");
  assert.equal(dark.background.solidColor, "#333333");
  assert.equal(dark.background.linearStart, "#3b3b3b");
  assert.equal(dark.background.linearEnd, "#2b2b2b");
  assert.equal(dark.background.radialInner, "#404040");
  assert.equal(dark.background.radialOuter, "#2b2b2b");
  assert.equal(dark.floor.color, "#383838");
  const light = cloneThemePresetSettings("workbench-light");
  assert.deepEqual(dark.materials, light.materials);
  assert.deepEqual(dark.lighting, light.lighting);
  assert.deepEqual(dark.environment, light.environment);
  assert.equal(getThemePresetIdForSettings(dark), "workbench-dark");
});

test("camera projection is not retained by normalized themes", () => {
  for (const id of THEME_PRESETS.map((preset) => preset.id)) {
    assert.equal(Object.hasOwn(cloneThemePresetSettings(id), "projection"), false, `${id} projection`);
  }
  assert.equal(Object.hasOwn(normalizeThemeSettings({ projection: "perspective" }), "projection"), false);
});

test("normalized themes never own CAD edge presentation", () => {
  for (const id of THEME_PRESETS.map((preset) => preset.id)) {
    assert.equal(Object.hasOwn(cloneThemePresetSettings(id), "edges"), false, `${id} edges`);
  }
  const withEdges = normalizeThemeSettings({
    ...cloneThemePresetSettings("workbench-light"),
    edges: { enabled: true, color: "#ABC" }
  });
  assert.equal(Object.hasOwn(withEdges, "edges"), false);
});

test("themes without fill and rim lights normalize to the viewer's legacy rig", () => {
  const normalized = normalizeThemeSettings({});

  assert.deepEqual(normalized.lighting.fill, {
    enabled: true,
    color: "#6b7f95",
    intensity: 0.46,
    position: { x: 120, y: 80, z: 210 }
  });
  assert.deepEqual(normalized.lighting.rim, {
    enabled: true,
    color: "#6db6e8",
    intensity: 0.04,
    position: { x: -260, y: 240, z: 180 }
  });

  const workbenchLight = cloneThemePresetSettings("workbench-light");
  const workbenchDark = cloneThemePresetSettings("workbench-dark");
  assert.deepEqual(workbenchLight.lighting.fill, normalized.lighting.fill);
  assert.deepEqual(workbenchLight.lighting.rim, normalized.lighting.rim);
  assert.deepEqual(workbenchDark.lighting.fill, normalized.lighting.fill);
  assert.deepEqual(workbenchDark.lighting.rim, normalized.lighting.rim);

  const customized = normalizeThemeSettings({
    lighting: {
      fill: { enabled: false, color: "#123456", intensity: 30, position: { x: 1, y: 2, z: 3 } },
      rim: { color: "not-a-color", intensity: -2 }
    }
  });
  assert.equal(customized.lighting.fill.enabled, false);
  assert.equal(customized.lighting.fill.color, "#123456");
  assert.equal(customized.lighting.fill.intensity, 20);
  assert.deepEqual(customized.lighting.fill.position, { x: 1, y: 2, z: 3 });
  assert.equal(customized.lighting.rim.color, "#6db6e8");
  assert.equal(customized.lighting.rim.intensity, 0);
});

test("fill color normalization keeps up to fifty colors and syncs the default fill", () => {
  assert.deepEqual(normalizeThemeFillColors(["#ABC", "nope", "#123456"], "#ffffff"), ["#aabbcc", "#123456"]);
  assert.deepEqual(normalizeThemeFillColors([], "#abc123"), ["#abc123"]);
  const fillColors = Array.from({ length: MAX_THEME_FILL_COLORS + 1 }, (_, index) => {
    return `#${String(index + 1).padStart(6, "0")}`;
  });

  const normalized = normalizeThemeSettings({
    ...cloneThemePresetSettings("workbench-dark"),
    materials: {
      ...cloneThemePresetSettings("workbench-dark").materials,
      defaultColor: "#111111",
      fillColors,
      cycleColors: true,
      overrideSourceColors: true
    }
  });

  assert.equal(normalized.materials.defaultColor, "#000001");
  assert.equal(normalized.materials.fillColors.length, MAX_THEME_FILL_COLORS);
  assert.equal(normalized.materials.fillColors.at(-1), "#000050");
  assert.equal(normalized.materials.cycleColors, true);
  assert.equal(normalized.materials.overrideSourceColors, true);
  assert.equal(resolveThemeFillColor(normalized.materials, 51), "#000002");
});

test("floor guides are dropped from normalized themes", () => {
  const normalized = normalizeThemeSettings({
    floor: {
      mode: "grid",
      color: "#101820",
      grid: {
        centerColor: "#123",
        cellColor: "#456789",
        opacity: 2,
        density: 99
      }
    }
  });

  assert.equal(normalized.floor.mode, THEME_FLOOR_MODES.GRID);
  assert.equal(Object.hasOwn(normalized.floor, "grid"), false);
  assert.equal(Object.hasOwn(normalized.floor, "axis"), false);
});

test("disabled color cycling preserves palettes without rotating fills", () => {
  const normalized = normalizeThemeSettings({
    materials: {
      defaultColor: "#111111",
      fillColors: ["#111111", "#222222", "#333333"],
      cycleColors: false
    }
  });

  assert.deepEqual(normalized.materials.fillColors, ["#111111", "#222222", "#333333"]);
  assert.equal(resolveThemeFillColor(normalized.materials, 0), "#111111");
  assert.equal(resolveThemeFillColor(normalized.materials, 2), "#111111");
});

test("system default preset follows the OS preference for the first-load pick", () => {
  assert.equal(resolveSystemThemePresetId({ prefersDark: false }), "workbench-light");
  assert.equal(resolveSystemThemePresetId({ prefersDark: true }), "workbench-dark");
});

test("a preset describes the scene and nothing outside it", () => {
  // A theme's reach ends at the render pane. It used to end further: the
  // luminance of the background above decided the app's light/dark chrome
  // (`inferThemeSettingsSceneTone`, deleted), so a dark scene could not be
  // looked at through a light window. Nothing here answers a question about
  // chrome, and the preset carries no field that only tinted it — `preview`
  // is a picture OF the scene, for the picker's swatch.
  for (const preset of THEME_PRESETS) {
    assert.deepEqual(
      Object.keys(preset).sort(),
      ["id", "label", "preview", "settings"],
      preset.id
    );
    assert.deepEqual(Object.keys(preset.preview).sort(), ["background", "modelColor"], preset.id);
  }
});

test("no built-in preset declares a system color mode", () => {
  assert.equal(themeSettingsSupportsSystemColorMode(cloneThemePresetSettings("workbench-light")), false);
  assert.equal(themeSettingsSupportsSystemColorMode(cloneThemePresetSettings("workbench-dark")), false);
});

test("normalizeThemeSettings reads only defaultColor and emits no tintColor field", () => {
  const normalized = normalizeThemeSettings({
    materials: {
      defaultColor: "#abc123",
      tintColor: "#ff0000"
    }
  });

  assert.equal(normalized.materials.defaultColor, "#abc123");
  assert.equal(Object.hasOwn(normalized.materials, "tintColor"), false);
});

test("built-in theme presets preserve source colors by default", () => {
  for (const preset of THEME_PRESETS) {
    assert.equal(
      preset.settings.materials.overrideSourceColors,
      false,
      `${preset.id} source color override default`
    );
  }
});

test("the snapshot theme is Workbench Light without the scene furniture", () => {
  // A snapshot is usually read by an agent rather than looked at. Workbench's ground grid
  // and origin axis are orientation you can ignore in a live viewport, and geometry-shaped
  // contrast in a still image: straight low-contrast lines crossing the model, at the same
  // weight as a real silhouette edge.
  const snapshot = cloneThemePresetSettings(SNAPSHOT_THEME_ID);
  const light = cloneThemePresetSettings("workbench-light");

  assert.equal(Object.hasOwn(light.floor, "grid"), false);
  assert.equal(Object.hasOwn(light.floor, "axis"), false);
  assert.equal(Object.hasOwn(snapshot.floor, "grid"), false);
  assert.equal(Object.hasOwn(snapshot.floor, "axis"), false);

  // Everything a part is made of is inherited unchanged, so it reads in a snapshot exactly
  // as it does in the viewer.
  assert.deepEqual(snapshot.materials, light.materials);
  assert.deepEqual(snapshot.background, light.background);
  assert.deepEqual(snapshot.lighting, light.lighting);
  assert.equal(Object.hasOwn(snapshot, "projection"), false);
});

test("the snapshot theme resolves by id but is never offered in the picker", () => {
  assert.equal(normalizeThemePresetId(SNAPSHOT_THEME_ID), SNAPSHOT_THEME_ID);
  assert.equal(getThemePresetById(SNAPSHOT_THEME_ID).id, SNAPSHOT_THEME_ID);
  // THEME_PRESETS is what the viewer's theme popover lists.
  assert.equal(THEME_PRESETS.some((preset) => preset.id === SNAPSHOT_THEME_ID), false);
});
