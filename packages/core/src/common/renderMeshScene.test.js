import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import * as THREE from "three";

import {
  captureModel,
  disposeSnapshotSceneResources,
  projectedVisibleGeometryFrame,
  renderJobContext,
  resolveOutputCameraProjection,
  resolveOutputCameraSpec,
  snapshotStudioSamples
} from "./renderMeshScene.js";
import { headlessSceneDress, headlessSceneFamily, headlessSceneModel } from "./headlessScene.js";
import { buildGlbDocumentFromBuffer } from "../lib/render/glbMeshData.js";
import { fitCameraDepthToBounds } from "./renderOptions.js";
import { applyPhotographicStudio, disposePhotographicStudio } from "./photographicStudio.js";
import { PHOTOGRAPHIC_STUDIO_FRAME } from "./photographicStudioRig.js";

function twoPartMeshData() {
  return {
    vertices: new Float32Array([
      0, 0, 0,
      1, 0, 0,
      0, 1, 0,
      2, 0, 0,
      3, 0, 0,
      2, 1, 0
    ]),
    indices: new Uint32Array([0, 1, 2, 3, 4, 5]),
    normals: new Float32Array([
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1,
      0, 0, 1
    ]),
    bounds: {
      min: [0, 0, 0],
      max: [3, 1, 0]
    },
    partCount: 2,
    parts: [
      {
        id: "left",
        name: "Left",
        vertexOffset: 0,
        vertexCount: 3,
        triangleOffset: 0,
        triangleCount: 1,
        bounds: { min: [0, 0, 0], max: [1, 1, 0] }
      },
      {
        id: "right",
        name: "Right",
        vertexOffset: 3,
        vertexCount: 3,
        triangleOffset: 1,
        triangleCount: 1,
        bounds: { min: [2, 0, 0], max: [3, 1, 0] }
      }
    ]
  };
}

test("projectedVisibleGeometryFrame fits actual vertices instead of sparse bounds", () => {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array([
    -1, -1, 0,
    1, -1, 0,
    -1, 1, 0,
    1, 1, 0
  ]), 3));
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  mesh.updateWorldMatrix(true, false);
  const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, 0.01, 100);
  camera.position.set(0, 0, 10);
  camera.up.set(0, 1, 0);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);

  const frame = projectedVisibleGeometryFrame([{ mesh }], camera);

  assert.equal(frame.count, 4);
  assert.equal(frame.centerX, 0);
  assert.equal(frame.centerY, 0);
  assert.equal(frame.spanX, 2);
  assert.equal(frame.spanY, 2);
});

test("output projection echo follows the per-output camera decision", () => {
  const orthographicContext = { camera: { preset: "iso", projection: "orthographic" } };
  // Named preset inherits the canonical job camera projection.
  assert.equal(resolveOutputCameraProjection(orthographicContext, "iso"), "orthographic");
  // A position does not implicitly choose a lens; projection is authoritative.
  assert.equal(
    resolveOutputCameraProjection(orthographicContext, {
      position: [120, -90, 60],
      target: [0, 0, 0]
    }),
    "orthographic"
  );
  assert.equal(resolveOutputCameraProjection(orthographicContext, {
    position: [120, -90, 60],
    target: [0, 0, 0],
    projection: "perspective"
  }), "perspective");
  assert.equal(resolveOutputCameraProjection({ camera: { projection: "perspective" } }, "iso"), "perspective");
});

test("snapshot scene policy composes display Render quality with technical quality", () => {
  const normal = renderJobContext(twoPartMeshData(), {});
  assert.equal(normal.sceneSettings.render.enabled, false);
  assert.equal(normal.quality.id, "interactive");
  assert.equal(normal.quality.renderScale, 1);
  assert.equal(normal.displaySettings.guides.grid.enabled, false, "snapshot inherits the Solid preset, which draws no grid");
  assert.equal(normal.displaySettings.guides.axis.enabled, false, "and no axes");
  assert.equal(normal.sceneSettings.appearance, "light", "in light, the CLI's default");
  for (const mode of ["solid", "xray", "wireframe"]) {
    const gridded = renderJobContext(twoPartMeshData(), { kind: "xbf", display: { mode, grid: true } });
    assert.equal(gridded.displaySettings.guides.grid.enabled, true, `${mode} draws the grid switched on`);
    assert.equal(gridded.displaySettings.guides.grid.density, 1);
    assert.equal(gridded.displaySettings.guides.axis.enabled, false, "and no axes");
  }
  assert.equal(renderJobContext(twoPartMeshData(), { preview: true, display: { grid: true } }).displaySettings.guides.grid.enabled, false,
    "Preview draws no grid");

  const rendered = renderJobContext(twoPartMeshData(), { preview: true });
  assert.equal(rendered.sceneSettings.render.enabled, true);
  assert.equal(rendered.quality.id, "high");
  assert.equal(rendered.projection, "perspective");
  assert.equal(rendered.displayMode, "shaded");
  assert.equal(rendered.quality.renderScale, 2);
});

test("per-output views inherit the photographic lens without inheriting a conflicting pose", () => {
  const context = { camera: { projection: "perspective", focalLength: 85, position: [2, 3, 4], target: [0, 0, 0] } };
  assert.deepEqual(resolveOutputCameraSpec(context, "top"), {
    preset: "top", projection: "perspective", focalLength: 85
  });
  assert.deepEqual(resolveOutputCameraSpec(context, { preset: "front", focalLength: 35 }), {
    preset: "front", projection: "perspective", focalLength: 35
  });
});

test("Preview's photographic look is its own request, never a display mode, and rejects list mode", () => {
  for (const mode of ["list"]) {
    assert.throws(() => renderJobContext(twoPartMeshData(), { mode, preview: true }), /Preview supports only view mode/);
  }
  assert.throws(() => renderJobContext(twoPartMeshData(), { display: { mode: "render" } }), /display\.mode must be one of/);
  assert.throws(() => renderJobContext(twoPartMeshData(), { preview: "true" }), /preview must be a boolean/);
});

test("snapshot scene disposal releases owned stage resources without touching model resources", () => {
  const scene = new THREE.Scene();
  const modelRoot = new THREE.Group();
  const modelGeometry = new THREE.BoxGeometry(1, 1, 1);
  const modelMaterial = new THREE.MeshStandardMaterial();
  modelRoot.add(new THREE.Mesh(modelGeometry, modelMaterial));
  scene.add(modelRoot);

  const ownedTexture = new THREE.Texture();
  const stageGeometry = new THREE.PlaneGeometry(2, 2);
  const stageMaterial = new THREE.MeshBasicMaterial({ map: ownedTexture });
  scene.add(new THREE.Mesh(stageGeometry, stageMaterial));
  scene.environment = ownedTexture;
  let modelGeometryDisposals = 0;
  let modelMaterialDisposals = 0;
  let stageGeometryDisposals = 0;
  let stageMaterialDisposals = 0;
  let textureDisposals = 0;
  modelGeometry.dispose = () => { modelGeometryDisposals += 1; };
  modelMaterial.dispose = () => { modelMaterialDisposals += 1; };
  stageGeometry.dispose = () => { stageGeometryDisposals += 1; };
  stageMaterial.dispose = () => { stageMaterialDisposals += 1; };
  ownedTexture.dispose = () => { textureDisposals += 1; };

  assert.deepEqual(disposeSnapshotSceneResources(scene, modelRoot), {
    geometryCount: 1,
    materialCount: 1,
    textureCount: 1
  });
  assert.equal(stageGeometryDisposals, 1);
  assert.equal(stageMaterialDisposals, 1);
  assert.equal(textureDisposals, 1);
  assert.equal(modelGeometryDisposals, 0);
  assert.equal(modelMaterialDisposals, 0);
});

test("Preview accepts common camera, selection, clipping, and quality controls", () => {
  const context = renderJobContext(twoPartMeshData(), {
    kind: "xbf",
    camera: { preset: "front" },
    preview: true,
    display: {
      mode: "parts",
      camera: { projection: "orthographic" },
      clip: { enabled: true, axis: "x", at: 0.5 },
      exploded: { enabled: true, amount: 0.5 }
    },
    selection: { hiddenPartIds: ["right"], selectedPartIds: ["left"] },
    quality: { tessellation: { chordTolerance: 0.001 } }
  });
  assert.equal(context.camera.projection, "perspective");
  assert.equal(context.displaySettings.clip.enabled, true);
  assert.equal(context.sceneSettings.view.surfaces.colorMode, "original", "Preview's own part colours, not the display mode's");
});

test("only an engine document has edges; Clip cuts every 3D file and Explode an assembly or a GLB of several parts", () => {
  const display = { mode: "wireframe", clip: { enabled: true, axis: "x" }, exploded: { enabled: true, amount: 0.5 } };
  const step = renderJobContext(twoPartMeshData(), { kind: "xbf", display });
  assert.equal(step.sceneSettings.view.mode, "wireframe");
  assert.equal(step.displaySettings.clip.enabled, true);
  const view = (kind, parts = 0) => {
    const context = renderJobContext({ ...twoPartMeshData(), explodeParts: parts }, { kind, display });
    return [context.sceneSettings.view.mode, context.sceneSettings.view.edges.enabled, context.displaySettings.clip.enabled,
      context.displaySettings.exploded.enabled];
  };
  for (const kind of ["stl", "3mf", "glb", "urdf", "srdf", "sdf"]) assert.deepEqual(view(kind), ["solid", false, true, false], kind);
  assert.deepEqual(view("glb", 2), ["solid", false, true, true], "a GLB of several parts explodes");
  assert.deepEqual(view("dxf"), ["solid", false, false, false], "a drawing is no scene to cut");
});

// A GLB on the snapshot's stage, as the parity page holds it (`headlessScene.js`): cadgen's export
// of two boxes, a 20 mm base and a 10 mm rider beside it (`lib/render/fixtures/README.md`).
const glbJob = (extra = {}) => ({ resolved: { kind: "glb", url: "/__render_asset/pair.glb", inputPath: "/models/pair.glb" }, ...extra });

async function pairModel(context) {
  const bytes = readFileSync(new URL("../lib/render/fixtures/pair.glb", import.meta.url));
  const document = await buildGlbDocumentFromBuffer(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
  const scene = headlessSceneFamily(glbJob()).build(THREE, document);
  return headlessSceneModel(THREE, scene, headlessSceneDress(context.sceneSettings));
}

async function pairCapture(job) {
  const context = renderJobContext({ bounds: { min: [0, -20, 0], max: [40, 0, 20] }, partCount: 2, explodeParts: 2 }, job);
  const model = await pairModel(context);
  const scene = new THREE.Scene();
  scene.add(model.root);
  return { context, model, scene };
}

// A stub renderer: captureModel does everything except produce pixels, and the
// camera it leaves behind IS the frame the pixels would have been drawn with.
function stubViewport(model, scene) {
  return {
    scene, model, context: null, sceneBuildStarted: 0,
    ready: Promise.resolve(),
    orthographicCamera: new THREE.OrthographicCamera(),
    perspectiveCamera: new THREE.PerspectiveCamera(),
    renderer: {
      setSize() {}, getPixelRatio() { return 1; }, render() {},
      domElement: { width: 64, height: 64, toDataURL() { return "data:image/png;base64,AAAA"; } }
    }
  };
}

// The renderer a photographic studio configures, with only what captureModel and the studio touch.
function studioRendererStub() {
  const clearColor = new THREE.Color();
  let clearAlpha = 1;
  let target = null;
  return {
    toneMapping: THREE.NoToneMapping, toneMappingExposure: 1, outputColorSpace: THREE.LinearSRGBColorSpace,
    shadowMap: { enabled: false, type: null }, autoClear: true, sceneDraws: 0,
    getClearColor(target) { target.copy(clearColor); }, getClearAlpha() { return clearAlpha; },
    setClearColor(color, alpha) { clearColor.copy(color); clearAlpha = alpha; },
    getRenderTarget() { return target; }, setRenderTarget(next) { target = next; },
    getDrawingBufferSize(size) { return size.set(64, 64); },
    setSize() {}, getPixelRatio() { return 1; },
    render(scene) { if (scene.children.some((child) => child.name === "cadgen-photographic-studio")) this.sceneDraws += 1; },
    domElement: { width: 64, height: 64, toDataURL() { return "data:image/png;base64,AAAA"; } }
  };
}

test("a snapshot fits its camera's depth range in every preset, as the viewer fits its own", async () => {
  // The viewer draws every preset with ordinary depth fitted to the frame (useViewerRuntime); a
  // still fits the same planes from the same inputs.
  for (const projection of ["perspective", "orthographic"]) {
    const job = glbJob({ mode: "view", display: { mode: "solid", camera: { projection } },
      output: { tightFrame: false }, outputs: [{ path: "solid.png", width: 64, height: 64, camera: "iso" }] });
    const { context, model, scene } = await pairCapture(job);
    const viewport = { ...stubViewport(model, scene), context };
    try {
      const result = await captureModel(viewport, { job });
      assert.equal(result.outputs[0].projection, projection);
      const camera = projection === "perspective" ? viewport.perspectiveCamera : viewport.orthographicCamera;
      const viewer = camera.clone();
      viewer.near = 0.1;
      viewer.far = 50000;
      viewer.updateProjectionMatrix();
      const center = model.bounds.min.map((value, axis) => (value + model.bounds.max[axis]) / 2);
      fitCameraDepthToBounds(viewer, model.bounds, { placedObjects: model.placedObjects(), groundZ: null, pivot: center });
      assert.deepEqual([camera.near, camera.far], [viewer.near, viewer.far], projection);
    } finally {
      model.dispose();
    }
  }
});

test("an exploded Render snapshot keeps its floor and floor shadow on the rest placement, as the viewer does", async () => {
  const job = glbJob({ mode: "view", preview: true, display: { exploded: { enabled: true, amount: 1 } },
    outputs: [{ path: "exploded.png", width: 64, height: 64, camera: "iso" }] });
  const { context, model, scene } = await pairCapture(job);
  const configuration = context.sceneSettings.render.configuration;
  const studioOptions = { sceneScale: context.sceneScale, shadowMapSize: context.quality.shadowMapSize };
  const studioRuntime = { scene, renderer: studioRendererStub(), modelBounds: model.bounds };
  // renderModel's studio: the floor sized from the rest placement.
  applyPhotographicStudio(THREE, studioRuntime, configuration, { ...studioOptions, bounds: model.bounds, groundBounds: model.restBounds });
  const viewport = { ...stubViewport(model, scene), renderer: studioRuntime.renderer, context, studioRuntime,
    studioConfiguration: configuration };
  const viewer = { scene: new THREE.Scene(), renderer: studioRendererStub() };
  try {
    const rest = model.bounds;
    await captureModel(viewport, { job });
    assert.notDeepEqual(model.bounds, rest, "the parts were exploded");
    // The viewer's studio for the model exploded the same way: lit where the parts are, floored
    // where the model rests (ShellViewport: `groundBounds: runtime.zeroPoseBounds`).
    applyPhotographicStudio(THREE, viewer, configuration, { ...studioOptions, bounds: model.bounds, groundBounds: model.restBounds });
    const placement = (object) => [...object.position.toArray(), ...object.scale.toArray()];
    const snapshotStudio = studioRuntime.photographicStudio;
    assert.deepEqual(placement(snapshotStudio.ground), placement(viewer.photographicStudio.ground), "the floor");
    assert.deepEqual(placement(snapshotStudio.contactShadow.layer), placement(viewer.photographicStudio.contactShadow.layer),
      "and the shadow baked on it");
  } finally {
    disposePhotographicStudio(studioRuntime);
    disposePhotographicStudio(viewer);
    model.dispose();
  }
});

test("a snapshot drawn at a render scale above 1 spreads its floor's dither by it", async () => {
  // Final draws twice the pixels it keeps: each kept pixel averages four, and the dither
  // must be drawn twice as wide to survive that, or the dark floor's bands come back.
  const job = glbJob({ mode: "view", preview: true, outputs: [{ path: "final.png", width: 64, height: 64, camera: "iso" }] });
  const { context, model, scene } = await pairCapture(job);
  const configuration = context.sceneSettings.render.configuration;
  const renderer = { ...studioRendererStub(), getPixelRatio() { return context.quality.renderScale; } };
  const studioRuntime = { scene, renderer, modelBounds: model.bounds };
  applyPhotographicStudio(THREE, studioRuntime, configuration, {
    sceneScale: context.sceneScale, shadowMapSize: context.quality.shadowMapSize, bounds: model.bounds, groundBounds: model.restBounds
  });
  const viewport = { ...stubViewport(model, scene), renderer, context, studioRuntime, studioConfiguration: configuration };
  try {
    assert.equal(context.quality.renderScale, 2, "Final draws at twice the size it keeps");
    await captureModel(viewport, { job });
    assert.equal(renderer.sceneDraws, PHOTOGRAPHIC_STUDIO_FRAME.stillSamples, "a Render still converges over its frame's samples");
    const studio = studioRuntime.photographicStudio;
    assert.equal(studio.ground.material.defines?.STUDIO_DITHER_SCALE, "2.0000");
    assert.equal(studio.contactShadow.layer.material.defines?.STUDIO_DITHER_SCALE, "2.0000");
  } finally {
    disposePhotographicStudio(studioRuntime);
    model.dispose();
  }
});

test("capture diagnostics separate readiness, the scene's update, framing, draw submission and PNG readback", async (t) => {
  let clock = 0;
  t.mock.method(performance, "now", () => clock);
  const job = glbJob({
    mode: "view", output: { tightFrame: true },
    outputs: [{ path: "first.png", width: 64, height: 64, camera: "iso" },
      { path: "second.png", width: 64, height: 64, camera: "front" }]
  });
  const { context, model, scene } = await pairCapture(job);
  t.after(() => model.dispose());
  const updateMatrices = scene.updateMatrixWorld.bind(scene);
  t.mock.method(scene, "updateMatrixWorld", (...args) => { clock += 7; return updateMatrices(...args); });
  const stages = {};
  const viewport = {
    scene, model, context, sceneBuildStarted: 0,
    ready: Promise.resolve().then(() => { clock += 3; }),
    orthographicCamera: new THREE.OrthographicCamera(),
    perspectiveCamera: new THREE.PerspectiveCamera(),
    renderer: {
      setSize() { clock += 2; },
      getPixelRatio() { return 1; },
      render() { clock += 11; },
      domElement: { width: 64, height: 64, toDataURL() { clock += 13; return "data:image/png;base64,AAAA"; } }
    }
  };
  const result = await captureModel(viewport, { job, stageTimings: stages });
  assert.equal(stages.waitViewportMs, 3);
  assert.deepEqual(stages.outputs, job.outputs.map(({ path }) => ({
    path, updateModelMs: 2, frameCameraMs: 7, drawSubmitMs: 11, encodeImageMs: 13
  })));
  assert.equal(result.outputs.length, 2);
  assert.ok(result.outputs.every((output) => output.dataUrl === "data:image/png;base64,AAAA"));
  assert.ok(stages.outputs.every((output) => !("prepareStudioMs" in output)), "no studio means no invented studio measurement");

  const listStages = {};
  const listing = { bounds: model.bounds, listParts: () => [] };
  await captureModel({ model: listing, context: { ...context, mode: "list" } }, { job, stageTimings: listStages });
  assert.deepEqual(listStages, {}, "a list does not report image stages");
});

test("a snapshot draws the job's annotation where it was drawn, whatever the exploded view does, cut by its clip, as heavy as on the viewer", async () => {
  const annotation = { units: "mm", marks: [
    { id: "1", kind: "stroke", points: [30, -10, 10, 40, 0, 10], color: "#ff2d55", width: 3 },
    { id: "2", kind: "area", points: [0, -20, 20, 20, -20, 20, 20, 0, 20], triangles: [0, 1, 2], color: "#00aa44" }
  ] };
  const job = glbJob({ mode: "view", annotation, display: { mode: "solid", exploded: { enabled: true, amount: 1 }, clip: { axis: "x" } },
    outputs: [{ path: "a.png", width: 64, height: 450, camera: "iso" }, { path: "b.png", width: 64, height: 450, camera: "top" }] });
  const { context, model, scene } = await pairCapture(job);
  const viewport = { ...stubViewport(model, scene), context };
  viewport.renderer.domElement = { ...viewport.renderer.domElement, height: 450 };
  const rest = model.bounds;
  try {
    await captureModel(viewport, { job });
    const layer = scene.getObjectByName("annotation");
    assert.ok(layer, "the annotation is in the scene");
    const [stroke] = layer.children;
    assert.notDeepEqual(model.bounds, rest, "the exploded view moved the parts");
    for (const mark of layer.children) assert.deepEqual(mark.matrixWorld.elements, new THREE.Matrix4().elements, "the ink stays put");
    assert.equal(viewport.sceneClip.planes.length, 1);
    for (const mark of layer.children) assert.deepEqual(mark.material.clippingPlanes, viewport.sceneClip.planes, "cut as the model is");
    // A 450-pixel output is half the viewer's reference height: its ink is drawn half as wide.
    assert.equal(stroke.material.linewidth, 1.5);
    assert.equal(layer.children.length, 2, "one layer serves every output of a height");
  } finally {
    viewport.annotationLayer?.layer.dispose();
    viewport.sceneClip?.dispose();
    model.dispose();
  }
});

test("a snapshot's Render still converges over every sample of its studio frame; a software renderer draws one", () => {
  assert.equal(snapshotStudioSamples(), PHOTOGRAPHIC_STUDIO_FRAME.stillSamples);
  assert.ok(PHOTOGRAPHIC_STUDIO_FRAME.stillSamples > 1);
  assert.equal(snapshotStudioSamples({ softwareRendering: true }), 1);
});
