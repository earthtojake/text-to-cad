import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import {
  applyDisplayRecordTransform,
  applyRuntimeModelBounds,
  buildStepClipPlane,
  runtimeModelKeyMatches,
  readBoundsCenter,
  resolveRuntimeModelFloorZ,
  syncRuntimeStepClipPlane,
  toNumber
} from "./modelRuntime.js";
import { VIEWER_SCENE_SCALE } from "./sceneScale.js";

const EPSILON = 1e-6;

function assertNear(actual, expected, message = "") {
  assert.ok(Math.abs(actual - expected) < EPSILON, `${message} expected ${expected}, received ${actual}`);
}

test("model runtime helpers coerce numbers and read bounds centers", () => {
  assert.equal(toNumber("4.5"), 4.5);
  assert.equal(toNumber("bad", 7), 7);

  const center = readBoundsCenter(THREE, {
    min: [0, 2, 4],
    max: [2, 4, 8]
  });
  assert.deepEqual(center.toArray(), [1, 3, 6]);
});

test("model runtime helpers apply display record base and effect transforms", () => {
  const mesh = new THREE.Object3D();
  const edges = new THREE.Object3D();
  const effectMatrix = new THREE.Matrix4().makeTranslation(2, 0, 0);
  applyDisplayRecordTransform(THREE, {
    mesh,
    edges,
    baseTransform: [
      1, 0, 0, 3,
      0, 1, 0, 4,
      0, 0, 1, 5,
      0, 0, 0, 1
    ],
    effectMatrix
  });

  const expected = effectMatrix.clone().multiply(new THREE.Matrix4().set(
    1, 0, 0, 3,
    0, 1, 0, 4,
    0, 0, 1, 5,
    0, 0, 0, 1
  ));
  assert.equal(mesh.matrixAutoUpdate, false);
  assert.equal(edges.matrixAutoUpdate, false);
  assert.equal(mesh.matrix.equals(expected), true);
  assert.equal(edges.matrix.equals(expected), true);
});

test("model runtime helpers update bounds and shadow settings", () => {
  const keyLight = new THREE.DirectionalLight();
  keyLight.position.set(0, 0, 20);
  const runtime = { keyLight };

  const result = applyRuntimeModelBounds(THREE, runtime, {
    min: [0, 0, 0],
    max: [4, 0, 0]
  }, VIEWER_SCENE_SCALE.CAD, { shadowMapSize: 512 });

  assert.deepEqual(result.boundsMin, [0, 0, 0]);
  assert.deepEqual(result.boundsMax, [4, 0, 0]);
  assertNear(result.radius, 2, "radius");
  assert.equal(runtime.modelRadius, 2);
  assert.equal(runtime.keyLight.shadow.mapSize.x, 512);
  assert.equal(runtime.keyLight.shadow.mapSize.y, 512);
  assert.equal(runtime.keyLight.shadow.camera.left, -60);
  assert.equal(runtime.keyLight.shadow.camera.right, 60);
});

test("model runtime resolves a world-z=0 floor in every scene scale", () => {
  const bounds = {
    min: [0, 0, -4],
    max: [1, 1, 10]
  };
  const modelPosition = new THREE.Vector3(0, 0, -6);

  // Both CAD and URDF scales place the floor at world z=0 (the model position's z), so the
  // model's absolute Z is honored rather than glued to its bbox bottom.
  assert.equal(resolveRuntimeModelFloorZ(bounds, modelPosition, VIEWER_SCENE_SCALE.CAD), -6);
  assert.equal(resolveRuntimeModelFloorZ(bounds, modelPosition, VIEWER_SCENE_SCALE.URDF), -6);
});

test("model runtime camera events only match the visible model key", () => {
  assert.equal(runtimeModelKeyMatches(null, "parts/a.step"), false);
  assert.equal(runtimeModelKeyMatches({ hasVisibleModel: false, activeModelKey: "parts/a.step" }, "parts/a.step"), false);
  assert.equal(runtimeModelKeyMatches({ hasVisibleModel: true, activeModelKey: "parts/a.step" }, "parts/a.step"), true);
  assert.equal(runtimeModelKeyMatches({ hasVisibleModel: true, activeModelKey: "parts/a.step" }, "parts/b.step"), false);
  assert.equal(runtimeModelKeyMatches({ hasVisibleModel: true, activeModelKey: "" }, "parts/b.step"), false);
  assert.equal(runtimeModelKeyMatches({ hasVisibleModel: true, activeModelKey: "" }, ""), true);
});

test("model runtime helpers build and sync STEP clip planes", () => {
  const material = new THREE.MeshStandardMaterial();
  const edgeMaterial = new THREE.LineBasicMaterial();
  const overlayMaterial = new THREE.MeshBasicMaterial();
  const overlay = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), overlayMaterial);
  const runtime = {
    THREE,
    modelBounds: {
      min: [0, 0, 0],
      max: [10, 0, 0]
    },
    modelGroup: new THREE.Group(),
    renderer: {},
    displayRecords: [{ material, edgeMaterial }],
    facePickGroup: new THREE.Group(),
    edgePickGroup: new THREE.Group(),
    vertexPickGroup: new THREE.Group(),
    surfaceLineGroup: new THREE.Group(),
    topologyDisplayEdgeLine: null
  };
  runtime.modelGroup.position.set(2, 0, 0);
  runtime.facePickGroup.add(overlay);

  const directPlane = buildStepClipPlane(THREE, {
    enabled: true,
    axis: "x",
    offset: 0.5
  }, runtime.modelBounds, runtime.modelGroup.position);
  assertNear(directPlane.normal.x, 1, "direct plane normal");
  assertNear(directPlane.constant, -7, "direct plane constant");

  syncRuntimeStepClipPlane(runtime, {
    enabled: true,
    axis: "x",
    offset: 0.5
  });

  assert.equal(runtime.renderer.localClippingEnabled, true);
  assert.equal(runtime.activeClipPlanes.length, 1);
  assert.equal(material.clippingPlanes.length, 1);
  assert.equal(edgeMaterial.clippingPlanes.length, 1);
  assert.equal(overlayMaterial.clippingPlanes.length, 1);
  assert.equal(material.userData.cadClipPlaneEnabled, true);

  syncRuntimeStepClipPlane(runtime, { enabled: false });
  assert.equal(runtime.activeClipPlane, null);
  assert.deepEqual(runtime.activeClipPlanes, []);
  assert.equal(material.clippingPlanes, null);
  assert.equal(edgeMaterial.clippingPlanes, null);
  assert.equal(overlayMaterial.clippingPlanes, null);
  assert.equal(material.userData.cadClipPlaneEnabled, false);
});
