import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";

import {
  buildModel,
  buildStepClipPlane
} from "./cadScene.js";
import {
  captureModel,
  disposeSnapshotSceneResources,
  modelOptionsForRenderJob,
  projectedVisibleGeometryFrame,
  renderJobContext,
  renderMeshJob,
  resolveOutputCameraProjection,
  resolveOutputCameraSpec,
  SECTION_PLANES,
  stepParametersForSnapshotOutput
} from "./renderMeshScene.js";
import { evaluateAnimationClip, normalizeAnimationClips } from "./animationRuntime.js";
import { resolveAnimationFrame } from "./animationClock.js";
import { stepModuleFromKinematics } from "./kinematicsModule.js";
import { normalizeStepModuleDefinition } from "./stepModule.js";
import { normalizeStepParameterRenderValues } from "./stepParameters.js";
import { stepParameterRuntime } from "./source.js";
import { buildComposedPackageMeshData } from "../lib/assembly/meshData.js";
import { applyExplodedViewProgress, computeExplodedViewLayout } from "../lib/viewer/explodedView.js";
import { fitCameraDepthToBounds } from "./renderOptions.js";
import { applyPhotographicStudio, disposePhotographicStudio } from "./photographicStudio.js";

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

test("component-only packages render and section every placed occurrence", async () => {
  const makeComponent = () => ({
    vertices: new Float32Array([-1, 0, -1, 1, 0, 1, 0, 1, -1]),
    indices: new Uint32Array([0, 1, 2]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
    parts: [{ id: "triangle", vertexCount: 3, triangleCount: 1 }],
    bounds: { min: [-1, 0, -1], max: [1, 1, 1] }
  });
  const mesh = buildComposedPackageMeshData({ occurrences: [
    { id: "a", component: "a" },
    { id: "b", component: "b", transform: [1, 0, 0, 10, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] }
  ], assembly: { root: { id: "root", nodeType: "assembly", children: [
    { id: "a", nodeType: "part", children: [] }, { id: "b", nodeType: "part", children: [] }
  ] } } }, { a: makeComponent(), b: makeComponent() });
  assert.equal(mesh.indices.length, 0);
  const list = await renderMeshJob(mesh, { mode: "list", selection: { focus: ["b"] } });
  assert.deepEqual(list.parts.map((part) => part.ref), ["#b"]);
  const result = await renderMeshJob(mesh, { mode: "section", section: { plane: "XY", offset: 0 },
    outputs: [{ path: "section.svg" }] });
  assert.equal(result.section.segmentCount, 2);
  assert.match(result.outputs[0].text, /10\.0000 0\.0000/);
  assert.match(result.outputs[0].text, /10\.5000 0\.5000/);
  assert.deepEqual(result.warnings, []);
});

test("a section is cut where job.section says, and an output's extension is its only format switch", async () => {
  // One triangle standing in the XZ plane (y = 0), spanning z = -1..1 and x = -1..1.
  const mesh = {
    vertices: new Float32Array([-1, 0, -1, 1, 0, 1, 0, 0, -1]),
    indices: new Uint32Array([0, 1, 2]),
    normals: new Float32Array([0, 1, 0, 0, 1, 0, 0, 1, 0]),
    parts: [],
    bounds: { min: [-1, 0, -1], max: [1, 0, 1] }
  };
  const cut = (section, path = "cut.svg") => renderMeshJob(mesh, { mode: "section", section, outputs: [{ path }] });
  assert.deepEqual(SECTION_PLANES, ["XY", "XZ", "YZ"]);
  // XY at Z=0 and YZ at X=0 both cross it; the offset moves the plane along its normal.
  assert.equal((await cut({ plane: "XY", offset: 0 })).section.segmentCount, 1);
  assert.equal((await cut({ plane: "YZ", offset: 0.5 })).section.segmentCount, 1);
  const missed = await cut({ plane: "XY", offset: 5 });
  assert.equal(missed.section.segmentCount, 0);
  assert.match(missed.warnings[0], /SECTION XY @ Z=5\.000 does not intersect the model/);
  // The default cut is XY at 0, the same thing Python fills in.
  assert.equal((await cut(undefined)).section.segmentCount, 1);
  // Only the two axis-aligned fields exist: an unknown plane is an error, not an XY cut.
  await assert.rejects(cut({ plane: "XW" }), /section\.plane must be one of: XY, XZ, YZ/);
  await assert.rejects(cut({ plane: "xy" }), /section\.plane must be one of/);
  // `format` is not a key: a .svg name is SVG text whatever else the output says.
  const svg = await renderMeshJob(mesh, { mode: "section", outputs: [{ path: "CUT.SVG", format: "png" }] });
  assert.equal(svg.outputs[0].mimeType, "image/svg+xml");
});

test("renderMeshJob list capture uses buildModel selection", async () => {
  const result = await renderMeshJob(twoPartMeshData(), {
    mode: "list",
    selection: {
      focus: ["right"]
    }
  });

  assert.equal(result.ok, true);
  assert.equal(result.mode, "list");
  // `ref` is the ONLY identifier a part carries: it pastes straight into --focus/--hide
  // and inspect. `id` and `occurrenceId` were the same string again and again (identical
  // in 600/600 parts on a real assembly) and are gone.
  assert.deepEqual(result.parts.map((part) => part.ref), ["#right"]);
  assert.deepEqual(Object.keys(result.parts[0]).sort(),
    ["bounds", "name", "ref", "triangleCount", "vertexCount"]);
  assert.deepEqual(result.bounds, {
    min: [2, 0, 0],
    max: [3, 1, 0]
  });
});

test("render view focus preserves full assembly while hide still filters", () => {
  const focusedContext = renderJobContext(twoPartMeshData(), {
    mode: "view",
    selection: {
      focus: ["right"]
    }
  });
  const focused = buildModel(
    THREE,
    twoPartMeshData(),
    modelOptionsForRenderJob(focusedContext, {
      mode: "view",
      selection: {
        focus: ["right"]
      }
    })
  );

  assert.deepEqual(focused.displayRecords.map((record) => record.partId), ["left", "right"]);
  assert.deepEqual(focused.bounds, {
    min: [0, 0, 0],
    max: [3, 1, 0]
  });
  // Focus must still be visible in the render: the focused part keeps full
  // opacity while every other part is ghosted, mirroring the interactive
  // viewer's focus treatment.
  const focusedById = new Map(focused.displayRecords.map((record) => [record.partId, record]));
  assert.equal(focusedById.get("right").material.opacity, 1);
  assert.ok(
    focusedById.get("left").material.opacity <= 0.05,
    `expected non-focused part to be ghosted, got opacity ${focusedById.get("left").material.opacity}`
  );
  focused.dispose();

  const hiddenContext = renderJobContext(twoPartMeshData(), {
    mode: "view",
    selection: {
      hide: ["left"]
    }
  });
  const hidden = buildModel(
    THREE,
    twoPartMeshData(),
    modelOptionsForRenderJob(hiddenContext, {
      mode: "view",
      selection: {
        hide: ["left"]
      }
    })
  );

  assert.deepEqual(hidden.displayRecords.map((record) => record.partId), ["right"]);
  assert.deepEqual(hidden.bounds, {
    min: [2, 0, 0],
    max: [3, 1, 0]
  });
  hidden.dispose();
});

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

test("snapshot and shared CAD scene use the same appearance ink", () => {
  for (const appearance of ["light", "dark"]) {
    const mesh = twoPartMeshData();
    const context = renderJobContext(mesh, { input: "part.step", kind: "step", display: { appearance } });
    const scene = buildModel(THREE, mesh, modelOptionsForRenderJob(context));
    assert.deepEqual(scene.runtime.edgeSettings.classes, context.edgeSettings.classes);
    assert.equal(scene.runtime.edgeSettings.color, "#253443");
    scene.dispose();
  }
});

test("snapshot scene policy composes display Render quality with technical quality", () => {
  const normal = renderJobContext(twoPartMeshData(), {});
  assert.equal(normal.sceneSettings.render.enabled, false);
  assert.equal(normal.quality.id, "interactive");
  assert.equal(normal.sharedRenderOptions.renderScale, 1);
  assert.equal(normal.displaySettings.guides.grid.enabled, false, "snapshot inherits the Solid preset, which draws no grid");
  assert.equal(normal.displaySettings.guides.axis.enabled, false, "and no axes");
  assert.equal(normal.sceneSettings.appearance, "light", "in light, the CLI's default");
  const gridded = renderJobContext(twoPartMeshData(), { display: { mode: "grid" } });
  assert.equal(gridded.displaySettings.guides.grid.enabled, true, "the Grid preset draws one");
  assert.equal(gridded.displaySettings.guides.grid.density, 2, "twice as fine");
  assert.equal(gridded.displaySettings.guides.axis.enabled, true, "with the axes");

  const rendered = renderJobContext(twoPartMeshData(), { display: { mode: "render" } });
  assert.equal(rendered.sceneSettings.render.enabled, true);
  assert.equal(rendered.quality.id, "high");
  assert.equal(rendered.projection, "perspective");
  assert.equal(rendered.displayMode, "shaded");
  assert.equal(rendered.sharedRenderOptions.renderScale, 2);

  const explicitScale = renderJobContext(twoPartMeshData(), {
    display: { mode: "render", lighting: { quality: "preview" } },
    output: { renderScale: 3 }
  });
  assert.equal(explicitScale.quality.id, "standard");
  assert.equal(explicitScale.sharedRenderOptions.renderScale, 3);
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

test("render display retains CAD runtimes and animation", () => {
  const stepAnimation = resolveAnimationFrame(SLIDE_CLIPS, { clip: "slide", time: 1.5 });
  const job = {
    kind: "step",
    display: { mode: "render" },
    selectorRuntime: {},
    displayEdgeRuntime: {},
    stepAnimation
  };
  const context = renderJobContext(twoPartMeshData(), job);
  assert.equal(context.selectorRuntime, job.selectorRuntime);
  assert.equal(context.displayEdgeRuntime, job.displayEdgeRuntime);
  assert.equal(context.edgesVisible, false);
  const options = modelOptionsForRenderJob(context, job);
  assert.equal(options.callbacks.animation, stepAnimation);
  assert.deepEqual(options.selection, { showEdges: false });
  const model = buildModel(THREE, { kind: "step", meshData: twoPartMeshData() }, options);
  model.update({ stepParameters: null });
  assert.deepEqual(model.displayRecords.map((record) => record.partId), ["left", "right"]);
  for (const record of model.displayRecords) assert.equal(record.material.opacity, 1);
  const left = model.displayRecords.find((record) => record.partId === "left");
  assert.deepEqual(roundedPoint(left.effectMatrix, [0, 0, 0]), [1.5, 0, 0]);
  model.dispose();
});

test("photographic Render rejects CAD-only capture modes", () => {
  for (const mode of ["list", "section"]) {
    assert.throws(() => renderJobContext(twoPartMeshData(), { mode, display: { mode: "render" } }), /Render display supports only view mode/);
  }
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

// A snapshot's still frame at clip time t must be the frame the viewer shows
// there. Both go through ONE effects pass (applySceneState, inside buildModel):
// kinematics folds the pose into effect matrices, then the clip's frame is
// merged OVER it. The snapshot reaches that pass through the job's
// `stepAnimation` -> callbacks.animation channel, the same key the docs hero
// drives playback with, so there is no snapshot-side twin to drift.
function roundedPoint(matrix, point) {
  return new THREE.Vector3(...point).applyMatrix4(matrix).toArray().map((v) => Math.round(v * 1e6) / 1e6);
}

const SLIDE_CLIPS = normalizeAnimationClips({
  slide: {
    duration: 4,
    update(t, m) {
      // The animation runtime addresses parts by label (part.label || part.name).
      m.get("Left").translate([t, 0, 0]);
    }
  }
});

function liftRuntime(liftMm) {
  // A one-mate kinematics block in the sidecar's RESOLVED form (world axis
  // numbers), compiled the way loadKinematicsModuleDefinition compiles it.
  const definition = normalizeStepModuleDefinition(
    stepModuleFromKinematics({
      mates: [{
        name: "lift",
        kind: "slider",
        parent: "#Right",
        child: "#Left",
        axis: { origin: [0, 0, 0], dir: [0, 0, 1] },
        limits: { value: [0, 10] }
      }]
    }),
    { url: "/__cad/asset?file=pair.step.json", cadPath: "pair.step" }
  );
  return stepParameterRuntime({
    definition,
    renderParameters: normalizeStepParameterRenderValues(definition, { lift: liftMm }),
    selectorRuntime: null,
    cadPath: "pair.step",
    sourceUrl: "/__cad/asset?file=pair.step.json"
  });
}

// The headless sequence: buildModel from the job's options (which carry the
// frame on callbacks.animation), then the per-output `model.update({
// stepParameters })` renderMeshJob performs before fitting each camera.
function buildStepModel(job) {
  const meshData = twoPartMeshData();
  const context = renderJobContext(meshData, job);
  const model = buildModel(THREE, { kind: "step", meshData }, modelOptionsForRenderJob(context, job));
  model.update({ stepParameters: stepParametersForSnapshotOutput(job.outputs?.[0], job) });
  return model;
}

test("the still frame rides the effects-pass channel the viewer and docs hero use", () => {
  const stepAnimation = resolveAnimationFrame(SLIDE_CLIPS, { clip: "slide", time: 1.5 });
  const job = { mode: "view", kind: "step", outputs: [{ path: "frame.png" }], stepAnimation };
  const options = modelOptionsForRenderJob(renderJobContext(twoPartMeshData(), job), job);
  // cadScene's applyParameters reads callbacks.animation; a job without a
  // frame request leaves the channel empty so the pass is pose-only.
  assert.equal(options.callbacks.animation, stepAnimation);
  assert.equal(
    modelOptionsForRenderJob(renderJobContext(twoPartMeshData(), {}), {}).callbacks.animation,
    null
  );
  assert.equal(options.receiveShadows, false, "normal CAD snapshots keep the inspection shadow policy");
  const renderJob = { display: { mode: "render" }, outputs: [{ path: "render.png" }] };
  assert.equal(
    modelOptionsForRenderJob(renderJobContext(twoPartMeshData(), renderJob), renderJob).receiveShadows,
    true,
    "Render snapshots enable opaque model receivers"
  );
});

test("a snapshot frame at time t is the clip evaluated at t, on the rendered records", () => {
  const stepAnimation = resolveAnimationFrame(SLIDE_CLIPS, { clip: "slide", time: 1.5 });
  const model = buildStepModel({ mode: "view", kind: "step", outputs: [{ path: "frame.png" }], stepAnimation });
  try {
    const byId = new Map(model.displayRecords.map((record) => [record.partId, record]));
    // What the viewer's pass computes for the same clip and elapsedSec.
    const expected = evaluateAnimationClip(THREE, model.meshData, SLIDE_CLIPS.slide, 1.5);
    assert.deepEqual(
      roundedPoint(byId.get("left").effectMatrix, [0, 0, 0]),
      roundedPoint(expected.matrices.get("left"), [0, 0, 0])
    );
    assert.deepEqual(roundedPoint(byId.get("left").effectMatrix, [0, 0, 0]), [1.5, 0, 0]);
    // The clip never touched the other part, and neither did the still.
    assert.equal(byId.get("right").effectMatrix, null);
    // The frame moves the bounds the camera frames on, exactly as a pose does:
    // the left part now spans x 1.5..2.5 beside the untouched right part.
    assert.deepEqual(model.bounds.min, [1.5, 0, 0]);
    assert.deepEqual(model.bounds.max, [3, 1, 0]);
  } finally {
    model.dispose();
  }
});

test("a snapshot frame layers over the kinematics pose in the viewer's order", () => {
  const stepParameters = liftRuntime(4);
  const posed = buildStepModel({ mode: "view", kind: "step", outputs: [{ path: "pose.png" }], stepParameters });
  const poseMatrix = posed.displayRecords.find((record) => record.partId === "left").effectMatrix.clone();
  posed.dispose();
  assert.deepEqual(roundedPoint(poseMatrix, [0, 0, 0]), [0, 0, 4]);

  const stepAnimation = resolveAnimationFrame(SLIDE_CLIPS, { clip: "slide", time: 1.5 });
  const composed = buildStepModel({
    mode: "view", kind: "step", outputs: [{ path: "frame.png" }], stepParameters, stepAnimation
  });
  try {
    const left = composed.displayRecords.find((record) => record.partId === "left");
    // Pose first, choreography on top in world space: the clip's matrix
    // PREMULTIPLIES the pose (applyAnimationFrameToEffects), never the reverse.
    const animMatrix = evaluateAnimationClip(THREE, composed.meshData, SLIDE_CLIPS.slide, 1.5).matrices.get("left");
    const expected = new THREE.Matrix4().multiplyMatrices(animMatrix, poseMatrix);
    assert.deepEqual(
      left.effectMatrix.elements.map((v) => Math.round(v * 1e6) / 1e6),
      expected.elements.map((v) => Math.round(v * 1e6) / 1e6)
    );
    assert.deepEqual(roundedPoint(left.effectMatrix, [0, 0, 0]), [1.5, 0, 4]);
  } finally {
    composed.dispose();
  }
});

test("photographic Render applies a non-rest kinematics transform", () => {
  const stepParameters = liftRuntime(4);
  const job = {
    mode: "view",
    kind: "step",
    display: { mode: "render" },
    outputs: [{ path: "render-pose.png" }],
    stepParameters
  };
  assert.equal(stepParametersForSnapshotOutput(job.outputs[0], job), stepParameters);
  const model = buildStepModel(job);
  try {
    const left = model.displayRecords.find((record) => record.partId === "left");
    assert.deepEqual(roundedPoint(left.effectMatrix, [0, 0, 0]), [0, 0, 4]);
  } finally {
    model.dispose();
  }
});

test("render display accepts common camera, selection, clipping, and quality controls", () => {
  const context = renderJobContext(twoPartMeshData(), {
    kind: "step",
    camera: { preset: "front" },
    display: {
      mode: "render",
      camera: { projection: "orthographic" },
      clip: { enabled: true, axis: "x", offsets: { x: 0.5 } },
      exploded: { enabled: true, amount: 0.5 },
      surfaces: { colorMode: "single", color: "#123456" }
    },
    selection: { hiddenPartIds: ["right"], selectedPartIds: ["left"] },
    quality: { tessellation: { chordTolerance: 0.001 } }
  });
  assert.equal(context.camera.projection, "orthographic");
  assert.equal(context.sharedRenderOptions.clip.enabled, true);
  const options = modelOptionsForRenderJob(context, { selection: { hiddenPartIds: ["right"] } });
  assert.deepEqual(options.selection.hiddenPartIds, ["right"]);
  assert.equal(options.materialSettings.overrideSourceColors, true);
  assert.equal(options.materialSettings.defaultColor, "#123456");
});

test("only a STEP job has edges, a section or an exploded view; every other kind renders Solid without them", () => {
  const display = { mode: "wireframe", clip: { enabled: true, axis: "x" }, exploded: { enabled: true, amount: 0.5 } };
  const step = renderJobContext(twoPartMeshData(), { kind: "step", display });
  assert.equal(step.sceneSettings.view.mode, "wireframe");
  assert.equal(step.sharedRenderOptions.clip.enabled, true);
  for (const kind of ["stl", "3mf", "glb", "dxf", "urdf", "srdf", "sdf"]) {
    const context = renderJobContext(twoPartMeshData(), { kind, display });
    assert.equal(context.sceneSettings.view.mode, "solid", kind);
    assert.equal(context.sceneSettings.view.edges.enabled, false, kind);
    assert.equal(context.sharedRenderOptions.clip.enabled, false, kind);
    assert.equal(context.displaySettings.exploded.enabled, false, kind);
  }
});

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

function orthographicFrame(camera) {
  return [camera.left, camera.right, camera.top, camera.bottom, camera.zoom, ...camera.position.toArray()]
    .map((value) => Number(value.toFixed(9)));
}

// A video's camera is locked to ONE box for the whole clip. Without that lock
// every frame re-fits to its own pose and a static part crawls around the image
// while the clip plays -- the breathing `frameBounds` exists to stop. This is
// the assertion that the lock is actually applied, frame by frame: the unit
// above it only checks that the union is computed correctly.
test("a locked frame fits the same camera on every frame of a clip", async () => {
  const stepAnimation = resolveAnimationFrame(SLIDE_CLIPS, { clip: "slide", time: 0 });
  const job = { mode: "view", kind: "step", outputs: [{ path: "frame.png", width: 64, height: 64, camera: "iso" }], stepAnimation };
  const meshData = twoPartMeshData();
  const context = renderJobContext(meshData, job);
  const model = buildModel(THREE, { kind: "step", meshData }, modelOptionsForRenderJob(context, job));
  const scene = new THREE.Scene();
  scene.add(model.root);
  const viewport = { ...stubViewport(model, scene), context };
  try {
    // The union of the whole clip, as prepareHeadlessRenderSequence measures it.
    const frameBounds = { min: [0, 0, 0], max: [4.75, 1, 0] };
    const frames = [];
    const posed = [];
    for (const elapsedSec of [0, 2, 3.75]) {
      const modelState = { callbacks: { animation: resolveAnimationFrame(SLIDE_CLIPS, { clip: "slide", time: elapsedSec }) } };
      await captureModel(viewport, { job, frameBounds, modelState });
      frames.push(orthographicFrame(viewport.orthographicCamera));
      // The pose really did move underneath it, so an unlocked fit would differ.
      posed.push(model.bounds.max[0]);
      await captureModel(viewport, { job, modelState });
      posed.push(orthographicFrame(viewport.orthographicCamera));
    }
    assert.deepEqual(frames[1], frames[0], "frame 2 of the clip is framed like frame 1");
    assert.deepEqual(frames[2], frames[0], "and so is the last one");
    assert.notDeepEqual(posed[1], posed[3], "without the lock the same three poses do NOT share a camera");
  } finally {
    model.dispose();
  }
});

// The renderer a photographic studio configures, with only what captureModel and the studio touch.
function studioRendererStub() {
  const clearColor = new THREE.Color();
  let clearAlpha = 1;
  return {
    toneMapping: THREE.NoToneMapping, toneMappingExposure: 1, outputColorSpace: THREE.LinearSRGBColorSpace,
    shadowMap: { enabled: false, type: null },
    getClearColor(target) { target.copy(clearColor); }, getClearAlpha() { return clearAlpha; },
    setClearColor(color, alpha) { clearColor.copy(color); clearAlpha = alpha; },
    setSize() {}, getPixelRatio() { return 1; }, render() {},
    domElement: { width: 64, height: 64, toDataURL() { return "data:image/png;base64,AAAA"; } }
  };
}

// The two parts at 100x: large enough that the floor is sized by them, not by its minimum.
function wideTwoPartMeshData() {
  const mesh = twoPartMeshData();
  const scaled = (bounds) => ({ min: bounds.min.map((value) => value * 100), max: bounds.max.map((value) => value * 100) });
  return {
    ...mesh, vertices: mesh.vertices.map((value) => value * 100), bounds: scaled(mesh.bounds),
    parts: mesh.parts.map((part) => ({ ...part, bounds: scaled(part.bounds) }))
  };
}

test("a snapshot fits its camera's depth range in every preset, as the viewer fits its own", async () => {
  // The viewer draws every preset with ordinary depth fitted to the frame (useViewerRuntime). A
  // snapshot without the studio drew with a logarithmic buffer and a fixed range instead, which
  // the instanced CAD edges cannot test against: under a perspective camera they all vanished.
  for (const projection of ["perspective", "orthographic"]) {
    const job = { mode: "view", kind: "step", display: { mode: "solid", camera: { projection } },
      output: { tightFrame: false }, outputs: [{ path: "solid.png", width: 64, height: 64, camera: "iso" }] };
    const meshData = twoPartMeshData();
    const context = renderJobContext(meshData, job);
    const model = buildModel(THREE, { kind: "step", meshData }, modelOptionsForRenderJob(context, job));
    const scene = new THREE.Scene();
    scene.add(model.root);
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
      fitCameraDepthToBounds(viewer, model.bounds, {
        placedObjects: model.displayRecords, modelGroup: model.runtime.modelGroup, groundZ: null, pivot: center
      });
      assert.deepEqual([camera.near, camera.far], [viewer.near, viewer.far], projection);
    } finally {
      model.dispose();
    }
  }
});

test("an exploded Render snapshot keeps its floor and floor shadow on the rest placement, as the viewer does", async () => {
  const job = { mode: "view", kind: "step",
    display: { mode: "render", lighting: { quality: "preview" }, exploded: { enabled: true, amount: 1 } },
    outputs: [{ path: "exploded.png", width: 64, height: 64, camera: "iso" }] };
  const meshData = wideTwoPartMeshData();
  const context = renderJobContext(meshData, job);
  const model = buildModel(THREE, { kind: "step", meshData }, modelOptionsForRenderJob(context, job));
  const scene = new THREE.Scene();
  scene.add(model.root);
  const configuration = context.sceneSettings.render.configuration;
  const studioOptions = { sceneScale: context.sceneScale, shadowMapSize: context.quality.shadowMapSize };
  const studioRuntime = { scene, renderer: studioRendererStub(), modelBounds: model.bounds };
  // renderModel's studio: the floor sized from the rest placement.
  applyPhotographicStudio(THREE, studioRuntime, configuration, { ...studioOptions, bounds: model.bounds, groundBounds: model.restBounds });
  const viewport = { ...stubViewport(model, scene), renderer: studioRuntime.renderer, context, studioRuntime,
    studioConfiguration: configuration };
  const viewer = { scene: new THREE.Scene(), renderer: studioRendererStub() };
  try {
    await captureModel(viewport, { job });
    assert.ok(model.displayRecords.some((record) => record.explodedViewMatrix), "the parts were exploded");
    // The viewer's studio for the model exploded the same way: lit where the parts are, floored
    // where the model rests (ShellViewport: `groundBounds: runtime.zeroPoseBounds`).
    model.refreshBounds();
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
  const job = { mode: "view", kind: "step", display: { mode: "render", lighting: { quality: "final" } },
    outputs: [{ path: "final.png", width: 64, height: 64, camera: "iso" }] };
  const meshData = wideTwoPartMeshData();
  const context = renderJobContext(meshData, job);
  const model = buildModel(THREE, { kind: "step", meshData }, modelOptionsForRenderJob(context, job));
  const scene = new THREE.Scene();
  scene.add(model.root);
  const configuration = context.sceneSettings.render.configuration;
  const renderer = { ...studioRendererStub(), getPixelRatio() { return context.sharedRenderOptions.renderScale; } };
  const studioRuntime = { scene, renderer, modelBounds: model.bounds };
  applyPhotographicStudio(THREE, studioRuntime, configuration, {
    sceneScale: context.sceneScale, shadowMapSize: context.quality.shadowMapSize, bounds: model.bounds, groundBounds: model.restBounds
  });
  const viewport = { ...stubViewport(model, scene), renderer, context, studioRuntime, studioConfiguration: configuration };
  try {
    assert.equal(context.sharedRenderOptions.renderScale, 2, "Final draws at twice the size it keeps");
    await captureModel(viewport, { job });
    const studio = studioRuntime.photographicStudio;
    assert.equal(studio.ground.material.defines?.STUDIO_DITHER_SCALE, "2.0000");
    assert.equal(studio.contactShadow.layer.material.defines?.STUDIO_DITHER_SCALE, "2.0000");
  } finally {
    disposePhotographicStudio(studioRuntime);
    model.dispose();
  }
});

test("an exploded snapshot radiates from the rest box the viewer explodes from, a declared box included", async () => {
  // A package's declared box (assembly.json's bbox) is tighter than its parts' boxes once a part
  // is turned; the viewer centres its layout on it (useStepExplode, `runtime.zeroPoseBounds`).
  const declaredBounds = { min: [0.5, 0, 0], max: [3, 0.5, 0] };
  const job = { mode: "view", kind: "step", display: { mode: "solid", exploded: { enabled: true, amount: 1 } },
    outputs: [{ path: "exploded.png", width: 64, height: 64, camera: "iso" }] };
  const meshData = { ...twoPartMeshData(), declaredBounds };
  const context = renderJobContext(meshData, job);
  const model = buildModel(THREE, { kind: "step", meshData }, modelOptionsForRenderJob(context, job));
  const scene = new THREE.Scene();
  scene.add(model.root);
  const viewport = { ...stubViewport(model, scene), context };
  const offsets = () => model.displayRecords.map((record) => record.explodedViewMatrix?.elements.slice(12, 15) ?? null);
  try {
    await captureModel(viewport, { job });
    const snapshot = offsets();
    assert.ok(snapshot.some(Boolean), "the parts were exploded");
    applyExplodedViewProgress(THREE, computeExplodedViewLayout(model.displayRecords, declaredBounds), 1);
    assert.deepEqual(snapshot, offsets());
  } finally {
    model.dispose();
  }
});

test("a snapshot's Clip cuts and caps the model where the viewer's does, measured against the rest box", async () => {
  // The snapshot's renderer ignored every material's plane (three honours them only with local
  // clipping on), so `display.clip` drew the whole model, uncapped. The viewer measures the
  // plane against the model at rest (`syncRuntimeStepClipPlane`), a declared box included.
  const declaredBounds = { min: [0.5, 0, 0], max: [3, 0.5, 0] };
  const clip = { enabled: true, axis: "x", offset: 0.1 };
  const job = { mode: "view", kind: "step", display: { mode: "solid", clip },
    outputs: [{ path: "clipped.png", width: 64, height: 64, camera: "iso" }] };
  const meshData = { ...twoPartMeshData(), declaredBounds };
  const context = renderJobContext(meshData, job);
  const model = buildModel(THREE, { kind: "step", meshData }, modelOptionsForRenderJob(context, job));
  const scene = new THREE.Scene();
  scene.add(model.root);
  const viewport = { ...stubViewport(model, scene), context };
  try {
    await captureModel(viewport, { job });
    assert.equal(viewport.renderer.localClippingEnabled, true, "the renderer honours a material's planes");
    const viewerPlane = buildStepClipPlane(THREE, clip, declaredBounds);
    const planes = (material) => (material.clippingPlanes || []).map((plane) => [...plane.normal.toArray(), plane.constant]);
    for (const record of model.displayRecords) {
      assert.deepEqual(planes(record.material), [[...viewerPlane.normal.toArray(), viewerPlane.constant]], record.partId);
    }
    assert.ok(scene.getObjectByName("Section fill"), "and the cut is capped");
  } finally {
    model.dispose();
  }
});

test("capture diagnostics separate readiness, pose, tight framing, draw submission and PNG readback", async (t) => {
  let clock = 0;
  t.mock.method(performance, "now", () => clock);
  const job = {
    mode: "view", kind: "stl", output: { tightFrame: true },
    outputs: [{ path: "first.png", width: 64, height: 64, camera: "iso" },
      { path: "second.png", width: 64, height: 64, camera: "front" }]
  };
  const meshData = twoPartMeshData();
  const context = renderJobContext(meshData, job);
  const model = buildModel(THREE, { kind: "stl", meshData }, modelOptionsForRenderJob(context, job));
  t.after(() => model.dispose());
  const update = model.update.bind(model);
  t.mock.method(model, "update", (...args) => { clock += 5; return update(...args); });
  const scene = new THREE.Scene();
  scene.add(model.root);
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
    path, updateModelMs: 7, frameCameraMs: 7, drawSubmitMs: 11, encodeImageMs: 13
  })));
  assert.equal(result.outputs.length, 2);
  assert.ok(result.outputs.every((output) => output.dataUrl === "data:image/png;base64,AAAA"));
  assert.ok(stages.outputs.every((output) => !("prepareStudioMs" in output)), "no studio means no invented studio measurement");

  const listStages = {};
  await captureModel({ model, context: { ...context, mode: "list" } }, { job, stageTimings: listStages });
  assert.deepEqual(listStages, {}, "a list does not report image stages");
});
