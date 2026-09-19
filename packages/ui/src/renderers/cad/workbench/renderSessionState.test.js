import assert from "node:assert/strict";
import test from "node:test";
import { resolveSceneSettings } from "@hardcore/core/common/sceneSettings.js";

import {
  DEFAULT_RENDER_PAYLOAD,
  createRenderSessionState,
  renderCameraSeed,
  readRenderSessionCamera,
  renderSessionForEnabledChange,
  renderSessionForReset,
  renderVisualSettingsKey,
  resetRenderPayload,
  resolveRenderCameraSnapshot,
  resolveRenderSessionQuality,
  setRenderPayloadValue
} from "./renderSessionState.js";

test("mode switching preserves the live fitted camera before any camera-change event", () => {
  const bounds = { min: [0, 0, 0], max: [34000, 0, 18000] };
  const fitted = resolveRenderCameraSnapshot({
    projection: "orthographic", orthographicHalfHeight: 21033, zoom: 1.3
  }, bounds);
  const viewer = { getPerspective: () => fitted };
  for (const lastEvent of [null, { ...fitted, orthographicHalfHeight: 120 }]) {
    const enabled = renderSessionForEnabledChange(createRenderSessionState(), true, {
      activeCamera: readRenderSessionCamera(viewer, lastEvent)
    });
    const disabled = renderSessionForEnabledChange(enabled, false, {
      activeCamera: resolveRenderCameraSnapshot({ projection: "perspective" }, bounds)
    });
    assert.deepEqual(disabled.cadCamera, fitted);
    assert.equal(disabled.cadCamera.orthographicHalfHeight, 21033);
    assert.equal(disabled.cadCamera.zoom, 1.3);
    assert.equal(disabled.cadProjection, "orthographic");
  }
  assert.deepEqual(readRenderSessionCamera(null, fitted), fitted);
});

test("render sessions default to an off, sparse photographic setup", () => {
  const state = createRenderSessionState();

  assert.equal(state.enabled, false);
  assert.deepEqual(state.payload, DEFAULT_RENDER_PAYLOAD);
  assert.equal(state.cadProjection, "orthographic");
  assert.equal(state.cadCamera, null);
  assert.deepEqual(state.openSectionIds, ["render"]);
});

test("Render tab selection stays outside the photographic payload and starts at Studio on re-entry", () => {
  const session = createRenderSessionState({
    enabled: true,
    openSectionIds: ["materials", "pose", "animation", "display", "animation"],
    payload: { exposure: 0.5 }
  });
  assert.deepEqual(session.openSectionIds, ["pose", "animation"]);
  assert.deepEqual(session.payload, { exposure: 0.5 });
  assert.deepEqual(
    createRenderSessionState(JSON.parse(JSON.stringify(session))).openSectionIds,
    ["pose", "animation"]
  );
  const disabled = renderSessionForEnabledChange(session, false);
  assert.deepEqual(disabled.openSectionIds, ["pose", "animation"]);
  const reenabled = renderSessionForEnabledChange(disabled, true);
  assert.deepEqual(reenabled.openSectionIds, ["render"]);
  assert.equal(reenabled.payload.exposure, 0.5);
});

test("photographic edits write directly into the sparse public payload", () => {
  let payload = setRenderPayloadValue(DEFAULT_RENDER_PAYLOAD, ["lighting", "size"], 1.75);
  payload = setRenderPayloadValue(payload, ["backdrop", "transparent"], true);
  payload = setRenderPayloadValue(payload, ["exposure"], -0.7);

  assert.deepEqual(payload, {
    lighting: { size: 1.75 },
    backdrop: { transparent: true },
    exposure: -0.7
  });
});

test("reset clears every customization while preserving the live pose, not its Render lens", () => {
  const payload = resetRenderPayload({
    position: [10, 20, 30],
    target: [1, 2, 3],
    up: [0, 0, 1],
    zoom: 1.2,
    projection: "perspective",
    focalLength: 85
  });

  assert.deepEqual(payload, {
    camera: {
      position: [10, 20, 30],
      target: [1, 2, 3],
      up: [0, 0, 1],
      zoom: 1.2
    }
  });
});

test("reset preserves enablement and the saved CAD restore camera", () => {
  const cadCamera = {
    position: [10, 20, 30], target: [1, 2, 3], up: [0, 0, 1],
    projection: "orthographic", orthographicHalfHeight: 24
  };
  const renderCamera = {
    position: [50, 60, 70], target: [4, 5, 6], up: [0, 0, 1],
    projection: "perspective", focalLength: 90
  };
  const customized = createRenderSessionState({
    enabled: false,
    cadCamera,
    cadProjection: "orthographic",
    payload: { studio: "dark", quality: "preview", exposure: 1, camera: renderCamera }
  });

  const disabledReset = renderSessionForReset(customized, { activeCamera: renderCamera });
  assert.equal(disabledReset.enabled, false);
  assert.deepEqual(disabledReset.payload, {});
  assert.deepEqual(disabledReset.cadCamera, cadCamera);

  const enabledReset = renderSessionForReset({ ...customized, enabled: true }, { activeCamera: renderCamera });
  assert.equal(enabledReset.enabled, true);
  assert.deepEqual(enabledReset.cadCamera, cadCamera);
  assert.deepEqual(enabledReset.payload.camera, {
    position: renderCamera.position,
    target: renderCamera.target,
    up: renderCamera.up
  });
});

test("first enable saves the CAD camera without seeding Render composition from it", () => {
  const cadCamera = {
    position: [90, 80, 70], target: [9, 8, 7], up: [0, 0, 1], zoom: 1.4,
    projection: "orthographic", focalLength: 21, orthographicHalfHeight: 18
  };
  const first = renderSessionForEnabledChange(createRenderSessionState(), true, {
    activeCamera: cadCamera,
    activeProjection: "orthographic"
  });
  assert.equal(first.enabled, true);
  assert.deepEqual(first.cadCamera, cadCamera);
  assert.deepEqual(first.payload, {});

  const savedRenderCamera = {
    position: [30, 40, 50], target: [3, 4, 5], up: [0, 0, 1],
    projection: "perspective", focalLength: 75
  };
  const disabled = renderSessionForEnabledChange({ ...first, payload: { exposure: 1 } }, false, {
    activeCamera: savedRenderCamera
  });
  const reenabled = renderSessionForEnabledChange(disabled, true, { activeCamera: cadCamera });
  assert.deepEqual(reenabled.payload.camera, savedRenderCamera);
  assert.deepEqual(reenabled.cadCamera, cadCamera);
});

test("render camera seeds retain lens and framing without CAD projection or model metadata", () => {
  assert.deepEqual(renderCameraSeed({
    position: [10, 20, 30], target: [1, 2, 3], up: [0, 0, 1], zoom: 1.4,
    projection: "orthographic", focalLength: 72, orthographicHalfHeight: 42, modelKey: "old"
  }), {
    position: [10, 20, 30], target: [1, 2, 3], up: [0, 0, 1], zoom: 1.4,
    focalLength: 72, orthographicHalfHeight: 42
  });
});

test("camera presets and projection-only payloads resolve against current model bounds", () => {
  const bounds = { min: [0, 0, 0], max: [20, 40, 10] };
  const front = resolveRenderCameraSnapshot({ preset: "front", projection: "perspective", focalLength: 80 }, bounds);
  assert.deepEqual(front.target, [10, 20, 5]);
  assert.ok(front.position[1] < 20);
  assert.equal(front.projection, "perspective");
  assert.equal(front.focalLength, 80);

  assert.equal(resolveRenderCameraSnapshot({ projection: "orthographic" }, bounds).projection, "orthographic");
});

test("camera and quality changes retain the Render visual settings identity", () => {
  const base = { exposure: 0.5, lighting: { size: 1.2 }, backdrop: { ground: true } };
  assert.equal(
    renderVisualSettingsKey({ ...base, camera: { preset: "front" } }),
    renderVisualSettingsKey({ ...base, camera: { preset: "top" } })
  );
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
  const final = resolveRenderSessionQuality(createRenderSessionState({ enabled: true }));
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
    const resolve = (session) => resolveSceneSettings({ appearance, prefersDark, render: session.payload }).render.configuration;
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
