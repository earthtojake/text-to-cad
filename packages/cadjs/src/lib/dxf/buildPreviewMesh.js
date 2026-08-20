import { Matrix4, ShapeUtils, Vector2, Vector3 } from "three";

import {
  assignHolesToRegions,
  buildFoldBridgeGeometry,
  buildFoldLine,
  buildRegionPlacements,
  decomposeFoldRegions,
  foldLineSpanForRegion,
  foldSignedDistance
} from "./foldRegions.js";

export const DEFAULT_DXF_PREVIEW_THICKNESS_MM = 2;
export const MIN_DXF_PREVIEW_THICKNESS_MM = 0.2;
export const MAX_DXF_PREVIEW_THICKNESS_MM = 25;
export const DEFAULT_DXF_BEND_ANGLE_DEG = 0;
export const MIN_DXF_BEND_ANGLE_DEG = 0;
export const MAX_DXF_BEND_ANGLE_DEG = 180;
export const DXF_BEND_DIRECTION = {
  UP: "up",
  DOWN: "down"
};

const POINT_KEY_SCALE = 1000;
const ARC_CHORD_TOLERANCE_MM = 0.35;
const MIN_ARC_SEGMENTS = 10;
const MAX_ARC_SEGMENTS = 160;
const BEND_LINE_ELEVATION_MM = 0.04;
const GEOMETRY_EPSILON_MM = 1e-3;
const BEND_LINE_AXIS_EPSILON_MM = 1e-2;
// How far short of the material's edge a fold line may stop. Generous next to the axis epsilon
// on purpose: a bend line is authored to a rounded coordinate while the contour it has to reach
// may end on a fillet tangent, so a few hundredths of a millimetre is authoring noise, not a
// bend line that fails to separate the part.
const BEND_LINE_FULL_SPAN_TOLERANCE_MM = 0.05;
const MIN_BEND_BRIDGE_SEGMENTS = 6;
const MAX_BEND_BRIDGE_SEGMENTS = 48;
const VISUAL_BEND_INSIDE_RADIUS_RATIO = 0.6;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function approxEqual(a, b, epsilon = GEOMETRY_EPSILON_MM) {
  return Math.abs(a - b) <= epsilon;
}

function normalizePoint(point) {
  if (!Array.isArray(point) || point.length < 2) {
    return [0, 0];
  }
  return [toFiniteNumber(point[0]), toFiniteNumber(point[1])];
}

function pointsEqual(a, b, epsilon = GEOMETRY_EPSILON_MM) {
  return Math.abs(a[0] - b[0]) <= epsilon && Math.abs(a[1] - b[1]) <= epsilon;
}

function pointKey(point) {
  return `${Math.round(point[0] * POINT_KEY_SCALE)}:${Math.round(point[1] * POINT_KEY_SCALE)}`;
}

function reversePoints(points) {
  return [...points].reverse();
}

function removeDuplicateClosure(points) {
  if (points.length > 1 && pointsEqual(points[0], points[points.length - 1])) {
    return points.slice(0, -1);
  }
  return points;
}

function removeConsecutiveDuplicates(points) {
  const deduped = [];
  for (const point of points) {
    if (deduped.length && pointsEqual(deduped[deduped.length - 1], point)) {
      continue;
    }
    deduped.push(point);
  }
  return removeDuplicateClosure(deduped);
}

function sampleCountForSweep(radius, sweepRadians) {
  const safeRadius = Math.max(Math.abs(radius), 0.01);
  const chordRatio = clamp(1 - (ARC_CHORD_TOLERANCE_MM / safeRadius), -1, 1);
  const maxSegmentAngle = chordRatio <= -1
    ? Math.PI / 8
    : clamp(2 * Math.acos(chordRatio), Math.PI / 64, Math.PI / 10);
  return clamp(
    Math.ceil(Math.max(Math.abs(sweepRadians), Math.PI / 36) / maxSegmentAngle),
    MIN_ARC_SEGMENTS,
    MAX_ARC_SEGMENTS
  );
}

function sampleArcPoints(center, radius, startAngleDeg, sweepAngleDeg) {
  const startAngleRad = (toFiniteNumber(startAngleDeg) * Math.PI) / 180;
  const sweepAngleRad = (toFiniteNumber(sweepAngleDeg) * Math.PI) / 180;
  const segments = sampleCountForSweep(radius, sweepAngleRad);
  const points = [];
  for (let index = 0; index <= segments; index += 1) {
    const t = index / segments;
    const angle = startAngleRad + sweepAngleRad * t;
    points.push([
      center[0] + radius * Math.cos(angle),
      center[1] + radius * Math.sin(angle)
    ]);
  }
  return points;
}

function sampleCirclePoints(center, radius) {
  const points = sampleArcPoints(center, radius, 0, 360);
  return removeDuplicateClosure(points);
}

function polygonSignedArea(points) {
  if (!Array.isArray(points) || points.length < 3) {
    return 0;
  }
  let area = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    area += current[0] * next[1] - next[0] * current[1];
  }
  return area / 2;
}

function normalizeLoopWinding(points, { clockwise }) {
  const deduped = removeConsecutiveDuplicates(points);
  if (deduped.length < 3) {
    return deduped;
  }
  const vectors = deduped.map(([x, y]) => new Vector2(x, y));
  const isClockwise = ShapeUtils.isClockWise(vectors);
  if ((clockwise && !isClockwise) || (!clockwise && isClockwise)) {
    return reversePoints(deduped);
  }
  return deduped;
}

function readGeometryRecords(dxfData) {
  const geometry = dxfData?.geometry || {};
  const lineRecords = Array.isArray(geometry.lines) ? geometry.lines : [];
  const arcRecords = Array.isArray(geometry.arcs) ? geometry.arcs : [];
  const circleRecords = Array.isArray(geometry.circles) ? geometry.circles : [];

  const cutPrimitives = [];
  const cutCircleLoops = [];
  const bendLines = [];
  const engravePolylines = [];

  for (const record of lineRecords) {
    const start = normalizePoint(record?.start);
    const end = normalizePoint(record?.end);
    const kind = String(record?.kind || "").trim().toLowerCase();
    if (kind === "bend") {
      bendLines.push([start, end]);
      continue;
    }
    if (pointsEqual(start, end)) {
      continue;
    }
    if (kind === "engrave") {
      engravePolylines.push([start, end]);
      continue;
    }
    if (kind && kind !== "cut") {
      continue;
    }
    cutPrimitives.push({ points: [start, end] });
  }

  for (const record of arcRecords) {
    const center = normalizePoint(record?.center);
    const radius = Math.max(toFiniteNumber(record?.radius), 0);
    if (radius <= 0) {
      continue;
    }
    const kind = String(record?.kind || "").trim().toLowerCase();
    const points = sampleArcPoints(
      center,
      radius,
      toFiniteNumber(record?.startAngleDeg),
      toFiniteNumber(record?.sweepAngleDeg)
    );
    if (kind === "bend") {
      bendLines.push([points[0], points[points.length - 1]]);
      continue;
    }
    if (kind === "engrave") {
      engravePolylines.push(points);
      continue;
    }
    if (kind && kind !== "cut") {
      continue;
    }
    cutPrimitives.push({ points });
  }

  for (const record of circleRecords) {
    const center = normalizePoint(record?.center);
    const radius = Math.max(toFiniteNumber(record?.radius), 0);
    if (radius <= 0) {
      continue;
    }
    const kind = String(record?.kind || "").trim().toLowerCase();
    if (kind === "engrave") {
      const loop = sampleCirclePoints(center, radius);
      engravePolylines.push([...loop, loop[0]]);
      continue;
    }
    if (kind && kind !== "cut") {
      continue;
    }
    cutCircleLoops.push(sampleCirclePoints(center, radius));
  }

  return {
    cutPrimitives,
    cutCircleLoops,
    bendLines,
    engravePolylines
  };
}

/** Walk cut primitives into chains by coincident endpoints: closed chains become loops,
 *  dead-ended ones are kept as OPEN chains (they render as score lines, not solids). */
function chainCutPrimitives(cutPrimitives) {
  const adjacency = new Map();
  const visited = new Set();
  const loops = [];
  const openChains = [];

  const addAdjacency = (key, value) => {
    const existing = adjacency.get(key);
    if (existing) {
      existing.push(value);
      return;
    }
    adjacency.set(key, [value]);
  };

  cutPrimitives.forEach((primitive, index) => {
    const startKey = pointKey(primitive.points[0]);
    const endKey = pointKey(primitive.points[primitive.points.length - 1]);
    addAdjacency(startKey, { index, reverse: false });
    addAdjacency(endKey, { index, reverse: true });
  });

  for (let primitiveIndex = 0; primitiveIndex < cutPrimitives.length; primitiveIndex += 1) {
    if (visited.has(primitiveIndex)) {
      continue;
    }
    visited.add(primitiveIndex);
    let loopPoints = [...cutPrimitives[primitiveIndex].points];
    let guard = 0;

    // Extend forward from the chain's tail until it closes on its head or dead-ends.
    const extend = () => {
      const startKey = pointKey(loopPoints[0]);
      let currentKey = pointKey(loopPoints[loopPoints.length - 1]);
      while (currentKey !== startKey) {
        const nextOptions = (adjacency.get(currentKey) || []).filter(({ index }) => !visited.has(index));
        if (!nextOptions.length) {
          return false;
        }
        const nextOption = nextOptions[0];
        visited.add(nextOption.index);
        const primitivePoints = cutPrimitives[nextOption.index].points;
        const orientedPoints = nextOption.reverse ? reversePoints(primitivePoints) : primitivePoints;
        loopPoints = loopPoints.concat(orientedPoints.slice(1));
        currentKey = pointKey(orientedPoints[orientedPoints.length - 1]);
        guard += 1;
        if (guard > cutPrimitives.length + 4) {
          throw new Error("DXF preview contour walk did not terminate");
        }
      }
      return true;
    };

    let closed = extend();
    if (!closed) {
      // The seed may sit mid-chain: walk the OTHER direction too before giving up, so one
      // polyline does not split into two chains at an arbitrary seed.
      loopPoints = reversePoints(loopPoints);
      closed = extend();
    }

    if (closed) {
      loopPoints = removeConsecutiveDuplicates(loopPoints);
      if (loopPoints.length >= 3) {
        loops.push(loopPoints);
      }
      continue;
    }
    // A chain that does not close is not a solid boundary. It USED to be dropped outright;
    // now it is kept as an open chain — a score/engrave path the viewer overlays on the
    // sheet — so a witness line or a decorative score no longer silently vanishes.
    if (loopPoints.length >= 2) {
      openChains.push(loopPoints);
    }
  }

  return { loops, openChains };
}

function buildCutLoops(dxfData) {
  const { cutPrimitives, cutCircleLoops, bendLines } = readGeometryRecords(dxfData);
  if (!cutPrimitives.length && !cutCircleLoops.length) {
    throw new Error("DXF preview requires cut-layer contour geometry");
  }

  const { loops } = chainCutPrimitives(cutPrimitives);

  for (const circleLoop of cutCircleLoops) {
    if (circleLoop.length >= 3) {
      loops.push(circleLoop);
    }
  }

  if (!loops.length) {
    throw new Error("DXF preview could not resolve any closed cut contours");
  }

  return {
    loops,
    bendLines
  };
}

/**
 * Flat-pattern facts for the Material sheet: bounding size and the NET area (outer loops
 * minus holes, holes-in-holes adding back — the even/odd containment rule the mesher
 * triangulates by). Millimetres in, mm/mm^2 out; weight is the caller's multiply.
 */
export function computeDxfFlatStats(dxfData) {
  const { cutPrimitives, cutCircleLoops } = readGeometryRecords(dxfData);
  const { loops } = chainCutPrimitives(cutPrimitives);
  for (const circleLoop of cutCircleLoops) {
    if (circleLoop.length >= 3) {
      loops.push(circleLoop);
    }
  }
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const loop of loops) {
    for (const [x, y] of loop) {
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  const sorted = [...loops].sort((a, b) => Math.abs(polygonSignedArea(b)) - Math.abs(polygonSignedArea(a)));
  const nodes = loopContainmentNodes(sorted);
  let areaMm2 = 0;
  for (const node of nodes) {
    areaMm2 += (node.depth % 2 === 0 ? 1 : -1) * node.area;
  }
  return {
    areaMm2: Math.max(areaMm2, 0),
    widthMm: Number.isFinite(minX) ? Math.max(maxX - minX, 0) : 0,
    heightMm: Number.isFinite(minY) ? Math.max(maxY - minY, 0) : 0
  };
}

/**
 * Every polyline that should render as a SCORE — an engraved/etched path lying on the
 * sheet's surface rather than cut through it: engrave-layer geometry, plus any cut-layer
 * chain that does not close (a witness line, a centre mark, a decorative score). Returned
 * in flat-pattern mm; the viewer folds and elevates them.
 */
export function extractDxfScorePolylines(dxfData) {
  const { cutPrimitives, engravePolylines } = readGeometryRecords(dxfData);
  const { openChains } = chainCutPrimitives(cutPrimitives);
  return [...engravePolylines, ...openChains];
}

function normalizeBendLine(line, index) {
  const start = normalizePoint(line?.[0]);
  const end = normalizePoint(line?.[1]);
  const ordered = end[1] < start[1] ? [end, start] : [start, end];
  return {
    id: `bend-${index + 1}`,
    index,
    start: ordered[0],
    end: ordered[1],
    x: (ordered[0][0] + ordered[1][0]) / 2,
    yMin: Math.min(ordered[0][1], ordered[1][1]),
    yMax: Math.max(ordered[0][1], ordered[1][1])
  };
}

function sortBendLines(rawBendLines) {
  return rawBendLines
    .map((line, index) => normalizeBendLine(line, index))
    .sort((a, b) => {
      const xDiff = a.x - b.x;
      if (Math.abs(xDiff) > GEOMETRY_EPSILON_MM) {
        return xDiff;
      }
      return a.yMin - b.yMin;
    })
    .map((line, index) => ({
      ...line,
      id: `bend-${index + 1}`,
      index
    }));
}

export function extractOrderedDxfBendLines(dxfData) {
  const { bendLines } = readGeometryRecords(dxfData);
  return sortBendLines(bendLines);
}

/** A folding bend has to be a usable hinge; WHERE it is and how it is angled no longer matter.
 *
 * Orientation used to be checked here, because the decomposition sliced the blank into vertical
 * X-slabs and could not represent anything else. It splits per FACE along each fold's own
 * segment now (see foldRegions.js), so a bend at any angle folds -- and the one rule left is
 * that the line has to be long enough to be a line at all. Whether it actually separates a face
 * in two is decided by the decomposition, which knows the faces. */
function validateActiveBendLines(bendLines, bendSettings) {
  bendLines.forEach((bendLine, index) => {
    const angleDeg = normalizeDxfBendAngleDeg(bendSettings?.[index]?.angleDeg, 0);
    if (angleDeg === 0) {
      return;
    }
    const length = Math.hypot(
      bendLine.end[0] - bendLine.start[0],
      bendLine.end[1] - bendLine.start[1]
    );
    if (length <= GEOMETRY_EPSILON_MM) {
      throw new Error("DXF bend line length is too small for preview bending");
    }
  });
}

export function normalizeDxfBendDirection(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized === DXF_BEND_DIRECTION.DOWN ? DXF_BEND_DIRECTION.DOWN : DXF_BEND_DIRECTION.UP;
}

export function normalizeDxfBendAngleDeg(value, fallback = DEFAULT_DXF_BEND_ANGLE_DEG) {
  const safeFallback = clamp(
    toFiniteNumber(fallback, DEFAULT_DXF_BEND_ANGLE_DEG),
    MIN_DXF_BEND_ANGLE_DEG,
    MAX_DXF_BEND_ANGLE_DEG
  );
  const numericValue = toFiniteNumber(value, safeFallback);
  return clamp(numericValue, MIN_DXF_BEND_ANGLE_DEG, MAX_DXF_BEND_ANGLE_DEG);
}

export function normalizeDxfPreviewThicknessMm(value, fallback = DEFAULT_DXF_PREVIEW_THICKNESS_MM) {
  const safeFallback = clamp(
    toFiniteNumber(fallback, DEFAULT_DXF_PREVIEW_THICKNESS_MM),
    MIN_DXF_PREVIEW_THICKNESS_MM,
    MAX_DXF_PREVIEW_THICKNESS_MM
  );
  const numericValue = toFiniteNumber(value, safeFallback);
  if (numericValue <= 0) {
    return safeFallback;
  }
  return clamp(numericValue, MIN_DXF_PREVIEW_THICKNESS_MM, MAX_DXF_PREVIEW_THICKNESS_MM);
}

export function normalizeDxfBendSettings(dxfData, value) {
  const bendLines = extractOrderedDxfBendLines(dxfData);
  const source = Array.isArray(value) ? value : [];
  return bendLines.map((bendLine, index) => {
    const current = source[index] && typeof source[index] === "object" ? source[index] : {};
    return {
      id: bendLine.id,
      direction: normalizeDxfBendDirection(current.direction),
      angleDeg: normalizeDxfBendAngleDeg(current.angleDeg, DEFAULT_DXF_BEND_ANGLE_DEG)
    };
  });
}

function loopBounds(loop) {
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const point of loop) {
    minX = Math.min(minX, point[0]);
    minY = Math.min(minY, point[1]);
    maxX = Math.max(maxX, point[0]);
    maxY = Math.max(maxY, point[1]);
  }
  return {
    minX,
    minY,
    maxX,
    maxY
  };
}

function pointOnSegment(point, start, end) {
  const cross = ((point[1] - start[1]) * (end[0] - start[0])) - ((point[0] - start[0]) * (end[1] - start[1]));
  if (Math.abs(cross) > GEOMETRY_EPSILON_MM) {
    return false;
  }
  const dot = ((point[0] - start[0]) * (end[0] - start[0])) + ((point[1] - start[1]) * (end[1] - start[1]));
  if (dot < -GEOMETRY_EPSILON_MM) {
    return false;
  }
  const squaredLength = ((end[0] - start[0]) ** 2) + ((end[1] - start[1]) ** 2);
  return dot <= squaredLength + GEOMETRY_EPSILON_MM;
}

function pointInLoop(point, loop) {
  let inside = false;
  for (let index = 0, previousIndex = loop.length - 1; index < loop.length; previousIndex = index, index += 1) {
    const current = loop[index];
    const previous = loop[previousIndex];
    if (pointOnSegment(point, previous, current)) {
      return true;
    }
    const crossesRay = (current[1] > point[1]) !== (previous[1] > point[1]);
    if (!crossesRay) {
      continue;
    }
    const xIntersection = previous[0] + ((point[1] - previous[1]) * (current[0] - previous[0])) / (current[1] - previous[1]);
    if (point[0] < xIntersection) {
      inside = !inside;
    }
  }
  return inside;
}

function loopContainmentNodes(sortedLoops) {
  const nodes = sortedLoops.map((loop, index) => ({
    loop,
    index,
    parentIndex: -1,
    depth: -1,
    area: Math.abs(polygonSignedArea(loop))
  }));

  for (let index = 0; index < nodes.length; index += 1) {
    const node = nodes[index];
    const representativePoint = node.loop[0];
    let parentIndex = -1;
    let parentArea = Number.POSITIVE_INFINITY;
    for (let candidateIndex = 0; candidateIndex < nodes.length; candidateIndex += 1) {
      if (candidateIndex === index) {
        continue;
      }
      const candidate = nodes[candidateIndex];
      if (candidate.area <= node.area + GEOMETRY_EPSILON_MM || candidate.area >= parentArea) {
        continue;
      }
      if (pointInLoop(representativePoint, candidate.loop)) {
        parentIndex = candidateIndex;
        parentArea = candidate.area;
      }
    }
    node.parentIndex = parentIndex;
  }

  const resolveDepth = (index) => {
    const node = nodes[index];
    if (node.depth >= 0) {
      return node.depth;
    }
    node.depth = node.parentIndex < 0 ? 0 : resolveDepth(node.parentIndex) + 1;
    return node.depth;
  };
  for (let index = 0; index < nodes.length; index += 1) {
    resolveDepth(index);
  }
  return nodes;
}

function buildFlatStripDefinitions(sortedLoops) {
  const nodes = loopContainmentNodes(sortedLoops);
  const strips = [];
  for (const node of nodes) {
    if (node.depth % 2 !== 0) {
      continue;
    }
    const outerLoop = normalizeLoopWinding(node.loop, { clockwise: true });
    const bounds = loopBounds(outerLoop);
    const holeLoops = nodes
      .filter((candidate) => candidate.parentIndex === node.index && candidate.depth % 2 === 1)
      .map((candidate) => normalizeLoopWinding(candidate.loop, { clockwise: false }));
    strips.push({
      index: strips.length,
      transformIndex: 0,
      leftX: bounds.minX,
      rightX: bounds.maxX,
      outerLoop,
      holeLoops,
      isLeftExterior: true,
      isRightExterior: true
    });
  }
  if (!strips.length) {
    throw new Error("DXF preview could not build flat extrusion geometry");
  }
  return strips;
}

/** The face that a bend line's guide should ride on.
 *
 * For a fold, the parent side is arbitrary but stable: the guide marks where the bend IS, so it
 * belongs to whichever face still contains the line's own position. For a crease, that is the
 * face the crease sits inside. */
function regionIndexForGuide(regions, bendLine, foldIndex, adjacency, parents) {
  const midpoint = [
    (bendLine.start[0] + bendLine.end[0]) / 2,
    (bendLine.start[1] + bendLine.end[1]) / 2
  ];
  if (foldIndex >= 0) {
    // The guide belongs to the fold's HINGE PARENT, which is the frame its curved band is
    // already built in, so the dashes land on the crease. Picking any face that merely sits on
    // the fold's negative side does not: with more than two faces, several share that side
    // without touching the fold, and the guide gets drawn with a face's matrix that has nothing
    // to do with this bend -- dashes floating off the part.
    const edge = adjacency.find((candidate) => candidate.foldIndex === foldIndex);
    if (edge) {
      const [a, b] = edge.regions;
      return parents[b]?.region === a ? a : b;
    }
  }
  const containing = regions.findIndex((region) => pointInLoop(midpoint, region.outerLoop));
  return containing >= 0 ? containing : 0;
}

/** Whether an edge of a face lies along a fold's band, where the bend continues.
 *
 * Those edges are internal: drawing them would put a cut line down the middle of a bend. The
 * slab version compared against the strip's left/right X; this asks the folds directly, so it
 * holds for a band at any angle. */
function isFoldBandEdge(start, end, strip) {
  for (const foldLine of strip.foldLines || []) {
    if (foldLine.halfWidth <= GEOMETRY_EPSILON_MM) {
      continue;
    }
    const startDistance = Math.abs(foldSignedDistance(foldLine, start));
    const endDistance = Math.abs(foldSignedDistance(foldLine, end));
    if (
      Math.abs(startDistance - foldLine.halfWidth) <= 1e-3 &&
      Math.abs(endDistance - foldLine.halfWidth) <= 1e-3
    ) {
      return true;
    }
  }
  return false;
}

function appendTriangle(vertices, indices, a, b, c) {
  const indexOffset = vertices.length / 3;
  vertices.push(...a, ...b, ...c);
  indices.push(indexOffset, indexOffset + 1, indexOffset + 2);
}

function orientTriangleY(a, b, c, positiveY = true) {
  const abx = b[0] - a[0];
  const abz = b[2] - a[2];
  const acx = c[0] - a[0];
  const acz = c[2] - a[2];
  const crossY = abz * acx - abx * acz;
  if ((positiveY && crossY < 0) || (!positiveY && crossY > 0)) {
    return [a, c, b];
  }
  return [a, b, c];
}

function applyMatrixToPoint(matrix, point) {
  const [x, y, z] = point;
  const elements = matrix.elements;
  return [
    elements[0] * x + elements[4] * y + elements[8] * z + elements[12],
    elements[1] * x + elements[5] * y + elements[9] * z + elements[13],
    elements[2] * x + elements[6] * y + elements[10] * z + elements[14]
  ];
}

function appendTransformedTriangle(vertices, indices, matrix, a, b, c, positiveY) {
  const triangle = orientTriangleY(
    applyMatrixToPoint(matrix, a),
    applyMatrixToPoint(matrix, b),
    applyMatrixToPoint(matrix, c),
    positiveY
  );
  appendTriangle(vertices, indices, triangle[0], triangle[1], triangle[2]);
}

function appendTransformedQuad(vertices, indices, matrix, a, b, c, d, reverse = false) {
  const transformedA = applyMatrixToPoint(matrix, a);
  const transformedB = applyMatrixToPoint(matrix, b);
  const transformedC = applyMatrixToPoint(matrix, c);
  const transformedD = applyMatrixToPoint(matrix, d);
  if (reverse) {
    appendTriangle(vertices, indices, transformedA, transformedC, transformedB);
    appendTriangle(vertices, indices, transformedA, transformedD, transformedC);
    return;
  }
  appendTriangle(vertices, indices, transformedA, transformedB, transformedC);
  appendTriangle(vertices, indices, transformedA, transformedC, transformedD);
}

function appendVertex(vertices, x, y, z) {
  vertices.push(x, y, z);
  return (vertices.length / 3) - 1;
}

function appendTransformedEdgeSegment(vertices, edgeIndices, matrix, start, end) {
  const transformedStart = applyMatrixToPoint(matrix, start);
  const transformedEnd = applyMatrixToPoint(matrix, end);
  const startIndex = appendVertex(vertices, transformedStart[0], transformedStart[1], transformedStart[2]);
  const endIndex = appendVertex(vertices, transformedEnd[0], transformedEnd[1], transformedEnd[2]);
  edgeIndices.push(startIndex, endIndex);
}

function appendLoopSideFaces(vertices, indices, matrix, loop, topY, bottomY, shouldSkipEdge = () => false) {
  for (let index = 0; index < loop.length; index += 1) {
    const start = loop[index];
    const end = loop[(index + 1) % loop.length];
    if (shouldSkipEdge(start, end)) {
      continue;
    }
    appendTransformedTriangle(
      vertices,
      indices,
      matrix,
      [start[0], topY, start[1]],
      [end[0], topY, end[1]],
      [end[0], bottomY, end[1]],
      true
    );
    appendTransformedTriangle(
      vertices,
      indices,
      matrix,
      [start[0], topY, start[1]],
      [end[0], bottomY, end[1]],
      [start[0], bottomY, start[1]],
      true
    );
  }
}

function appendLoopEdgeSegments(vertices, edgeIndices, matrix, loop, topY, bottomY, shouldSkipEdge = () => false) {
  for (let index = 0; index < loop.length; index += 1) {
    const start = loop[index];
    const end = loop[(index + 1) % loop.length];
    if (shouldSkipEdge(start, end)) {
      continue;
    }
    appendTransformedEdgeSegment(
      vertices,
      edgeIndices,
      matrix,
      [start[0], topY, start[1]],
      [end[0], topY, end[1]]
    );
    appendTransformedEdgeSegment(
      vertices,
      edgeIndices,
      matrix,
      [start[0], bottomY, start[1]],
      [end[0], bottomY, end[1]]
    );
    appendTransformedEdgeSegment(
      vertices,
      edgeIndices,
      matrix,
      [start[0], topY, start[1]],
      [start[0], bottomY, start[1]]
    );
  }
}

function bendAngleRadiansForSetting(setting) {
  return (normalizeDxfBendDirection(setting?.direction) === DXF_BEND_DIRECTION.DOWN ? -1 : 1)
    * ((normalizeDxfBendAngleDeg(setting?.angleDeg) * Math.PI) / 180);
}

function bendArcPoint(bendProfile, surfaceY, z, angleRadians) {
  const centerY = (bendProfile.angleRadians < 0 ? -1 : 1) * bendProfile.neutralRadius;
  const startVectorY = surfaceY - centerY;
  return [
    bendProfile.leftX - startVectorY * Math.sin(angleRadians),
    centerY + startVectorY * Math.cos(angleRadians),
    z
  ];
}

function appendBendArcSurface(vertices, indices, matrix, bendProfile, surfaceY, zMin, zMax, startAngle, endAngle, reverse) {
  appendTransformedQuad(
    vertices,
    indices,
    matrix,
    bendArcPoint(bendProfile, surfaceY, zMin, startAngle),
    bendArcPoint(bendProfile, surfaceY, zMin, endAngle),
    bendArcPoint(bendProfile, surfaceY, zMax, endAngle),
    bendArcPoint(bendProfile, surfaceY, zMax, startAngle),
    reverse
  );
}

function appendBendCapSurface(vertices, indices, matrix, bendProfile, halfThickness, z, startAngle, endAngle, reverse) {
  appendTransformedQuad(
    vertices,
    indices,
    matrix,
    bendArcPoint(bendProfile, halfThickness, z, startAngle),
    bendArcPoint(bendProfile, halfThickness, z, endAngle),
    bendArcPoint(bendProfile, -halfThickness, z, endAngle),
    bendArcPoint(bendProfile, -halfThickness, z, startAngle),
    reverse
  );
}

function appendBendArcEdgeSegments(vertices, edgeIndices, matrix, bendProfile, surfaceY, z, startAngle, endAngle) {
  appendTransformedEdgeSegment(
    vertices,
    edgeIndices,
    matrix,
    bendArcPoint(bendProfile, surfaceY, z, startAngle),
    bendArcPoint(bendProfile, surfaceY, z, endAngle)
  );
}

function appendBendRadialEdgeSegment(vertices, edgeIndices, matrix, bendProfile, halfThickness, z, angleRadians) {
  appendTransformedEdgeSegment(
    vertices,
    edgeIndices,
    matrix,
    bendArcPoint(bendProfile, halfThickness, z, angleRadians),
    bendArcPoint(bendProfile, -halfThickness, z, angleRadians)
  );
}

function appendBendBridgeInterval(vertices, indices, edgeVertices, edgeIndices, bendTransform, interval, halfThickness) {
  const { bendProfile } = bendTransform;
  const angleRadians = bendProfile.angleRadians;
  if (Math.abs(angleRadians) <= 1e-6) {
    return;
  }

  const [zMin, zMax] = interval;
  if (zMax - zMin <= GEOMETRY_EPSILON_MM) {
    return;
  }

  const matrix = bendTransform.matrix;
  const segmentCount = bendBridgeSegmentCount(bendProfile.neutralRadius + halfThickness, angleRadians);
  const reverseArcSurface = angleRadians < 0;
  const reverseMinCap = angleRadians > 0;
  const reverseMaxCap = angleRadians < 0;

  for (let segmentIndex = 0; segmentIndex < segmentCount; segmentIndex += 1) {
    const startAngle = angleRadians * (segmentIndex / segmentCount);
    const endAngle = angleRadians * ((segmentIndex + 1) / segmentCount);

    appendBendArcSurface(
      vertices,
      indices,
      matrix,
      bendProfile,
      halfThickness,
      zMin,
      zMax,
      startAngle,
      endAngle,
      reverseArcSurface
    );
    appendBendArcSurface(
      vertices,
      indices,
      matrix,
      bendProfile,
      -halfThickness,
      zMin,
      zMax,
      startAngle,
      endAngle,
      reverseArcSurface
    );
    appendBendCapSurface(
      vertices,
      indices,
      matrix,
      bendProfile,
      halfThickness,
      zMin,
      startAngle,
      endAngle,
      reverseMinCap
    );
    appendBendCapSurface(
      vertices,
      indices,
      matrix,
      bendProfile,
      halfThickness,
      zMax,
      startAngle,
      endAngle,
      reverseMaxCap
    );

    for (const surfaceY of [halfThickness, -halfThickness]) {
      appendBendArcEdgeSegments(edgeVertices, edgeIndices, matrix, bendProfile, surfaceY, zMin, startAngle, endAngle);
      appendBendArcEdgeSegments(edgeVertices, edgeIndices, matrix, bendProfile, surfaceY, zMax, startAngle, endAngle);
    }
  }

  for (const angle of [0, angleRadians]) {
    appendBendRadialEdgeSegment(edgeVertices, edgeIndices, matrix, bendProfile, halfThickness, zMin, angle);
    appendBendRadialEdgeSegment(edgeVertices, edgeIndices, matrix, bendProfile, halfThickness, zMax, angle);
  }
}

function buildBounds(vertices) {
  if (!vertices.length) {
    return {
      min: [0, 0, 0],
      max: [0, 0, 0]
    };
  }
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let minZ = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  let maxZ = Number.NEGATIVE_INFINITY;
  for (let index = 0; index < vertices.length; index += 3) {
    const x = vertices[index];
    const y = vertices[index + 1];
    const z = vertices[index + 2];
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    minZ = Math.min(minZ, z);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
    maxZ = Math.max(maxZ, z);
  }
  return {
    min: [minX, minY, minZ],
    max: [maxX, maxY, maxZ]
  };
}

function buildTriangulatedFlatPattern(dxfData) {
  const { loops, bendLines: rawBendLines } = buildCutLoops(dxfData);
  const sortedLoops = [...loops].sort((a, b) => Math.abs(polygonSignedArea(b)) - Math.abs(polygonSignedArea(a)));
  const outerLoop = normalizeLoopWinding(sortedLoops[0] || [], { clockwise: true });
  if (!outerLoop.length) {
    throw new Error("DXF preview requires one outer contour");
  }
  const holeLoops = sortedLoops.slice(1).map((loop) => normalizeLoopWinding(loop, { clockwise: false }));
  const bendLines = sortBendLines(rawBendLines);
  return {
    loops: sortedLoops,
    outerLoop,
    holeLoops,
    bendLines
  };
}

export function buildDxfPreviewMeshData(dxfData, thicknessMm, bendSettings = null, options = null) {
  const guideElevationSign = options?.guideElevationSign === -1 ? -1 : 1;
  const { loops, outerLoop, holeLoops, bendLines } = buildTriangulatedFlatPattern(dxfData);
  const normalizedThicknessMm = normalizeDxfPreviewThicknessMm(
    thicknessMm,
    toFiniteNumber(dxfData?.defaultThicknessMm, DEFAULT_DXF_PREVIEW_THICKNESS_MM)
  );
  const normalizedBendSettings = normalizeDxfBendSettings(dxfData, bendSettings);
  validateActiveBendLines(bendLines, normalizedBendSettings);
  const halfThickness = normalizedThicknessMm / 2;
  let strips;
  let guideLineSegments;
  let transforms;
  // Only a bend that actually FOLDS needs the strip decomposition, which is what the
  // comment on validateActiveBendLines has always claimed. The decomposition slices the
  // part into vertical X-slabs at each bend's midpoint X, so a bend line that is not
  // vertical, or not full-length, becomes a phantom full-height boundary in the middle of
  // the part — and any hole straddling that phantom X was rejected as "crossing bend
  // lines" from tens of millimetres away. The orientation guard did not catch it because
  // it returns early at angle 0, which is the default: an inert crease mark skipped the
  // guard and then drove the orientation-sensitive decomposition anyway.
  const hasFoldingBend = bendLines.some(
    (_, index) => normalizeDxfBendAngleDeg(normalizedBendSettings?.[index]?.angleDeg, 0) !== 0
  );
  let foldBridges = [];
  if (bendLines.length && hasFoldingBend) {
    // Fold lines are built for the bends that actually FOLD. A bend left at 0 degrees is a
    // crease mark: it draws as a guide and must not cut the blank into faces.
    const foldLines = [];
    const guideOwners = [];
    bendLines.forEach((bendLine, index) => {
      const setting = normalizedBendSettings?.[index];
      const angleDeg = normalizeDxfBendAngleDeg(setting?.angleDeg, 0);
      if (angleDeg === 0) {
        guideOwners.push({ bendLine, foldIndex: -1 });
        return;
      }
      const foldLine = buildFoldLine({
        bendLine,
        angleRadians: bendAngleRadiansForSetting(setting),
        insideRadiusMm: toFiniteNumber(options?.bendInsideRadiusMm, 0),
        kFactor: clamp(toFiniteNumber(options?.bendKFactor, 0.5), 0.05, 0.95),
        halfThicknessMm: halfThickness
      });
      if (!foldLine) {
        throw new Error("DXF bend line length is too small for preview bending");
      }
      guideOwners.push({ bendLine, foldIndex: foldLines.length });
      foldLines.push(foldLine);
    });

    const { regions, adjacency } = decomposeFoldRegions(outerLoop, foldLines);
    assignHolesToRegions(regions, holeLoops, foldLines);
    const { placements, parents } = buildRegionPlacements(regions, foldLines, adjacency);

    strips = regions.map((region, index) => ({
      index,
      transformIndex: index,
      outerLoop: normalizeLoopWinding(region.outerLoop, { clockwise: true }),
      holeLoops: region.holeLoops.map((loop) => normalizeLoopWinding(loop, { clockwise: false })),
      region,
      foldLines
    }));
    transforms = placements;

    // One curved band per hinge, in the PARENT's frame, spanning the length the two faces
    // actually share along that fold.
    foldBridges = adjacency.map((edge) => {
      const [a, b] = edge.regions;
      const parentIsA = parents[b]?.region === a;
      const parentIndex = parentIsA ? a : b;
      const childIndex = parentIsA ? b : a;
      const foldLine = foldLines[edge.foldIndex];
      const childSide = regions[childIndex].sides
        .find((entry) => entry.foldIndex === edge.foldIndex)?.side || 1;
      const parentSpan = foldLineSpanForRegion(regions[parentIndex], foldLine);
      const childSpan = foldLineSpanForRegion(regions[childIndex], foldLine);
      if (!parentSpan || !childSpan) {
        return null;
      }
      return buildFoldBridgeGeometry({
        foldLine,
        side: childSide,
        span: {
          min: Math.max(parentSpan.min, childSpan.min),
          max: Math.min(parentSpan.max, childSpan.max)
        },
        halfThickness,
        parentMatrix: placements[parentIndex]
      });
    }).filter(Boolean);

    // Guides ride on the face that owns them, so a crease on a folded face folds with it.
    const guideY = guideElevationSign * (halfThickness + BEND_LINE_ELEVATION_MM);
    guideLineSegments = guideOwners.flatMap(({ bendLine, foldIndex }) => {
      const ownerIndex = regionIndexForGuide(regions, bendLine, foldIndex, adjacency, parents);
      const matrix = transforms[ownerIndex] || new Matrix4().identity();
      return [
        ...applyMatrixToPoint(matrix, [bendLine.start[0], guideY, bendLine.start[1]]),
        ...applyMatrixToPoint(matrix, [bendLine.end[0], guideY, bendLine.end[1]])
      ];
    });
  } else {
    strips = buildFlatStripDefinitions(loops);
    transforms = [new Matrix4().identity()];
    // Crease marks still draw, at their REAL endpoints. Emitting the flat plate without
    // them (as one reading of "skip the decomposition" would) would silently drop the bend
    // lines from every flat pattern that has them, which is the whole point of the layer.
    // Unfolded, the guides need no transform, so this is what buildSegmentTransforms
    // produces for the first bend with an identity base matrix.
    const guideY = guideElevationSign * (halfThickness + BEND_LINE_ELEVATION_MM);
    guideLineSegments = bendLines.flatMap((bendLine) => [
      bendLine.start[0], guideY, bendLine.start[1],
      bendLine.end[0], guideY, bendLine.end[1]
    ]);
  }

  const triangleVertices = [];
  const indices = [];
  const edgeVertices = [];
  const edgeIndices = [];

  for (const strip of strips) {
    const matrix = transforms[strip.transformIndex] || transforms[transforms.length - 1] || new Matrix4().identity();
    const outerVectors = strip.outerLoop.map(([x, y]) => new Vector2(x, y));
    const holeVectors = strip.holeLoops.map((loop) => loop.map(([x, y]) => new Vector2(x, y)));
    const faces = ShapeUtils.triangulateShape(outerVectors, holeVectors);
    const combinedLoops = outerVectors.concat(...holeVectors);

    for (const face of faces) {
      const a2 = combinedLoops[face[0]];
      const b2 = combinedLoops[face[1]];
      const c2 = combinedLoops[face[2]];
      appendTransformedTriangle(
        triangleVertices,
        indices,
        matrix,
        [a2.x, halfThickness, a2.y],
        [b2.x, halfThickness, b2.y],
        [c2.x, halfThickness, c2.y],
        true
      );
      appendTransformedTriangle(
        triangleVertices,
        indices,
        matrix,
        [a2.x, -halfThickness, a2.y],
        [b2.x, -halfThickness, b2.y],
        [c2.x, -halfThickness, c2.y],
        false
      );
    }

    // Only a fold's band edge is internal; a flat pattern's every edge is a real cut.
    const skipOuterEdge = strip.foldLines
      ? (start, end) => isFoldBandEdge(start, end, strip)
      : () => false;
    appendLoopSideFaces(triangleVertices, indices, matrix, strip.outerLoop, halfThickness, -halfThickness, skipOuterEdge);
    appendLoopEdgeSegments(edgeVertices, edgeIndices, matrix, strip.outerLoop, halfThickness, -halfThickness, skipOuterEdge);

    for (const holeLoop of strip.holeLoops) {
      appendLoopSideFaces(triangleVertices, indices, matrix, holeLoop, halfThickness, -halfThickness);
      appendLoopEdgeSegments(edgeVertices, edgeIndices, matrix, holeLoop, halfThickness, -halfThickness);
    }
  }
  for (const bridge of foldBridges) {
    for (const [a, b, c] of bridge.triangles) {
      appendTriangle(triangleVertices, indices, a, b, c);
    }
    for (const [a, b] of bridge.edges) {
      appendVertex(edgeVertices, a[0], a[1], a[2]);
      appendVertex(edgeVertices, b[0], b[1], b[2]);
      const index = (edgeVertices.length / 3) - 2;
      edgeIndices.push(index, index + 1);
    }
  }

  const triangleVertexCount = triangleVertices.length / 3;
  const combinedVertices = new Float32Array(triangleVertices.length + edgeVertices.length);
  combinedVertices.set(triangleVertices, 0);
  combinedVertices.set(edgeVertices, triangleVertices.length);

  const combinedEdgeIndices = new Uint32Array(edgeIndices.length);
  for (let index = 0; index < edgeIndices.length; index += 1) {
    combinedEdgeIndices[index] = edgeIndices[index] + triangleVertexCount;
  }

  const bounds = buildBounds(combinedVertices);
  return {
    format_version: "dxf-preview-mesh-v2",
    has_source_colors: false,
    bounds,
    vertex_count: combinedVertices.length / 3,
    triangle_count: indices.length / 3,
    edge_index_count: combinedEdgeIndices.length,
    vertices: combinedVertices,
    colors: new Float32Array(0),
    normals: new Float32Array(0),
    indices: new Uint32Array(indices),
    edge_indices: combinedEdgeIndices,
    guide_line_segments: new Float32Array(guideLineSegments),
    parts: []
  };
}
