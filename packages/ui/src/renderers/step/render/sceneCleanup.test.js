import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { buildModel } from "@text-to-cad/core/common/cadScene.js";
import { disposeViewerCadScene } from "./sceneCleanup.js";
import { renderMemoryAccounting } from "./renderMemoryAccounting.js";

const bounds = { min: [0, 0, 0], max: [2, 1, 1] };
function mesh(n) {
  return { vertices: new Float32Array([0, 0, 0, n, 0, 0, 0, 1, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]), indices: new Uint32Array([0, 1, 2]), bounds,
    parts: [{ id: "surface", vertexCount: 3, triangleCount: 1 }] };
}
function source(values) {
  return { bounds, partTransformsBaked: false, parts: values.map((value, i) => ({ id: `part${i}`, occurrenceId: `part${i}`,
    componentId: `cid${i}`, sourceMesh: value, sourceMeshKey: `${i}:${value.vertices[3]}`,
    bounds, vertexCount: 3, triangleCount: 1, transform: [1, 0, 0, i * 2, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] })) };
}
const settings = { renderPartsIndividually: true, callbacks: { faceIdsForPart: () => ["face"] } };

test("full teardown clears reparented partial reconciliation and preserves another scene's shared geometry", () => {
  const old = source([mesh(1), mesh(1.2), mesh(1.4)]);
  const next = source([mesh(2), mesh(2.2), mesh(2.4)]);
  const materials = [];
  let reject = false, creations = 0;
  const instrumented = { ...THREE, MeshPhysicalMaterial: class extends THREE.MeshPhysicalMaterial {
    constructor(...args) {
      if (reject && ++creations === 2) throw new Error("second changed record fails");
      super(...args); materials.push(this);
    }
  } };
  const scene = buildModel(instrumented, old, settings);
  const other = buildModel(THREE, old, settings);
  const oldGeometries = scene.displayRecords.map(record => record.geometry);
  const oldDisposals = oldGeometries.map(() => 0);
  oldGeometries.forEach((geometry, i) => geometry.addEventListener("dispose", () => { oldDisposals[i]++; }));
  const runtime = { cadScene: scene, displayRecords: scene.displayRecords, modelGroup: new THREE.Group(),
    edgesGroup: new THREE.Group(), hasVisibleModel: true, activeModelKey: "same" };
  runtime.modelGroup.add(scene.modelGroup); runtime.edgesGroup.add(scene.edgesGroup);
  assert.equal(scene.root.children.length, 0, "the real viewer reparents both scene groups");
  reject = true;
  assert.throws(() => scene.update({ source: next }), /second changed record fails/);
  assert.equal(scene.source, next, "source changes before failed reconciliation completes");
  const orphan = scene.modelGroup.children.find(object => object.userData?.partId === "part0");
  assert.ok(orphan && orphan.geometry !== oldGeometries[0], "new record attached but is absent from installed record array");
  let orphanDisposed = 0, orphanMaterialDisposed = 0;
  orphan.geometry.addEventListener("dispose", () => { orphanDisposed++; });
  orphan.material.addEventListener("dispose", () => { orphanMaterialDisposed++; });
  const clearSceneGroup = group => { assert.equal(group.children.length, 0, "shared scene owns teardown of reparented children"); };
  disposeViewerCadScene(runtime, { clearSceneGroup });
  assert.equal(runtime.modelGroup.children.length, 0); assert.equal(runtime.edgesGroup.children.length, 0);
  assert.equal(scene.modelGroup.children.length, 0); assert.equal(scene.edgesGroup.children.length, 0);
  assert.equal(scene.runtime.ownedGeometries.size, 0);
  assert.equal(scene.runtime.cadEdgeInstanceSets.size, 0); assert.equal(scene.runtime.cadSurfaceInstanceSets.size, 0);
  assert.equal(orphanDisposed, 1); assert.equal(orphanMaterialDisposed, 1);
  assert.deepEqual(oldDisposals, [0, 0, 0], "another scene owns every old cached geometry");
  reject = false;
  const restored = buildModel(instrumented, old, settings);
  assert.deepEqual(restored.displayRecords.map(record => record.sourcePart.sourceMesh), old.parts.map(part => part.sourceMesh));
  assert.deepEqual(restored.displayRecords.map(record => record.mesh.matrix.elements.slice(12, 15)), [[0, 0, 0], [2, 0, 0], [4, 0, 0]]);
  restored.dispose(); assert.deepEqual(oldDisposals, [0, 0, 0]);
  other.dispose(); assert.deepEqual(oldDisposals, [1, 1, 1]);
  scene.dispose(); assert.equal(orphanDisposed, 1, "cleanup is idempotent");
});

test("reparented same-model disposal retains cached GPU/BVH while detaching every material", () => {
  const input = source([mesh(1), mesh(2)]), scene = buildModel(THREE, input, settings);
  const geometry = scene.displayRecords[0].geometry, bvh = { retained: true };
  geometry.boundsTree = bvh;
  let gpu = 0, materials = 0;
  geometry.addEventListener("dispose", () => { gpu++; });
  scene.displayRecords.forEach(record => record.material.addEventListener("dispose", () => { materials++; }));
  const runtime = { cadScene: scene, displayRecords: scene.displayRecords, modelGroup: new THREE.Group(), edgesGroup: new THREE.Group() };
  runtime.modelGroup.add(scene.modelGroup); runtime.edgesGroup.add(scene.edgesGroup);
  disposeViewerCadScene(runtime, { releaseGpu: false, clearSceneGroup: group => assert.equal(group.children.length, 0) });
  assert.equal(gpu, 0); assert.equal(geometry.boundsTree, bvh); assert.equal(materials, 2);
  const next = buildModel(THREE, input, settings);
  assert.equal(next.displayRecords[0].geometry, geometry);
  next.dispose(); assert.equal(gpu, 1); assert.equal(geometry.boundsTree, null);
});

test("a throwing cleanup keeps the object reachable and cannot certify disposed ownership", () => {
  const scene = buildModel(THREE, source([mesh(1)]), settings), object = scene.displayRecords[0].mesh;
  const runtime = { cadScene: scene, displayRecords: scene.displayRecords, modelGroup: new THREE.Group(), edgesGroup: new THREE.Group() };
  runtime.modelGroup.add(scene.modelGroup); runtime.edgesGroup.add(scene.edgesGroup);
  object.userData.beforeDispose = () => { throw new Error("cleanup refuses"); };
  assert.throws(() => disposeViewerCadScene(runtime), /cleanup refuses/);
  assert.equal(runtime.cadScene, scene); assert.equal(object.parent, scene.modelGroup);
  assert.equal(scene.runtime.ownedGeometries.has(object.geometry), true);
  delete object.userData.beforeDispose;
  disposeViewerCadScene(runtime);
  assert.equal(object.parent, null); assert.equal(scene.runtime.ownedGeometries.size, 0);
});

// The default groups are the renderer's own; a group it is handed is held to the same rule.
test("failed stage cleanup counts the attached orphan until retry", () => {
  const input = source([mesh(1)]), scene = buildModel(THREE, input, settings);
  const runtime = { cadScene: scene, displayRecords: scene.displayRecords, modelGroup: new THREE.Group(),
    edgesGroup: new THREE.Group(), stageGroup: new THREE.Group() };
  runtime.modelGroup.add(scene.modelGroup); runtime.edgesGroup.add(scene.edgesGroup);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(300), 3));
  const orphan = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial()); runtime.stageGroup.add(orphan);
  let fail = true;
  const clearSceneGroup = group => {
    if (group !== runtime.stageGroup) return;
    if (fail) throw new Error("stage cleanup");
    orphan.geometry.dispose(); orphan.material.dispose(); orphan.removeFromParent();
  };
  assert.throws(() => disposeViewerCadScene(runtime, { clearSceneGroup, groups: ["stageGroup"] }), /stage cleanup/);
  assert.equal(runtime.cadScene, null);
  assert.equal(runtime.sceneCleanupFailed, true); assert.equal(orphan.parent, runtime.stageGroup);
  assert.ok(renderMemoryAccounting(runtime).surfaceBytes >= 1200, "attached orphan is counted outside the installed array");
  fail = false; disposeViewerCadScene(runtime, { clearSceneGroup, groups: ["stageGroup"] });
  assert.equal(runtime.sceneCleanupFailed, false);
  assert.equal(renderMemoryAccounting(runtime).surfaceBytes, 0);
});

test("a late geometry disposal failure does not decrement an earlier other-scene owner twice on retry", () => {
  const shared = mesh(1), privateMesh = mesh(2), input = source([shared, privateMesh]);
  const scene = buildModel(THREE, input, settings), other = buildModel(THREE, source([shared]), settings);
  const sharedGeometry = scene.displayRecords[0].geometry, privateGeometry = scene.displayRecords[1].geometry;
  assert.equal(other.displayRecords[0].geometry, sharedGeometry);
  let sharedDisposals = 0;
  sharedGeometry.addEventListener("dispose", () => { sharedDisposals++; });
  const fail = () => { throw new Error("GPU dispose listener"); };
  privateGeometry.addEventListener("dispose", fail);
  assert.throws(() => scene.dispose(), /GPU dispose listener/);
  privateGeometry.removeEventListener("dispose", fail);
  scene.dispose(); assert.equal(sharedDisposals, 0);
  other.dispose(); assert.equal(sharedDisposals, 1);
});

test("initial construction failure clears inaccessible orphans, and exposes a failed scene only when cleanup fails", () => {
  for (const cleanupFails of [false, true]) {
    const input = source([mesh(1), mesh(2)]), materials = [];
    let creates = 0;
    const primary = new Error("initial second material"), cleanup = new Error("initial orphan cleanup");
    const failCleanup = () => { throw cleanup; };
    const instrumented = { ...THREE, MeshPhysicalMaterial: class extends THREE.MeshPhysicalMaterial {
      constructor(...args) {
        if (++creates === 2) throw primary;
        super(...args); materials.push(this);
        if (cleanupFails) this.addEventListener("dispose", failCleanup);
      }
    } };
    let failure;
    try { buildModel(instrumented, input, settings); } catch (error) { failure = error; }
    assert.ok(failure);
    if (!cleanupFails) assert.equal(failure, primary);
    else {
      assert.equal(failure.cause, primary); assert.equal(failure.cleanupError, cleanup);
      assert.ok(failure.failedCadScene.modelGroup.children.length > 0);
      materials[0].removeEventListener("dispose", failCleanup);
      failure.failedCadScene.dispose();
      assert.equal(failure.failedCadScene.modelGroup.children.length, 0);
      assert.equal(failure.failedCadScene.runtime.ownedGeometries.size, 0);
    }
  }
});
