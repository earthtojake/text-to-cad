// meshData from a component's stored mesh (cadgen/store/meshes.py).
//
// Produces the structure buildMeshDataFromGlbBuffer produced from a component
// GLB, so everything downstream — package composition, themes, selection
// ranges — is untouched by the artifact swap. Geometry is cadgen's OCCT mesh
// of the exact surfaces, in CAD units, handed on INDEXED: the mesh's shared
// vertices, normals and index buffer are the render buffers, never expanded
// per corner. CAD edges ride beside the triangles as indexed line segments
// built from the same mesh's edge table and points.

import { linearRgbToHex } from "../color.js";
import { MESH_EDGE_CLASSES, MESH_TABLE_COLUMNS } from "./tessellationCache.js";

// The line pass groups CAD edges by class so display.edges.classes styles each
// one; every other edge class the extractor knows (boundary, nonManifold,
// unknown) draws as a feature edge, `none` is not drawn at all.
export const CAD_EDGE_LINE_CLASSES = Object.freeze(["feature", "tangent", "seam", "degenerate"]);

// Each edge class code's line class (its CAD_EDGE_LINE_CLASSES index), -1 for an edge not drawn.
const LINE_CLASS_OF_CODE = Object.freeze(MESH_EDGE_CLASSES.map((name) => (
  name === "none" ? -1 : Math.max(0, CAD_EDGE_LINE_CLASSES.indexOf(name))
)));

// The render buffers own their memory: a decoded stored mesh is one buffer
// holding positions, normals, indices, tables and every polyline, and sharing a
// view would keep the whole entry resident once the meshData outlives it.
function ownedArray(array, Ctor) {
  if (array instanceof Ctor && array.byteOffset === 0 && array.byteLength === array.buffer.byteLength) {
    return array;
  }
  return new Ctor(array || []);
}

// Indexed line segments for the GL_LINES edge pass: every polyline point once
// (`positions`, xyz), one Uint32 pair per segment (`indices`), both grouped by
// class in CAD_EDGE_LINE_CLASSES order so a class is a contiguous point range
// and a contiguous segment range (`classRanges`). Per segment this is 8 bytes
// plus ~14 bytes of shared points — about 1.5 bytes per surface triangle.
// `table` is a stored mesh's edge table (MESH_TABLE_COLUMNS u32 per edge: ord,
// pointStart, pointCount, class code) over `points` (f32 xyz).
export function buildCadEdgeLines(table, points) {
  const lineClasses = CAD_EDGE_LINE_CLASSES.length;
  const classPoints = new Array(lineClasses).fill(0);
  const classSegments = new Array(lineClasses).fill(0);
  const rows = table instanceof Uint32Array ? table : new Uint32Array(0);
  for (let row = 0; row < rows.length; row += MESH_TABLE_COLUMNS) {
    const lineClass = LINE_CLASS_OF_CODE[rows[row + 3]] ?? -1;
    const pointCount = rows[row + 2];
    if (lineClass < 0 || pointCount < 2) continue;
    classPoints[lineClass] += pointCount;
    classSegments[lineClass] += pointCount - 1;
  }
  const pointStarts = [];
  const segmentStarts = [];
  let pointTotal = 0;
  let segmentTotal = 0;
  for (let lineClass = 0; lineClass < lineClasses; lineClass += 1) {
    pointStarts.push(pointTotal);
    segmentStarts.push(segmentTotal);
    pointTotal += classPoints[lineClass];
    segmentTotal += classSegments[lineClass];
  }
  const positions = new Float32Array(pointTotal * 3);
  const indices = new Uint32Array(segmentTotal * 2);
  const pointCursor = [...pointStarts];
  const segmentCursor = [...segmentStarts];
  for (let row = 0; row < rows.length; row += MESH_TABLE_COLUMNS) {
    const lineClass = LINE_CLASS_OF_CODE[rows[row + 3]] ?? -1;
    const pointCount = rows[row + 2];
    if (lineClass < 0 || pointCount < 2) continue;
    const first = pointCursor[lineClass];
    const start = rows[row + 1] * 3;
    positions.set(points.subarray(start, start + pointCount * 3), first * 3);
    let segment = segmentCursor[lineClass] * 2;
    for (let point = 0; point + 1 < pointCount; point += 1) {
      indices[segment] = first + point;
      indices[segment + 1] = first + point + 1;
      segment += 2;
    }
    pointCursor[lineClass] += pointCount;
    segmentCursor[lineClass] += pointCount - 1;
  }
  const classRanges = [];
  for (let lineClass = 0; lineClass < lineClasses; lineClass += 1) {
    if (classSegments[lineClass] > 0) {
      classRanges.push({
        classId: CAD_EDGE_LINE_CLASSES[lineClass],
        pointStart: pointStarts[lineClass],
        pointCount: classPoints[lineClass],
        segmentStart: segmentStarts[lineClass],
        segmentCount: classSegments[lineClass],
      });
    }
  }
  return { positions, indices, classRanges };
}

// `index` is the component's SURF index, or the stand-in a mesh entry carries
// (surfIndexFromCacheEntry): only its part colour is read here.
export function buildMeshDataFromSurf(index, component) {
  if (!component?.positions) throw new TypeError("Display data needs the component's mesh");
  const vertices = ownedArray(component.positions, Float32Array);
  const normals = ownedArray(component.normals, Float32Array);
  // The render pipeline and the selector runtime take u32 indices; a stored mesh of
  // at most 65,535 vertices keeps u16 ones, widened here as they are copied.
  const indices = ownedArray(component.indices, Uint32Array);
  const vertexCount = vertices.length / 3;
  const triangleCount = indices.length / 3;
  const cadEdges = buildCadEdgeLines(component.edgeTable, component.edgePoints);

  const bounds = {
    min: [...component.bounds.min],
    max: [...component.bounds.max],
  };

  // The surf's partColor is LINEAR RGBA (a build123d/OCCT Color), while
  // `part.color` is the sRGB hex the viewer decodes with new THREE.Color.
  const partColor = Array.isArray(index.partColor) ? index.partColor : null;
  const color = partColor ? linearRgbToHex(partColor) : null;
  const part = {
    id: "surf:0",
    occurrenceId: "",
    primitiveIndex: 0,
    name: "",
    label: "",
    nodeType: "part",
    color,
    opacity: partColor && Number.isFinite(partColor[3]) ? partColor[3] : 1,
    hasSourceColors: Boolean(color),
    bounds,
    vertexOffset: 0,
    vertexCount,
    triangleOffset: 0,
    triangleCount,
    edgeIndexOffset: 0,
    edgeIndexCount: 0,
  };

  return {
    vertices,
    indices,
    normals,
    colors: new Float32Array(0),
    edge_indices: new Uint32Array(0),
    cadEdgePositions: cadEdges.positions,
    cadEdgeIndices: cadEdges.indices,
    cadEdgeClassRanges: cadEdges.classRanges,
    bounds,
    parts: [part],
    has_source_colors: Boolean(color),
    sourceColor: color || "",
    // The faces no mesher could cover, which this mesh does not draw: the viewer names the
    // parts drawn without them.
    unmeshedFaces: [...(component.unmeshedFaces || [])],
  };
}
