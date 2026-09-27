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
  syncMaterialClipPlanes,
  syncRuntimeStepClipPlane,
  toNumber,
  sceneRadiusForBounds
} from "./modelRuntime.js";
import { VIEWER_SCENE_SCALE } from "./sceneScale.js";
import {
  dissolveCadSurfaceInstanceSets,
  reconcileCadSurfaceInstanceSets,
  syncCadSurfaceInstanceRecord
} from "../../common/cadSurfaceInstances.js";

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
    displayRecords: [{ material, edgeMaterials: [edgeMaterial] }],
    facePickGroup: new THREE.Group(),
    edgePickGroup: new THREE.Group(),
    topologyDisplayEdgeLine: null
  };
  runtime.modelGroup.position.set(2, 0, 0);
  runtime.facePickGroup.add(overlay);

  const directPlane = buildStepClipPlane(THREE, {
    enabled: true,
    axis: "x",
    offsets: { x: 0.5 }
  }, runtime.modelBounds, runtime.modelGroup.position);
  assertNear(directPlane.normal.x, -1, "default section exposes the opposite side");
  assertNear(directPlane.constant, 7, "direct plane constant");

  syncRuntimeStepClipPlane(runtime, {
    enabled: true,
    axis: "x",
    offsets: { x: 0.5 }
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

  // With no section before or now there is nothing to reconcile: a posed animation frame
  // asks for this sync every time, and must not walk every material to clear nothing.
  material.clippingPlanes = "untouched";
  syncRuntimeStepClipPlane(runtime, { enabled: false });
  assert.equal(material.clippingPlanes, "untouched");
  // A section switched on again is applied, and switching it off clears once more.
  syncRuntimeStepClipPlane(runtime, { enabled: true, axis: "x", offsets: { x: 0.5 } });
  assert.equal(material.clippingPlanes.length, 1);
  syncRuntimeStepClipPlane(runtime, { enabled: false });
  assert.equal(material.clippingPlanes, null);
});

test("clip-only changes update live instance materials without reconciling membership", () => {
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const group = new THREE.Group();
  const records = Array.from({ length: 4 }, (_, index) => {
    const material = new THREE.MeshStandardMaterial({ color: index % 2 ? 0xff0000 : 0x00ff00 });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(index * 2, 0, 0);
    mesh.updateMatrix();
    return { partId: `part${index}`, geometry, mesh, material };
  });
  const sets = reconcileCadSurfaceInstanceSets(THREE, records, group);
  const set = [...sets][0];
  assert.equal(sets.size, 1);
  const matrix = set.object.instanceMatrix;
  const color = set.object.instanceColor;
  const matrices = [...matrix.array], colors = [...color.array], slots = records.map(r => r.surfaceInstance.slot);
  const matrixVersion = matrix.version, colorVersion = color.version;
  const drawMaterial = set.object.material;
  const disposedMaterial = new THREE.MeshStandardMaterial();
  const disposedSet = { disposed: true, object: { material: disposedMaterial } };
  const directMaterial = new THREE.MeshStandardMaterial();
  const directSet = { disposed: false, object: { material: directMaterial } };
  const runtime = {
    THREE, displayRecords: records, modelGroup: group,
    modelBounds: { min: [0, 0, 0], max: [10, 1, 1] },
    cadSurfaceInstanceSets: new Set([set, directSet, disposedSet]),
    cadScene: { runtime: { cadSurfaceInstanceSets: sets }, syncSurfaceInstances() {
      assert.fail("clipping must not run membership reconciliation");
    } }
  };
  group.position.x = 2;
  try {
    for (const offset of [0.25, 0.75]) {
      syncRuntimeStepClipPlane(runtime, { enabled: true, axis: "x", offsets: { x: offset } });
      assertNear(drawMaterial.clippingPlanes[0].constant, 2 + 10 * offset);
      assert.equal(drawMaterial.clippingPlanes, records[0].material.clippingPlanes);
      assert.equal(directMaterial.clippingPlanes, drawMaterial.clippingPlanes);
      assert.equal(disposedMaterial.clippingPlanes, null);
      assert.equal(set.object.material, drawMaterial);
      assert.equal(set.object.instanceMatrix, matrix);
      assert.equal(set.object.instanceColor, color);
      assert.deepEqual(records.map(r => r.surfaceInstance.slot), slots);
      assert.ok(records.every(r => r.surfaceInstance.set === set));
      assert.deepEqual([...matrix.array], matrices);
      assert.deepEqual([...color.array], colors);
      assert.equal(matrix.version, matrixVersion);
      assert.equal(color.version, colorVersion);
    }
    // The ordinary sync may refresh its prior material recipe afterward. It
    // must retain the current clip values and leave instance attributes alone.
    records.forEach(syncCadSurfaceInstanceRecord);
    assertNear(drawMaterial.clippingPlanes[0].constant, 9.5);
    syncRuntimeStepClipPlane(runtime, { enabled: false });
    assert.equal(drawMaterial.clippingPlanes, null);
    assert.equal(directMaterial.clippingPlanes, null);
    assert.deepEqual([...matrix.array], matrices);
    assert.deepEqual([...color.array], colors);
    assert.equal(matrix.version, matrixVersion);
    assert.equal(color.version, colorVersion);
    dissolveCadSurfaceInstanceSets(sets, group);
    assert.equal(set.disposed, true);
    runtime.cadSurfaceInstanceSets = new Set([set]);
    syncRuntimeStepClipPlane(runtime, { enabled: true });
    assert.equal(drawMaterial.clippingPlanes, null, "late clip pass cannot mutate a retired draw");
  } finally {
    dissolveCadSurfaceInstanceSets(sets, group);
    geometry.dispose();
    records.forEach(record => record.material.dispose());
    directMaterial.dispose(); disposedMaterial.dispose();
  }
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
  assert.equal(buildStepClipPlane(THREE, { enabled: true, offsets: { x: 1 } }, bounds), null);
  assert.equal(buildStepClipPlane(THREE, { enabled: true, offsets: { x: 0 }, invert: true }, bounds), null);
  assert.ok(buildStepClipPlane(THREE, { enabled: true, offsets: { x: 1 }, invert: true }, bounds));
  assert.ok(buildStepClipPlane(THREE, { enabled: true, offsets: { x: 0 } }, bounds));
  assert.ok(buildStepClipPlane(THREE, { enabled: true, offsets: { x: 0.5 } }, bounds));
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

test("clip coordinates span authored bounds even when the posed envelope changes", () => {
  const rest = { min: [-20, -30, -40], max: [80, 170, 260] };
  const runtime = { THREE, zeroPoseBounds: rest,
    modelBounds: { min: [-100, -100, -100], max: [900, 900, 900] },
    modelGroup: new THREE.Group(), displayRecords: [] };
  runtime.modelGroup.position.set(7, 11, 13);
  for (const [index, axis] of ['x', 'y', 'z'].entries()) {
    for (const offset of [0, 0.25, 0.5, 0.75, 1]) {
      for (const invert of [false, true]) {
        syncRuntimeStepClipPlane(runtime, { enabled: true, axis, offset, invert });
        if ((!invert && offset === 1) || (invert && offset === 0)) {
          assert.equal(runtime.activeClipPlane, null);
        } else {
          const point = runtime.modelGroup.position.clone();
          point.setComponent(index, point.getComponent(index) + rest.min[index] + offset * (rest.max[index] - rest.min[index]));
          assertNear(runtime.activeClipPlane.distanceToPoint(point), 0, 'displayed coordinate is the plane');
        }
      }
    }
  }
});
