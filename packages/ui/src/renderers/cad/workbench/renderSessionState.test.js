import assert from "node:assert/strict";
import test from "node:test";
import { resolveSceneSettings } from "@hardcore/core/common/sceneSettings.js";

import {
  DEFAULT_RENDER_PAYLOAD,
  createRenderSessionState,
  readRenderSessionCamera,
  renderSessionForEnabledChange,
  renderSessionForReset,
  renderVisualSettingsKey,
  resetRenderPayload,
  resolveRenderCameraSnapshot,
  resolveRenderSessionQuality,
  setRenderPayloadValue
} from "./renderSessionState.js";

test("mode switching keeps one live camera in both directions", () => {
  const bounds = { min: [0, 0, 0], max: [34000, 0, 18000] };
  const fitted = resolveRenderCameraSnapshot({
    projection: "orthographic", orthographicHalfHeight: 21033, zoom: 1.3
  }, bounds);
  const viewer = { getPerspective: () => fitted };
  const oldCamera = resolveRenderCameraSnapshot({ projection: "perspective", focalLength: 35 }, bounds);
  const enabled = renderSessionForEnabledChange(createRenderSessionState({ cadCamera: oldCamera }), true, {
    activeCamera: readRenderSessionCamera(viewer, null)
  });
  assert.deepEqual(enabled.cadCamera, fitted);
  assert.equal(enabled.cadProjection, "orthographic");

  const renderViewport = resolveRenderCameraSnapshot({
    position: [3, 4, 5], target: [1, 2, 3], projection: "perspective", focalLength: 80
  }, bounds);
  const disabled = renderSessionForEnabledChange(enabled, false, { activeCamera: renderViewport });
  assert.deepEqual(disabled.cadCamera, renderViewport);
  assert.equal(disabled.cadProjection, "perspective");
  assert.notDeepEqual(disabled.cadCamera, oldCamera);

  const reenabled = renderSessionForEnabledChange(disabled, true, { activeCamera: renderViewport });
  assert.deepEqual(reenabled.cadCamera, renderViewport);
  assert.deepEqual(readRenderSessionCamera(null, fitted), fitted);
});

test("render sessions default to an off, sparse photographic setup", () => {
  const state = createRenderSessionState();

  assert.equal(state.enabled, false);
  assert.deepEqual(state.payload, DEFAULT_RENDER_PAYLOAD);
  assert.equal(state.cadProjection, "orthographic");
  assert.equal(state.cadCamera, null);
  assert.equal(Object.hasOwn(state, "openSectionIds"), false);
});

test("mode-specific tab state is discarded", () => {
  const session = createRenderSessionState({
    enabled: true,
    openSectionIds: ["materials", "pose", "animation", "display", "animation"],
    payload: { exposure: 0.5 }
  });
  assert.equal(Object.hasOwn(session, "openSectionIds"), false);
  assert.deepEqual(session.payload, { quality: "preview", exposure: 0.5 });
  assert.equal(Object.hasOwn(createRenderSessionState(JSON.parse(JSON.stringify(session))), "openSectionIds"), false);
  const disabled = renderSessionForEnabledChange(session, false);
  const reenabled = renderSessionForEnabledChange(disabled, true);
  assert.equal(Object.hasOwn(reenabled, "openSectionIds"), false);
  assert.equal(reenabled.payload.exposure, 0.5);
});

test("enabled legacy sessions migrate payload.camera into the common camera", () => {
  const legacyCamera = {
    position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1],
    projection: "perspective", focalLength: 75
  };
  const migrated = createRenderSessionState({
    enabled: true,
    cadCamera: { ...legacyCamera, position: [0, 0, 1] },
    payload: { camera: legacyCamera, quality: "final", exposure: 0.25 }
  });
  assert.deepEqual(migrated.cadCamera, legacyCamera);
  assert.deepEqual(migrated.payload, { quality: "final", exposure: 0.25 });
  assert.equal(migrated.cadProjection, "perspective");
});

test("photographic edits write directly into the sparse public payload", () => {
  let payload = setRenderPayloadValue(DEFAULT_RENDER_PAYLOAD, ["lighting", "size"], 1.75);
  payload = setRenderPayloadValue(payload, ["backdrop", "transparent"], true);
  payload = setRenderPayloadValue(payload, ["exposure"], -0.7);

  assert.deepEqual(payload, {
    quality: "preview",
    lighting: { size: 1.75 },
    backdrop: { transparent: true },
    exposure: -0.7
  });
});

test("reset payload returns the sparse Preview default", () => {
  assert.deepEqual(resetRenderPayload(), { quality: "preview" });
});

test("reset preserves enablement and the common camera", () => {
  const commonCamera = {
    position: [10, 20, 30], target: [1, 2, 3], up: [0, 0, 1],
    projection: "orthographic", orthographicHalfHeight: 24
  };
  const customized = createRenderSessionState({
    enabled: false,
    cadCamera: commonCamera,
    cadProjection: "orthographic",
    payload: { quality: "final", exposure: 1 }
  });

  const disabledReset = renderSessionForReset(customized);
  assert.equal(disabledReset.enabled, false);
  assert.deepEqual(disabledReset.payload, { quality: "preview" });
  assert.deepEqual(disabledReset.cadCamera, commonCamera);

  const enabledReset = renderSessionForReset({ ...customized, enabled: true });
  assert.equal(enabledReset.enabled, true);
  assert.deepEqual(enabledReset.cadCamera, commonCamera);
  assert.deepEqual(enabledReset.payload, { quality: "preview" });
});

test("every mode transition records the current viewport instead of restoring an older camera", () => {
  const firstViewport = {
    position: [90, 80, 70], target: [9, 8, 7], up: [0, 0, 1], zoom: 1.4,
    projection: "orthographic", focalLength: 21, orthographicHalfHeight: 18
  };
  const first = renderSessionForEnabledChange(createRenderSessionState(), true, {
    activeCamera: firstViewport,
    activeProjection: "orthographic"
  });
  assert.equal(first.enabled, true);
  assert.deepEqual(first.cadCamera, firstViewport);
  assert.deepEqual(first.payload, { quality: "preview" });

  const secondViewport = {
    position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1],
    projection: "perspective", focalLength: 75
  };
  const disabled = renderSessionForEnabledChange({ ...first, payload: { exposure: 1 } }, false, {
    activeCamera: secondViewport
  });
  assert.deepEqual(disabled.cadCamera, secondViewport);
  assert.deepEqual(disabled.payload, { quality: "preview", exposure: 1 });
  const reenabled = renderSessionForEnabledChange(disabled, true, { activeCamera: secondViewport });
  assert.deepEqual(reenabled.cadCamera, secondViewport);
});

test("camera presets and projection-only specs resolve against current model bounds", () => {
  const bounds = { min: [0, 0, 0], max: [20, 40, 10] };
  const front = resolveRenderCameraSnapshot({ preset: "front", projection: "perspective", focalLength: 80 }, bounds);
  assert.deepEqual(front.target, [10, 20, 5]);
  assert.ok(front.position[1] < 20);
  assert.equal(front.projection, "perspective");
  assert.equal(front.focalLength, 80);

  assert.equal(resolveRenderCameraSnapshot({ projection: "orthographic" }, bounds).projection, "orthographic");
});

test("quality changes retain the Render visual settings identity", () => {
  const base = { exposure: 0.5, lighting: { size: 1.2 }, backdrop: { ground: true } };
  assert.equal(
    renderVisualSettingsKey({ ...base, quality: "preview" }),
    renderVisualSettingsKey({ ...base, quality: "final" })
  );
  assert.notEqual(renderVisualSettingsKey(base), renderVisualSettingsKey({ ...base, exposure: 1 }));
});

test("Render quality resolves independently from the photographic visual payload", () => {
  assert.equal(resolveRenderSessionQuality(createRenderSessionState()).id, "interactive");
  assert.equal(resolveRenderSessionQuality(createRenderSessionState({
    enabled: true,
    payload: { quality: "preview" }
  })).id, "standard");
  const final = resolveRenderSessionQuality(createRenderSessionState({
    enabled: true,
    payload: { quality: "final" }
  }));
  assert.equal(final.id, "high");
  assert.equal(final.targetPixelError, 0.25);
  assert.equal(final.snapshotLodLevel, 3);
  assert.equal(final.shadowMapSize, 4096);
  assert.equal(final.environmentMapSize, 512);
});


for (const [appearance, prefersDark, studio] of [
  ["light", false, "light"], ["dark", false, "dark"],
  ["system", true, "dark"], ["system", false, "light"]
]) {
  test(`Render defaults and Reset use global ${appearance} appearance (dark system: ${prefersDark})`, () => {
    const resolve = (session) => resolveSceneSettings({
      appearance,
      prefersDark,
      display: { mode: "render", render: session.payload }
    }).render.configuration;
    const initial = createRenderSessionState({ enabled: true, payload: { studio: "dark" } });
    assert.equal(Object.hasOwn(initial.payload, "studio"), false);
    assert.equal(resolve(initial).studio, studio);
    const edited = createRenderSessionState({
      ...initial, payload: { exposure: -1, backdrop: { color: "#123456" }, quality: "preview" }
    });
    const reentered = renderSessionForEnabledChange(renderSessionForEnabledChange(edited, false), true);
    assert.equal(resolve(reentered).backdrop.color, "#123456");
    assert.equal(resolve(reentered).exposure, -1);
    assert.deepEqual(resolve(renderSessionForReset(reentered)), resolve(initial));
  });
}
