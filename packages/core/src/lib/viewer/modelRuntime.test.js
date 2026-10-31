import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";
import {
  applyRuntimeModelBounds,
  runtimeModelKeyMatches,
  resolveRuntimeModelFloorZ,
  toNumber,
  sceneRadiusForBounds
} from "./modelRuntime.js";
import { buildStepClipPlane, syncMaterialClipPlanes } from "./clipPlane.js";
import { VIEWER_SCENE_SCALE } from "./sceneScale.js";

const EPSILON = 1e-6;

function assertNear(actual, expected, message = "") {
  assert.ok(Math.abs(actual - expected) < EPSILON, `${message} expected ${expected}, received ${actual}`);
}

test("model runtime helpers coerce numbers", () => {
  assert.equal(toNumber("4.5"), 4.5);
  assert.equal(toNumber("bad", 7), 7);
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

test("a clip plane is placed in the model's coordinates and exposes the opposite side by default", () => {
  const plane = buildStepClipPlane(THREE, { axis: "x", at: 5 }, { min: [0, 0, 0], max: [10, 0, 0] }, new THREE.Vector3(2, 0, 0));
  assertNear(plane.normal.x, -1, "default section exposes the opposite side");
  assertNear(plane.constant, 7, "direct plane constant");
});

test("stable clip state preserves userData while live planes and shader transitions update", () => {
  const material = new THREE.MeshStandardMaterial();
  const owner = {};
  material.userData = { owner };
  const original = material.userData;
  syncMaterialClipPlanes(material, []);
  const disabled = material.userData;
  assert.notEqual(disabled, original, "initialize explicit clip flags without mutating the previous object");
  assert.equal(original.cadClipPlaneEnabled, undefined);
  assert.equal(disabled.owner, owner);
  syncMaterialClipPlanes(material, []);
  assert.equal(material.userData, disabled);
  const version = material.version;
  const first = [new THREE.Plane(new THREE.Vector3(1, 0, 0), -1)];
  syncMaterialClipPlanes(material, first);
  const enabled = material.userData;
  assert.notEqual(enabled, disabled);
  assert.equal(disabled.cadClipPlaneEnabled, false);
  assert.equal(material.version, version + 1);
  const shifted = [new THREE.Plane(new THREE.Vector3(1, 0, 0), -2)];
  syncMaterialClipPlanes(material, shifted);
  assert.equal(material.clippingPlanes, shifted, "offset changes still bind the current plane");
  assert.equal(material.userData, enabled, "offset-only changes allocate no new metadata");
  assert.equal(material.version, version + 1, "offset changes do not change shader structure");
  syncMaterialClipPlanes(material, [...shifted, new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)]);
  assert.equal(material.userData.cadClipPlaneCount, 2);
  assert.notEqual(material.userData, enabled);
  assert.equal(material.version, version + 2);
  syncMaterialClipPlanes(material, []);
  assert.equal(material.userData.cadClipPlaneEnabled, false);
  assert.equal(material.userData.cadClipPlaneCount, 0);
  assert.equal(material.clippingPlanes, null);
  assert.equal(material.version, version + 3);
  material.dispose();
});

test("opening Clip at a neutral boundary does not activate shader clipping", () => {
  const bounds = { min: [0,0,0], max: [10,10,10] };
  assert.equal(buildStepClipPlane(THREE, { at: 10 }, bounds), null);
  assert.equal(buildStepClipPlane(THREE, { at: 0, invert: true }, bounds), null);
  assert.ok(buildStepClipPlane(THREE, { at: 10, invert: true }, bounds));
  assert.ok(buildStepClipPlane(THREE, { at: 0 }, bounds));
  assert.ok(buildStepClipPlane(THREE, {}, bounds));
});

test("the ground is sized from the bounds it is given, so a viewer can hand it the REST pose", () => {
  // The grid and stage take this radius. A robot posed far out has bigger bounds than at rest;
  // sizing the floor from the rest box is what keeps it from rescaling under a moving model.
  const rest = { min: [-1, -1, 0], max: [1, 1, 2] };
  const posed = { min: [-1, -1, 0], max: [4, 1, 2] };
  const restRadius = sceneRadiusForBounds(THREE, rest, VIEWER_SCENE_SCALE.CAD);
  assert.ok(Math.abs(restRadius - Math.hypot(2, 2, 2) / 2) < 1e-9);
  assert.ok(sceneRadiusForBounds(THREE, posed, VIEWER_SCENE_SCALE.CAD) > restRadius);
  const runtime = {};
  assert.equal(applyRuntimeModelBounds(THREE, runtime, rest, VIEWER_SCENE_SCALE.CAD).radius, restRadius);
});
