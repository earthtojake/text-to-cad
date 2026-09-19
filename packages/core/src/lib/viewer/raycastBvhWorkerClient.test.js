import assert from "node:assert/strict";
import test from "node:test";
import { Worker as Thread } from "node:worker_threads";
import * as THREE from "three";
import { MeshBVH } from "three-mesh-bvh";
import { buildModel } from "../../common/cadScene.js";
import { buildSerializedRaycastBvh, raycastBvhResultTransfers } from "./raycastBvhBuild.js";
import { createRaycastBvhWorkerClient } from "./raycastBvhWorkerClient.js";
import { attachAcceleratedRaycast, estimateGeometryBvhBuildBytes, estimateGeometryBvhBytes, scheduleRuntimeRaycastBvh } from "./raycastBvh.js";

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

function geometry() {
  const result = new THREE.BufferGeometry();
  result.setAttribute("position", new THREE.BufferAttribute(new Float32Array([
    0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0,
    2, 0, 1, 3, 0, 1, 3, 1, 1,
  ]), 3));
  result.setIndex(new THREE.BufferAttribute(new Uint32Array([0, 1, 2, 0, 2, 3, 4, 5, 6]), 1));
  return result;
}

function meshOf(value) {
  const mesh = new THREE.Mesh(value, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide }));
  mesh.updateMatrixWorld();
  return mesh;
}

function fixture() {
  const workers = [];
  const client = createRaycastBvhWorkerClient({ createWorker: () => {
    const worker = {
      terminated: false,
      postMessage(payload, transfer) {
        this.payload = structuredClone(payload, { transfer });
      },
      terminate() { this.terminated = true; this.payload = null; },
      complete() {
        const serialized = buildSerializedRaycastBvh(this.payload);
        this.onmessage({ data: structuredClone({ serialized }, { transfer: raycastBvhResultTransfers(serialized) }) });
      },
    };
    workers.push(worker);
    return worker;
  } });
  const events = [];
  const options = {
    workerClient: client,
    reserveBuild: ({ geometry: value, estimatedBytes }) => {
      events.push({ kind: "reserve", geometry: value, bytes: estimatedBytes });
      return { ok: true, token: value.uuid };
    },
    finishBuild: (token, { builtBytes }) => events.push({ kind: "finish", token, bytes: builtBytes }),
  };
  return { workers, client, options, events };
}

function hits(mesh, ray, stock = false) {
  const intersections = [];
  if (stock) THREE.Mesh.prototype.raycast.call(mesh, ray, intersections);
  else mesh.raycast(ray, intersections);
  return intersections.map((hit) => ({ faceIndex: hit.faceIndex, materialIndex: hit.face.materialIndex,
    distance: Number(hit.distance.toFixed(9)), point: hit.point.toArray().map((v) => Number(v.toFixed(9))) }))
    .sort((a, b) => a.distance - b.distance || a.faceIndex - b.faceIndex);
}

test("worker admission owns copies and scratch; pending and built picking keep exact triangle order", async () => {
  const { workers, options, events } = fixture();
  const value = geometry();
  const mesh = meshOf(value);
  mesh.position.set(10, 0, 0);
  mesh.scale.set(-2, 3, 0.5);
  mesh.updateMatrixWorld();
  const position = value.attributes.position.array;
  const index = value.index.array;
  const originalPosition = position.slice(), originalIndex = index.slice();
  const rays = [
    new THREE.Raycaster(new THREE.Vector3(4.2, 1.5, 5), new THREE.Vector3(0, 0, -1), 0, 10),
    new THREE.Raycaster(new THREE.Vector3(9.2, 1.5, 5), new THREE.Vector3(0, 0, -1), 1, 6),
    new THREE.Raycaster(new THREE.Vector3(4.2, 1.5, 5), new THREE.Vector3(0, 0, -1), 0, 1),
  ];
  const expected = rays.map((ray) => hits(mesh, ray, true));
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }, { mesh: meshOf(value) }] }, { ...options, deferUntilRaycast: true });
  await tick();
  assert.equal(workers.length, 0, "no worker before a qualifying ray");
  assert.deepEqual(rays.map((ray) => hits(mesh, ray)), expected);
  await tick();
  assert.equal(workers.length, 1);
  assert.equal(value.boundsTree, undefined);
  assert.deepEqual(rays.map((ray) => hits(mesh, ray)), expected, "stock intersections remain available during build");
  assert.equal(value.attributes.position.array, position);
  assert.equal(value.index.array, index);
  assert.deepEqual(position, originalPosition);
  assert.deepEqual(index, originalIndex);
  assert.notEqual(workers[0].payload.position.buffer, position.buffer);
  assert.notEqual(workers[0].payload.index.buffer, index.buffer);
  assert.equal(events[0].bytes, estimateGeometryBvhBuildBytes(value));
  assert.ok(events[0].bytes > position.byteLength + index.byteLength + estimateGeometryBvhBytes(value));
  workers[0].complete();
  await tick();
  assert.ok(value.boundsTree);
  assert.equal(workers[0].terminated, true);
  assert.equal(events.filter((event) => event.kind === "finish").length, 1);
  assert.ok(events[1].bytes > 0 && events[1].bytes < events[0].bytes);
  assert.deepEqual(rays.map((ray) => hits(mesh, ray)), expected);
  assert.deepEqual(index, originalIndex);
  assert.deepEqual(position, originalPosition);
});

test("worker groups and draw ranges preserve the stock hit multiset, including infinite group counts", async () => {
  for (const count of [3, Infinity]) {
    const { workers, options } = fixture();
    const value = geometry();
    value.addGroup(0, 3, 0);
    value.addGroup(3, count, 1);
    value.setDrawRange(3, 6);
    const mesh = meshOf(value);
    mesh.material = [mesh.material, new THREE.MeshBasicMaterial({ side: THREE.DoubleSide })];
    const rays = [0.2, 0.8, 2.8].map((x) => new THREE.Raycaster(new THREE.Vector3(x, 0.9, 5), new THREE.Vector3(0, 0, -1)));
    const expected = rays.map((ray) => hits(mesh, ray, true));
    scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }] }, options);
    await tick();
    workers[0].complete();
    await tick();
    assert.deepEqual(rays.map((ray) => hits(mesh, ray)), expected);
  }
});

test("worker acceleration preserves nonindexed geometry and Float64 positions", async () => {
  const { workers, options } = fixture();
  const value = geometry().toNonIndexed();
  value.setAttribute("position", new THREE.BufferAttribute(new Float64Array(value.attributes.position.array), 3));
  const mesh = meshOf(value);
  const position = value.attributes.position.array;
  const ray = new THREE.Raycaster(new THREE.Vector3(2.8, 0.5, 5), new THREE.Vector3(0, 0, -1));
  const expected = hits(mesh, ray, true);
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }] }, options);
  await tick();
  workers[0].complete();
  await tick();
  assert.ok(value.boundsTree);
  assert.equal(value.index, null, "deserializing must not create a render index");
  assert.equal(value.attributes.position.array, position);
  assert.deepEqual(hits(mesh, ray), expected);
});

test("deformation guards remain authoritative while a worker is pending", async () => {
  const { workers, options, events } = fixture();
  const value = geometry();
  const mesh = meshOf(value);
  const ray = new THREE.Raycaster(new THREE.Vector3(0.6, 0.3, 5), new THREE.Vector3(0, 0, -1));
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }] }, { ...options, deferUntilRaycast: true });
  assert.equal(hits(mesh, ray)[0].faceIndex, 0);
  await tick();
  mesh.userData.cadBeforeRaycast = () => {
    value.translate(10, 0, 0);
    value.userData.__bvhSkipped = true;
    return false;
  };
  assert.deepEqual(hits(mesh, ray), []);
  workers[0].complete();
  await tick();
  assert.equal(value.boundsTree, undefined);
  assert.equal(events[1].bytes, 0);
});

test("a single FIFO releases its reservation before admitting the next request after worker failure", async () => {
  const { workers, options, events } = fixture();
  const first = geometry(), second = geometry();
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: meshOf(first) }] }, options);
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: meshOf(second) }] }, options);
  await tick();
  assert.equal(workers.length, 1);
  assert.deepEqual(events.map((event) => event.kind), ["reserve"]);
  workers[0].onerror({ message: "test failure" });
  await tick();
  assert.equal(workers[0].terminated, true);
  assert.equal(first.boundsTree, undefined);
  assert.equal(first.userData.__bvhSkipped, true);
  assert.equal(workers.length, 2);
  assert.deepEqual(events.map((event) => event.kind), ["reserve", "finish", "reserve"]);
  assert.equal(events[1].bytes, 0);
  workers[1].complete();
  await tick();
  assert.ok(second.boundsTree);
  assert.equal(workers[1].terminated, true);
});

test("denied work allocates no worker or input copy and leaves stock picking usable", async () => {
  const { workers, options, events } = fixture();
  const value = geometry();
  const mesh = meshOf(value);
  Object.defineProperty(value.attributes.position.array, "constructor", { get() { throw new Error("must not copy denied input"); } });
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh }] }, { ...options, reserveBuild: () => ({ ok: false }) });
  await tick();
  assert.equal(workers.length, 0);
  assert.equal(events.length, 0);
  assert.equal(value.boundsTree, undefined);
  const ray = new THREE.Raycaster(new THREE.Vector3(0.6, 0.3, 5), new THREE.Vector3(0, 0, -1));
  assert.equal(hits(mesh, ray)[0].faceIndex, 0);
});

test("all changed geometry snapshots reject completed worker trees", async () => {
  const mutations = [
    (value) => value.setAttribute("position", new THREE.BufferAttribute(value.attributes.position.array, 3)),
    (value) => { value.attributes.position.array = value.attributes.position.array.slice(); },
    (value) => { value.attributes.position.needsUpdate = true; },
    (value) => { value.attributes.position.normalized = true; },
    (value) => { value.attributes.position.count -= 1; },
    (value) => value.setIndex(new THREE.BufferAttribute(value.index.array, 1)),
    (value) => { value.index.array = value.index.array.slice(); },
    (value) => { value.index.needsUpdate = true; },
    (value) => value.addGroup(0, 3, 0),
    (value) => value.setDrawRange(3, 6),
    (value) => { value.userData.__bvhSkipped = true; },
  ];
  for (const mutate of mutations) {
    const { workers, options, events } = fixture();
    const value = geometry();
    scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: meshOf(value) }] }, options);
    await tick();
    mutate(value);
    workers[0].complete();
    await tick();
    assert.equal(value.boundsTree, undefined);
    assert.equal(events[1].bytes, 0);
    assert.equal(value.userData.__bvhQueued, undefined);
  }
});

test("dispose cancels idle, FIFO-queued and active work; a re-adopted geometry rejects the old result", async () => {
  const { workers, options, events } = fixture();
  const idle = geometry();
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: meshOf(idle) }] }, options);
  idle.dispose();
  await tick();
  assert.equal(workers.length, 0);
  const active = geometry(), queued = geometry();
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: meshOf(active) }] }, options);
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: meshOf(queued) }] }, options);
  await tick();
  const late = workers[0].onmessage;
  const serialized = buildSerializedRaycastBvh(workers[0].payload);
  queued.dispose();
  active.dispose();
  scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: meshOf(active) }] }, options);
  await tick();
  assert.equal(workers[0].terminated, true);
  assert.equal(workers.length, 2, "released queued geometry never received an isolate");
  late({ data: { serialized } });
  await tick();
  assert.equal(active.boundsTree, undefined, "old ownership token cannot attach after re-adoption");
  assert.equal(queued.boundsTree, undefined);
  assert.equal(events[1].bytes, 0);
  workers[1].complete();
  await tick();
  assert.ok(active.boundsTree);
});

test("two scene owners share one pending BVH; only the last release terminates it", async () => {
  const { workers, options, events } = fixture();
  const value = geometry();
  const bounds = { min: [0, 0, 0], max: [3, 1, 1] };
  const component = { vertices: value.attributes.position.array, indices: value.index.array, bounds };
  const source = { vertices: new Float32Array(), indices: new Uint32Array(), bounds,
    parts: [{ id: "o1", sourceMesh: component, sourceMeshKey: "part", vertexCount: 7, triangleCount: 3, bounds }] };
  const first = buildModel(THREE, source, { renderPartsIndividually: true });
  const second = buildModel(THREE, source, { renderPartsIndividually: true });
  const shared = first.displayRecords[0].geometry;
  assert.equal(second.displayRecords[0].geometry, shared);
  scheduleRuntimeRaycastBvh(first.runtime, options);
  scheduleRuntimeRaycastBvh(second.runtime, options);
  await tick();
  assert.equal(workers.length, 1);
  first.dispose();
  assert.equal(workers[0].terminated, false);
  second.dispose();
  assert.equal(workers[0].terminated, true);
  await tick();
  assert.equal(shared.boundsTree, null);
  assert.equal(events[1].bytes, 0);
});

test("worker startup and protocol failures leave the display arrays intact without inline retry", async () => {
  for (const mode of ["startup", "protocol", "message"]) {
    const f = fixture();
    const options = mode === "startup" ? { ...f.options,
      workerClient: createRaycastBvhWorkerClient({ createWorker: () => { throw new Error("blocked worker"); } }),
    } : f.options;
    const value = geometry();
    const position = value.attributes.position.array.slice(), index = value.index.array.slice();
    scheduleRuntimeRaycastBvh({ displayRecords: [{ mesh: meshOf(value) }] }, options);
    await tick();
    if (mode === "protocol") f.workers[0].onmessage({ data: { serialized: { version: 99 } } });
    if (mode === "message") f.workers[0].onmessageerror();
    await tick();
    assert.equal(value.boundsTree, undefined);
    assert.equal(value.userData.__bvhSkipped, true);
    assert.deepEqual(value.attributes.position.array, position);
    assert.deepEqual(value.index.array, index);
    assert.equal(f.events[1].bytes, 0);
  }
});

test("the browser worker entry builds and transfers only BVH buffers in a real isolated thread", async (t) => {
  const ended = [];
  const entry = new URL("./raycastBvhWorker.js", import.meta.url).href;
  const client = createRaycastBvhWorkerClient({ createWorker: () => {
    const thread = new Thread(`
      import { parentPort } from 'node:worker_threads';
      globalThis.self = { postMessage: (data, transfer) => parentPort.postMessage(data, transfer) };
      await import(${JSON.stringify(entry)});
      parentPort.on('message', data => self.onmessage({ data }));
    `, { eval: true });
    const adapter = {
      postMessage: (data, transfer) => thread.postMessage(data, transfer),
      terminate: () => { ended.push(thread.terminate()); },
    };
    thread.on("message", (data) => adapter.onmessage?.({ data }));
    thread.on("error", (error) => adapter.onerror?.(error));
    thread.on("messageerror", () => adapter.onmessageerror?.());
    return adapter;
  } });
  t.after(async () => { await Promise.all(ended); });
  const value = geometry();
  const mesh = meshOf(value);
  const position = value.attributes.position.array.slice(), index = value.index.array.slice();
  const request = client.enqueue(() => ({ payload: { position, index, groups: [], drawRange: { start: 0, count: Infinity } },
    transfer: [position.buffer, index.buffer] }));
  const serialized = await request.promise;
  assert.deepEqual(Object.keys(serialized).sort(), ["indirectBuffer", "roots", "version"]);
  assert.equal(position.byteLength, 0);
  assert.equal(index.byteLength, 0);
  assert.equal(value.attributes.position.array.length, 21);
  assert.equal(value.index.array.length, 9);
  value.boundsTree = MeshBVH.deserialize(serialized, value, { setIndex: false });
  attachAcceleratedRaycast(mesh);
  const ray = new THREE.Raycaster(new THREE.Vector3(2.8, 0.5, 5), new THREE.Vector3(0, 0, -1));
  assert.deepEqual(hits(mesh, ray), hits(mesh, ray, true));
  assert.equal(ended.length, 1);
});
