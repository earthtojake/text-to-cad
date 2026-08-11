import assert from "node:assert/strict";
import test from "node:test";

import {
  cloneThemePresetSettings,
  DEFAULT_FLOOR_GRID_SETTINGS,
  DEFAULT_THEME_PRESET_ID,
  DEFAULT_THEME_SETTINGS,
  getThemePresetIdForSettings,
  inferThemeSettingsSceneTone,
  MAX_FLOOR_GRID_DENSITY,
  THEME_COLOR_MODES,
  THEME_FLOOR_MODES,
  THEME_PRESETS,
  MAX_THEME_FILL_COLORS,
  normalizeThemeFillColors,
  normalizeThemeSettings,
  resolveThemeFillColor,
  resolveThemeSettingsBackdropColor,
  resolveThemeSettingsForColorMode,
  resolveSystemThemePresetId,
  themeSettingsSupportsSystemColorMode,
  SNAPSHOT_THEME_ID,
  normalizeThemePresetId,
  getThemePresetById,
  cloneThemeSettings
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

const BLUE_FILL_COLORS = Object.freeze(["#4cc9f0"]);
const MAGENTA_FILL_COLORS = Object.freeze(["#ff4faf"]);
const CLAY_FILL_COLORS = Object.freeze(["#b9856e"]);
const TERMINAL_FILL_COLORS = Object.freeze(["#073a20"]);
const DARKOAL_FILL_COLORS = Object.freeze([
  "#b6c4ce",
  "#c2a1a5",
  "#e6d1af",
  "#b0ab85",
  "#91ae86",
  "#7cab9f",
  "#7da5b9",
  "#8996be",
  "#988ebe",
  "#ad8dab"
]);

test("theme presets expose a default material color", () => {
  const blue = cloneThemePresetSettings("blue");
  const pink = cloneThemePresetSettings("pink");

  assert.equal(THEME_PRESETS.find((preset) => preset.id === "pink")?.label, "Magenta");
  assert.equal(blue.materials.defaultColor, "#4cc9f0");
  assert.deepEqual(blue.materials.fillColors, BLUE_FILL_COLORS);
  assert.equal(blue.materials.cycleColors, false);
  assert.equal(resolveThemeFillColor(blue.materials, 3), "#4cc9f0");
  assert.equal(pink.materials.defaultColor, "#ff4faf");
  assert.deepEqual(pink.materials.fillColors, MAGENTA_FILL_COLORS);
  assert.equal(pink.materials.cycleColors, false);
  assert.equal(resolveThemeFillColor(pink.materials, 3), "#ff4faf");
  assert.equal(getThemePresetIdForSettings(blue), "blue");
  assert.equal(getThemePresetIdForSettings(pink), "pink");
});

test("workbench ships as split light and dark presets", () => {
  assert.equal(DEFAULT_THEME_PRESET_ID, "workbench-light");
  assert.equal(THEME_PRESETS[0]?.id, "workbench-light");
  assert.equal(THEME_PRESETS[0]?.label, "Light");
  assert.equal(THEME_PRESETS[1]?.id, "workbench-dark");
  assert.equal(THEME_PRESETS[1]?.label, "Dark");
  assert.equal(getThemePresetIdForSettings(DEFAULT_THEME_SETTINGS), "workbench-light");
  assert.deepEqual(cloneThemePresetSettings("light"), cloneThemePresetSettings("workbench-light"));
  assert.deepEqual(cloneThemePresetSettings("workbench"), cloneThemePresetSettings("workbench-light"));
  assert.deepEqual(cloneThemePresetSettings("dark"), cloneThemePresetSettings("workbench-dark"));
});

test("workbench-light preset uses neutral material treatment while preserving source colors", () => {
  const cinematic = cloneThemePresetSettings("workbench-light");

  assert.equal(cinematic.colorMode, THEME_COLOR_MODES.LIGHT);
  assert.equal(cinematic.materials.defaultColor, "#b6c4ce");
  assert.deepEqual(cinematic.materials.fillColors, WORKBENCH_FILL_COLORS);
  assert.equal(cinematic.materials.cycleColors, false);
  assert.equal(resolveThemeFillColor(cinematic.materials, 3), "#b6c4ce");
  assert.equal(cinematic.materials.overrideSourceColors, false);
  assert.equal(cinematic.materials.tintMode, "blend");
  assert.equal(cinematic.materials.tintStrength, 0);
  assert.equal(cinematic.materials.saturation, 1.18);
  assert.equal(cinematic.materials.contrast, 1.12);
  assert.equal(cinematic.materials.brightness, 1.02);
  assert.equal(cinematic.materials.roughness, 0.58);
  assert.equal(cinematic.materials.clearcoat, 0.12);
  assert.equal(cinematic.materials.opacity, 1);
  assert.equal(cinematic.materials.envMapIntensity, 0.42);
  assert.equal(cinematic.materials.emissiveIntensity, 0.02);
  assert.equal(Object.hasOwn(cinematic, "edges"), false);
  assert.equal(cinematic.environment.enabled, false);
  assert.equal(cinematic.environment.intensity, 0.32);
  assert.equal(cinematic.background.type, "solid");
  assert.equal(cinematic.background.solidColor, "#f0f4f9");
  assert.equal(cinematic.background.linearStart, "#f0f4f9");
  assert.equal(cinematic.background.linearEnd, "#f0f4f9");
  assert.equal(cinematic.floor.mode, THEME_FLOOR_MODES.STAGE);
  assert.equal(cinematic.floor.enabled, false);
  // No stage floor plane, but a faint ground grid and an origin axis to read
  // part position against.
  assert.equal(cinematic.floor.grid.enabled, true);
  assert.equal(cinematic.floor.grid.opacity, 0.16);
  assert.equal(cinematic.floor.axis.enabled, true);
  assert.equal(cinematic.floor.followModel, true);
  assert.equal(cinematic.floor.reflectivity, 0.14);
  assert.equal(cinematic.lighting.toneMappingExposure, 1.16);
  assert.equal(cinematic.lighting.ambient.intensity, 0.4);
  assert.equal(cinematic.lighting.hemisphere.intensity, 1.12);
  // Flat theme: light and dark mode-color slots are identical (no per-variable split).
  assert.equal(cinematic.modeColors.light.background.linearStart, "#f0f4f9");
  assert.equal(cinematic.modeColors.dark.background.linearStart, "#f0f4f9");
  assert.equal(cinematic.modeColors.dark.floor.color, "#e2e9f0");
});

test("workbench-dark preset uses the workbench dark color treatment", () => {
  const dark = cloneThemePresetSettings("workbench-dark");

  assert.equal(THEME_PRESETS.some((preset) => preset.id === "dark"), false);
  assert.equal(dark.colorMode, THEME_COLOR_MODES.DARK);
  assert.equal(dark.materials.defaultColor, "#b6c4ce");
  assert.deepEqual(dark.materials.fillColors, WORKBENCH_FILL_COLORS);
  assert.equal(dark.materials.cycleColors, false);
  assert.equal(resolveThemeFillColor(dark.materials, 3), "#b6c4ce");
  assert.equal(Object.hasOwn(dark, "edges"), false);
  assert.equal(dark.background.type, "solid");
  assert.equal(dark.background.solidColor, "#181f28");
  assert.equal(dark.background.linearStart, "#242e3a");
  assert.equal(dark.background.linearEnd, "#0c1016");
  assert.equal(dark.background.radialInner, "#293443");
  assert.equal(dark.background.radialOuter, "#0c1016");
  assert.equal(dark.floor.color, "#202832");
  assert.equal(dark.lighting.spot.color, "#b3d4f2");
  assert.equal(dark.lighting.point.color, "#bfd8f0");
  assert.equal(dark.lighting.ambient.color, "#dfe7f0");
  assert.equal(dark.lighting.hemisphere.groundColor, "#333d4b");
  assert.equal(inferThemeSettingsSceneTone(dark), "dark");
  assert.equal(getThemePresetIdForSettings(dark), "workbench-dark");
});

test("vibrant ships as a bright photoreal stage after cinematic", () => {
  const vibrant = cloneThemePresetSettings("vibrant");
  const vibrantPreset = THEME_PRESETS.find((preset) => preset.id === "vibrant");

  assert.equal(THEME_PRESETS[3]?.id, "vibrant");
  assert.equal(vibrantPreset?.label, "Vibrant");
  assert.equal(vibrant.colorMode, THEME_COLOR_MODES.LIGHT);
  assert.equal(vibrant.projection, "perspective");
  // Vibrant shows off each model's own colors; the palette is kept but not cycled.
  assert.equal(vibrant.materials.cycleColors, false);
  assert.equal(vibrant.materials.fillColors.length > 1, true);
  assert.equal(vibrant.materials.overrideSourceColors, false);
  assert.equal(vibrant.materials.saturation, 1.32);
  assert.equal(vibrant.materials.clearcoat, 0.55);
  assert.equal(Object.hasOwn(vibrant, "edges"), false);
  assert.equal(vibrant.background.type, "radial");
  assert.equal(vibrant.background.solidColor, "#f2f4f7");
  assert.equal(vibrant.floor.mode, "stage");
  assert.equal(vibrant.floor.enabled, true);
  assert.equal(vibrant.floor.followModel, true);
  assert.equal(vibrant.environment.enabled, true);
  assert.equal(vibrant.environment.presetId, "studio-hdri-43");
  assert.equal(vibrant.lighting.rim.enabled, true);
  assert.equal(inferThemeSettingsSceneTone(vibrant), "light");
  assert.equal(getThemePresetIdForSettings(vibrant), "vibrant");
});

test("projection is a per-theme trait: canvases orthographic, stages perspective", () => {
  const orthographic = ["workbench-light", "workbench-dark"];
  const perspective = ["cinematic", "vibrant", "blue", "pink", "clay-sunrise", "terminal"];
  for (const id of orthographic) {
    assert.equal(cloneThemePresetSettings(id).projection, "orthographic", `${id} projection`);
  }
  for (const id of perspective) {
    assert.equal(cloneThemePresetSettings(id).projection, "perspective", `${id} projection`);
  }
  // Themes predating the setting normalize to the orthographic default.
  assert.equal(normalizeThemeSettings({}).projection, "orthographic");
  assert.equal(normalizeThemeSettings({ projection: "perspective" }).projection, "perspective");
  assert.equal(normalizeThemeSettings({ projection: "fisheye" }).projection, "orthographic");
});

test("themes stay edge-agnostic unless they opt into their own outline", () => {
  // Most themes carry no edges and leave the outline to per-file display
  // settings; Terminal is the exception and owns a neon-green outline.
  assert.equal(Object.hasOwn(cloneThemePresetSettings("workbench"), "edges"), false);
  assert.equal(Object.hasOwn(cloneThemePresetSettings("cinematic"), "edges"), false);
  assert.equal(Object.hasOwn(cloneThemePresetSettings("vibrant"), "edges"), false);
  assert.equal(Object.hasOwn(cloneThemePresetSettings("blue"), "edges"), false);

  const terminal = cloneThemePresetSettings("terminal");
  assert.equal(terminal.edges.enabled, true);
  assert.equal(terminal.edges.color, "#66ff99");

  // When a theme declares edges, they normalize through the display-edge
  // normalizer and survive on the theme.
  const withEdges = normalizeThemeSettings({
    ...cloneThemePresetSettings("workbench"),
    edges: { enabled: true, color: "#ABC" }
  });
  assert.equal(withEdges.edges.enabled, true);
  assert.equal(withEdges.edges.color, "#aabbcc");
});

test("built-in theme preset ids stay explicit with cinematic third", () => {
  assert.deepEqual(THEME_PRESETS.map((preset) => preset.id), [
    "workbench-light",
    "workbench-dark",
    "cinematic",
    "vibrant",
    "blue",
    "pink",
    "clay-sunrise",
    "terminal"
  ]);
});

test("cinematic ships as a real dark studio preset, not an alias", () => {
  const cinematicPreset = THEME_PRESETS.find((preset) => preset.id === "cinematic");
  const cinematic = cloneThemePresetSettings("cinematic");

  assert.equal(THEME_PRESETS[2]?.id, "cinematic");
  assert.equal(cinematicPreset?.label, "Cinematic");
  assert.notDeepEqual(cinematic, cloneThemePresetSettings("workbench-light"));
  assert.equal(cinematic.colorMode, THEME_COLOR_MODES.DARK);
  assert.equal(cinematic.materials.defaultColor, "#c9c2bb");
  assert.equal(cinematic.materials.cycleColors, false);
  assert.equal(cinematic.materials.overrideSourceColors, false);
  assert.equal(cinematic.materials.metalness, 0.32);
  assert.equal(cinematic.materials.clearcoat, 0.5);
  assert.equal(cinematic.materials.envMapIntensity, 1.5);
  assert.equal(cinematic.background.type, "radial");
  assert.equal(cinematic.background.radialOuter, "#0a0a0d");
  assert.equal(cinematic.floor.mode, THEME_FLOOR_MODES.STAGE);
  assert.equal(cinematic.floor.enabled, true);
  assert.equal(cinematic.floor.grid.enabled, true);
  assert.equal(cinematic.floor.followModel, true);
  assert.equal(cinematic.environment.enabled, true);
  assert.equal(cinematic.environment.presetId, "studio-hdri-43");
  assert.equal(cinematic.lighting.fill.enabled, true);
  assert.equal(cinematic.lighting.fill.color, "#a6a9ad");
  assert.equal(cinematic.lighting.rim.intensity, 1.3);
  assert.equal(inferThemeSettingsSceneTone(cinematic), "dark");
  assert.equal(getThemePresetIdForSettings(cinematic), "cinematic");
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

test("stylized presets keep their palettes and declare an opinionated color mode", () => {
  const paletteExpectations = [
    {
      presetId: "blue",
      colorMode: THEME_COLOR_MODES.DARK,
      materialColor: BLUE_FILL_COLORS[0],
      fillColors: BLUE_FILL_COLORS,
      cycleColors: false,
      backgroundColor: "#04131f",
      floorColor: "#062a42"
    },
    {
      presetId: "pink",
      colorMode: THEME_COLOR_MODES.DARK,
      materialColor: MAGENTA_FILL_COLORS[0],
      fillColors: MAGENTA_FILL_COLORS,
      cycleColors: false,
      backgroundColor: "#1d0a16",
      floorColor: "#2b0e20"
    },
    {
      presetId: "clay-sunrise",
      colorMode: THEME_COLOR_MODES.LIGHT,
      materialColor: CLAY_FILL_COLORS[0],
      fillColors: CLAY_FILL_COLORS,
      cycleColors: false,
      backgroundColor: "#f3eadc",
      floorColor: "#d9a97c"
    },
    {
      presetId: "terminal",
      colorMode: THEME_COLOR_MODES.DARK,
      materialColor: TERMINAL_FILL_COLORS[0],
      fillColors: TERMINAL_FILL_COLORS,
      cycleColors: false,
      backgroundColor: "#020403",
      floorColor: "#02120a",
      // Terminal ships a transparent grid floor (no solid stage) and owns a
      // neon-green outline, unlike the other stylized stages.
      floorEnabled: false,
      hasEdges: true
    }
  ];

  for (const expectation of paletteExpectations) {
    const settings = cloneThemePresetSettings(expectation.presetId);
    assert.equal(settings.colorMode, expectation.colorMode);
    assert.equal(settings.materials.defaultColor, expectation.materialColor);
    assert.deepEqual(settings.materials.fillColors, expectation.fillColors);
    assert.equal(settings.materials.cycleColors, expectation.cycleColors);
    assert.equal(Object.hasOwn(settings, "edges"), expectation.hasEdges === true);
    assert.equal(settings.background.solidColor, expectation.backgroundColor);
    assert.equal(settings.floor.color, expectation.floorColor);
    assert.equal(settings.floor.enabled, expectation.floorEnabled !== false, `${expectation.presetId} floor enabled`);
    // Terminal keeps its grid even with the solid floor disabled.
    if (expectation.floorEnabled === false) {
      assert.equal(settings.floor.grid.enabled, true, `${expectation.presetId} grid enabled`);
    }
    assert.equal(settings.projection, "perspective", `${expectation.presetId} projection`);
    assert.equal(getThemePresetIdForSettings(settings), expectation.presetId);
  }
});

test("fill color normalization keeps up to fifty colors and syncs the default fill", () => {
  assert.deepEqual(normalizeThemeFillColors(["#ABC", "nope", "#123456"], "#ffffff"), ["#aabbcc", "#123456"]);
  assert.deepEqual(normalizeThemeFillColors([], "#abc123"), ["#abc123"]);
  const fillColors = Array.from({ length: MAX_THEME_FILL_COLORS + 1 }, (_, index) => {
    return `#${String(index + 1).padStart(6, "0")}`;
  });

  const normalized = normalizeThemeSettings({
    ...cloneThemePresetSettings("dark"),
    materials: {
      ...cloneThemePresetSettings("dark").materials,
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

test("floor grid settings normalize as theme-owned controls", () => {
  const normalized = normalizeThemeSettings({
    floor: {
      mode: "grid",
      color: "#101820",
      gridCenter: "#123",
      gridCellColor: "#456789",
      gridOpacity: 2,
      gridDensity: 99
    }
  });

  assert.equal(normalized.floor.mode, THEME_FLOOR_MODES.GRID);
  assert.equal(normalized.floor.gridCenterColor, "#112233");
  assert.equal(normalized.floor.gridCellColor, "#456789");
  assert.equal(normalized.floor.gridOpacity, 1);
  assert.equal(normalized.floor.gridDensity, MAX_FLOOR_GRID_DENSITY);

  const fallback = normalizeThemeSettings({ floor: { color: "#111111" } });
  assert.notEqual(fallback.floor.gridCenterColor, DEFAULT_FLOOR_GRID_SETTINGS.gridCenterColor);
  assert.equal(fallback.floor.gridOpacity, DEFAULT_FLOOR_GRID_SETTINGS.gridOpacity);
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

test("backdrop color resolves the dominant background for glass tinting", () => {
  assert.equal(resolveThemeSettingsBackdropColor(cloneThemePresetSettings("workbench-light")), "#f0f4f9");
  assert.equal(resolveThemeSettingsBackdropColor(cloneThemePresetSettings("workbench-dark")), "#181f28");
  // Radial backgrounds resolve to the inner/outer midpoint.
  assert.equal(resolveThemeSettingsBackdropColor(cloneThemePresetSettings("cinematic")), "#121216");
});

test("system default preset follows the OS preference for the first-load pick", () => {
  assert.equal(resolveSystemThemePresetId({ prefersDark: false }), "workbench-light");
  assert.equal(resolveSystemThemePresetId({ prefersDark: true }), "workbench-dark");
});

test("scene tone is inferred from the dominant background color", () => {
  assert.equal(inferThemeSettingsSceneTone(cloneThemePresetSettings("workbench-light")), "light");
  assert.equal(inferThemeSettingsSceneTone(cloneThemePresetSettings("workbench-dark")), "dark");
  assert.equal(inferThemeSettingsSceneTone(cloneThemePresetSettings("workbench-dark")), "dark");
  assert.equal(inferThemeSettingsSceneTone(cloneThemePresetSettings("blue")), "dark");
  assert.equal(inferThemeSettingsSceneTone(cloneThemePresetSettings("clay-sunrise")), "light");
  // The background drives tone, not the floor: a dark-canvas theme reads dark
  // even when given a light floor color.
  assert.equal(inferThemeSettingsSceneTone({
    ...cloneThemePresetSettings("workbench-dark"),
    floor: {
      ...cloneThemePresetSettings("workbench-dark").floor,
      color: "#f8fafc"
    }
  }), "dark");
  // ...and a light-canvas theme reads light even with a dark floor color.
  assert.equal(inferThemeSettingsSceneTone({
    ...cloneThemePresetSettings("workbench-light"),
    floor: {
      ...cloneThemePresetSettings("workbench-light").floor,
      color: "#030914"
    }
  }), "light");
});

test("no built-in preset declares a system color mode", () => {
  assert.equal(themeSettingsSupportsSystemColorMode(cloneThemePresetSettings("workbench-light")), false);
  assert.equal(themeSettingsSupportsSystemColorMode(cloneThemePresetSettings("workbench-dark")), false);
  assert.equal(themeSettingsSupportsSystemColorMode(cloneThemePresetSettings("blue")), false);
  assert.equal(themeSettingsSupportsSystemColorMode(cloneThemePresetSettings("terminal")), false);
});

test("normalizeThemeSettings migrates legacy tint color into default color", () => {
  const normalized = normalizeThemeSettings({
    materials: {
      tintColor: "#abc123"
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
  const snapshot = cloneThemeSettings(SNAPSHOT_THEME_ID);
  const light = cloneThemeSettings("workbench-light");

  assert.equal(light.floor.grid.enabled, true, "workbench-light is the one WITH a grid");
  assert.equal(light.floor.axis.enabled, true);
  assert.equal(snapshot.floor.grid.enabled, false);
  assert.equal(snapshot.floor.axis.enabled, false);

  // Everything a part is made of is inherited unchanged, so it reads in a snapshot exactly
  // as it does in the viewer.
  assert.deepEqual(snapshot.materials, light.materials);
  assert.deepEqual(snapshot.background, light.background);
  assert.deepEqual(snapshot.lighting, light.lighting);
  assert.equal(snapshot.projection, light.projection);
});

test("the snapshot theme resolves by id but is never offered in the picker", () => {
  assert.equal(normalizeThemePresetId(SNAPSHOT_THEME_ID), SNAPSHOT_THEME_ID);
  assert.equal(getThemePresetById(SNAPSHOT_THEME_ID).id, SNAPSHOT_THEME_ID);
  // THEME_PRESETS is what the viewer's theme popover lists.
  assert.equal(THEME_PRESETS.some((preset) => preset.id === SNAPSHOT_THEME_ID), false);
});
