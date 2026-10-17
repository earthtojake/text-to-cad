// TEST-ONLY: synthetic stored-mesh bodies (GLB), for tests in any package that
// need a stored mesh no producer made (a single triangle, an empty or wire-only
// component, hundreds of distinct components). cadgen is the only producer of
// real meshes (cadgen/store/meshes.py encode_payload); nothing in the product
// imports this module. Browser-safe, so browser tests can use it too.

import {
  MESH_EDGE_CLASSES,
  canonicalMeshGltf,
  decodeComponentTessellation,
  meshEdgePolylines,
  meshFaceRanges,
  tessellationDecodedBytes,
} from "./tessellationCache.js";

const UNSIGNED_SHORT_VERTEX_LIMIT = 65535;

/** A part key for a test (`<64 hex>-v1`), from a hex `seed` repeated to 64 digits. */
export function testPartKey(seed = "a") {
  const hex = String(seed).replace(/[^0-9a-f]/g, "") || "a";
  return `${hex.repeat(Math.ceil(64 / hex.length)).slice(0, 64)}-v1`;
}

/**
 * A synthetic stored-mesh body for `component`, laid out as cadgen writes one: either
 * `{positions, normals, indices, faceRanges: [{ord, color?, indexStart, indexCount}],
 * edges: [{ord, visibilityClass?, polyline}], bounds, unmeshedFaces?}` or a decoded component
 * (`decodeComponentTessellation(...).component`), whose tables it reads back. It names `part`.
 */
export function encodeMeshFixture(component, { part }) {
  const faceRanges = component.faceTable ? meshFaceRanges(component) : component.faceRanges || [];
  const edges = component.edgeTable ? meshEdgePolylines(component) : component.edges || [];
  const palette = new Map();
  const faces = new Uint32Array(faceRanges.length * 4);
  faceRanges.forEach((range, row) => {
    let color = 0;
    if (range.color != null) {
      const spelling = JSON.stringify(range.color);
      if (!palette.has(spelling)) palette.set(spelling, { row: palette.size + 1, color: [...range.color] });
      color = palette.get(spelling).row;
    }
    faces.set([range.ord, range.indexStart, range.indexCount, color], row * 4);
  });
  const edgeTable = new Uint32Array(edges.length * 4);
  const edgePoints = new Float32Array(edges.reduce((sum, edge) => sum + edge.polyline.length, 0));
  let pointCursor = 0;
  edges.forEach((edge, row) => {
    edgePoints.set(edge.polyline, pointCursor * 3);
    const pointCount = edge.polyline.length / 3;
    edgeTable.set([edge.ord, pointCursor, pointCount, MESH_EDGE_CLASSES.indexOf(edge.visibilityClass ?? "none")], row * 4);
    pointCursor += pointCount;
  });
  const vertexCount = component.positions.length / 3;
  const cad = {
    part,
    bounds: { min: [...component.bounds.min], max: [...component.bounds.max] },
    faceColors: [...palette.values()].map((entry) => entry.color),
  };
  if (component.unmeshedFaces?.length) cad.unmeshedFaces = [...component.unmeshedFaces];
  const counts = {
    vertexCount,
    indexCount: component.indices.length,
    faceCount: faceRanges.length,
    edgeCount: edges.length,
    edgePointCount: pointCursor,
  };
  const gltf = canonicalMeshGltf(cad, counts);
  const IndexArray = vertexCount <= UNSIGNED_SHORT_VERTEX_LIMIT ? Uint16Array : Uint32Array;
  const sections = {
    POSITION: new Float32Array(component.positions),
    NORMAL: new Float32Array(component.normals),
    indices: IndexArray.from(component.indices),
    "cadgen.faces": faces,
    "cadgen.edges": edgeTable,
    "cadgen.edgePoints": edgePoints,
  };
  const views = gltf.bufferViews || [];
  const binLength = gltf.buffers?.[0].byteLength ?? 0;
  const json = new TextEncoder().encode(JSON.stringify(gltf));
  const jsonLength = (json.length + 3) & ~3;
  const total = 20 + jsonLength + (binLength ? 8 + binLength : 0);
  const bytes = new Uint8Array(total);
  const view = new DataView(bytes.buffer);
  view.setUint32(0, 0x46546c67, true);
  view.setUint32(4, 2, true);
  view.setUint32(8, total, true);
  view.setUint32(12, jsonLength, true);
  view.setUint32(16, 0x4e4f534a, true);
  bytes.set(json, 20);
  bytes.fill(0x20, 20 + json.length, 20 + jsonLength);
  if (binLength) {
    const binStart = 20 + jsonLength + 8;
    view.setUint32(binStart - 8, binLength, true);
    view.setUint32(binStart - 4, 0x004e4942, true);
    views.forEach((entry, index) => {
      const name = entry.name ?? ["POSITION", "NORMAL", "indices"][index];
      const array = sections[name];
      bytes.set(new Uint8Array(array.buffer, array.byteOffset, array.byteLength), binStart + entry.byteOffset);
    });
  }
  return bytes;
}

/**
 * What a part's record says of its display mesh `bytes`, but the object's address (which a test
 * hashes): `{byteLength, decodedBytes, <counts>, unmeshedFaceCount?}`, as cadgen's
 * `meshes.body_facts` reads it.
 */
export function partMeshFacts(bytes) {
  const decoded = decodeComponentTessellation(bytes);
  if (!decoded) throw new TypeError("not a stored mesh body");
  const { component } = decoded;
  const counts = {
    vertexCount: component.positions.length / 3,
    indexCount: component.indices.length,
    faceCount: component.faceTable.length / 4,
    edgeCount: component.edgeTable.length / 4,
    edgePointCount: component.edgePoints.length / 3,
  };
  return {
    byteLength: bytes.byteLength, decodedBytes: tessellationDecodedBytes(counts), ...counts,
    ...(component.unmeshedFaces.length ? { unmeshedFaceCount: component.unmeshedFaces.length } : {}),
  };
}

/** What a part's record says of its selector table `bytes`, but the object's address. */
export function partSelectorFacts(bytes) {
  const { stats } = JSON.parse(new TextDecoder().decode(bytes));
  return { byteLength: bytes.byteLength, faceCount: stats.faceCount, edgeCount: stats.edgeCount,
    vertexCount: stats.vertexCount };
}
