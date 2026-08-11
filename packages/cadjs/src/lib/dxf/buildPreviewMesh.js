import { Matrix4, ShapeUtils, Vector2, Vector3 } from "three";

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

/** Only bends that are actually FOLDING need the banded strip decomposition, and that
 *  decomposition is X-slab based — so the vertical-line requirement applies to active
 *  bends, never to a flat pattern whose angled bend lines are just crease marks. (The
 *  viewer's boxed fold handles any orientation; it catches this error and falls back.) */
function validateActiveBendLines(bendLines, bendSettings) {
  bendLines.forEach((bendLine, index) => {
    const angleDeg = normalizeDxfBendAngleDeg(bendSettings?.[index]?.angleDeg, 0);
    if (angleDeg === 0) {
      return;
    }
    if (Math.abs(bendLine.start[0] - bendLine.end[0]) > BEND_LINE_AXIS_EPSILON_MM) {
      throw new Error("DXF 3D bend preview currently requires vertical bend lines");
    }
    if (Math.abs(bendLine.end[1] - bendLine.start[1]) <= GEOMETRY_EPSILON_MM) {
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

function clipEdgeAgainstMinX(start, end, minX) {
  const deltaX = end[0] - start[0];
  if (Math.abs(deltaX) <= GEOMETRY_EPSILON_MM) {
    return [minX, start[1]];
  }
  const t = (minX - start[0]) / deltaX;
  return [minX, start[1] + (end[1] - start[1]) * t];
}

function clipEdgeAgainstMaxX(start, end, maxX) {
  const deltaX = end[0] - start[0];
  if (Math.abs(deltaX) <= GEOMETRY_EPSILON_MM) {
    return [maxX, start[1]];
  }
  const t = (maxX - start[0]) / deltaX;
  return [maxX, start[1] + (end[1] - start[1]) * t];
}

function clipLoopAgainstMinX(loop, minX) {
  if (!loop.length) {
    return [];
  }
  const output = [];
  for (let index = 0; index < loop.length; index += 1) {
    const current = loop[index];
    const previous = loop[(index + loop.length - 1) % loop.length];
    const currentInside = current[0] >= minX - GEOMETRY_EPSILON_MM;
    const previousInside = previous[0] >= minX - GEOMETRY_EPSILON_MM;
    if (currentInside) {
      if (!previousInside) {
        output.push(clipEdgeAgainstMinX(previous, current, minX));
      }
      output.push(current);
    } else if (previousInside) {
      output.push(clipEdgeAgainstMinX(previous, current, minX));
    }
  }
  return removeConsecutiveDuplicates(output);
}

function clipLoopAgainstMaxX(loop, maxX) {
  if (!loop.length) {
    return [];
  }
  const output = [];
  for (let index = 0; index < loop.length; index += 1) {
    const current = loop[index];
    const previous = loop[(index + loop.length - 1) % loop.length];
    const currentInside = current[0] <= maxX + GEOMETRY_EPSILON_MM;
    const previousInside = previous[0] <= maxX + GEOMETRY_EPSILON_MM;
    if (currentInside) {
      if (!previousInside) {
        output.push(clipEdgeAgainstMaxX(previous, current, maxX));
      }
      output.push(current);
    } else if (previousInside) {
      output.push(clipEdgeAgainstMaxX(previous, current, maxX));
    }
  }
  return removeConsecutiveDuplicates(output);
}

function clipLoopToSlab(loop, leftX, rightX) {
  return clipLoopAgainstMaxX(clipLoopAgainstMinX(loop, leftX), rightX);
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

function holeClassificationForStrip(loop, leftX, rightX) {
  const bounds = loopBounds(loop);
  if (bounds.maxX <= leftX + GEOMETRY_EPSILON_MM || bounds.minX >= rightX - GEOMETRY_EPSILON_MM) {
    return "outside";
  }
  if (bounds.minX >= leftX - GEOMETRY_EPSILON_MM && bounds.maxX <= rightX + GEOMETRY_EPSILON_MM) {
    return "inside";
  }
  return "intersects";
}

function buildBendProfiles(outerBounds, bendLines, bendSettings, halfThickness, bendGeometry = null) {
  // Sheet-metal bend geometry the caller may pin: an explicit inside radius (mm) and a
  // K-factor placing the neutral axis within the thickness. The defaults reproduce the
  // historical visual bend: radius 0.6x thickness, neutral axis at mid-thickness (K=0.5).
  const requestedRadius = toFiniteNumber(bendGeometry?.insideRadiusMm, 0);
  const kFactor = clamp(toFiniteNumber(bendGeometry?.kFactor, 0.5), 0.05, 0.95);
  const profiles = bendLines.map((bendLine, index) => {
    const bendSetting = bendSettings[index] || {
      direction: DXF_BEND_DIRECTION.UP,
      angleDeg: DEFAULT_DXF_BEND_ANGLE_DEG
    };
    const angleRadians = bendAngleRadiansForSetting(bendSetting);
    const angleMagnitude = Math.abs(angleRadians);
    const insideRadius = requestedRadius > 0
      ? Math.max(requestedRadius, GEOMETRY_EPSILON_MM)
      : Math.max(halfThickness * 2 * VISUAL_BEND_INSIDE_RADIUS_RATIO, GEOMETRY_EPSILON_MM);
    const neutralRadius = insideRadius + kFactor * halfThickness * 2;
    const desiredHalfWidth = angleMagnitude > 1e-6 ? (neutralRadius * angleMagnitude) / 2 : 0;
    return {
      bendLine,
      angleRadians,
      insideRadius,
      neutralRadius,
      leftX: bendLine.x - desiredHalfWidth,
      rightX: bendLine.x + desiredHalfWidth
    };
  });

  for (let index = 0; index < profiles.length; index += 1) {
    const profile = profiles[index];
    profile.leftX = clamp(profile.leftX, outerBounds.minX, profile.bendLine.x);
    profile.rightX = clamp(profile.rightX, profile.bendLine.x, outerBounds.maxX);
  }

  for (let index = 0; index < profiles.length - 1; index += 1) {
    const current = profiles[index];
    const next = profiles[index + 1];
    const midpoint = (current.bendLine.x + next.bendLine.x) / 2;
    current.rightX = Math.min(current.rightX, midpoint);
    next.leftX = Math.max(next.leftX, midpoint);
  }

  return profiles.map((profile) => {
    const flatWidth = Math.max(profile.rightX - profile.leftX, 0);
    const angleMagnitude = Math.abs(profile.angleRadians);
    const neutralRadius = angleMagnitude > 1e-6 && flatWidth > GEOMETRY_EPSILON_MM
      ? flatWidth / angleMagnitude
      : profile.neutralRadius;
    return {
      ...profile,
      flatWidth,
      neutralRadius,
      insideRadius: Math.max(neutralRadius - kFactor * halfThickness * 2, GEOMETRY_EPSILON_MM)
    };
  });
}

function ensureHolesDoNotCrossBendBands(holeLoops, bendProfiles) {
  for (const holeLoop of holeLoops) {
    for (const bendProfile of bendProfiles) {
      if (bendProfile.rightX - bendProfile.leftX <= GEOMETRY_EPSILON_MM) {
        continue;
      }
      if (holeClassificationForStrip(holeLoop, bendProfile.leftX, bendProfile.rightX) !== "outside") {
        throw new Error("DXF 3D bend preview does not support holes crossing bend radius bands");
      }
    }
  }
}

function buildStripDefinitions(outerLoop, holeLoops, bendProfiles) {
  const outerBounds = loopBounds(outerLoop);
  ensureHolesDoNotCrossBendBands(holeLoops, bendProfiles);

  const strips = [];
  let leftX = outerBounds.minX;
  for (let index = 0; index <= bendProfiles.length; index += 1) {
    const bendProfile = bendProfiles[index] || null;
    const rightX = bendProfile ? bendProfile.leftX : outerBounds.maxX;
    if (rightX - leftX <= GEOMETRY_EPSILON_MM) {
      if (bendProfile) {
        leftX = Math.max(leftX, bendProfile.rightX);
      }
      continue;
    }
    const clippedOuter = normalizeLoopWinding(clipLoopToSlab(outerLoop, leftX, rightX), { clockwise: true });
    if (clippedOuter.length < 3) {
      if (bendProfile) {
        leftX = Math.max(leftX, bendProfile.rightX);
      }
      continue;
    }

    const stripHoles = [];
    for (const holeLoop of holeLoops) {
      const classification = holeClassificationForStrip(holeLoop, leftX, rightX);
      if (classification === "inside") {
        stripHoles.push(normalizeLoopWinding(holeLoop, { clockwise: false }));
        continue;
      }
      if (classification === "intersects") {
        throw new Error("DXF 3D bend preview does not support holes crossing bend lines");
      }
    }

    strips.push({
      index: strips.length,
      transformIndex: index,
      leftX,
      rightX,
      outerLoop: clippedOuter,
      holeLoops: stripHoles,
      isLeftExterior: approxEqual(leftX, outerBounds.minX),
      isRightExterior: approxEqual(rightX, outerBounds.maxX)
    });

    if (bendProfile) {
      leftX = Math.max(leftX, bendProfile.rightX);
    }
  }

  if (!strips.length) {
    throw new Error("DXF preview could not build bendable strip geometry");
  }
  return {
    strips,
    bounds: outerBounds
  };
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

function isInternalStripBoundaryEdge(start, end, strip) {
  if (!approxEqual(start[0], end[0], BEND_LINE_AXIS_EPSILON_MM)) {
    return false;
  }
  if (approxEqual(start[0], strip.leftX, BEND_LINE_AXIS_EPSILON_MM) && !strip.isLeftExterior) {
    return true;
  }
  if (approxEqual(start[0], strip.rightX, BEND_LINE_AXIS_EPSILON_MM) && !strip.isRightExterior) {
    return true;
  }
  return false;
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

function buildRotationAroundAxisMatrix(axisStart, axisEnd, angleRadians) {
  if (Math.abs(angleRadians) <= 1e-9) {
    return new Matrix4().identity();
  }
  const start = new Vector3(...axisStart);
  const end = new Vector3(...axisEnd);
  const axisVector = end.clone().sub(start);
  if (axisVector.lengthSq() <= 1e-12) {
    return new Matrix4().identity();
  }
  axisVector.normalize();
  const translateToOrigin = new Matrix4().makeTranslation(-start.x, -start.y, -start.z);
  const rotate = new Matrix4().makeRotationAxis(axisVector, angleRadians);
  const translateBack = new Matrix4().makeTranslation(start.x, start.y, start.z);
  return translateBack.multiply(rotate).multiply(translateToOrigin);
}

function buildBendContinuationMatrix(bendProfile) {
  const angleRadians = bendProfile.angleRadians;
  const angleMagnitude = Math.abs(angleRadians);
  if (angleMagnitude <= 1e-9 || bendProfile.flatWidth <= GEOMETRY_EPSILON_MM) {
    return new Matrix4().identity();
  }
  const bendSign = angleRadians < 0 ? -1 : 1;
  const endX = bendProfile.leftX + bendProfile.neutralRadius * Math.sin(angleMagnitude);
  const endY = bendSign * bendProfile.neutralRadius * (1 - Math.cos(angleMagnitude));
  const translateToTangent = new Matrix4().makeTranslation(-bendProfile.rightX, 0, 0);
  const rotate = new Matrix4().makeRotationZ(angleRadians);
  const translateToEnd = new Matrix4().makeTranslation(endX, endY, 0);
  return translateToEnd.multiply(rotate).multiply(translateToTangent);
}

function buildSegmentTransforms(bendProfiles, halfThickness, guideElevationSign = 1) {
  const transforms = [new Matrix4().identity()];
  const bendTransforms = [];
  const guideLineSegments = [];
  // Which face the bend guides hover over. The guides are one-sided (the solid is
  // symmetric, they are not): a consumer whose axis convention maps this mesher's +Y to
  // its own "down" (the CAD viewer's Z-up mapping does) asks for -1 so the guides land on
  // the face the user is looking at instead of under the sheet.
  const guideY = guideElevationSign * (halfThickness + BEND_LINE_ELEVATION_MM);
  let currentMatrix = new Matrix4().identity();

  for (const bendProfile of bendProfiles) {
    const bendLine = bendProfile.bendLine;
    const baseMatrix = currentMatrix.clone();
    guideLineSegments.push(
      ...applyMatrixToPoint(baseMatrix, [bendLine.start[0], guideY, bendLine.start[1]]),
      ...applyMatrixToPoint(baseMatrix, [bendLine.end[0], guideY, bendLine.end[1]])
    );

    bendTransforms.push({
      bendProfile,
      matrix: baseMatrix
    });
    if (bendProfile.flatWidth > GEOMETRY_EPSILON_MM) {
      currentMatrix = baseMatrix.clone().multiply(buildBendContinuationMatrix(bendProfile));
    } else {
      const axisStart = applyMatrixToPoint(baseMatrix, [bendLine.start[0], 0, bendLine.start[1]]);
      const axisEnd = applyMatrixToPoint(baseMatrix, [bendLine.end[0], 0, bendLine.end[1]]);
      const bendMatrix = buildRotationAroundAxisMatrix(axisStart, axisEnd, bendProfile.angleRadians);
      currentMatrix = bendMatrix.clone().multiply(baseMatrix);
    }
    transforms.push(currentMatrix.clone());
  }

  return {
    transforms,
    bendTransforms,
    guideLineSegments
  };
}

function mergeIntervals(intervals) {
  const sortedIntervals = intervals
    .map(([min, max]) => [Math.min(min, max), Math.max(min, max)])
    .filter(([min, max]) => max - min > GEOMETRY_EPSILON_MM)
    .sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const interval of sortedIntervals) {
    const previous = merged[merged.length - 1];
    if (previous && interval[0] <= previous[1] + GEOMETRY_EPSILON_MM) {
      previous[1] = Math.max(previous[1], interval[1]);
      continue;
    }
    merged.push([...interval]);
  }
  return merged;
}

function collectBoundaryIntervals(loop, boundaryX) {
  const intervals = [];
  for (let index = 0; index < loop.length; index += 1) {
    const start = loop[index];
    const end = loop[(index + 1) % loop.length];
    if (
      approxEqual(start[0], boundaryX, BEND_LINE_AXIS_EPSILON_MM) &&
      approxEqual(end[0], boundaryX, BEND_LINE_AXIS_EPSILON_MM) &&
      Math.abs(end[1] - start[1]) > GEOMETRY_EPSILON_MM
    ) {
      intervals.push([start[1], end[1]]);
    }
  }
  return intervals;
}

function intersectIntervalSets(leftIntervals, rightIntervals) {
  const intersections = [];
  for (const left of leftIntervals) {
    for (const right of rightIntervals) {
      const min = Math.max(left[0], right[0]);
      const max = Math.min(left[1], right[1]);
      if (max - min > GEOMETRY_EPSILON_MM) {
        intersections.push([min, max]);
      }
    }
  }
  return mergeIntervals(intersections);
}

function collectBendIntervals(strips, bendProfile) {
  const leftIntervals = [];
  const rightIntervals = [];
  for (const strip of strips) {
    if (approxEqual(strip.rightX, bendProfile.leftX, BEND_LINE_AXIS_EPSILON_MM) && !strip.isRightExterior) {
      leftIntervals.push(...collectBoundaryIntervals(strip.outerLoop, bendProfile.leftX));
    }
    if (approxEqual(strip.leftX, bendProfile.rightX, BEND_LINE_AXIS_EPSILON_MM) && !strip.isLeftExterior) {
      rightIntervals.push(...collectBoundaryIntervals(strip.outerLoop, bendProfile.rightX));
    }
  }
  const mergedLeft = mergeIntervals(leftIntervals);
  const mergedRight = mergeIntervals(rightIntervals);
  if (mergedLeft.length && mergedRight.length) {
    return intersectIntervalSets(mergedLeft, mergedRight);
  }
  if (mergedLeft.length) {
    return mergedLeft;
  }
  if (mergedRight.length) {
    return mergedRight;
  }
  return [[bendProfile.bendLine.yMin, bendProfile.bendLine.yMax]].filter(([min, max]) => max - min > GEOMETRY_EPSILON_MM);
}

function bendBridgeSegmentCount(radius, angleRadians) {
  return clamp(
    sampleCountForSweep(Math.max(radius, GEOMETRY_EPSILON_MM), angleRadians),
    MIN_BEND_BRIDGE_SEGMENTS,
    MAX_BEND_BRIDGE_SEGMENTS
  );
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

function appendBendBridgeGeometry(vertices, indices, edgeVertices, edgeIndices, strips, bendTransforms, halfThickness) {
  for (const bendTransform of bendTransforms) {
    const intervals = collectBendIntervals(strips, bendTransform.bendProfile);
    for (const interval of intervals) {
      appendBendBridgeInterval(vertices, indices, edgeVertices, edgeIndices, bendTransform, interval, halfThickness);
    }
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
  let bendTransforms;
  let guideLineSegments;
  let transforms;
  if (bendLines.length) {
    const outerBounds = loopBounds(outerLoop);
    const bendProfiles = buildBendProfiles(outerBounds, bendLines, normalizedBendSettings, halfThickness, {
      insideRadiusMm: options?.bendInsideRadiusMm,
      kFactor: options?.bendKFactor
    });
    ({ strips } = buildStripDefinitions(outerLoop, holeLoops, bendProfiles));
    ({ transforms, bendTransforms, guideLineSegments } = buildSegmentTransforms(bendProfiles, halfThickness, guideElevationSign));
  } else {
    strips = buildFlatStripDefinitions(loops);
    transforms = [new Matrix4().identity()];
    bendTransforms = [];
    guideLineSegments = [];
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

    const skipOuterEdge = (start, end) => isInternalStripBoundaryEdge(start, end, strip);
    appendLoopSideFaces(triangleVertices, indices, matrix, strip.outerLoop, halfThickness, -halfThickness, skipOuterEdge);
    appendLoopEdgeSegments(edgeVertices, edgeIndices, matrix, strip.outerLoop, halfThickness, -halfThickness, skipOuterEdge);

    for (const holeLoop of strip.holeLoops) {
      appendLoopSideFaces(triangleVertices, indices, matrix, holeLoop, halfThickness, -halfThickness);
      appendLoopEdgeSegments(edgeVertices, edgeIndices, matrix, holeLoop, halfThickness, -halfThickness);
    }
  }
  appendBendBridgeGeometry(
    triangleVertices,
    indices,
    edgeVertices,
    edgeIndices,
    strips,
    bendTransforms,
    halfThickness
  );

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
