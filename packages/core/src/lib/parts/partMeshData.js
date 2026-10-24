// CAD edges as indexed line segments, grouped by class: what a tube skin's edge pass draws
// (`common/tubeSkin.js`), from an edge table and its points.

import { MESH_EDGE_CLASSES, MESH_TABLE_COLUMNS } from "./tessellationCache.js";

// The line pass groups CAD edges by class so display.edges.classes styles each
// one; every other edge class the extractor knows (boundary, nonManifold,
// unknown) draws as a feature edge, `none` is not drawn at all.
export const CAD_EDGE_LINE_CLASSES = Object.freeze(["feature", "tangent", "seam", "degenerate"]);

// Each edge class code's line class (its CAD_EDGE_LINE_CLASSES index), -1 for an edge not drawn.
const LINE_CLASS_OF_CODE = Object.freeze(MESH_EDGE_CLASSES.map((name) => (
  name === "none" ? -1 : Math.max(0, CAD_EDGE_LINE_CLASSES.indexOf(name))
)));

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
