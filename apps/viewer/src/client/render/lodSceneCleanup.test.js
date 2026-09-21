import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { buildModel } from "cadgen-js/common/cadScene.js";
import { disposeViewerCadScene } from "./lodSceneCleanup.js";
import { createLodSceneAdoption } from "./lodSceneAdoption.js";
import { createLodScheduler } from "./lodScheduler.js";
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
  assert.equal(disposeViewerCadScene(runtime, { clearSceneGroup }), next);
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

test("failed stage cleanup retains its retired source identity and counts the attached orphan until retry", () => {
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
  assert.throws(() => disposeViewerCadScene(runtime, { clearSceneGroup }), /stage cleanup/);
  assert.equal(runtime.cadScene, null); assert.equal(runtime.retiringCadSource, input);
  assert.equal(runtime.sceneCleanupFailed, true); assert.equal(orphan.parent, runtime.stageGroup);
  assert.ok(renderMemoryAccounting(runtime).surfaceBytes >= 1200, "attached orphan is counted outside the installed array");
  fail = false; assert.equal(disposeViewerCadScene(runtime, { clearSceneGroup }), input);
  assert.equal(runtime.retiringCadSource, null); assert.equal(runtime.sceneCleanupFailed, false);
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

const drain = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };

test("real partially reconciled scene retains its scheduler lease through exact restoration or fatal teardown", async () => {
  for (const failRestore of [false, true]) {
    const oldMesh = mesh(1), nextMesh = mesh(2);
    const base = source(Array(3).fill(oldMesh)), candidate = source(Array(3).fill(nextMesh));
    for (const value of [base, candidate]) value.parts.forEach(part => { part.componentId = "a"; });
    const descriptor = { occurrences: base.parts.map(part => ({ id: part.id, component: "a" })) };
    let reject = false, creations = 0;
    const instrumented = { ...THREE, MeshPhysicalMaterial: class extends THREE.MeshPhysicalMaterial {
      constructor(...args) {
        if (reject && ++creations === 2) throw new Error("second occurrence material fails");
        super(...args);
      }
    } };
    const original = buildModel(instrumented, base, settings);
    const runtime = { cadScene: original, displayRecords: original.displayRecords,
      modelGroup: new THREE.Group(), edgesGroup: new THREE.Group() };
    runtime.modelGroup.add(original.modelGroup); runtime.edgesGroup.add(original.edgesGroup);
    const context = { meshHash: "revision", meshData: base };
    const tracker = createLodSceneAdoption({ currentContext: () => context });
    let timer, released = 0, loads = 0, restoreQueued = false, fatal = false;
    const scheduler = createLodScheduler({ minimumLevel: 1,
      setTimeoutFn: callback => { timer = callback; return 1; }, clearTimeoutFn: () => { timer = null; },
      reserveLevel: () => ({ ok: true, token: "retained-old-and-new" }), releaseLevel: () => { released++; },
      loadLevel: async () => { loads++; return { meshData: nextMesh }; },
      applyLevel: async (_cid, _level, _payload, { signal }) => {
        const completion = tracker.expect({ context, source: candidate, descriptor, componentId: "a",
          componentMesh: nextMesh, baseSource: base, baseMesh: oldMesh, signal, currentSource: () => candidate,
          commit: value => { context.meshData = value; }, restore: () => { restoreQueued = true; return base; },
          failed: () => { fatal = true; } });
        tracker.published(candidate);
        const outcome = await completion;
        return outcome.status === "disposed-failed" ? { status: "scene-failed" } : outcome.status === "adopted";
      },
    });
    scheduler.setComponents([{ cid: "a", diagonal: 2, level: 0 }]);
    const camera = { camera: { kind: "perspective", fovYDeg: 45 }, viewportHeightPx: 1000, distanceFor: () => 10000 };
    scheduler.onCameraSample(camera); timer(); await drain();
    assert.equal(loads, 1); assert.equal(released, 0); assert.equal(scheduler.levelOf("a"), 0);
    reject = true; creations = 0;
    assert.throws(() => original.update({ source: candidate }), /second occurrence/);
    const orphan = original.modelGroup.children.find(object => object.userData?.partId === "part0");
    assert.ok(orphan);
    tracker.failed(candidate); await drain(); assert.equal(released, 0);
    const disposedSource = disposeViewerCadScene(runtime);
    tracker.disposed(disposedSource, { recover: true }); await drain();
    assert.equal(restoreQueued, true); assert.equal(released, 0); assert.equal(context.meshData, base);
    assert.equal(orphan.parent, null); assert.equal(original.runtime.ownedGeometries.size, 0);
    reject = failRestore; creations = 0;
    if (failRestore) {
      assert.throws(() => buildModel(instrumented, base, settings), /second occurrence/);
      tracker.disposed(base, { recover: true });
    } else {
      const restored = buildModel(instrumented, base, settings);
      runtime.cadScene = restored; runtime.displayRecords = restored.displayRecords;
      runtime.modelGroup.add(restored.modelGroup); runtime.edgesGroup.add(restored.edgesGroup);
      assert.equal(restored.displayRecords.length, 3);
      assert.ok(restored.displayRecords.every(record => record.sourcePart.sourceMesh === oldMesh));
      assert.deepEqual(restored.displayRecords.map(record => record.mesh.matrix.elements.slice(12, 15)), [[0, 0, 0], [2, 0, 0], [4, 0, 0]]);
      tracker.adopted(base);
    }
    await drain(); assert.equal(released, 1); assert.equal(loads, 1); assert.equal(scheduler.levelOf("a"), 0);
    assert.equal(fatal, failRestore); assert.equal(scheduler.snapshot().sceneFailed, failRestore);
    if (failRestore) {
      scheduler.onCameraSample(camera); timer(); await drain(); assert.equal(loads, 1, "fatal scene stops camera retries");
    }
    scheduler.dispose(); disposeViewerCadScene(runtime);
    await drain(); assert.equal(released, 1, "ownership releases once across teardown/unmount");
  }
});

test("a real failed two-CID reconciliation holds both leases through restoration or confirmed fatal teardown", async () => {
  for (const failRestore of [false, true]) {
    const oldMeshes = [mesh(1), mesh(1.2)], nextMeshes = [mesh(2), mesh(2.2)];
    const base = source(oldMeshes.flatMap(value => Array(3).fill(value)));
    const candidate = source(nextMeshes.flatMap(value => Array(3).fill(value)));
    for (const value of [base, candidate]) value.parts.forEach((part, i) => { part.componentId = i < 3 ? "a" : "b"; });
    const descriptor = { occurrences: base.parts.map(part => ({ id: part.id, component: part.componentId })) };
    let reject = false, creations = 0;
    const instrumented = { ...THREE, MeshPhysicalMaterial: class extends THREE.MeshPhysicalMaterial {
      constructor(...args) { if (reject && ++creations === 4) throw new Error("first second-CID record fails"); super(...args); }
    } };
    const original = buildModel(instrumented, base, settings);
    const runtime = { cadScene: original, displayRecords: original.displayRecords, modelGroup: new THREE.Group(), edgesGroup: new THREE.Group() };
    runtime.modelGroup.add(original.modelGroup); runtime.edgesGroup.add(original.edgesGroup);
    const context = { descriptor, meshHash: "revision", meshData: base }, tracker = createLodSceneAdoption({ currentContext: () => context });
    const timers = new Map(); let nextTimer = 0, released = 0, commits = 0, restoreQueued = false;
    const scheduler = createLodScheduler({ minimumLevel: 1, batchSize: 4,
      setTimeoutFn: fn => { timers.set(++nextTimer, fn); return nextTimer; }, clearTimeoutFn: id => timers.delete(id),
      reserveLevel: ({ cid }) => ({ ok: true, token: cid }), releaseLevel: () => { released++; },
      loadLevel: async cid => ({ meshData: nextMeshes[cid === "a" ? 0 : 1] }),
      applyBatch: async (entries, { signal }) => {
        assert.equal(entries.length, 2);
        const completion = tracker.expectBatch({ context, descriptor, source: candidate, baseSource: base, signal,
          currentSource: () => candidate, items: entries.map(({ cid, payload }) => ({ componentId: cid,
            componentMesh: payload.meshData, baseMesh: oldMeshes[cid === "a" ? 0 : 1] })),
          commit: () => { commits++; context.meshData = candidate; }, restore: () => { restoreQueued = true; return base; },
        }); tracker.published(candidate);
        const outcome = await completion;
        return outcome.status === "disposed-failed" ? { status: "scene-failed" } : outcome.status === "adopted";
      },
    });
    scheduler.setComponents(["a", "b"].map(cid => ({ cid, level: 0, diagonal: 3 })));
    scheduler.onCameraSample({ camera: { kind: "perspective", fovYDeg: 45 }, viewportHeightPx: 1000, distanceFor: () => 10000 });
    for (const [id, fn] of [...timers]) { timers.delete(id); fn(); }
    for (let i = 0; i < 3; i++) await drain();
    assert.equal(scheduler.snapshot().adopting, 2); assert.equal(released, 0);
    reject = true; creations = 0; assert.throws(() => original.update({ source: candidate }), /second-CID record/);
    const changed = original.modelGroup.children.filter(object => object.userData?.partId && Number(object.userData.partId.slice(4)) < 3);
    assert.equal(changed.length, 3, "first CID attached before the second CID failed");
    tracker.failed(candidate); await drain(); assert.equal(released, 0); assert.equal(commits, 0);
    tracker.disposed(disposeViewerCadScene(runtime), { recover: true }); await drain();
    assert.equal(restoreQueued, true); assert.equal(released, 0); assert.equal(context.meshData, base);
    assert.ok(changed.every(object => object.parent === null)); assert.equal(original.runtime.ownedGeometries.size, 0);
    reject = failRestore; creations = 0;
    if (failRestore) {
      assert.throws(() => buildModel(instrumented, base, settings), /second-CID record/);
      tracker.disposed(base, { recover: true });
    } else {
      const restored = buildModel(instrumented, base, settings);
      assert.equal(restored.displayRecords.length, 6);
      assert.deepEqual(restored.displayRecords.map(record => record.sourcePart.sourceMesh), base.parts.map(part => part.sourceMesh));
      tracker.adopted(base); restored.dispose();
    }
    await drain(); assert.equal(released, 2); assert.equal(commits, 0);
    assert.deepEqual(scheduler.snapshot().levelCounts, { 0: 2 }); assert.equal(scheduler.snapshot().sceneFailed, failRestore);
    scheduler.dispose(); disposeViewerCadScene(runtime);
  }
});
