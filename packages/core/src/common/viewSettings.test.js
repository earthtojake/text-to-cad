import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { buildStepClipPlane } from "../lib/viewer/clipPlane.js";
import { resolveCadEdgeSettings } from "./cadInk.js";
import { resolveViewSceneSettings } from "./sceneSettings.js";
import { renderJobContext } from "./renderMeshScene.js";
import { DEFAULT_PART_COLOR_SETTINGS } from "./displaySettings.js";
import {
  ALL_VIEW_FEATURES, EDGELESS_VIEW_FEATURES, RENDER_FLOOR_PLACEMENT, STEP_PART_VIEW_FEATURES, VIEW_MODE_VALUES, normalizePreviewSettings,
  normalizeViewSettings, previewSettingsChanged, readPreviewSettings, readViewSettings, resolveViewSettings, scenePartCount,
  viewFeaturesForKind, viewGridDefaults
} from "./viewSettings.js";

const PREVIEW = { preview: true };

// What a snapshot job is resolved against: the scene's box.
const mesh = () => ({ bounds: { min: [0, 0, 0], max: [1, 1, 0] } });

test("input stays sparse and refuses what a display does not have", () => {
  assert.deepEqual(normalizeViewSettings(), { mode: "solid" });
  assert.deepEqual(normalizeViewSettings({ mode: "parts", grid: true }), { mode: "parts", grid: true });
  for (const [input, message] of [
    // Preview's look is no display mode: it is asked for on its own (`preview`).
    [{ mode: "render" }, /display\.mode must be one of: solid, shaded, parts, xray, hidden-line, wireframe/],
    [{ mode: "grid" }, /display\.mode must be one of/],
    [{ grid: "on" }, /display\.grid must be a boolean/],
    // A mode has no settings of its own, and Preview's are not the display's.
    [{ modes: { solid: { flat: true } } }, /Unsupported display fields: modes/],
    [{ preview: { floor: { finish: "glossy" } } }, /Unsupported display fields: preview/],
    [{ surfaces: {} }, /Unsupported display fields: surfaces/],
    [{ camera: { enabled: true } }, /Unsupported display\.camera fields: enabled/],
    [{ camera: { focalLength: 19 } }, /display\.camera\.focalLength/],
    [{ clip: null }, /clip/]
  ]) assert.throws(() => normalizeViewSettings(input), message);
});

test("a stored display keeps what this build reads and leaves out the rest, setting by setting", () => {
  const stored = { mode: "grid", modes: { solid: { flat: true } }, grid: true, clip: { enabled: true, at: 4 }, exploded: { amount: 2 } };
  assert.deepEqual(readViewSettings(stored), { mode: "solid", grid: true, clip: { enabled: true, at: 4 } });
  assert.deepEqual(readViewSettings(null), { mode: "solid" });
  assert.deepEqual(readPreviewSettings({ floor: { finish: "glossy" }, lighting: { exposure: 9 }, grid: {} }), { floor: { finish: "glossy" } });
});

test("Preview's settings are sparse, canonical and its own", () => {
  assert.deepEqual(normalizePreviewSettings({ floor: { color: "#AbC" } }), { floor: { color: "#aabbcc" } });
  for (const input of [{ grid: {} }, { background: { enabled: true } }, { floor: { finish: "shiny" } }, { lighting: { quality: "ultra" } }]) {
    assert.throws(() => normalizePreviewSettings(input));
  }
  assert.equal(previewSettingsChanged({}), false);
  assert.equal(previewSettingsChanged({ floor: { finish: "matte" } }), false, "a value at its default is no change");
  assert.equal(previewSettingsChanged({ floor: { finish: "glossy" } }), true);
});

test("each mode is its own look at its defaults; Preview, asked for on its own, alone is in perspective, whatever the camera says", () => {
  assert.deepEqual(VIEW_MODE_VALUES, ["solid", "shaded", "parts", "xray", "hidden-line", "wireframe"]);
  for (const mode of VIEW_MODE_VALUES) {
    const view = resolveViewSettings({ mode, camera: { projection: "orthographic" } });
    assert.deepEqual([view.mode, view.camera.projection], [mode, "orthographic"]);
    const previewed = resolveViewSettings({ mode, camera: { projection: "orthographic" } }, PREVIEW);
    assert.deepEqual([previewed.mode, previewed.camera.projection, previewed.edges.enabled], ["render", "perspective", false], `Preview over ${mode}`);
  }
  const look = mode => {
    const { surfaces, edges } = resolveViewSettings({ mode });
    return [surfaces.style, surfaces.colorMode, surfaces.opacity, edges.enabled, edges.visibility];
  };
  assert.deepEqual(look("solid"), ["shaded", "original", 1, true, "visible"]);
  assert.deepEqual(look("shaded"), ["shaded", "original", 1, false, "visible"]);
  assert.deepEqual(look("parts"), ["shaded", "by-part", 1, true, "visible"]);
  assert.deepEqual(look("xray"), ["shaded", "original", 0.22, true, "all"]);
  assert.deepEqual(look("hidden-line"), ["hidden", "original", 1, true, "visible"]);
  assert.deepEqual(look("wireframe"), ["off", "original", 1, true, "all"]);
  assert.deepEqual(resolveViewSettings({ mode: "parts" }).surfaces.colors, [...DEFAULT_PART_COLOR_SETTINGS.colors]);
  const preview = resolveViewSettings({}, PREVIEW);
  assert.deepEqual([preview.lighting.enabled, preview.background.enabled, preview.floor.enabled, preview.edges.enabled], [true, true, true, false]);
  assert.equal(resolveViewSettings({}, { ...PREVIEW, previewSettings: { floor: { enabled: false } } }).floor.enabled, false);
  assert.equal(resolveViewSettings({ mode: "solid" }, { previewSettings: { lighting: { exposure: 1 } } }).lighting.enabled, false,
    "Preview's settings draw nothing outside Preview");
});

test("viewer preview and snapshot final are environment defaults, not changes", () => {
  assert.equal(resolveViewSettings({}, PREVIEW).lighting.quality, "final");
  const options = { lightingQuality: "preview" };
  assert.equal(resolveViewSettings({}, { ...options, ...PREVIEW }).lighting.quality, "preview");
  assert.equal(previewSettingsChanged({ lighting: { quality: "preview" } }, options), false);
  assert.equal(previewSettingsChanged({ lighting: { quality: "final" } }, options), true);
  assert.equal(resolveViewSceneSettings({ display: {}, ...options, ...PREVIEW }).quality.id, "standard");
});

test("the grid is a switch every mode draws, off by default, the same measuring grid wherever it is on, and never in Preview", () => {
  for (const appearance of ["light", "dark"]) {
    const dark = appearance === "dark";
    const grid = { color: dark ? "#5d9ac0" : "#4ea8cc", opacity: dark ? 0.35 : 0.45, density: 1 };
    assert.deepEqual(viewGridDefaults(appearance), grid);
    for (const mode of VIEW_MODE_VALUES) {
      assert.deepEqual(resolveViewSettings({ mode }, { appearance }).grid, { enabled: false, ...grid }, `${mode} (${appearance})`);
      assert.deepEqual(resolveViewSettings({ mode, grid: true }, { appearance }).grid, { enabled: true, ...grid }, `${mode} on its grid (${appearance})`);
      assert.equal(resolveViewSettings({ mode, grid: true }, { appearance }).axes.enabled, false, "no axis guide");
    }
    assert.equal(resolveViewSettings({ grid: true }, { appearance, ...PREVIEW }).grid.enabled, false);
  }
  assert.equal(resolveViewSettings({ grid: true }, { features: EDGELESS_VIEW_FEATURES }).grid.enabled, true, "a view without edges has its grid");
});

test("hidden-line and wireframe edges are light on a dark backdrop", () => {
  for (const mode of ["hidden-line", "wireframe"]) {
    assert.equal(resolveViewSettings({ mode }, { appearance: "dark" }).edges.color, "#c9d3de");
    assert.equal(resolveViewSettings({ mode }).edges.color, "#253443");
  }
  assert.equal(resolveViewSettings({ mode: "solid" }, { appearance: "dark" }).edges.color, "#253443");
});

test("Preview's custom lighting and background keep CAD edges off", () => {
  const custom = resolveViewSceneSettings({ display: {}, ...PREVIEW, previewSettings: { background: { opacity: 0.35 } } });
  assert.equal(custom.camera.projection, "perspective");
  assert.equal(custom.render.configuration.backdrop.opacity, 0.35);
  assert.equal(custom.display.edges.enabled, false);
  assert.equal(custom.theme, null);
});

test("snapshot public boundary rejects removed camera fields and explicit null display", () => {
  for (const job of [
    { display: null }, { display: { mode: "grid" } }, { display: { mode: "render" } }, { preview: "yes" },
    { display: { modes: { render: {} } } },
    { camera: { projection: "perspective" } },
    { outputs: [{ camera: { focalLength: 85 } }] }
  ]) assert.throws(() => renderJobContext(mesh(), job));
});

test("a clip is placed at its coordinate in millimetres, else through the middle", () => {
  const bounds = { min: [-10, 2, 100], max: [30, 12, 200] };
  const modelOffset = new THREE.Vector3(5, 5, -150);
  for (const invert of [false, true]) {
    const view = resolveViewSettings({ clip: { axis: "z", at: 137.5, invert } });
    assert.equal(view.clip.enabled, true, "a supplied clip cuts");
    const plane = buildStepClipPlane(THREE, view.clip, bounds, modelOffset);
    assert.equal(plane.distanceToPoint(new THREE.Vector3(0, 0, 137.5 - 150)), 0);
    assert.equal(Math.sign(plane.distanceToPoint(new THREE.Vector3(0, 0, 160 - 150))), invert ? 1 : -1,
      "the lower side is kept unless inverted");
    const middle = buildStepClipPlane(THREE, resolveViewSettings({ clip: { axis: "z", invert } }).clip, bounds, modelOffset);
    assert.equal(middle.distanceToPoint(new THREE.Vector3(0, 0, 150 - 150)), 0);
  }
  const middleX = resolveViewSettings({ clip: {} }).clip;
  assert.equal(buildStepClipPlane(THREE, middleX, bounds).distanceToPoint(new THREE.Vector3(10, 0, 0)), 0, "{} halves it along x");
  assert.equal(resolveViewSettings({}).clip.enabled, false, "no clip at all is no clip");
  assert.equal(buildStepClipPlane(THREE, { axis: "z", at: 120 }, null).distanceToPoint(new THREE.Vector3(0, 0, 120)), 0,
    "a placed plane needs no bounds");
  assert.equal(buildStepClipPlane(THREE, { axis: "z", at: 0 }, bounds).distanceToPoint(new THREE.Vector3(0, 0, 150)), -150,
    "below the model it cuts everything away");
});

test("a plane that cuts nothing activates no clipping", () => {
  const bounds = { min: [-10, 2, 100], max: [30, 12, 200] };
  assert.equal(buildStepClipPlane(THREE, { axis: "z", at: 200 }, bounds), null, "at the top, keeping the lower side");
  assert.equal(buildStepClipPlane(THREE, { axis: "z", at: 250 }, bounds), null, "past the top");
  assert.equal(buildStepClipPlane(THREE, { axis: "z", at: 100, invert: true }, bounds), null, "at the bottom, inverted");
  assert.ok(buildStepClipPlane(THREE, { axis: "z", at: 200, invert: true }, bounds));
  assert.equal(buildStepClipPlane(THREE, { enabled: false, axis: "z", at: 150 }, bounds), null);
});

test("default grouped edges preserve the original class palette in both appearances", () => {
  for (const appearance of ["light", "dark"]) {
    const scene = resolveViewSceneSettings({ appearance });
    assert.deepEqual(resolveCadEdgeSettings(scene.display.edges).classes, resolveCadEdgeSettings().classes);
  }
});

test("a file that is not a CAD model has no edges, explode or section, and shows an edge-made mode as Solid, without rewriting what was saved", () => {
  const saved = { mode: "wireframe", grid: true, clip: { enabled: true, axis: "x" }, exploded: { enabled: true, amount: 0.8 } };
  const step = resolveViewSettings(saved, { features: ALL_VIEW_FEATURES });
  assert.equal(step.mode, "wireframe");
  assert.equal(step.edges.enabled, true);
  const mesh = resolveViewSettings(saved, { features: EDGELESS_VIEW_FEATURES });
  assert.equal(mesh.mode, "solid");
  assert.equal(mesh.surfaces.style, "shaded");
  assert.equal(mesh.edges.enabled, false, "Solid draws no edges where there are none");
  assert.equal(mesh.grid.enabled, true);
  assert.deepEqual([step.clip.enabled, step.exploded.enabled, mesh.clip.enabled, mesh.exploded.enabled], [true, true, false, false]);
  // Preview's look is not made of edges, and stays available.
  assert.equal(resolveViewSettings({}, { features: EDGELESS_VIEW_FEATURES, ...PREVIEW }).mode, "render");
  for (const mode of ["shaded", "xray", "hidden-line"]) assert.equal(resolveViewSettings({ mode }, { features: EDGELESS_VIEW_FEATURES }).mode, "solid");
  assert.equal(normalizeViewSettings(saved).mode, "wireframe", "the saved settings still mean Wireframe on the next STEP file");
});

test("what each kind of file offers: an engine document every mode, any other 3D file Solid, and Parts where it has several parts", () => {
  assert.equal(viewFeaturesForKind("xbf", { parts: 2 }), ALL_VIEW_FEATURES);
  assert.equal(viewFeaturesForKind("xbf", { parts: 1 }), STEP_PART_VIEW_FEATURES, "a part file has no Parts and no Explode");
  assert.deepEqual(STEP_PART_VIEW_FEATURES, { modes: ["solid", "shaded", "xray", "hidden-line", "wireframe"], settings: ["edges", "clip"] });
  assert.deepEqual(viewFeaturesForKind("stl", { parts: 1 }), { modes: ["solid"], settings: ["clip"] });
  assert.deepEqual(viewFeaturesForKind("3mf", { parts: 3 }), { modes: ["solid", "parts"], settings: ["clip"] });
  assert.deepEqual(viewFeaturesForKind("urdf", { parts: 4 }), { modes: ["solid", "parts"], settings: ["clip"] });
  assert.deepEqual(viewFeaturesForKind("glb", { parts: 5, explodeParts: 2 }), { modes: ["solid", "parts"], settings: ["clip", "exploded"] });
  assert.deepEqual(viewFeaturesForKind("glb", { parts: 5, explodeParts: 1 }).settings, ["clip"]);
  assert.equal(viewFeaturesForKind("dxf"), EDGELESS_VIEW_FEATURES);
  assert.deepEqual([scenePartCount({ meshCount: 3 }), scenePartCount({ partCount: 2 }), scenePartCount(null)], [3, 2, 0]);
  // A mesh's Parts colours its parts, with no edges to draw.
  const parts = resolveViewSettings({ mode: "parts" }, { features: viewFeaturesForKind("3mf", { parts: 3 }) });
  assert.deepEqual([parts.mode, parts.surfaces.colorMode, parts.edges.enabled], ["parts", "by-part", false]);
  assert.equal(resolveViewSettings({ mode: "parts" }, { features: viewFeaturesForKind("stl", { parts: 1 }) }).mode, "solid");
});

test("a view is resolved from the lists it opts into, one feature at a time", () => {
  const saved = { mode: "xray", clip: { enabled: true, axis: "x" }, exploded: { enabled: true, amount: 0.5 } };
  const everything = resolveViewSettings(saved);
  assert.deepEqual(resolveViewSettings(saved, { features: ALL_VIEW_FEATURES }), everything);
  assert.deepEqual(resolveViewSettings(saved, { features: {} }), everything, "a list left out stands for the full set");
  const noClip = resolveViewSettings(saved, { features: { settings: ALL_VIEW_FEATURES.settings.filter(id => id !== "clip") } });
  assert.deepEqual([noClip.clip.enabled, noClip.exploded.enabled, noClip.edges.enabled, noClip.mode], [false, true, true, "xray"]);
  assert.equal(resolveViewSettings(saved, { features: { modes: ["solid"] } }).mode, "solid");
  assert.deepEqual(EDGELESS_VIEW_FEATURES.modes, ["solid"]);
});

test("light Preview separates a white background from the gray floor", () => {
  const view = resolveViewSettings({ appearance: "light" }, PREVIEW);
  assert.equal(view.background.color, "#ffffff");
  assert.equal(view.floor.color, "#e7e7e5");
  const scene = resolveViewSceneSettings({ display: { appearance: "light" }, ...PREVIEW });
  assert.equal(scene.render.configuration.backdrop.color, "#ffffff");
  assert.equal(scene.render.configuration.backdrop.groundColor, "#e7e7e5");
  assert.equal(resolveViewSettings({}, { ...PREVIEW, previewSettings: { background: { color: "#abc123" } } }).background.color, "#abc123");
});

test("dark Preview is a charcoal studio, not a black void: background and floor share one charcoal", () => {
  const view = resolveViewSettings({ appearance: "dark" }, PREVIEW);
  assert.equal(view.background.color, "#202226");
  assert.equal(view.floor.color, "#202226");
  const scene = resolveViewSceneSettings({ display: { appearance: "dark" }, ...PREVIEW });
  assert.equal(scene.render.configuration.backdrop.color, "#202226");
  assert.equal(scene.render.configuration.backdrop.groundColor, "#202226");
});

test("the floor is matte until Glossy is chosen, and a snapshot's Preview is the viewer's at its defaults", () => {
  const glossy = { floor: { finish: "glossy" } };
  assert.equal(resolveViewSettings({}, PREVIEW).floor.finish, "matte");
  assert.equal(resolveViewSettings({}, { ...PREVIEW, previewSettings: glossy }).floor.finish, "glossy");
  assert.equal(previewSettingsChanged(glossy), true);
  // The viewer's Preview, nothing changed, and a snapshot's `preview` resolve through the same recipe.
  const viewer = resolveViewSceneSettings({ display: {}, ...PREVIEW }).render.configuration.backdrop;
  const snapshot = renderJobContext(mesh(), { kind: "xbf", display: {}, ...PREVIEW }).sceneSettings.render.configuration.backdrop;
  assert.equal(snapshot.groundFinish, "matte");
  assert.deepEqual(snapshot, viewer);
});

test("Preview's floor stands at the model's lowest point until Model origin is chosen, and a snapshot's stands where the viewer's does", () => {
  assert.equal(RENDER_FLOOR_PLACEMENT, "lowest");
  for (const appearance of ["light", "dark"]) assert.equal(resolveViewSettings({}, { appearance, ...PREVIEW }).floor.placement, "lowest");
  const origin = { floor: { placement: "origin" } };
  assert.equal(previewSettingsChanged(origin), true);
  assert.equal(resolveViewSceneSettings({ display: {}, ...PREVIEW, previewSettings: origin }).render.configuration.backdrop.groundPlacement, "origin");
  const viewer = resolveViewSceneSettings({ display: {}, ...PREVIEW }).render.configuration.backdrop;
  const snapshot = renderJobContext(mesh(), { kind: "xbf", display: {}, ...PREVIEW }).sceneSettings.render.configuration.backdrop;
  assert.deepEqual([viewer.groundPlacement, snapshot.groundPlacement], ["lowest", "lowest"]);
});
