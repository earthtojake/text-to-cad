import assert from "node:assert/strict";
import test from "node:test";
import { createViewSettingsStore } from "./viewSettingsStore.js";
import { createViewerRenderStateResolver } from "./renderState.js";

test("a mode and the grid compose, survive mode switches, and leave shared state alone", () => {
  const store = createViewSettingsStore({ camera: { focalLength: 80 }, clip: { enabled: true, at: 4 }, exploded: { enabled: true, amount: 0.4 } });
  store.setGrid(true);
  store.patchPreview({ lighting: { exposure: 1 } });
  const before = store.getSnapshot();
  assert.deepEqual([before.display.mode, before.display.grid, before.scene.view.grid.enabled], ["solid", true, true]);
  assert.equal(before.scene.view.lighting.exposure, 0);
  assert.equal(store.renderScene().view.lighting.exposure, 1);
  store.selectMode("xray");
  assert.equal(store.getSnapshot().scene.view.grid.enabled, true, "the grid is every mode's");
  store.selectMode("solid");
  assert.deepEqual(store.getSnapshot(), before);
  store.resetPreview();
  assert.deepEqual(store.getSnapshot().preview, {});
  for (const key of ["mode", "grid", "camera", "clip", "exploded"]) assert.deepEqual(store.getSnapshot().display[key], before.display[key]);
  assert.deepEqual(createViewSettingsStore(before.display, {}, before.preview).getSnapshot(), before);
  // A mode has nothing of its own to set.
  assert.throws(() => store.patch({ modes: { solid: { flat: true } } }), /Unsupported display fields: modes/);
});

test("Preview is no display mode: a file is never in it, and Preview resolves Render from the same display with its own settings", () => {
  assert.throws(() => createViewSettingsStore({ mode: "render" }), /display\.mode must be one of: solid, shaded, parts, xray, hidden-line, wireframe/);
  const store = createViewSettingsStore({ mode: "xray" });
  assert.throws(() => store.selectMode("render"), /display\.mode must be one of/);
  assert.throws(() => store.patch({ mode: "render" }), /display\.mode must be one of/);
  store.patchPreview({ lighting: { exposure: 1 } });
  const { display, scene } = store.getSnapshot();
  assert.deepEqual([display.mode, scene.view.mode, scene.render.enabled], ["xray", "xray", false]);
  const drawn = store.renderScene();
  assert.deepEqual([drawn.view.mode, drawn.view.lighting.exposure, drawn.render.enabled], ["render", 1, true]);
  assert.equal(store.getSnapshot().display, display, "asking for Preview's scene commits nothing");
  assert.throws(() => store.patchPreview({ grid: {} }), /Unsupported preview fields: grid/);
});

test("Preview edits preserve the scene and no-op mode, grid and reset actions publish nothing", () => {
  const store = createViewSettingsStore();
  const scene = store.getSnapshot().scene;
  store.patchPreview({ floor: { finish: "glossy" } });
  assert.equal(store.getSnapshot().scene, scene);
  store.resetPreview();
  let updates = 0;
  store.subscribe(() => updates++);
  store.selectMode("solid");
  store.setGrid(false);
  store.resetPreview();
  store.patch({ mode: "solid" });
  assert.equal(updates, 0);
  store.setGrid(true);
  store.setGrid(false);
  assert.deepEqual(store.getSnapshot().display, { mode: "solid" }, "a grid switched off is left unsaid");
});

test("Clip edits preserve all unrelated renderer inputs through both resolution stages", () => {
  for (const mode of ["solid", "xray"]) {
    const store = createViewSettingsStore({ mode });
    const resolve = createViewerRenderStateResolver();
    const before = store.getSnapshot();
    const oldRuntime = resolve({ themeSettings: before.scene.theme, displaySettings: before.scene.display });
    store.patch({ clip: { enabled: true, at: 0.4 } });
    const after = store.getSnapshot();
    const newRuntime = resolve({ themeSettings: after.scene.theme, displaySettings: after.scene.display });
    for (const name of ["theme", "camera", "render", "quality"]) assert.equal(after.scene[name], before.scene[name], name);
    assert.equal(newRuntime.themeSettings, oldRuntime.themeSettings);
    assert.equal(newRuntime.edgeSettings, oldRuntime.edgeSettings);
    for (const name of ["surfaces", "guides", "partColor", "exploded"]) assert.equal(newRuntime.displaySettings[name], oldRuntime.displaySettings[name], name);
    assert.notEqual(newRuntime.clipSettings, oldRuntime.clipSettings);
  }
});

test("Preview's lighting and floor edits leave the file's scene as it is, and no-op edits publish nothing", () => {
  const store = createViewSettingsStore();
  const before = store.getSnapshot();
  store.patchPreview({ lighting: { exposure: 0.7 }, floor: { opacity: 0.8 } });
  const after = store.getSnapshot();
  assert.equal(after.scene, before.scene);
  assert.deepEqual([store.renderScene().view.lighting.exposure, store.renderScene().view.floor.opacity], [0.7, 0.8]);
  let updates = 0;
  store.subscribe(() => updates++);
  store.patchPreview({ lighting: { exposure: 0.7 } });
  store.configure({ appearance: "light" });
  assert.equal(updates, 0);
  assert.equal(store.getSnapshot(), after);
});


