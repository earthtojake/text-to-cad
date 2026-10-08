// TEST-ONLY: synthetic stored-mesh bodies (GLB), for tests in any package that
// need a stored mesh no producer made (a single triangle, an empty or wire-only
// component, hundreds of distinct components). cadgen is the only producer of
// real meshes (cadgen/store/meshes.py encode_payload); nothing in the product
// imports this module. Browser-safe, so browser tests can use it too.

import { TESSELLATION_LADDER } from "./fixtures/tessellationLadder.js";
import { installTessellationLadder } from "./lodPolicy.js";
import {
  MESH_EDGE_CLASSES,
  MESH_PAYLOAD_VERSION,
  TESSELLATION_VERSION,
  canonicalMeshGltf,
  meshEdgePolylines,
  meshFaceRanges,
  tessellationCacheKey,
  tessellationQuality,
} from "./tessellationCache.js";

const UNSIGNED_SHORT_VERTEX_LIMIT = 65535;

/** The display ladder a cadgen server publishes, as cadgen wrote it for the tests. */
export const TEST_TESSELLATION_LADDER = TESSELLATION_LADDER;

/** Install that ladder, as a host installs the one its server publishes. */
export function installTestTessellationLadder() {
  return installTessellationLadder(TESSELLATION_LADDER);
}

/**
 * A synthetic stored-mesh body for `component`, laid out as cadgen writes one: either
 * `{positions, normals, indices, faceRanges: [{ord, color?, indexStart, indexCount}],
 * edges: [{ord, visibilityClass?, polyline}], bounds, scale}` or a decoded component
 * (`decodeComponentTessellation(...).component`), whose tables it reads back. Its tolerances
 * are `tessellation`'s, else the test ladder's standard rung.
 */
export function encodeMeshFixture(component, {
  surfaceInput,
  surfaceObject,
  tessellation = TESSELLATION_LADDER.levels[TESSELLATION_LADDER.defaultLevel],
  partColor = null,
} = {}) {
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
    payloadVersion: MESH_PAYLOAD_VERSION,
    tessellatorVersion: TESSELLATION_VERSION,
    tessellationInput: tessellationCacheKey(surfaceInput, tessellation),
    surfaceInput,
    surfaceObject,
    quality: tessellationQuality(tessellation),
    bounds: { min: [...component.bounds.min], max: [...component.bounds.max] },
    scale: component.scale,
    partColor: partColor ?? null,
    faceColors: [...palette.values()].map((entry) => entry.color),
  };
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
