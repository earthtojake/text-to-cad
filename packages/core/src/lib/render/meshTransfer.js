export function meshDataTransferList(meshData) {
  const buffers = [
    meshData?.vertices?.buffer,
    meshData?.indices?.buffer,
    meshData?.normals?.buffer,
    meshData?.colors?.buffer,
    meshData?.edge_indices?.buffer,
    meshData?.surfaceEdgeBarycentric?.buffer,
    meshData?.surfaceEdgeClass?.buffer,
    meshData?.guide_line_segments?.buffer
  ].filter((buffer) => buffer instanceof ArrayBuffer && buffer.byteLength > 0);
  return [...new Set(buffers)];
}
