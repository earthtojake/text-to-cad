import assert from "node:assert/strict";
import test from "node:test";
import { resolveViewSettings, viewSettingsAreCustom, VIEW_GROUP_KEYS } from "@hardcore/core/common/viewSettings.js";
import { createViewSettingsStore } from "./viewSettingsStore.js";
import { createViewerRenderStateResolver } from "../components/viewer/renderState.js";

test("successive control and agent actions compose atomically without writing resolved defaults", () => {
  const store = createViewSettingsStore({ mode: "render" });
  store.patch({ surfaces: { opacity: 0.65 } });
  store.setEnabled("clip", true);
  store.patch({ lighting: { exposure: 0.7 } });
  store.patch({ surfaces: { colorMode: "single", color: "#abcdef" } });
  const display = store.getSnapshot().display;
  assert.deepEqual(display.surfaces, { opacity: 0.65, colorMode: "single", color: "#abcdef" });
  assert.deepEqual(display.lighting, { exposure: 0.7 });
  assert.equal(display.clip.enabled, true);
  assert.equal(Object.hasOwn(display, "floor"), false);
  assert.equal(display.mode, "render");
  assert.equal(viewSettingsAreCustom(display), true);
  const restored = createViewSettingsStore(display);
  assert.deepEqual(restored.getSnapshot(), store.getSnapshot());
});

test("enable is idempotent, and every gate discards its old values including Clip", () => {
  const store = createViewSettingsStore({ floor: { opacity: 0.8 }, clip: { enabled: true, offsets: { x: 0.4 }, invert: true } });
  let updates = 0;
  store.subscribe(() => updates++);
  store.setEnabled("floor", true);
  store.setEnabled("clip", true);
  assert.equal(updates, 0);
  store.setEnabled("floor", false);
  assert.deepEqual(store.getSnapshot().display.floor, { enabled: false });
  store.setEnabled("floor", true);
  assert.equal(store.getSnapshot().scene.view.floor.opacity, 0.6);
  store.setEnabled("clip", false);
  store.setEnabled("clip", true);
  assert.equal(store.getSnapshot().scene.view.clip.offsets.x, 0.5);
  assert.equal(store.getSnapshot().scene.view.clip.invert, false);
});

test("every disabled group reopens with preset defaults, including restored stale values", () => {
  const edits = {
    camera: { projection: "perspective", focalLength: 90 },
    surfaces: { colorMode: "single", color: "#abcdef", opacity: 0.4 },
    edges: { visibility: "all", color: "#abcdef" },
    lighting: { exposure: 2, rotation: 45, fill: 0.8 },
    background: { color: "#abcdef", opacity: 0.3 },
    floor: { placement: "lowest", color: "#abcdef", opacity: 0.9 },
    grid: { color: "#abcdef", opacity: 0.9 },
    axes: { color: "#abcdef", opacity: 0.9 },
    clip: { offsets: { x: 0.4, z: 0.7 }, invert: true },
    exploded: { amount: 0.7 }
  };
  for (const mode of ["solid", "render"]) {
    for (const group of [...VIEW_GROUP_KEYS, "clip", "exploded"]) {
      const store = createViewSettingsStore({ mode, [group]: { ...edits[group], enabled: true } });
      store.setEnabled(group, false);
      assert.deepEqual(store.getSnapshot().display[group], { enabled: false });
      assert.equal(store.getSnapshot().scene.view[group].enabled, false);
      store.setEnabled(group, true);
      const expected = resolveViewSettings({ mode, [group]: { enabled: true } })[group];
      assert.deepEqual(store.getSnapshot().scene.view[group], expected, `${mode}/${group}`);
      store.restore({ mode, [group]: { ...edits[group], enabled: false } });
      store.setEnabled(group, true);
      assert.deepEqual(store.getSnapshot().scene.view[group], expected, `restored ${mode}/${group}`);
    }
  }
});

test("preset selection preserves tools; Reset disables them", () => {
  const store = createViewSettingsStore({ clip: { enabled: true, offsets: { z: 0.3 } }, exploded: { enabled: true, amount: 0.4 } });
  const tools = store.getSnapshot().display;
  store.patch({ camera: { projection: "perspective" }, surfaces: { opacity: 0.5 } });
  store.selectPreset("solid");
  assert.equal(store.getSnapshot().scene.camera.projection, "orthographic");
  assert.equal(viewSettingsAreCustom(store.getSnapshot().display), false);
  assert.deepEqual(store.getSnapshot().display, tools);
  store.selectPreset("render");
  store.patch({ lighting: { exposure: 1 } });
  store.reset();
  assert.deepEqual(store.getSnapshot().display, { mode: "render" });
  assert.equal(store.getSnapshot().scene.camera.projection, "perspective");
});

test("Clip edits preserve all unrelated renderer inputs through both resolution stages", () => {
  for (const mode of ["solid", "render"]) {
    const store = createViewSettingsStore({ mode });
    const resolve = createViewerRenderStateResolver();
    const before = store.getSnapshot();
    const oldRuntime = resolve({ themeSettings: before.scene.theme, displaySettings: before.scene.display });
    store.patch({ clip: { enabled: true, offsets: { x: 0.4 } } });
    const after = store.getSnapshot();
    const newRuntime = resolve({ themeSettings: after.scene.theme, displaySettings: after.scene.display });
    for (const name of ["theme", "camera", "render", "quality"]) assert.equal(after.scene[name], before.scene[name], name);
    assert.equal(newRuntime.themeSettings, oldRuntime.themeSettings);
    assert.equal(newRuntime.edgeSettings, oldRuntime.edgeSettings);
    for (const name of ["surfaces", "guides", "partColor", "exploded"]) assert.equal(newRuntime.displaySettings[name], oldRuntime.displaySettings[name], name);
    assert.notEqual(newRuntime.clipSettings, oldRuntime.clipSettings);
  }
});

test("lighting and floor edits do not invalidate geometry settings, and no-op edits publish nothing", () => {
  const store = createViewSettingsStore({ mode: "render" });
  const before = store.getSnapshot();
  store.patch({ lighting: { exposure: 0.7 }, floor: { opacity: 0.8 } });
  const after = store.getSnapshot();
  assert.equal(after.scene.display, before.scene.display);
  assert.equal(after.scene.camera, before.scene.camera);
  let updates = 0;
  store.subscribe(() => updates++);
  store.patch({ lighting: { exposure: 0.7 } });
  store.configure({ appearance: "light" });
  assert.equal(updates, 0);
  assert.equal(store.getSnapshot(), after);
});


test("model-tool reset preserves exact Custom appearance and disables spatial tools", () => {
  const display = { mode: "render", camera: { projection: "orthographic" }, lighting: { exposure: 0.7 },
    clip: { enabled: true, offsets: { x: 0.5 } }, exploded: { enabled: true, amount: 0.75 } };
  const store = createViewSettingsStore(display);
  store.resetModelTools();
  assert.deepEqual(store.getSnapshot().display, { ...display, clip: { enabled: false }, exploded: { enabled: false } });
  assert.equal(store.getSnapshot().scene.view.clip.enabled, false);
  assert.equal(store.getSnapshot().scene.view.exploded.enabled, false);
});
