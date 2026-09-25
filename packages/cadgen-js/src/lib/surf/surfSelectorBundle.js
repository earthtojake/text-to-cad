// Selector bundle from a .surf component (design/surface-rendering.md R3).
//
// Produces the exact {manifest, buffers} shape loadRenderSelectorBundle
// produced from a component GLB's STEP_TOPOLOGY extension, so
// buildSelectorRuntime and everything above it (reference panel, picking,
// measure, display edges) is untouched by the artifact swap. Rows carry
// the same columns in the same spelling; geometry-derived values (areas,
// centers, bboxes, edge polylines) come from the client tessellation of
// the exact surfaces, which is the same source the GLB tables were
// derived from server-side — just fresher.

import { tessellateComponent } from "./tessellate.js";

export const STEP_TOPOLOGY_SCHEMA_VERSION = 2;

const OCCURRENCE_ID = "o1";
const IDENTITY_TRANSFORM = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];

const OCCURRENCE_COLUMNS = [
  "id", "path", "name", "sourceName", "parentId", "transform", "bbox",
  "shapeStart", "shapeCount", "faceStart", "faceCount", "edgeStart", "edgeCount",
];
const SHAPE_COLUMNS = [
  "id", "occurrenceId", "ordinal", "kind", "name", "sourceName", "bbox",
  "center", "area", "volume", "faceStart", "faceCount", "edgeStart", "edgeCount",
];
const FACE_COLUMNS = [
  "id", "occurrenceId", "shapeId", "ordinal", "surfaceType", "area", "center",
  "normal", "bbox", "edgeStart", "edgeCount", "relevance", "flags", "params",
  "triangleStart", "triangleCount",
];
const EDGE_COLUMNS = [
  "id", "occurrenceId", "shapeId", "ordinal", "curveType", "length", "center",
  "bbox", "faceStart", "faceCount", "relevance", "flags", "params",
  "segmentStart", "segmentCount", "adjacentFaceCount", "continuity",
  "dihedralDeg", "visibilityClass", "surfaceHalfEdgeStart", "surfaceHalfEdgeCount",
];

// Mirror of cadgen's step_topology_capabilities / class codes.
const CLASS_CODES = {
  none: 0, feature: 1, tangent: 2, seam: 3, degenerate: 4, boundary: 5,
  nonManifold: 6, unknown: 7,
};
const RENDER_VISIBILITY_CLASSES = ["feature", "tangent", "seam", "degenerate"];

function capabilities() {
  return {
    edgeClassification: {
      algorithm: "oc-brep-continuity-v1",
      angularToleranceDeg: 2,
      samples: 3,
    },
    surfaceEdgeRendering: {
      algorithm: "surf-grid-clip-v1",
      primitiveAttributes: {
        barycentric: "_CAD_EDGE_BARYCENTRIC",
        class: "_CAD_EDGE_CLASS",
      },
      classCodes: { ...CLASS_CODES },
      visibilityClasses: [...RENDER_VISIBILITY_CLASSES],
    },
  };
}

function emptyBounds() {
  return {
    min: [Infinity, Infinity, Infinity],
    max: [-Infinity, -Infinity, -Infinity],
  };
}

function growBounds(bounds, x, y, z) {
  if (x < bounds.min[0]) bounds.min[0] = x;
  if (y < bounds.min[1]) bounds.min[1] = y;
  if (z < bounds.min[2]) bounds.min[2] = z;
  if (x > bounds.max[0]) bounds.max[0] = x;
  if (y > bounds.max[1]) bounds.max[1] = y;
  if (z > bounds.max[2]) bounds.max[2] = z;
}

function mergeBounds(target, source) {
  if (!Number.isFinite(source.min[0])) return;
  growBounds(target, source.min[0], source.min[1], source.min[2]);
  growBounds(target, source.max[0], source.max[1], source.max[2]);
}

function finiteBounds(bounds) {
  if (!Number.isFinite(bounds.min[0])) {
    return { min: [0, 0, 0], max: [0, 0, 0] };
  }
  return { min: [...bounds.min], max: [...bounds.max] };
}

// Per-face mesh statistics over the merged component buffers.
function faceStatistics(component, range) {
  const { positions, normals: vertexNormals, indices } = component;
  const bounds = emptyBounds();
  let area = 0;
  const centroid = [0, 0, 0];
  const normal = [0, 0, 0];
  for (let i = range.indexStart; i < range.indexStart + range.indexCount; i += 3) {
    const a = indices[i] * 3;
    const b = indices[i + 1] * 3;
    const c = indices[i + 2] * 3;
    const ux = positions[b] - positions[a];
    const uy = positions[b + 1] - positions[a + 1];
    const uz = positions[b + 2] - positions[a + 2];
    const vx = positions[c] - positions[a];
    const vy = positions[c + 1] - positions[a + 1];
    const vz = positions[c + 2] - positions[a + 2];
    const nx = uy * vz - uz * vy;
    const ny = uz * vx - ux * vz;
    const nz = ux * vy - uy * vx;
    const triangleArea = Math.hypot(nx, ny, nz) / 2;
    area += triangleArea;
    for (const vertex of [a, b, c]) {
      growBounds(bounds, positions[vertex], positions[vertex + 1], positions[vertex + 2]);
      centroid[0] += (positions[vertex] * triangleArea) / 3;
      centroid[1] += (positions[vertex + 1] * triangleArea) / 3;
      centroid[2] += (positions[vertex + 2] * triangleArea) / 3;
      normal[0] += (vertexNormals[vertex] * triangleArea) / 3;
      normal[1] += (vertexNormals[vertex + 1] * triangleArea) / 3;
      normal[2] += (vertexNormals[vertex + 2] * triangleArea) / 3;
    }
  }
  const safeArea = Math.max(area, 1e-12);
  const normalLength = Math.hypot(normal[0], normal[1], normal[2]) / safeArea;
  return {
    area,
    center: centroid.map((value) => value / safeArea),
    // Meaningful only when the face is nearly planar (matches the GLB
    // tables, where curved faces average out to shorter vectors).
    normal:
      normalLength > 0.5
        ? (() => {
            const length = Math.hypot(normal[0], normal[1], normal[2]) || 1;
            return [normal[0] / length, normal[1] / length, normal[2] / length];
          })()
        : null,
    bounds: finiteBounds(bounds),
  };
}

const ANALYTIC_SURFACES = new Set(["plane", "cylinder", "cone", "sphere", "torus"]);

export function buildSelectorBundleFromSurf(index, floats, options = {}) {
  const component = options.component || tessellateComponent(index, floats);
  const faces = index.faces || [];
  const edges = index.edges || [];
  const shapesMeta = index.shapes || [{ ord: 1, kind: "shape", volume: null }];

  const rangeByOrd = new Map(component.faceRanges.map((range) => [range.ord, range]));
  const faceRowByOrd = new Map(faces.map((face, row) => [face.ord, row]));
  const edgeRowByOrd = new Map(edges.map((edge, row) => [edge.ord, row]));

  // --- Face statistics + totals -------------------------------------------
  const statsByOrd = new Map();
  let totalArea = 0;
  const overallBounds = emptyBounds();
  for (const face of faces) {
    const range = rangeByOrd.get(face.ord);
    const stats = range
      ? faceStatistics(component, range)
      : { area: 0, center: [0, 0, 0], normal: null, bounds: finiteBounds(emptyBounds()) };
    // Prefer the EXACT metrics the extractor stored (GProps) over the
    // mesh-derived estimates; the mesh keeps supplying the normal.
    if (Number.isFinite(face.area)) stats.area = face.area;
    if (Array.isArray(face.center)) stats.center = face.center;
    if (Array.isArray(face.bbox) && face.bbox.length === 6) {
      stats.bounds = { min: face.bbox.slice(0, 3), max: face.bbox.slice(3, 6) };
    }
    statsByOrd.set(face.ord, stats);
    totalArea += stats.area;
    mergeBounds(overallBounds, stats.bounds);
  }
  totalArea = Math.max(totalArea, 1e-12);
  const diag = Math.hypot(
    overallBounds.max[0] - overallBounds.min[0],
    overallBounds.max[1] - overallBounds.min[1],
    overallBounds.max[2] - overallBounds.min[2],
  ) || 1e-9;
  const sizeFloor = Math.max(diag * diag * 1e-6, 1e-12);

  // --- Edge geometry from polylines ----------------------------------------
  const polylineByOrd = new Map(component.edges.map((edge) => [edge.ord, edge.polyline]));
  const edgeGeometry = new Map();
  let totalLength = 0;
  for (const edge of edges) {
    const polyline = polylineByOrd.get(edge.ord) || new Float32Array(0);
    const bounds = emptyBounds();
    let length = 0;
    const center = [0, 0, 0];
    const pointCount = polyline.length / 3;
    for (let i = 0; i < pointCount; i += 1) {
      growBounds(bounds, polyline[i * 3], polyline[i * 3 + 1], polyline[i * 3 + 2]);
      center[0] += polyline[i * 3];
      center[1] += polyline[i * 3 + 1];
      center[2] += polyline[i * 3 + 2];
      if (i > 0) {
        length += Math.hypot(
          polyline[i * 3] - polyline[(i - 1) * 3],
          polyline[i * 3 + 1] - polyline[(i - 1) * 3 + 1],
          polyline[i * 3 + 2] - polyline[(i - 1) * 3 + 2],
        );
      }
    }
    const exactLength = Number.isFinite(edge.length) ? edge.length : length;
    totalLength += exactLength;
    edgeGeometry.set(edge.ord, {
      polyline,
      length: exactLength,
      center: Array.isArray(edge.center)
        ? edge.center
        : pointCount ? center.map((value) => value / pointCount) : [0, 0, 0],
      bounds: Array.isArray(edge.bbox) && edge.bbox.length === 6
        ? { min: edge.bbox.slice(0, 3), max: edge.bbox.slice(3, 6) }
        : finiteBounds(bounds),
    });
  }
  totalLength = Math.max(totalLength, 1e-12);
  const lengthFloor = Math.max(diag * 1e-5, 1e-12);

  // --- Relations ------------------------------------------------------------
  const faceEdgeRows = [];
  const faceEdgeRanges = new Map();
  for (const face of faces) {
    const start = faceEdgeRows.length;
    const seen = new Set();
    for (const loop of face.loops || []) {
      for (const pcurve of loop) {
        const row = edgeRowByOrd.get(pcurve.edgeOrd);
        if (row !== undefined && !seen.has(row)) {
          seen.add(row);
          faceEdgeRows.push(row);
        }
      }
    }
    faceEdgeRanges.set(face.ord, { start, count: faceEdgeRows.length - start });
  }
  const edgeFaceRows = [];
  const edgeFaceRanges = new Map();
  for (const edge of edges) {
    const start = edgeFaceRows.length;
    for (const faceOrd of edge.faceOrds || []) {
      const row = faceRowByOrd.get(faceOrd);
      if (row !== undefined) edgeFaceRows.push(row);
    }
    edgeFaceRanges.set(edge.ord, { start, count: edgeFaceRows.length - start });
  }

  // --- Edge proxy polylines ---------------------------------------------------
  const edgePositions = [];
  const edgeIndices = [];
  const edgeIds = [];
  const segmentRanges = new Map();
  for (const edge of edges) {
    const row = edgeRowByOrd.get(edge.ord);
    const { polyline } = edgeGeometry.get(edge.ord);
    const pointBase = edgePositions.length / 3;
    const segmentStart = edgeIds.length;
    for (const value of polyline) edgePositions.push(value);
    const pointCount = polyline.length / 3;
    for (let i = 0; i + 1 < pointCount; i += 1) {
      edgeIndices.push(pointBase + i, pointBase + i + 1);
      edgeIds.push(row);
    }
    segmentRanges.set(edge.ord, { start: segmentStart, count: edgeIds.length - segmentStart });
  }

  // --- Surface half-edges (barycentric overlay index) -------------------------
  // Grouped per edge so edge rows can carry contiguous [start, count) runs.
  const halfEdgesByEdgeRow = new Map();
  for (const range of component.faceRanges) {
    const faceRow = faceRowByOrd.get(range.ord);
    const triangleBase = range.indexStart / 3;
    const triangleCount = range.indexCount / 3;
    for (let t = 0; t < triangleCount; t += 1) {
      for (let side = 0; side < 3; side += 1) {
        const ord = component.sideOrds[(triangleBase + t) * 3 + side];
        if (!ord) continue;
        const edgeRow = edgeRowByOrd.get(ord);
        if (edgeRow === undefined) continue;
        const classCode = CLASS_CODES[edges[edgeRow].class] || 0;
        if (!classCode) continue;
        let list = halfEdgesByEdgeRow.get(edgeRow);
        if (!list) halfEdgesByEdgeRow.set(edgeRow, (list = []));
        list.push([edgeRow, faceRow, 0, 0, triangleBase + t, side, classCode]);
      }
    }
  }
  const surfaceHalfEdges = [];
  const halfEdgeRanges = new Map();
  for (const edge of edges) {
    const row = edgeRowByOrd.get(edge.ord);
    const list = halfEdgesByEdgeRow.get(row) || [];
    const start = surfaceHalfEdges.length / 7;
    for (const halfEdge of list) surfaceHalfEdges.push(...halfEdge);
    halfEdgeRanges.set(edge.ord, { start, count: list.length });
  }

  // --- Shape rows --------------------------------------------------------------
  const shapeBounds = new Map();
  const shapeAreas = new Map();
  const shapeFaceCounts = new Map();
  const shapeEdgeCounts = new Map();
  for (const face of faces) {
    const shapeOrd = face.shape || 1;
    const stats = statsByOrd.get(face.ord);
    if (!shapeBounds.has(shapeOrd)) shapeBounds.set(shapeOrd, emptyBounds());
    mergeBounds(shapeBounds.get(shapeOrd), stats.bounds);
    shapeAreas.set(shapeOrd, (shapeAreas.get(shapeOrd) || 0) + stats.area);
    shapeFaceCounts.set(shapeOrd, (shapeFaceCounts.get(shapeOrd) || 0) + 1);
  }
  for (const edge of edges) {
    const shapeOrd = edge.shape || 1;
    shapeEdgeCounts.set(shapeOrd, (shapeEdgeCounts.get(shapeOrd) || 0) + 1);
  }
  const shapeRows = shapesMeta.map((shape) => {
    const bounds = finiteBounds(shapeBounds.get(shape.ord) || emptyBounds());
    return [
      `${OCCURRENCE_ID}.s${shape.ord}`,
      OCCURRENCE_ID,
      shape.ord,
      shape.kind,
      null,
      null,
      bounds,
      [(bounds.min[0] + bounds.max[0]) / 2, (bounds.min[1] + bounds.max[1]) / 2, (bounds.min[2] + bounds.max[2]) / 2],
      shapeAreas.get(shape.ord) || 0,
      shape.volume ?? null,
      0,
      shapeFaceCounts.get(shape.ord) || 0,
      0,
      shapeEdgeCounts.get(shape.ord) || 0,
    ];
  });

  // --- Face rows ------------------------------------------------------------
  const faceRows = faces.map((face) => {
    const stats = statsByOrd.get(face.ord);
    const range = rangeByOrd.get(face.ord);
    const relation = faceEdgeRanges.get(face.ord);
    let relevance = 100 * Math.sqrt(Math.max(stats.area, 0) / totalArea);
    if (ANALYTIC_SURFACES.has(face.surfaceType)) relevance += 8;
    if (stats.area < sizeFloor) relevance -= 45;
    const referenceable = Boolean(range && range.indexCount > 0 && stats.area > 1e-12);
    if (!referenceable) relevance = 0;
    return [
      `${OCCURRENCE_ID}.f${face.ord}`,
      OCCURRENCE_ID,
      `${OCCURRENCE_ID}.s${face.shape || 1}`,
      face.ord,
      face.surfaceType || face.surface?.kind || "",
      stats.area,
      stats.center,
      stats.normal,
      stats.bounds,
      relation.start,
      relation.count,
      Math.max(0, Math.min(100, Math.round(relevance))),
      referenceable ? 0 : 1,
      face.params ?? null,
      range ? range.indexStart / 3 : 0,
      range ? range.indexCount / 3 : 0,
    ];
  });

  // --- Edge rows ------------------------------------------------------------
  const edgeRows = edges.map((edge) => {
    const geometry = edgeGeometry.get(edge.ord);
    const relation = edgeFaceRanges.get(edge.ord);
    const segments = segmentRanges.get(edge.ord);
    const halfEdges = halfEdgeRanges.get(edge.ord);
    let relevance = 100 * Math.sqrt(Math.max(geometry.length, 0) / totalLength);
    if (["line", "circle", "ellipse"].includes(edge.curveType)) relevance += 8;
    if (geometry.length < lengthFloor) relevance -= 45;
    const referenceable = geometry.polyline.length >= 6 && edge.class !== "degenerate";
    if (!referenceable) relevance = 0;
    return [
      `${OCCURRENCE_ID}.e${edge.ord}`,
      OCCURRENCE_ID,
      `${OCCURRENCE_ID}.s${edge.shape || 1}`,
      edge.ord,
      edge.curveType || edge.curve?.kind || "",
      geometry.length,
      geometry.center,
      geometry.bounds,
      relation.start,
      relation.count,
      Math.max(0, Math.min(100, Math.round(relevance))),
      edge.flags || 0,
      edge.params ?? null,
      segments.start,
      segments.count,
      edge.adjacentFaceCount ?? (edge.faceOrds || []).length,
      edge.continuity || "",
      edge.dihedralDeg ?? null,
      edge.class,
      halfEdges.start,
      halfEdges.count,
    ];
  });

  const bbox = finiteBounds(overallBounds);
  const occurrenceRows = [[
    OCCURRENCE_ID, "1", null, null, null, IDENTITY_TRANSFORM, bbox,
    0, shapeRows.length, 0, faceRows.length, 0, edgeRows.length,
  ]];

  const visibilityCounts = {};
  for (const edge of edges) {
    visibilityCounts[edge.class] = (visibilityCounts[edge.class] || 0) + 1;
  }

  const manifest = {
    schemaVersion: STEP_TOPOLOGY_SCHEMA_VERSION,
    profile: "artifact",
    entryKind: "part",
    capabilities: capabilities(),
    bbox,
    stats: {
      occurrenceCount: 1,
      leafOccurrenceCount: 1,
      shapeCount: shapeRows.length,
      faceCount: faceRows.length,
      edgeCount: edgeRows.length,
      faceProxyRunCount: component.faceRanges.length,
      edgeProxyPointCount: edgePositions.length / 3,
      edgeProxySegmentCount: edgeIds.length,
      surfaceHalfEdgeCount: surfaceHalfEdges.length / 7,
    },
    edgeRendering: {
      visibilityClasses: [...RENDER_VISIBILITY_CLASSES],
      generatedVisibilityClasses: RENDER_VISIBILITY_CLASSES.filter(
        (classId) => (visibilityCounts[classId] || 0) > 0,
      ),
      visibilityClassCounts: visibilityCounts,
      generatedVisibilityClassCounts: visibilityCounts,
    },
    tables: {
      occurrenceColumns: OCCURRENCE_COLUMNS,
      shapeColumns: SHAPE_COLUMNS,
      faceColumns: FACE_COLUMNS,
      edgeColumns: EDGE_COLUMNS,
    },
    occurrences: occurrenceRows,
    shapes: shapeRows,
    faces: faceRows,
    edges: edgeRows,
    faceProxy: {
      source: "surf",
      runsView: "faceRuns",
      runColumns: ["occurrenceRow", "primitiveIndex", "triangleStart", "triangleCount", "faceRow"],
    },
    edgeProxy: {
      positionsView: "edgePositions",
      indicesView: "edgeIndices",
      edgeIdsView: "edgeIds",
    },
    relations: {
      faceEdgeRowsView: "faceEdgeRows",
      edgeFaceRowsView: "edgeFaceRows",
    },
    buffers: { littleEndian: true },
  };

  const faceRuns = new Uint32Array(component.faceRanges.length * 5);
  component.faceRanges.forEach((range, runIndex) => {
    faceRuns.set(
      [0, 0, range.indexStart / 3, range.indexCount / 3, faceRowByOrd.get(range.ord) ?? 0],
      runIndex * 5,
    );
  });

  return {
    manifest,
    buffers: {
      faceRuns,
      edgePositions: Float32Array.from(edgePositions),
      edgeIndices: Uint32Array.from(edgeIndices),
      edgeIds: Uint32Array.from(edgeIds),
      faceEdgeRows: Uint32Array.from(faceEdgeRows),
      edgeFaceRows: Uint32Array.from(edgeFaceRows),
      surfaceHalfEdges: Uint32Array.from(surfaceHalfEdges),
    },
  };
}
