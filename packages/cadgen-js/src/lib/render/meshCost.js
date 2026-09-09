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
  return {
    triangleCount: Math.max(indicesTriangleCount, partTriangleCount),
    typedArrayBytes: [
      meshData?.vertices,
      meshData?.indices,
      meshData?.normals,
      meshData?.colors,
      meshData?.edge_indices,
      meshData?.surfaceEdgeBarycentric,
      meshData?.surfaceEdgeClass,
      meshData?.guide_line_segments
    ].reduce((sum, value) => sum + typedArrayBytes(value), 0)
  };
}

export function isLargeMeshData(meshData) {
  const cost = estimateMeshRenderCost(meshData);
  return cost.triangleCount >= LARGE_MESH_TRIANGLE_COUNT ||
    cost.typedArrayBytes >= LARGE_MESH_TYPED_ARRAY_BYTES;
}
