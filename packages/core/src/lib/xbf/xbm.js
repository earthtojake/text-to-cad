// One part's tessellation as cadgen's engine serves it (`GET /api/doc/<id>/part/<key>`): the
// XBM2 wire format (`cadgen/engine/mesh.py`, `Mesh.to_bytes`). It is read the way the engine
// writes it for: typed-array views over the fetched bytes, no parse and no copy. A face is a
// range of the index buffer, an edge a range of the polyline buffer, a vertex a row of the
// vertex table; every element is named by its ordinal, the part's `TopExp.MapShapes` ordinal,
// which the document's element names use too.
//
// The 80-byte little-endian header: magic "XBM2", format version 2, six u32 counts (nodes,
// indices, faces, edges, edge points, vertices), seven u32 byte offsets (positions, normals,
// indices, face table, edge table, edge points, vertex table), linear and angular deflection
// (f32), 12 reserved bytes. Every array is 4-byte aligned.

export const XBM_MAGIC = 0x324d4258; // "XBM2", read as a little-endian u32
export const XBM_VERSION = 2;
export const XBM_HEADER_BYTES = 80;

/** Edge classes as the engine reads them from the B-rep (`mesh.py`). */
export const XBF_EDGE_CLASS = Object.freeze({ FEATURE: 1, TANGENT: 2, SEAM: 3, BOUNDARY: 5, NONMANIFOLD: 6 });
export const XBF_EDGE_CLASS_NAMES = Object.freeze({ 1: "feature", 2: "tangent", 3: "seam", 5: "boundary", 6: "non-manifold" });

/**
 * The line a class is drawn in: boundary and non-manifold edges are drawn as feature edges
 * (they are where a surface ends or branches, as sharp as a crease); tangent and seam edges are
 * their own, fainter lines.
 * @param {number} kind  An edge table's class.
 * @returns {"feature" | "tangent" | "seam"}
 */
export function xbfEdgeLine(kind) {
  return kind === XBF_EDGE_CLASS.TANGENT ? "tangent" : kind === XBF_EDGE_CLASS.SEAM ? "seam" : "feature";
}

/**
 * @typedef {object} XbmPart
 * @property {Float32Array} positions  `nodes * 3`.
 * @property {Float32Array} normals  `nodes * 3`: the surface's normals at each node.
 * @property {Uint32Array} indices  Triangle corners.
 * @property {Uint32Array} faces  `faces * 3`: face ordinal, first index, index count (0: unmeshed).
 * @property {Uint32Array} edges  `edges * 4`: edge ordinal, first point, point count, class.
 * @property {Float32Array} edgePoints  `points * 3`: every edge's polyline, one after another.
 * @property {Float32Array} vertices  `vertices * 4`: vertex ordinal, x, y, z.
 * @property {number} linear  The linear deflection it was meshed at.
 * @property {number} angular  The angular deflection, in radians.
 * @property {number} byteLength  The buffer's size.
 */

/**
 * The part buffer's arrays, as views over `buffer` itself.
 * @param {ArrayBuffer} buffer
 * @returns {XbmPart}
 */
export function readXbmPart(buffer) {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < XBM_HEADER_BYTES) {
    throw new Error("not an XBM2 part buffer: it is shorter than its header");
  }
  const head = new DataView(buffer, 0, XBM_HEADER_BYTES);
  if (head.getUint32(0, true) !== XBM_MAGIC) throw new Error("not an XBM2 part buffer: its magic is not XBM2");
  const version = head.getUint32(4, true);
  if (version !== XBM_VERSION) throw new Error(`XBM2 part buffer of format version ${version}; this reader reads ${XBM_VERSION}`);
  const [nodes, indices, faces, edges, points, vertices] = [8, 12, 16, 20, 24, 28].map(at => head.getUint32(at, true));
  const offsets = [32, 36, 40, 44, 48, 52, 56].map(at => head.getUint32(at, true));
  const view = (Kind, at, count) => {
    const offset = offsets[at];
    if (offset % 4 || offset + count * 4 > buffer.byteLength) throw new Error("XBM2 part buffer: an array lies outside the buffer");
    return new Kind(buffer, offset, count);
  };
  return {
    positions: view(Float32Array, 0, nodes * 3),
    normals: view(Float32Array, 1, nodes * 3),
    indices: view(Uint32Array, 2, indices),
    faces: view(Uint32Array, 3, faces * 3),
    edges: view(Uint32Array, 4, edges * 4),
    edgePoints: view(Float32Array, 5, points * 3),
    vertices: view(Float32Array, 6, vertices * 4),
    linear: head.getFloat32(60, true),
    angular: head.getFloat32(64, true),
    byteLength: buffer.byteLength
  };
}

/** How many triangles a part has. */
export function xbmTriangleCount(part) {
  return Math.floor(part.indices.length / 3);
}

/** The ordinals of the faces the mesher left without triangles (their count is 0). */
export function xbmUnmeshedFaces(part) {
  const found = [];
  for (let row = 0; row < part.faces.length; row += 3) if (part.faces[row + 2] === 0) found.push(part.faces[row]);
  return found;
}

/**
 * For each triangle, its face table row: what a hit triangle's face is. Made once per part
 * when something first picks it.
 * @returns {Int32Array}  -1 for a triangle no row claims (none, in a buffer the engine wrote).
 */
export function xbmTriangleFaceRows(part) {
  const rows = new Int32Array(xbmTriangleCount(part)).fill(-1);
  for (let row = 0; row < part.faces.length / 3; row += 1) {
    const first = part.faces[row * 3 + 1], count = part.faces[row * 3 + 2];
    rows.fill(row, first / 3, (first + count) / 3);
  }
  return rows;
}

/** The face table row of a face ordinal, or -1. */
export function xbmFaceRow(part, ordinal) {
  for (let row = 0; row < part.faces.length / 3; row += 1) if (part.faces[row * 3] === ordinal) return row;
  return -1;
}

/** The edge table row of an edge ordinal, or -1. */
export function xbmEdgeRow(part, ordinal) {
  for (let row = 0; row < part.edges.length / 4; row += 1) if (part.edges[row * 4] === ordinal) return row;
  return -1;
}

/** The vertex table row of a vertex ordinal, or -1. */
export function xbmVertexRow(part, ordinal) {
  for (let row = 0; row < part.vertices.length / 4; row += 1) if (part.vertices[row * 4] === ordinal) return row;
  return -1;
}
