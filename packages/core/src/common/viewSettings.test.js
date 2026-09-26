import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { buildModel, buildStepClipPlane } from "./cadScene.js";
import { resolveCadEdgeSettings } from "./cadInk.js";
import { applyMaterialSettingsToRecord as applyViewerMaterialSettings } from "../lib/viewer/surfaceMaterials.js";
import { resolveViewSceneSettings } from "./sceneSettings.js";
import { renderJobContext, modelOptionsForRenderJob } from "./renderMeshScene.js";
import { ALL_VIEW_FEATURES, EDGELESS_VIEW_FEATURES, normalizeViewSettings, resolveViewSettings, resetViewSettings, viewSettingsAreCustom, VIEW_PRESET_VALUES } from "./viewSettings.js";

test("grouped input stays sparse, canonicalizes colors and rejects old fields", () => {
  assert.deepEqual(normalizeViewSettings(), { mode: "solid" });
  assert.deepEqual(normalizeViewSettings({ floor: { color: "#AbC" } }), { mode: "solid", floor: { color: "#aabbcc" } });
  for (const input of [{ mode: null }, { mode: "shaded_edges" }, { render: {} }, { guides: {} }, { edges: { silhouette: true } }, { floor: null }, { clip: null }, { camera: { focalLength: 19 } }, { surfaces: { opacity: 2 } }]) {
    assert.throws(() => normalizeViewSettings(input));
  }
});

test("presets share independent groups, Render alone defaults to perspective", () => {
  for (const mode of VIEW_PRESET_VALUES) {
    const view = resolveViewSettings({ mode });
    assert.equal(view.camera.projection, mode === "render" ? "perspective" : "orthographic");
    assert.equal(viewSettingsAreCustom({ mode }), false);
  }
  assert.equal(resolveViewSettings({ mode: "solid", floor: { color: "#ffffff" } }).floor.enabled, true);
  const view = resolveViewSettings({ mode: "render", lighting: { enabled: false }, background: { enabled: false }, surfaces: { enabled: false }, edges: {} });
  assert.equal(view.lighting.enabled, false);
  assert.equal(view.floor.enabled, true);
  assert.equal(view.background.enabled, false);
  assert.equal(view.edges.enabled, true);
  assert.equal(view.surfaces.style, "shaded");
  assert.equal(view.surfaces.opacity, 1);
});

test("viewer preview and snapshot final are environment defaults, not custom overrides", () => {
  assert.equal(resolveViewSettings({ mode: "render" }).lighting.quality, "final");
  const options = { lightingQuality: "preview" };
  assert.equal(resolveViewSettings({ mode: "render" }, options).lighting.quality, "preview");
  assert.equal(viewSettingsAreCustom({ mode: "render" }, options), false);
  assert.equal(viewSettingsAreCustom({ mode: "render", lighting: { quality: "preview" } }, options), false);
  assert.equal(viewSettingsAreCustom({ mode: "render", lighting: { quality: "final" } }, options), true);
  assert.equal(resolveViewSceneSettings({ display: { mode: "render" }, ...options }).quality.id, "standard");
});

test("Axes and Grid share their default color in both appearances", () => {
  for (const appearance of ["light", "dark"]) {
    const view = resolveViewSettings({ appearance });
    assert.equal(view.axes.color, view.grid.color);
  }
});

test("Custom compares effective preset values and excludes model tools", () => {
  const tools = { clip: { enabled: true, offsets: { x: 0.2 } }, exploded: { enabled: true, amount: 0.5 } };
  assert.equal(viewSettingsAreCustom({ mode: "solid", ...tools }), false);
  assert.equal(viewSettingsAreCustom({ mode: "solid", surfaces: { opacity: 1 } }), false);
  assert.equal(viewSettingsAreCustom({ mode: "solid", appearance: "dark" }, { appearance: "dark" }), false);
  assert.equal(viewSettingsAreCustom({ mode: "solid", appearance: "dark" }), true);
  assert.equal(viewSettingsAreCustom({ mode: "solid", floor: { color: "#ff0000" } }), true);
  assert.deepEqual(resetViewSettings({ mode: "render", floor: { enabled: false }, ...tools }), { mode: "render" });
});

test("mixed capabilities retain neutral lights and background independently", () => {
  const floorOnly = resolveViewSceneSettings({ display: { floor: {} } });
  assert.equal(floorOnly.render.enabled, true);
  assert.equal(floorOnly.render.configuration.lighting.enabled, false);
  assert.ok(floorOnly.theme.lighting);
  assert.equal(floorOnly.render.configuration.backdrop.color, floorOnly.theme.background.solidColor);
  const custom = resolveViewSceneSettings({ display: { mode: "render", lighting: { enabled: false }, background: { opacity: 0.35 }, edges: { color: "#ff0000" } } });
  assert.equal(custom.camera.projection, "perspective");
  assert.equal(custom.render.configuration.backdrop.opacity, 0.35);
  assert.equal(custom.display.edges.color, "#ff0000");
  assert.equal(custom.display.edges.enabled, true);
  assert.ok(custom.theme.lighting);
});

test("snapshot public boundary rejects removed camera fields and explicit null display", () => {
  for (const job of [
    { display: null }, { display: { mode: "shaded" } },
    { camera: { projection: "perspective" } },
    { outputs: [{ camera: { focalLength: 85 } }] }
  ]) assert.throws(() => renderJobContext(mesh(), job));
});

test("public scalar clip reaches the correct geometric plane and inversion", () => {
  const bounds = { min: [-10, 2, 100], max: [30, 12, 200] };
  for (const invert of [false, true]) {
    const view = resolveViewSettings({ clip: { enabled: true, axis: "z", offset: 0.25, invert } });
    const plane = buildStepClipPlane(THREE, view.clip, bounds);
    assert.equal(plane.distanceToPoint(new THREE.Vector3(0, 0, 125)), 0);
    assert.equal(Math.sign(plane.distanceToPoint(new THREE.Vector3(0, 0, 150))), invert ? 1 : -1);
  }
  const neutral = resolveViewSettings({ clip: { enabled: true, axis: "z", offset: 1 } });
  assert.equal(buildStepClipPlane(THREE, neutral.clip, bounds), null, "maximum offset keeps the default side without a shader plane");
  const defaultZero = resolveViewSettings({ clip: { enabled: true, axis: "z", offset: 0 } });
  assert.equal(buildStepClipPlane(THREE, defaultZero.clip, bounds).distanceToPoint(new THREE.Vector3(0, 0, 150)), -50);
});

test("default grouped edges preserve the original class palette in both appearances", () => {
  for (const appearance of ["light", "dark"]) {
    const scene = resolveViewSceneSettings({ appearance });
    assert.deepEqual(resolveCadEdgeSettings(scene.display.edges).classes, resolveCadEdgeSettings().classes);
  }
});

function mesh() {
  return {
    vertices: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]), indices: new Uint32Array([0, 1, 2]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]), bounds: { min: [0, 0, 0], max: [1, 1, 0] },
    parts: [{ id: "part", vertexOffset: 0, vertexCount: 3, triangleOffset: 0, triangleCount: 1, bounds: { min: [0, 0, 0], max: [1, 1, 0] } }]
  };
}

test("draw bridge keeps surface opacity, edge visibility and edge color independent", () => {
  // Edges belong to a CAD model, so the job says it is one.
  const context = renderJobContext(mesh(), { kind: "step", display: { mode: "solid", surfaces: { opacity: 0.63 }, edges: { visibility: "visible", color: "#ff0000" } } });
  const model = buildModel(THREE, mesh(), { ...modelOptionsForRenderJob(context), edgeRendering: { mode: "basic" } });
  try {
    const record = model.displayRecords[0];
    assert.equal(record.material.opacity, 0.63);
    assert.equal(record.edgeMaterials[0].depthTest, true);
    assert.equal(record.edgeMaterials[0].color.getHexString(), "ff0000");
    const next = resolveViewSceneSettings({ display: { surfaces: { opacity: 0.4 }, edges: { visibility: "all", color: "#0000ff" } } });
    model.update({ displayMode: next.display.mode, surfaceSettings: next.view.surfaces, edgeSettings: next.display.edges });
    assert.equal(model.displayRecords[0].material.opacity, 0.4);
    assert.equal(model.displayRecords[0].edgeMaterials[0].depthTest, false);
    applyViewerMaterialSettings(THREE, model.displayRecords[0], model.runtime.materialSettings, {
      displayMode: next.display.mode, surfaceSettings: next.view.surfaces
    });
    assert.equal(model.displayRecords[0].material.opacity, 0.4, "viewer fallback follows the same grouped opacity");
  } finally { model.dispose(); }
});

test("hidden-line uses a depth-only surface; wireframe off and edges disabled draw neither", () => {
  for (const [display, colorWrite, depthWrite, edges] of [
    [{ mode: "hidden-line" }, false, true, true],
    [{ mode: "wireframe", edges: { enabled: false } }, false, false, false],
    [{ mode: "wireframe", surfaces: { enabled: false } }, true, true, true]
  ]) {
    const context = renderJobContext(mesh(), { kind: "step", display });
    const model = buildModel(THREE, mesh(), { ...modelOptionsForRenderJob(context), edgeRendering: { mode: "basic" } });
    try {
      assert.equal(model.displayRecords[0].material.colorWrite, colorWrite);
      assert.equal(model.displayRecords[0].material.depthWrite, depthWrite);
      assert.equal(Boolean(model.displayRecords[0].edges), edges);
    } finally { model.dispose(); }
  }
});

test("a file that is not a CAD model has no edges, explode or section, and shows an edge-made preset as Solid, without rewriting what was saved", () => {
  const saved = { mode: "wireframe", edges: { enabled: true, visibility: "all", color: "#ff0000" },
    clip: { enabled: true, axis: "x" }, exploded: { enabled: true, amount: 0.8 } };
  const step = resolveViewSettings(saved, { features: ALL_VIEW_FEATURES });
  assert.equal(step.mode, "wireframe");
  assert.equal(step.edges.enabled, true);
  const mesh = resolveViewSettings(saved, { features: EDGELESS_VIEW_FEATURES });
  assert.equal(mesh.mode, "solid");
  assert.equal(mesh.surfaces.style, resolveViewSettings({ mode: "solid" }).surfaces.style);
  assert.equal(mesh.edges.enabled, false);
  assert.equal(step.clip.enabled, true);
  assert.equal(step.exploded.enabled, true);
  assert.equal(mesh.clip.enabled, false);
  assert.equal(mesh.exploded.enabled, false);
  // Surfaces hidden or off leave a STEP model its edges; a mesh would be left with nothing.
  for (const style of ["hidden", "off"]) {
    assert.equal(resolveViewSettings({ mode: "solid", surfaces: { style } }, { features: ALL_VIEW_FEATURES }).surfaces.style, style);
    assert.equal(resolveViewSettings({ mode: "solid", surfaces: { style } }, { features: EDGELESS_VIEW_FEATURES }).surfaces.style, "shaded");
  }
  assert.equal(resolveViewSettings({ mode: "solid", surfaces: { style: "flat" } }, { features: EDGELESS_VIEW_FEATURES }).surfaces.style, "flat");
  // Render is not made of edges, and stays available.
  assert.equal(resolveViewSettings({ mode: "render" }, { features: EDGELESS_VIEW_FEATURES }).mode, "render");
  for (const mode of ["xray", "hidden-line"]) assert.equal(resolveViewSettings({ mode }, { features: EDGELESS_VIEW_FEATURES }).mode, "solid");
  assert.equal(normalizeViewSettings(saved).mode, "wireframe", "the saved settings still mean Wireframe on the next STEP file");
});

test("a view is resolved from the lists it opts into, one feature at a time", () => {
  const saved = { mode: "xray", edges: { enabled: true, visibility: "all" }, clip: { enabled: true, axis: "x" }, exploded: { enabled: true, amount: 0.5 } };
  const everything = resolveViewSettings(saved);
  assert.deepEqual(resolveViewSettings(saved, { features: ALL_VIEW_FEATURES }), everything);
  assert.deepEqual(resolveViewSettings(saved, { features: {} }), everything, "a list left out stands for the full set");
  const noClip = resolveViewSettings(saved, { features: { sections: ALL_VIEW_FEATURES.sections.filter(id => id !== "clip") } });
  assert.equal(noClip.clip.enabled, false);
  assert.equal(noClip.exploded.enabled, true);
  assert.equal(noClip.edges.enabled, true);
  assert.equal(noClip.mode, "xray");
  assert.equal(resolveViewSettings(saved, { features: { modes: ["solid", "render"] } }).mode, "solid");
  assert.deepEqual(EDGELESS_VIEW_FEATURES.sections, ["mode", "camera", "surfaces", "lighting", "background", "floor", "grid", "axes"]);
});


test("light Render separates a white background from the gray floor", () => {
  const view = resolveViewSettings({ mode: "render", appearance: "light" });
  assert.equal(view.background.color, "#ffffff");
  assert.equal(view.floor.color, "#e7e7e5");
  const scene = resolveViewSceneSettings({ display: { mode: "render", appearance: "light" } });
  assert.equal(scene.render.configuration.backdrop.color, "#ffffff");
  assert.equal(scene.render.configuration.backdrop.groundColor, "#e7e7e5");
  assert.equal(resolveViewSettings({ mode: "render", background: { color: "#abc123" } }).background.color, "#abc123");
});
