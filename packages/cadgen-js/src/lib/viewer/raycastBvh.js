import { MeshBVH, acceleratedRaycast } from "three-mesh-bvh";

// BVHs are built with { indirect: true } so the geometry's index buffer is
// never reordered: faceIds/faceRuns lookups keyed by faceIndex stay valid and
// shared render geometry stays byte-identical. acceleratedRaycast falls back
// to stock three.js raycasting whenever a geometry has no boundsTree, so
// attaching it is always safe.
const BVH_OPTIONS = Object.freeze({ indirect: true });

// A BVH build is one synchronous pass (~0.35 s per million triangles), so very
// large geometries are skipped rather than risking a visible idle-time stall;
// they keep stock raycasting.
export const DEFAULT_MAX_BVH_TRIANGLES = 2_500_000;

function geometryTriangleCount(geometry) {
  if (geometry?.index) {
    return Math.floor(geometry.index.count / 3);
  }
  const position = geometry?.attributes?.position;
  return position ? Math.floor(position.count / 3) : 0;
}

function scheduleIdle(task) {
  if (typeof globalThis.requestIdleCallback === "function") {
    globalThis.requestIdleCallback(() => task(), { timeout: 2000 });
    return;
  }
  setTimeout(task, 0);
}

export function attachAcceleratedRaycast(mesh) {
  if (mesh?.isMesh) {
    mesh.raycast = acceleratedRaycast;
  }
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

// Attaches accelerated raycasting to every display mesh and builds one BVH per
// unique (shared) geometry in idle time, one geometry per idle slice.
export function scheduleRuntimeRaycastBvh(runtime, { maxTriangles = DEFAULT_MAX_BVH_TRIANGLES } = {}) {
  const records = Array.isArray(runtime?.displayRecords) ? runtime.displayRecords : [];
  const pending = [];
  for (const record of records) {
    const mesh = record?.mesh;
    const geometry = mesh?.geometry;
    if (!geometry) {
      continue;
    }
    attachAcceleratedRaycast(mesh);
    if (!geometry.boundsTree && !geometry.userData.__bvhSkipped && !geometry.userData.__bvhQueued) {
      geometry.userData.__bvhQueued = true;
      pending.push(geometry);
    }
  }
  const step = () => {
    const geometry = pending.shift();
    if (!geometry) {
      return;
    }
    delete geometry.userData.__bvhQueued;
    buildGeometryBvh(geometry, maxTriangles);
    if (pending.length) {
      scheduleIdle(step);
    }
  };
  if (pending.length) {
    scheduleIdle(step);
  }
}

// The merged face-pick proxy is rebuilt as a fresh BufferGeometry on every
// selector sync, but always wraps the same proxy typed arrays, so the built
// BVH is cached on the proxy and reattached across rebuilds.
export function ensureFacePickBvh(runtime, selectorRuntime, { maxTriangles = DEFAULT_MAX_BVH_TRIANGLES } = {}) {
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
    try {
      const bvh = new MeshBVH(geometry, BVH_OPTIONS);
      bvh.__builtFromIndexArray = proxy.faceIndices;
      proxy.__facePickBvh = bvh;
      geometry.boundsTree = bvh;
    } catch {
      proxy.__facePickBvhSkipped = true;
    }
  });
}
