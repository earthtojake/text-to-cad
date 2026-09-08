// Every typed-array field a meshData can carry, in one place: the worker
// transfer list and the render-cost estimate both walk it.
export const MESH_DATA_ARRAY_FIELDS = Object.freeze([
  "vertices",
  "indices",
  "normals",
  "colors",
  "edge_indices",
  "cadEdgeSegments",
  "guide_line_segments"
]);

export function meshDataTransferList(meshData) {
  const buffers = MESH_DATA_ARRAY_FIELDS
    .map((field) => meshData?.[field]?.buffer)
    .filter((buffer) => buffer instanceof ArrayBuffer && buffer.byteLength > 0);
  return [...new Set(buffers)];
}
