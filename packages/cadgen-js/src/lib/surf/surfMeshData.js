// meshData from a .surf container (design/surface-rendering.md R2/R5).
//
// Produces the structure buildMeshDataFromGlbBuffer produced from a component
// GLB, so everything downstream — package composition, themes, selection
// ranges — is untouched by the artifact swap. Geometry is tessellated
// client-side from exact surfaces (grid + clip, curvature-driven), in CAD
// units, and handed on INDEXED: the tessellator's shared vertices, normals and
// index buffer are the render buffers, never expanded per corner. CAD edges
// ride beside the triangles as per-class line segments built from the same
// tessellation's boundary polylines (design/viewer-memory.md lever B).

import { linearRgbToHex } from "../color.js";
import { parseSurf } from "./container.js";
import { tessellateComponent } from "./tessellate.js";

// The line pass groups CAD edges by class so display.edges.classes styles each
// one; every other edge class the extractor knows (boundary, nonManifold,
// unknown) draws as a feature edge, `none` is not drawn at all.
export const CAD_EDGE_LINE_CLASSES = Object.freeze(["feature", "tangent", "seam", "degenerate"]);

function lineClassForEdge(edge) {
  const visibilityClass = String(edge?.visibilityClass || "").trim();
  if (visibilityClass === "none") {
    return "";
  }
  return CAD_EDGE_LINE_CLASSES.includes(visibilityClass) ? visibilityClass : "feature";
}

// A typed array is shared when it owns its buffer (a fresh tessellation) and
// copied when it is a view (a decoded .tess cache entry is one buffer holding
// positions, normals, face ords, indices, side ords and every polyline; sharing
// a view would keep the whole entry resident once the meshData outlives it).
function ownedArray(array, Ctor) {
  if (array instanceof Ctor && array.byteOffset === 0 && array.byteLength === array.buffer.byteLength) {
    return array;
  }
  return Ctor.from(array || []);
}

// Segment endpoints (six floats per segment) for the line pass, grouped by
// class in CAD_EDGE_LINE_CLASSES order, plus the [segmentStart, segmentCount)
// range of each non-empty class.
export function buildCadEdgeSegments(edges) {
  const byClass = new Map(CAD_EDGE_LINE_CLASSES.map((classId) => [classId, []]));
  let segmentTotal = 0;
  for (const edge of Array.isArray(edges) ? edges : []) {
    const classId = lineClassForEdge(edge);
    const polyline = edge?.polyline;
    if (!classId || !(polyline instanceof Float32Array) || polyline.length < 6) {
      continue;
    }
    byClass.get(classId).push(polyline);
    segmentTotal += polyline.length / 3 - 1;
  }
  const segments = new Float32Array(segmentTotal * 6);
  const classRanges = [];
  let segmentCursor = 0;
  for (const classId of CAD_EDGE_LINE_CLASSES) {
    const segmentStart = segmentCursor;
    for (const polyline of byClass.get(classId)) {
      const pointCount = polyline.length / 3;
      for (let point = 0; point + 1 < pointCount; point += 1) {
        segments.set(polyline.subarray(point * 3, point * 3 + 6), segmentCursor * 6);
        segmentCursor += 1;
      }
    }
    if (segmentCursor > segmentStart) {
      classRanges.push({ classId, segmentStart, segmentCount: segmentCursor - segmentStart });
    }
  }
  return { segments, classRanges };
}

export function buildMeshDataFromSurf(index, floats, options = {}) {
  const component = options.component || tessellateComponent(index, floats, options);
  const vertices = ownedArray(component.positions, Float32Array);
  const normals = ownedArray(component.normals, Float32Array);
  const indices = ownedArray(component.indices, Uint32Array);
  const vertexCount = vertices.length / 3;
  const triangleCount = indices.length / 3;
  const cadEdges = buildCadEdgeSegments(component.edges);

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
    cadEdgeSegments: cadEdges.segments,
    cadEdgeClassRanges: cadEdges.classRanges,
    bounds,
    parts: [part],
    has_source_colors: Boolean(color),
    sourceColor: color || "",
  };
}

export function buildMeshDataFromSurfBuffer(buffer, options = {}) {
  const { index, floats } = parseSurf(buffer);
  return buildMeshDataFromSurf(index, floats, options);
}
