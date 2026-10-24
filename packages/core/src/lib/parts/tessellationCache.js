// The edge table's vocabulary: the class codes a CAD edge is drawn by and the width of a
// table's rows, as cadgen's part store wrote them. The store, its GLB body and the codec that
// read one are gone with the old pipeline and the docs hero's package; a tube skin's edge table
// (`common/tubeSkin.js`) and the edge lines it draws (`partMeshData.js`) still speak it.

// The edge table's class codes, in the order cadgen wrote them.
export const MESH_EDGE_CLASSES = Object.freeze([
  "none", "feature", "tangent", "seam", "degenerate", "boundary", "nonManifold", "unknown",
]);
// Both tables are rows of four u32: (ord, start, count, reference).
export const MESH_TABLE_COLUMNS = 4;
