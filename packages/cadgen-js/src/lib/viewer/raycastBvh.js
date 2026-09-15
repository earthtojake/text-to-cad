import { MeshBVH, acceleratedRaycast } from "three-mesh-bvh";
import { Matrix4, Ray, Vector3 } from "three";
import { defaultRaycastBvhWorkerClient } from "./raycastBvhWorkerClient.js";

// BVHs are built with { indirect: true } so the geometry's index buffer is
// never reordered: faceIds/faceRuns lookups keyed by faceIndex stay valid and
// shared render geometry stays byte-identical. acceleratedRaycast falls back
// to stock three.js raycasting whenever a geometry has no boundsTree, so
// attaching it is always safe.
const BVH_OPTIONS = Object.freeze({ indirect: true });

// Bound disposable accelerator work, including environments without workers.
// Larger geometries retain stock raycasting.
export const DEFAULT_MAX_BVH_TRIANGLES = 2_500_000;
export const ESTIMATED_BVH_BYTES_PER_TRIANGLE = 32;
// Includes primitive bounds, the temporary split tree, and the worker isolate.
// This is an admission estimate, not a browser RSS limit.
const BVH_WORKER_BASE_BYTES = 16 * 1024 * 1024;
const BVH_WORKER_SCRATCH_BYTES_PER_TRIANGLE = 96;

function geometryTriangleCount(geometry) {
  if (geometry?.index) {
    return Math.floor(geometry.index.count / 3);
  }
  const position = geometry?.attributes?.position;
  return position ? Math.floor(position.count / 3) : 0;
}

export function estimateGeometryBvhBytes(geometry) {
  return geometryTriangleCount(geometry) * ESTIMATED_BVH_BYTES_PER_TRIANGLE;
}

export function estimateGeometryBvhBuildBytes(geometry) {
  return BVH_WORKER_BASE_BYTES
    + (geometry?.attributes?.position?.array?.byteLength || 0)
    + (geometry?.index?.array?.byteLength || 0)
    + geometryTriangleCount(geometry) * BVH_WORKER_SCRATCH_BYTES_PER_TRIANGLE
    + estimateGeometryBvhBytes(geometry);
}

export function builtGeometryBvhBytes(geometry, seenBuffers = new Set()) {
  const tree = geometry?.boundsTree;
  // Indirect builds preserve the render index by retaining a separate triangle
  // permutation. It is CPU storage just like the packed node roots. A view
  // retains its whole allocation, and reattached/shared trees own it only once.
  let bytes = 0;
  for (const value of [...(Array.isArray(tree?._roots) ? tree._roots : []), tree?._indirectBuffer]) {
    const buffer = ArrayBuffer.isView(value) ? value.buffer : value;
    if (!buffer || !Number.isFinite(buffer.byteLength) || seenBuffers.has(buffer)) continue;
    seenBuffers.add(buffer);
    bytes += buffer.byteLength;
  }
  return bytes;
}

// Input copies and worker admission wait for idle time so they do not compete
// with progressive display publication. Without worker support, the build also
// runs in this idle slice. A page that never idles still admits a tree after
// half a minute; until then picking uses stock raycasting.
const BVH_IDLE_TIMEOUT_MS = 30000;

function scheduleIdle(task) {
  if (typeof globalThis.requestIdleCallback === "function") {
    globalThis.requestIdleCallback(() => task(), { timeout: BVH_IDLE_TIMEOUT_MS });
    return;
  }
  setTimeout(task, 0);
}

const raycastDemand = new WeakMap();
const inverseWorld = new Matrix4();
const candidateRay = new Ray();
const candidatePoint = new Vector3();

function intersectsCandidateBounds(mesh, raycaster) {
  const geometry = mesh.geometry;
  if (!geometry.boundingBox) geometry.computeBoundingBox();
  if (!geometry.boundingBox) return true;
  inverseWorld.copy(mesh.matrixWorld).invert();
  candidateRay.copy(raycaster.ray).recast(Math.max(0, raycaster.near || 0)).applyMatrix4(inverseWorld);
  // A ray beginning inside the box can hit a face before its box exit, even
  // when that exit is beyond far. World-space distance handles scale/mirrors.
  if (geometry.boundingBox.containsPoint(candidateRay.origin)) return true;
  if (!candidateRay.intersectBox(geometry.boundingBox, candidatePoint)) return false;
  candidatePoint.applyMatrix4(mesh.matrixWorld);
  return candidatePoint.distanceTo(raycaster.ray.origin) <= raycaster.far;
}

function raycastWithDemand(raycaster, intersections) {
  // Deformation must materialize its exact CPU positions/bounds first.
  if (this.userData?.cadBeforeRaycast?.(raycaster) === false) return;
  const enqueue = raycastDemand.get(this);
  if (enqueue && !this.geometry.boundsTree) {
    if (!intersectsCandidateBounds(this, raycaster)) return;
    enqueue(this.geometry);
  }
  // The first qualifying ray is still exact. Building its accelerator waits
  // for idle time; a click never synchronously builds a batch of BVHs.
  return acceleratedRaycast.call(this, raycaster, intersections);
}

export function attachAcceleratedRaycast(mesh, enqueue = null) {
  if (!mesh?.isMesh) return;
  if (enqueue) raycastDemand.set(mesh, enqueue);
  else raycastDemand.delete(mesh);
  // One function also avoids allocating a wrapper per occurrence per publish.
  mesh.raycast = raycastWithDemand;
}

function buildGeometryBvh(geometry, maxTriangles) {
  if (!geometry || geometry.boundsTree || geometry.userData.__bvhSkipped) {
    return;
  }
  const triangles = geometryTriangleCount(geometry);
  if (!triangles || triangles > maxTriangles || !geometry.attributes?.position) {
    geometry.userData.__bvhSkipped = true;
    return;
  }
  try {
    geometry.boundsTree = new MeshBVH(geometry, BVH_OPTIONS);
  } catch {
    geometry.userData.__bvhSkipped = true;
  }
}

function captureGeometry(geometry) {
  const position = geometry.attributes.position;
  const index = geometry.index;
  if (position?.isInterleavedBufferAttribute || position?.itemSize !== 3 || position.normalized
    || !(position.array instanceof Float32Array || position.array instanceof Float64Array)
    || (index && (index.isInterleavedBufferAttribute || index.itemSize !== 1 || index.normalized
      || !(index.array instanceof Uint16Array || index.array instanceof Uint32Array)))
    || geometry.morphAttributes?.position?.length) return null;
  return {
    position, positionArray: position.array, positionVersion: position.version,
    positionCount: position.count,
    index, indexArray: index?.array, indexVersion: index?.version,
    indexCount: index?.count,
    groups: geometry.groups.map(({ start, count, materialIndex }) => ({ start, count, materialIndex })),
    start: geometry.drawRange.start, count: geometry.drawRange.count,
  };
}

function matchesGeometry(geometry, snapshot) {
  return geometry.attributes.position === snapshot.position
    && snapshot.position.array === snapshot.positionArray && snapshot.position.version === snapshot.positionVersion
    && snapshot.position.count === snapshot.positionCount && snapshot.position.itemSize === 3 && !snapshot.position.normalized
    && geometry.index === snapshot.index && geometry.index?.array === snapshot.indexArray
    && geometry.index?.version === snapshot.indexVersion && geometry.index?.count === snapshot.indexCount
    && (!geometry.index || (geometry.index.itemSize === 1 && !geometry.index.normalized))
    && geometry.groups.length === snapshot.groups.length && geometry.groups.every((group, i) =>
      group.start === snapshot.groups[i].start && group.count === snapshot.groups[i].count
      && group.materialIndex === snapshot.groups[i].materialIndex)
    && geometry.drawRange.start === snapshot.start && geometry.drawRange.count === snapshot.count
    && !geometry.morphAttributes?.position?.length;
}

function copiedGeometry(snapshot) {
  const position = new snapshot.positionArray.constructor(snapshot.positionArray);
  const index = snapshot.indexArray ? new snapshot.indexArray.constructor(snapshot.indexArray) : null;
  return {
    payload: {
      position, index,
      groups: snapshot.groups,
      drawRange: { start: snapshot.start, count: snapshot.count },
    },
    transfer: [position.buffer, ...(index ? [index.buffer] : [])],
  };
}

function deserializeGeometryBvh(serialized, geometry) {
  if (serialized.version !== 1 || !Array.isArray(serialized.roots) || !serialized.roots.length
    || !serialized.roots.every((root) => root instanceof ArrayBuffer && root.byteLength > 0 && root.byteLength % 32 === 0)
    || !(serialized.indirectBuffer instanceof Uint16Array || serialized.indirectBuffer instanceof Uint32Array)) {
    throw new Error("Unsupported BVH worker result");
  }
  return MeshBVH.deserialize(serialized, geometry, { setIndex: false, setBoundingBox: false });
}

const geometryBuilds = new WeakMap();

// Attaches accelerated raycasting to every display mesh and builds one BVH per
// unique (shared) geometry in idle time, one geometry per idle slice. Viewers
// can defer the request itself until a ray reaches the component's bounds.
export function scheduleRuntimeRaycastBvh(runtime, {
  maxTriangles = DEFAULT_MAX_BVH_TRIANGLES,
  reserveBuild = null,
  finishBuild = null,
  onBuildDenied = null,
  deferUntilRaycast = false,
  workerClient = defaultRaycastBvhWorkerClient(),
} = {}) {
  const records = Array.isArray(runtime?.displayRecords) ? runtime.displayRecords : [];
  const pending = [];
  let scheduled = false;
  const enqueue = (geometry) => {
    if (!geometry.boundsTree && !geometry.userData.__bvhSkipped && !geometry.userData.__bvhQueued) {
      const entry = { geometry, cancelled: false, request: null };
      const cleanup = () => {
        geometry.removeEventListener("dispose", entry.release);
        if (geometryBuilds.get(geometry) === entry) {
          geometryBuilds.delete(geometry);
          delete geometry.userData.__bvhQueued;
        }
      };
      entry.cleanup = cleanup;
      entry.release = () => {
        entry.cancelled = true;
        entry.request?.cancel();
        const index = pending.indexOf(entry);
        if (index !== -1) pending.splice(index, 1);
        cleanup();
      };
      geometry.addEventListener("dispose", entry.release);
      geometryBuilds.set(geometry, entry);
      geometry.userData.__bvhQueued = true;
      pending.push(entry);
      if (!scheduled) {
        scheduled = true;
        scheduleIdle(step);
      }
    }
  };
  const step = () => {
    const entry = pending.shift();
    if (!entry) {
      scheduled = false;
      return;
    }
    const { geometry } = entry;
    const current = () => !entry.cancelled && geometryBuilds.get(geometry) === entry
      && geometry.userData.__bvhQueued && !geometry.userData.__bvhSkipped && !geometry.boundsTree;
    const advance = () => {
      entry.cleanup();
      if (pending.length) scheduleIdle(step);
      else scheduled = false;
    };
    if (!current()) { advance(); return; }
    const triangles = geometryTriangleCount(geometry);
    if (!triangles || triangles > maxTriangles) {
      geometry.userData.__bvhSkipped = true;
      advance();
      return;
    }
    if (!workerClient) {
      const estimatedBytes = estimateGeometryBvhBytes(geometry);
      const reservation = reserveBuild?.({ geometry, estimatedBytes }) ?? { ok: true, token: null };
      if (reservation.ok === false) onBuildDenied?.({ geometry, estimatedBytes, ...(reservation.detail || {}) });
      else {
        buildGeometryBvh(geometry, maxTriangles);
        finishBuild?.(reservation.token, { geometry, builtBytes: builtGeometryBvhBytes(geometry) });
      }
      advance();
      return;
    }
    let reservation = null;
    let snapshot = null;
    let builtBytes = 0;
    entry.request = workerClient.enqueue(() => {
      if (!current()) return null;
      const currentTriangles = geometryTriangleCount(geometry);
      if (!currentTriangles || currentTriangles > maxTriangles) {
        geometry.userData.__bvhSkipped = true;
        return null;
      }
      snapshot = captureGeometry(geometry);
      if (!snapshot) { geometry.userData.__bvhSkipped = true; return null; }
      const estimatedBytes = estimateGeometryBvhBuildBytes(geometry);
      const admitted = reserveBuild?.({ geometry, estimatedBytes }) ?? { ok: true, token: null };
      if (admitted.ok === false) {
        onBuildDenied?.({ geometry, estimatedBytes, ...(admitted.detail || {}) });
        return null;
      }
      reservation = admitted;
      if (!current() || !matchesGeometry(geometry, snapshot)) return null;
      return copiedGeometry(snapshot);
    });
    const settle = (serialized, error = null) => {
      try {
        if (error) throw error;
        if (serialized && current() && matchesGeometry(geometry, snapshot)) {
          geometry.boundsTree = deserializeGeometryBvh(serialized, geometry);
          if (!entry.cancelled) builtBytes = builtGeometryBvhBytes(geometry);
        }
      } catch (failure) {
        if (current() && failure?.name !== "AbortError") geometry.userData.__bvhSkipped = true;
      } finally {
        try {
          if (reservation) finishBuild?.(reservation.token, { geometry, builtBytes });
        } finally {
          advance();
        }
      }
    };
    // Release this reservation in the first settlement callback, before the
    // client's next FIFO admission (not several Promise.finally hops later).
    entry.request.promise.then((serialized) => settle(serialized), (error) => settle(null, error));
  };
  for (const record of records) {
    const mesh = record?.mesh;
    const geometry = mesh?.geometry;
    if (!geometry) continue;
    attachAcceleratedRaycast(mesh, deferUntilRaycast ? enqueue : null);
    if (!deferUntilRaycast) enqueue(geometry);
  }
}

// The merged face-pick proxy is rebuilt as a fresh BufferGeometry on every
// selector sync, but always wraps the same proxy typed arrays, so the built
// BVH is cached on the proxy and reattached across rebuilds.
export function ensureFacePickBvh(runtime, selectorRuntime, options = null) {
  const {
    maxTriangles = DEFAULT_MAX_BVH_TRIANGLES,
    reserveBuild = null,
    finishBuild = null,
    onBuildDenied = null,
  } = options || runtime?.raycastBvhOptions || {};
  const mesh = runtime?.facePickMesh;
  const proxy = selectorRuntime?.proxy;
  if (!mesh?.geometry || !proxy) {
    return;
  }
  attachAcceleratedRaycast(mesh);
  const cached = proxy.__facePickBvh;
  if (cached && cached.__builtFromIndexArray === proxy.faceIndices) {
    mesh.geometry.boundsTree = cached;
    return;
  }
  if (proxy.__facePickBvhPending || proxy.__facePickBvhSkipped) {
    return;
  }
  proxy.__facePickBvhPending = true;
  scheduleIdle(() => {
    proxy.__facePickBvhPending = false;
    const activeMesh = runtime?.facePickMesh;
    const geometry = activeMesh?.geometry;
    if (!geometry || geometry.index?.array !== proxy.faceIndices) {
      return;
    }
    if (geometryTriangleCount(geometry) > maxTriangles) {
      proxy.__facePickBvhSkipped = true;
      return;
    }
    const estimatedBytes = estimateGeometryBvhBytes(geometry);
    const reservation = reserveBuild?.({ geometry, estimatedBytes }) ?? { ok: true, token: null };
    if (reservation.ok === false) {
      onBuildDenied?.({ geometry, estimatedBytes, ...(reservation.detail || {}) });
      return;
    }
    try {
      const bvh = new MeshBVH(geometry, BVH_OPTIONS);
      bvh.__builtFromIndexArray = proxy.faceIndices;
      proxy.__facePickBvh = bvh;
      geometry.boundsTree = bvh;
      finishBuild?.(reservation.token, { geometry, builtBytes: builtGeometryBvhBytes(geometry) });
    } catch {
      proxy.__facePickBvhSkipped = true;
      finishBuild?.(reservation.token, { geometry, builtBytes: 0 });
    }
  });
}
