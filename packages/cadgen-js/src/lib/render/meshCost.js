import {
  entryAssetBytes,
  entryMeshAssetBytes
} from "../entryAssets.js";
import {
  entrySourceFormat,
  RENDER_FORMAT
} from "../fileFormats.js";

export const LARGE_STEP_GLB_BYTES = 32 * 1024 * 1024;
export const LARGE_MESH_TRIANGLE_COUNT = 1_000_000;
export const LARGE_MESH_TYPED_ARRAY_BYTES = 160 * 1024 * 1024;

function typedArrayBytes(value) {
  return ArrayBuffer.isView(value) ? Number(value.byteLength) || 0 : 0;
}

export function hasMeshGeometry(meshData) {
  const hasTriangles = (mesh) => [mesh?.vertices, mesh?.indices].every(
    (value) => (Array.isArray(value) || ArrayBuffer.isView(value)) && value.length >= 3
  );
  return hasTriangles(meshData) || (Array.isArray(meshData?.parts) &&
    meshData.parts.some((part) => hasTriangles(part?.sourceMesh)));
}

export function entryStepGlbBytes(entry) {
  return entrySourceFormat(entry) === RENDER_FORMAT.STEP
    ? entryAssetBytes(entry, "glb")
    : 0;
}

export function hasStepGlbByteCost(entry) {
  return entryStepGlbBytes(entry) > 0;
}

export function isLargeStepGlbEntry(entry) {
  return entryStepGlbBytes(entry) >= LARGE_STEP_GLB_BYTES;
}

export function isLargeNativeGlbEntry(entry) {
  return entrySourceFormat(entry) === RENDER_FORMAT.GLB &&
    entryMeshAssetBytes(entry) >= LARGE_STEP_GLB_BYTES;
}

export function shouldUseGlbMeshWorkerForEntry(entry) {
  return isLargeStepGlbEntry(entry) || isLargeNativeGlbEntry(entry);
}

export function estimateMeshRenderCost(meshData) {
  const indicesTriangleCount = Math.floor((Number(meshData?.indices?.length) || 0) / 3);
  const partTriangleCount = Array.isArray(meshData?.parts)
    ? meshData.parts.reduce((sum, part) => {
        const triangleCount = Number(part?.triangleCount);
        return sum + (Number.isFinite(triangleCount) && triangleCount > 0 ? triangleCount : 0);
      }, 0)
    : 0;
  const meshes = new Set([meshData]);
  for (const part of Array.isArray(meshData?.parts) ? meshData.parts : []) {
    if (part?.sourceMesh) meshes.add(part.sourceMesh);
  }
  const arrays = new Set();
  for (const mesh of meshes) {
    for (const field of ["vertices", "indices", "normals", "colors", "edge_indices",
      "surfaceEdgeBarycentric", "surfaceEdgeClass", "guide_line_segments"]) {
      if (mesh?.[field]) arrays.add(mesh[field]);
    }
  }
  return {
    triangleCount: Math.max(indicesTriangleCount, partTriangleCount),
    typedArrayBytes: [...arrays].reduce((sum, value) => sum + typedArrayBytes(value), 0)
  };
}

export function isLargeMeshData(meshData) {
  const cost = estimateMeshRenderCost(meshData);
  return cost.triangleCount >= LARGE_MESH_TRIANGLE_COUNT ||
    cost.typedArrayBytes >= LARGE_MESH_TYPED_ARRAY_BYTES;
}
