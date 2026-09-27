import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { builtGeometryBvhBytes, ensureFacePickBvh, estimateGeometryBvhBytes, scheduleRuntimeRaycastBvh } from "./raycastBvh.js";

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

// Two triangles over four SHARED vertices (the indexed surf shape), the second
// one raised so a ray down each column hits a known face index.
function indexedGeometry() {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array([
    0, 0, 0,
    1, 0, 0,
    1, 1, 0,
    0, 1, 0,
    2, 0, 1,
    3, 0, 1,
    3, 1, 1
  ]), 3));
  geometry.setIndex(new THREE.BufferAttribute(new Uint32Array([0, 1, 2, 0, 2, 3, 4, 5, 6]), 1));
  return geometry;
}

test("scheduleRuntimeRaycastBvh builds an indirect BVH over indexed geometry and keeps triangle order", async () => {
  const geometry = indexedGeometry();
  const savedIndex = geometry.index.array.slice();
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
  mesh.userData.faceIds = new Uint32Array([10, 11, 12]);
  mesh.updateMatrixWorld();
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }] });
  await tick();

  assert.ok(geometry.boundsTree, "BVH built on the indexed geometry");
  assert.deepEqual(geometry.index.array, savedIndex, "indirect build leaves the index buffer untouched");
  assert.equal(geometry.attributes.position.count, 7, "no de-indexed copy was made");
  const hitFirst = new THREE.Raycaster(new THREE.Vector3(0.6, 0.3, 5), new THREE.Vector3(0, 0, -1)).intersectObject(mesh, false);
  const hitLast = new THREE.Raycaster(new THREE.Vector3(2.9, 0.5, 5), new THREE.Vector3(0, 0, -1)).intersectObject(mesh, false);
  assert.equal(hitFirst[0]?.faceIndex, 0);
  assert.equal(hitLast[0]?.faceIndex, 2);
  assert.equal(mesh.userData.faceIds[hitLast[0].faceIndex], 12, "faceRuns keyed by triangle index resolve");
});

test("ensureFacePickBvh rebuilds when the proxy index array identity changes", async () => {
  const proxy = {
    facePositions: new Float32Array([0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0]),
    faceIndices: new Uint32Array([0, 1, 2, 0, 2, 3])
  };
  const makeMesh = () => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(proxy.facePositions, 3));
    geometry.setIndex(new THREE.BufferAttribute(proxy.faceIndices, 1));
    return new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  };
  const runtime = { facePickMesh: makeMesh() };
  ensureFacePickBvh(runtime, { proxy });
  await tick();
  const first = runtime.facePickMesh.geometry.boundsTree;
  assert.ok(first, "first BVH built in idle time");
  assert.equal(first.__builtFromIndexArray, proxy.faceIndices);

  // Same arrays, fresh geometry (a selector sync): the cached BVH is reattached.
  runtime.facePickMesh = makeMesh();
  ensureFacePickBvh(runtime, { proxy });
  assert.equal(runtime.facePickMesh.geometry.boundsTree, first);

  // New index array (a LOD swap): the cache misses and a new BVH is built.
  proxy.faceIndices = new Uint32Array([0, 2, 1, 0, 3, 2]);
  runtime.facePickMesh = makeMesh();
  ensureFacePickBvh(runtime, { proxy });
  await tick();
  const second = runtime.facePickMesh.geometry.boundsTree;
  assert.ok(second && second !== first, "index identity change rebuilds the BVH");
  assert.equal(second.__builtFromIndexArray, proxy.faceIndices);
});

test("a component released while its BVH was queued never gets a tree built for it", async () => {
  const kept = indexedGeometry();
  const released = indexedGeometry();
  const meshOf = (geometry) => {
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
    mesh.updateMatrixWorld();
    return mesh;
  };
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: meshOf(kept) }, { mesh: meshOf(released) }] });
  assert.equal(released.userData.__bvhQueued, true, "both are queued before any idle slice runs");

  // The publish that drops every occurrence of a component: cadScene's
  // releaseUnusedRecordGeometry disposes the geometry and clears the flag. It
  // cannot reach the already-scheduled queue, so the queue must notice.
  delete released.userData.__bvhQueued;
  released.dispose();

  await tick();
  await tick();
  assert.ok(kept.boundsTree, "the component still on screen gets its tree");
  assert.equal(released.boundsTree, undefined, "the released one does not");
});

test("a geometry queued twice builds once", async () => {
  const geometry = indexedGeometry();
  const meshOf = () => {
    const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
    mesh.updateMatrixWorld();
    return mesh;
  };
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: meshOf() }] });
  // Released and re-adopted by a later publish while the first queue still
  // holds it: the second schedule sees no flag and queues it again.
  delete geometry.userData.__bvhQueued;
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: meshOf() }] });
  let builds = 0;
  let tree = undefined;
  Object.defineProperty(geometry, "boundsTree", {
    configurable: true,
    get: () => tree,
    set: (value) => { tree = value; builds += 1; }
  });
  await tick();
  await tick();
  await tick();
  assert.equal(builds, 1, "one tree, not one per queue entry");
});

test("a denied BVH reservation leaves correct stock raycasting available", async () => {
  const geometry = indexedGeometry();
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
  mesh.updateMatrixWorld();
  const denied = [];
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }] }, {
    reserveBuild: ({ estimatedBytes }) => ({ ok: false, detail: { requestedBytes: estimatedBytes } }),
    onBuildDenied: (detail) => denied.push(detail),
  });
  await tick();
  assert.equal(geometry.boundsTree, undefined);
  assert.equal(denied[0].requestedBytes, estimateGeometryBvhBytes(geometry));
  const hits = new THREE.Raycaster(
    new THREE.Vector3(0.6, 0.3, 5),
    new THREE.Vector3(0, 0, -1)
  ).intersectObject(mesh, false);
  assert.equal(hits[0]?.faceIndex, 0, "acceleratedRaycast falls back without a tree");
});

test("a BVH reservation spans the idle build and reports retained bytes", async () => {
  const geometry = indexedGeometry();
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  const events = [];
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }] }, {
    reserveBuild: ({ estimatedBytes }) => {
      events.push(["reserve", estimatedBytes]);
      return { ok: true, token: "b1" };
    },
    finishBuild: (token, { builtBytes }) => events.push(["finish", token, builtBytes]),
  });
  await tick();
  assert.equal(events[0][0], "reserve");
  assert.equal(events[1][0], "finish");
  assert.equal(events[1][1], "b1");
  assert.ok(events[1][2] > 0);
  const tree = geometry.boundsTree;
  assert.equal(events[1][2], tree._roots.reduce((sum, root) => sum + root.byteLength, 0)
    + tree._indirectBuffer.byteLength, "finished allocation includes the real indirect permutation");
});

test("BVH accounting owns packed buffers once across shared trees", () => {
  const root = new ArrayBuffer(64);
  const permutation = new ArrayBuffer(32);
  const geometry = { boundsTree: { _roots: [root], _indirectBuffer: new Uint16Array(permutation, 4, 3) } };
  const seen = new Set();
  assert.equal(builtGeometryBvhBytes(geometry, seen), 96);
  assert.equal(builtGeometryBvhBytes({ boundsTree: geometry.boundsTree }, seen), 0);
  assert.equal(builtGeometryBvhBytes({}), 0);
});

test("deferred display BVHs reject far rays and share one build after an exact first pick", async () => {
  const geometry = indexedGeometry();
  geometry.computeBoundingBox();
  const material = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide });
  const first = new THREE.Mesh(geometry, material);
  const second = new THREE.Mesh(geometry, material);
  second.position.set(10, 0, 0);
  second.scale.set(-2, 3, 0.5);
  first.updateMatrixWorld();
  second.updateMatrixWorld();
  const events = [];
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: first }, { mesh: second }] }, {
    deferUntilRaycast: true,
    reserveBuild: () => { events.push("reserve"); return { ok: true, token: "demand" }; },
    finishBuild: () => events.push("finish"),
  });
  await tick();
  assert.equal(geometry.boundsTree, undefined, "display alone allocates no accelerator");
  const miss = new THREE.Raycaster(new THREE.Vector3(100, 0, 5), new THREE.Vector3(0, 0, -1));
  assert.deepEqual(miss.intersectObject(first, false), []);
  assert.equal(geometry.userData.__bvhQueued, undefined, "bounds miss queues nothing");
  const tooShort = new THREE.Raycaster(new THREE.Vector3(0.6, 0.3, 5), new THREE.Vector3(0, 0, -1), 0, 1);
  assert.deepEqual(tooShort.intersectObject(first, false), []);
  assert.equal(geometry.userData.__bvhQueued, undefined, "candidate beyond far queues nothing");
  const ray = new THREE.Raycaster(new THREE.Vector3(0.6, 0.3, 5), new THREE.Vector3(0, 0, -1), 1, 6);
  assert.equal(ray.intersectObject(first, false)[0]?.faceIndex, 0);
  const mirrorRay = new THREE.Raycaster(new THREE.Vector3(4.2, 1.5, 5), new THREE.Vector3(0, 0, -1));
  assert.equal(mirrorRay.intersectObject(second, false)[0]?.faceIndex, 2, "mirrored nonuniform occurrence keeps exact triangle identity");
  assert.equal(geometry.boundsTree, undefined, "both first picks use stock raycasting without building synchronously");
  assert.deepEqual(events, []);
  await tick();
  assert.deepEqual(events, ["reserve", "finish"], "one admitted build for shared geometry");
  assert.equal(mirrorRay.intersectObject(second, false)[0]?.faceIndex, 2);
});

test("deferred BVHs honor deformation before bounds and release before the idle build", async () => {
  const geometry = indexedGeometry();
  geometry.computeBoundingBox();
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
  mesh.updateMatrixWorld();
  mesh.userData.cadBeforeRaycast = () => {
    geometry.translate(10, 0, 0);
    geometry.computeBoundingBox();
    delete mesh.userData.cadBeforeRaycast;
  };
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }] }, { deferUntilRaycast: true });
  const ray = new THREE.Raycaster(new THREE.Vector3(10.6, 0.3, 5), new THREE.Vector3(0, 0, -1));
  assert.equal(ray.intersectObject(mesh, false)[0]?.faceIndex, 0);
  assert.equal(geometry.userData.__bvhQueued, true);
  delete geometry.userData.__bvhQueued;
  geometry.dispose();
  await tick();
  assert.equal(geometry.boundsTree, undefined, "released geometry is not built by pending demand");
});

test("deferred BVH denied admission leaves first and later picks exact", async () => {
  const geometry = indexedGeometry();
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
  mesh.updateMatrixWorld();
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }] }, {
    deferUntilRaycast: true,
    reserveBuild: () => ({ ok: false }),
  });
  const ray = new THREE.Raycaster(new THREE.Vector3(0.6, 0.3, 5), new THREE.Vector3(0, 0, -1));
  assert.equal(ray.intersectObject(mesh, false)[0]?.faceIndex, 0);
  await tick();
  assert.equal(geometry.boundsTree, undefined);
  assert.equal(ray.intersectObject(mesh, false)[0]?.faceIndex, 0);
  await tick();
  mesh.userData.cadBeforeRaycast = () => false;
  assert.deepEqual(ray.intersectObject(mesh, false), [], "deformation rejection remains authoritative");
});
