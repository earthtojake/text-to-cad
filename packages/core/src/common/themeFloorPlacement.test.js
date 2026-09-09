// Floor placement is a floor-DEPENDENT theme trait (user decision 2026-08-30):
// `followModel` may only act when the theme's stage floor is enabled. With the
// floor off — the workbench engineering canvases, terminal's grid-only stage —
// placement is pinned to the true world z=0 plane so the model always reads
// against its authored coordinates, and no hidden setting can move the stage
// under the model. This pins the whole preset lineup so a new theme cannot
// reintroduce the leak silently.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  RENDER_ONLY_THEME_PRESETS,
  THEME_PRESETS,
  normalizeThemeSettings
} from "./themeSettings.js";

const ALL_PRESETS = [...THEME_PRESETS, ...RENDER_ONLY_THEME_PRESETS];

test("every preset couples followModel to its floor being enabled", () => {
  assert.ok(ALL_PRESETS.length >= 8, "the full theme lineup is under test");
  for (const preset of ALL_PRESETS) {
    const floor = normalizeThemeSettings(preset.settings).floor;
    if (floor.enabled !== true) {
      assert.equal(
        floor.followModel,
        false,
        `${preset.id}: followModel must be inert while the floor is disabled`
      );
    }
  }
});

test("workbench light/dark render at true coordinates: floor off, placement pinned", () => {
  for (const id of ["workbench-light", "workbench-dark"]) {
    const preset = ALL_PRESETS.find((entry) => entry.id === id);
    assert.ok(preset, `${id} preset exists`);
    const floor = normalizeThemeSettings(preset.settings).floor;
    assert.equal(floor.enabled, false, `${id}: workbench has no stage floor`);
    assert.equal(floor.followModel, false, `${id}: placement never follows the model`);
    assert.equal(floor.grid.enabled, true, `${id}: the reference grid stays on`);
  }
});

test("stage themes with a floor keep followModel available (default on)", () => {
  const stageThemes = ALL_PRESETS.filter(
    (preset) => normalizeThemeSettings(preset.settings).floor.enabled === true
  );
  assert.ok(stageThemes.length >= 4, "the presentation stages are under test");
  for (const preset of stageThemes) {
    const floor = normalizeThemeSettings(preset.settings).floor;
    assert.equal(
      floor.followModel,
      true,
      `${preset.id}: an enabled stage floor follows below-zero geometry by default`
    );
  }
});

test("disabling the floor makes an explicit followModel:true inert", () => {
  const floor = normalizeThemeSettings({
    floor: { enabled: false, followModel: true, grid: { enabled: true } }
  }).floor;
  assert.equal(floor.followModel, false);
  const enabled = normalizeThemeSettings({
    floor: { enabled: true, followModel: true }
  }).floor;
  assert.equal(enabled.followModel, true);
});
