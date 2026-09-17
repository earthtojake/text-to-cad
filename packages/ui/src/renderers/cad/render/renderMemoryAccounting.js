// Byte attribution of what the viewer retains for the displayed model, read by
// the headless memory harness through window.__cadRenderMemoryProbe(). Every
// GPU-side array is counted once (occurrences share component geometry), split
// into surface geometry, CAD edge lines and raycast BVHs, beside the render
// asset caches' own accounting. It also refreshes the shared admission ledger.
import { renderAssetCacheStats } from "@hardcore/core/lib/renderAssetClient.js";
import { cadEdgeInstanceSets } from "@hardcore/core/common/cadEdgeInstances.js";
import { builtGeometryBvhBytes } from "@hardcore/core/lib/viewer/raycastBvh.js";
import { MESH_DATA_ARRAY_FIELDS } from "@hardcore/core/lib/render/meshTransfer.js";
import { lodStagingBuffers, syncSelectorCacheAccounting } from "./lodStagingMemory.js";
import { viewerMemoryPolicy } from "./viewerMemoryPolicy.js";

function retainBackingBytes(value, seen) {
  const buffer = ArrayBuffer.isView(value) ? value.buffer : value instanceof ArrayBuffer ? value : null;
  if (!buffer || seen.has(buffer)) return 0;
  seen.add(buffer);
  return buffer.byteLength;
}

function retainMeshBackingBytes(mesh, seen) {
  return MESH_DATA_ARRAY_FIELDS.reduce((sum, field) => sum + retainBackingBytes(mesh?.[field], seen), 0);
}

// Before scene adoption, the asset hook owns the component arrays. A short
// typed view keeps its whole allocation alive, including packed sections that
// are not uploaded. Keep that CPU cost separate from estimated GPU input.
export function componentMemoryAccounting(componentMeshDataByCid) {
  const buffers = new Set();
  const meshes = new Set(Object.values(componentMeshDataByCid || {}));
  for (const mesh of meshes) {
    for (const part of Array.isArray(mesh?.parts) ? mesh.parts : []) {
      if (part?.sourceMesh) meshes.add(part.sourceMesh);
    }
  }
  const arrays = new Set();
  for (const mesh of meshes) {
    for (const field of MESH_DATA_ARRAY_FIELDS) {
      if (ArrayBuffer.isView(mesh?.[field])) arrays.add(mesh[field]);
    }
  }
  let gpuInputBytes = 0;
  for (const array of arrays) gpuInputBytes += array.byteLength;
  let displayCpuBytes = 0;
  for (const mesh of meshes) displayCpuBytes += retainMeshBackingBytes(mesh, buffers);
  return { displayCpuBytes, gpuInputBytes, buffers };
}

function geometryBuffers(geometry) {
  const buffers = new Set();
  if (geometry?.index) {
    buffers.add(geometry.index);
  }
  for (const attribute of Object.values(geometry?.attributes || {})) {
    buffers.add(attribute.isInterleavedBufferAttribute ? attribute.data : attribute);
  }
  return buffers;
}

export function renderMemoryAccounting(runtime) {
  const records = Array.isArray(runtime?.displayRecords) ? runtime.displayRecords : [];
  const seenGeometries = new Set();
  const seenBuffers = new Set();
  const seenArrayBuffers = new Set();
  const seenMaterials = new Set();
  let displayCpuBytes = retainMeshBackingBytes(runtime?.cadScene?.meshData, seenArrayBuffers);
  let selectorCpuBytes = 0;
  const seenSourceMeshes = new Set();
  const totals = {
    occurrences: 0,
    edgeObjects: 0,
    edgeInstanceSets: 0,
    edgeInstances: 0,
    surfaceInstanceSets: 0,
    surfaceInstances: 0,
    surfaceInstanceBytes: 0,
    geometries: 0,
    buffers: 0,
    materials: 0,
    surfaceBytes: 0,
    edgeBytes: 0,
    bvhBytes: 0,
    bvhGeometries: 0,
    // Picking, which the byte accounting used to miss entirely: the triangle ->
    // face-row map is allocated PER OCCURRENCE (one Uint32 per occurrence
    // triangle), and the merged face/edge/vertex pick proxies carry their own
    // geometry and BVH. On an assembly with thousands of occurrences these are
    // the same order as the geometry itself, so a memory decision taken without
    // them is taken half-blind.
    faceIdBytes: 0,
    faceIdArrays: 0,
    pickBytes: 0,
    pickGeometries: 0,
    deformationBytes: 0
  };
  const visit = (object, kind) => {
    const geometry = object?.geometry;
    if (!geometry) {
      return;
    }
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      if (material) {
        seenMaterials.add(material);
      }
    }
    if (seenGeometries.has(geometry)) {
      return;
    }
    seenGeometries.add(geometry);
    for (const buffer of geometryBuffers(geometry)) {
      if (seenBuffers.has(buffer)) {
        continue;
      }
      seenBuffers.add(buffer);
      displayCpuBytes += retainBackingBytes(buffer.array, seenArrayBuffers);
      totals[kind === "edge" ? "edgeBytes" : "surfaceBytes"] += buffer.array?.byteLength || 0;
    }
    const bvh = builtGeometryBvhBytes(geometry, seenArrayBuffers);
    if (bvh) {
      totals.bvhBytes += bvh;
      totals.bvhGeometries += 1;
    }
  };
  const seenFaceIds = new Set();
  const countFaceIds = (object) => {
    const faceIds = object?.userData?.faceIds;
    if (!ArrayBuffer.isView(faceIds) || seenFaceIds.has(faceIds)) {
      return;
    }
    seenFaceIds.add(faceIds);
    totals.faceIdBytes += faceIds.byteLength;
    selectorCpuBytes += retainBackingBytes(faceIds, seenArrayBuffers);
    totals.faceIdArrays += 1;
  };
  for (const record of records) {
    // Source meshes also retain arrays that are not GPU attributes, such as
    // the input CAD edge lines from which segment textures were built.
    const sourceMesh = record?.sourcePart?.sourceMesh;
    if (sourceMesh && !seenSourceMeshes.has(sourceMesh)) {
      seenSourceMeshes.add(sourceMesh);
      displayCpuBytes += retainMeshBackingBytes(sourceMesh, seenArrayBuffers);
    }
    displayCpuBytes += retainBackingBytes(record?.rawColors, seenArrayBuffers);
    if (record?.mesh) {
      totals.occurrences += 1;
      visit(record.mesh, "surface");
      countFaceIds(record.mesh);
    }
    if (record?.edges) {
      totals.edgeObjects += 1;
      record.edges.traverse ? record.edges.traverse((child) => visit(child, "edge")) : visit(record.edges, "edge");
    }
    if (record?.edgeInstance) {
      totals.edgeInstances += 1;
    }
  }
  if (runtime?.sceneCleanupFailed) {
    for (const [group, kind] of [[runtime.modelGroup, "surface"], [runtime.edgesGroup, "edge"], [runtime.stageGroup, "surface"]]) {
      group?.traverse?.(object => { visit(object, kind); countFaceIds(object); });
    }
    for (const part of (runtime.cadScene?.meshData || runtime.retiringCadSource)?.parts || []) {
      if (part.sourceMesh && !seenSourceMeshes.has(part.sourceMesh)) {
        seenSourceMeshes.add(part.sourceMesh);
        displayCpuBytes += retainMeshBackingBytes(part.sourceMesh, seenArrayBuffers);
      }
    }
  }
  // Instanced CAD edges: one draw per component; its segment texture (shared
  // by every occurrence, cached on the component), instance texture and quad.
  const seenSegmentTextures = new Set();
  for (const set of cadEdgeInstanceSets(runtime)) {
    totals.edgeInstanceSets += 1;
    visit(set.object, "edge");
    for (const material of set.materials) {
      seenMaterials.add(material);
    }
    totals.edgeBytes += set.instanceByteLength;
    displayCpuBytes += retainBackingBytes(set.instanceData, seenArrayBuffers);
    if (!seenSegmentTextures.has(set.segments)) {
      seenSegmentTextures.add(set.segments);
      totals.edgeBytes += set.segments.byteLength;
      displayCpuBytes += retainBackingBytes(set.segments.texture?.image?.data, seenArrayBuffers);
    }
  }
  // Instanced CAD surfaces share their component geometry with the proxy
  // records above, but own matrix/color attributes and a cloned draw material.
  // Those allocations must participate in admission even though they do not
  // appear in a record's private Mesh.
  const surfaceInstanceSets = runtime?.cadSurfaceInstanceSets
    || runtime?.cadScene?.runtime?.cadSurfaceInstanceSets
    || [];
  for (const set of surfaceInstanceSets) {
    const object = set?.object;
    if (!object) continue;
    totals.surfaceInstanceSets += 1;
    totals.surfaceInstances += Number(object.count) || set.records?.length || 0;
    visit(object, "surface");
    for (const buffer of [object.instanceMatrix, object.instanceColor]) {
      if (!buffer || seenBuffers.has(buffer)) continue;
      seenBuffers.add(buffer);
      displayCpuBytes += retainBackingBytes(buffer.array, seenArrayBuffers);
      const byteLength = buffer.array?.byteLength || 0;
      totals.surfaceInstanceBytes += byteLength;
      totals.surfaceBytes += byteLength;
    }
  }
  // The merged pick proxies: their own geometry, their own BVH, their own
  // face-id map, all outside the display records.
  const pickRoots = [
    runtime?.facePickMesh,
    runtime?.facePickGroup,
    runtime?.edgePickGroup,
    runtime?.vertexPickGroup
  ];
  for (const root of pickRoots) {
    if (!root) {
      continue;
    }
    const visitPick = (object) => {
      countFaceIds(object);
      const geometry = object?.geometry;
      if (!geometry || seenGeometries.has(geometry)) {
        return;
      }
      seenGeometries.add(geometry);
      totals.pickGeometries += 1;
      for (const buffer of geometryBuffers(geometry)) {
        if (!seenBuffers.has(buffer)) {
          seenBuffers.add(buffer);
          selectorCpuBytes += retainBackingBytes(buffer.array, seenArrayBuffers);
          totals.pickBytes += buffer.array?.byteLength || 0;
        }
      }
      const bvh = builtGeometryBvhBytes(geometry, seenArrayBuffers);
      if (bvh) {
        totals.bvhBytes += bvh;
        totals.bvhGeometries += 1;
      }
    };
    if (typeof root.traverse === "function") {
      root.traverse(visitPick);
    } else {
      visitPick(root);
    }
  }
  // Tube deformation retains a refined rest mesh/mapping beside the posed
  // display geometry. Count typed arrays reachable from its private state that
  // were not already attributed to a visible geometry.
  const seenDeformationObjects = new Set();
  const visitDeformation = (value) => {
    if (!value || typeof value !== "object" || seenDeformationObjects.has(value)) return;
    seenDeformationObjects.add(value);
    if (ArrayBuffer.isView(value)) {
      if (!seenArrayBuffers.has(value.buffer)) {
        seenArrayBuffers.add(value.buffer);
        // A subview keeps the entire allocation alive. This matches the cache
        // accounting and prevents packed deformation state from looking free.
        totals.deformationBytes += value.buffer.byteLength;
      }
      return;
    }
    if (value instanceof ArrayBuffer) {
      if (!seenArrayBuffers.has(value)) {
        seenArrayBuffers.add(value);
        totals.deformationBytes += value.byteLength;
      }
      return;
    }
    for (const child of Object.values(value)) visitDeformation(child);
  };
  for (const record of records) visitDeformation(record?.tubeDeformationState);
  totals.geometries = seenGeometries.size;
  totals.buffers = seenBuffers.size;
  totals.materials = seenMaterials.size;
  const gpuEstimatedBytes = totals.surfaceBytes + totals.edgeBytes + totals.pickBytes;
  const assetCaches = renderAssetCacheStats();
  // The full backing of each excluded view has already been charged above.
  // GPU mirrors contain the uploaded views; CPU references retain the entire
  // allocation, even when some packed sections never reach a GPU attribute.
  const additionalAssetCaches = renderAssetCacheStats({ excludeBuffers: lodStagingBuffers(seenArrayBuffers) });
  viewerMemoryPolicy.setRetained("displayCpu", displayCpuBytes);
  viewerMemoryPolicy.setRetained("gpuEstimated", gpuEstimatedBytes);
  viewerMemoryPolicy.setRetained("bvh", totals.bvhBytes);
  viewerMemoryPolicy.setRetained("deformation", totals.deformationBytes);
  syncSelectorCacheAccounting(viewerMemoryPolicy, Number(additionalAssetCaches.selector?.typedBytes) || 0, selectorCpuBytes);
  viewerMemoryPolicy.setRetained("assetCaches", Object.entries(additionalAssetCaches).reduce(
    (sum, [name, stats]) => name === "surfLeash" || name === "selector"
      ? sum
      : sum + (Number(stats?.typedBytes) || 0),
    0
  ));
  return {
    ...totals,
    displayCpuBytes,
    selectorCpuBytes,
    gpuEstimatedBytes,
    assetCaches,
    additionalAssetCaches,
    memoryPolicy: viewerMemoryPolicy.snapshot(),
    at: typeof performance !== "undefined" ? performance.now() : Date.now()
  };
}
