import { DRAWING_TOOL } from "./drawingTools.js";
import {
  drawingPointToPixels,
  getDrawingStrokePoints,
  getFillStrokePoints,
  isClosedDrawingStroke,
  isFillBoundaryStroke,
  isFillStroke,
  isSurfaceLineStroke,
  pointInPolygon2d
} from "./drawingGeometry.js";

export const DRAWING_STROKE_COLOR = "#ef4444";
export const DRAWING_STROKE_HALO = "rgba(255, 255, 255, 0.94)";
export const DRAWING_STROKE_WIDTH = 4;
export const DRAWING_STROKE_HALO_WIDTH = 8;
export const DRAWING_ARROW_HEAD_LENGTH = 18;
export const DRAWING_MIN_POINT_DISTANCE_PX = 2.5;
export const DRAWING_MIN_STROKE_LENGTH_PX = 4;
export const DRAWING_ERASE_THRESHOLD_PX = 16;
export const DRAWING_FILL_COLOR = "rgba(239, 68, 68, 0.22)";
export const DRAWING_GUESSED_FILL_COLOR = "rgba(239, 68, 68, 0.16)";
export const DRAWING_FILL_ANALYSIS_MAX_DIMENSION = 420;
export const DRAWING_FILL_ANALYSIS_MIN_DIMENSION = 96;
export const DRAWING_FILL_CONNECT_GAP_PX = 28;
export const DRAWING_FILL_RAY_COUNT = 72;
export const DRAWING_FILL_MIN_REGION_PIXELS = 56;
export const DRAWING_FILL_MAX_REGION_RATIO = 0.92;
export const SURFACE_LINE_COLOR = "#ef4444";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function pointsEqual2d(a, b, epsilon = 1e-4) {
  return Math.abs(a[0] - b[0]) <= epsilon && Math.abs(a[1] - b[1]) <= epsilon;
}

export function maxDrawingStrokeOrdinal(strokes) {
  let maxOrdinal = 0;
  for (const stroke of Array.isArray(strokes) ? strokes : []) {
    const match = /^stroke-(\d+)$/.exec(String(stroke?.id || ""));
    if (!match) {
      continue;
    }
    const nextOrdinal = Number(match[1]);
    if (Number.isFinite(nextOrdinal) && nextOrdinal > maxOrdinal) {
      maxOrdinal = nextOrdinal;
    }
  }
  return maxOrdinal;
}

export function buildRectanglePixelCorners(start, end) {
  return [
    [start[0], start[1]],
    [end[0], start[1]],
    [end[0], end[1]],
    [start[0], end[1]]
  ];
}

export function buildCirclePixelPolygon(center, edge, segmentCount = 56) {
  const radius = Math.hypot(edge[0] - center[0], edge[1] - center[1]);
  if (radius < 1e-4) {
    return [center];
  }
  const segments = Math.max(segmentCount, 12);
  const points = [];
  for (let index = 0; index <= segments; index += 1) {
    const angle = (index / segments) * Math.PI * 2;
    points.push([
      center[0] + Math.cos(angle) * radius,
      center[1] + Math.sin(angle) * radius
    ]);
  }
  return points;
}

export function getDrawingBoundaryPixelPoints(stroke, width, height) {
  const pixelPoints = getDrawingStrokePoints(stroke).map((point) => drawingPointToPixels(point, width, height));
  if (pixelPoints.length < 2) {
    return pixelPoints;
  }
  if (stroke.tool === DRAWING_TOOL.RECTANGLE) {
    const corners = buildRectanglePixelCorners(pixelPoints[0], pixelPoints[pixelPoints.length - 1]);
    return [...corners, corners[0]];
  }
  if (stroke.tool === DRAWING_TOOL.CIRCLE) {
    return buildCirclePixelPolygon(pixelPoints[0], pixelPoints[pixelPoints.length - 1]);
  }
  return pixelPoints;
}

function drawArrowHead(context, start, end, lineWidth) {
  const dx = end[0] - start[0];
  const dy = end[1] - start[1];
  const lengthPx = Math.hypot(dx, dy);
  if (lengthPx < 1) {
    return;
  }
  const ux = dx / lengthPx;
  const uy = dy / lengthPx;
  const angle = Math.PI / 7;
  const headLength = Math.max(DRAWING_ARROW_HEAD_LENGTH, lineWidth * 3.25);
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const left = [
    end[0] - headLength * (ux * cos - uy * sin),
    end[1] - headLength * (uy * cos + ux * sin)
  ];
  const right = [
    end[0] - headLength * (ux * cos + uy * sin),
    end[1] - headLength * (uy * cos - ux * sin)
  ];

  context.beginPath();
  context.moveTo(end[0], end[1]);
  context.lineTo(left[0], left[1]);
  context.moveTo(end[0], end[1]);
  context.lineTo(right[0], right[1]);
  context.stroke();
}

function drawPointDot(context, point, lineWidth) {
  context.beginPath();
  context.arc(point[0], point[1], lineWidth * 0.65, 0, Math.PI * 2);
  context.fill();
}

function drawPolylineStroke(context, pixelPoints) {
  context.beginPath();
  pixelPoints.forEach((point, index) => {
    if (index === 0) {
      context.moveTo(point[0], point[1]);
      return;
    }
    context.lineTo(point[0], point[1]);
  });
  context.stroke();
}

function drawRectangleStroke(context, start, end) {
  const x = Math.min(start[0], end[0]);
  const y = Math.min(start[1], end[1]);
  const width = Math.abs(end[0] - start[0]);
  const height = Math.abs(end[1] - start[1]);
  context.strokeRect(x, y, width, height);
}

function drawCircleStroke(context, center, edge) {
  const radius = Math.hypot(edge[0] - center[0], edge[1] - center[1]);
  context.beginPath();
  context.arc(center[0], center[1], radius, 0, Math.PI * 2);
  context.stroke();
}

function drawFillStroke(context, stroke, width, height, { color, alpha = 1 }) {
  const points = getFillStrokePoints(stroke);
  if (points.length < 3) {
    return;
  }

  const pixelPoints = points.map((point) => drawingPointToPixels(point, width, height));
  context.save();
  context.globalAlpha = alpha;
  context.fillStyle = color;
  context.beginPath();
  pixelPoints.forEach((point, index) => {
    if (index === 0) {
      context.moveTo(point[0], point[1]);
      return;
    }
    context.lineTo(point[0], point[1]);
  });
  context.closePath();
  context.fill();
  context.restore();
}

function drawLineStroke(context, stroke, width, height, { color, lineWidth, alpha = 1 }) {
  if (isFillStroke(stroke)) {
    return;
  }
  const points = getDrawingStrokePoints(stroke);
  if (!points.length) {
    return;
  }

  const pixelPoints = points.map((point) => drawingPointToPixels(point, width, height));

  context.save();
  context.globalAlpha = alpha;
  context.strokeStyle = color;
  context.fillStyle = color;
  context.lineCap = "round";
  context.lineJoin = "round";
  context.lineWidth = lineWidth;

  if (pixelPoints.length === 1) {
    drawPointDot(context, pixelPoints[0], lineWidth);
    context.restore();
    return;
  }

  if (stroke.tool === DRAWING_TOOL.RECTANGLE) {
    drawRectangleStroke(context, pixelPoints[0], pixelPoints[pixelPoints.length - 1]);
    context.restore();
    return;
  }

  if (stroke.tool === DRAWING_TOOL.CIRCLE) {
    drawCircleStroke(context, pixelPoints[0], pixelPoints[pixelPoints.length - 1]);
    context.restore();
    return;
  }

  drawPolylineStroke(context, pixelPoints);

  if (stroke.tool === DRAWING_TOOL.ARROW || stroke.tool === DRAWING_TOOL.DOUBLE_ARROW) {
    drawArrowHead(context, pixelPoints[pixelPoints.length - 2], pixelPoints[pixelPoints.length - 1], lineWidth);
  }
  if (stroke.tool === DRAWING_TOOL.DOUBLE_ARROW) {
    drawArrowHead(context, pixelPoints[1], pixelPoints[0], lineWidth);
  }

  context.restore();
}

function createOffscreenCanvas(width, height) {
  if (typeof OffscreenCanvas !== "undefined") {
    return new OffscreenCanvas(width, height);
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function getOpenBoundaryEndpoints(stroke, width, height) {
  if (!isFillBoundaryStroke(stroke) || isClosedDrawingStroke(stroke)) {
    return [];
  }
  const pixelPoints = getDrawingBoundaryPixelPoints(stroke, width, height);
  if (pixelPoints.length < 2) {
    return [];
  }
  const allowSelfConnect = stroke?.tool === DRAWING_TOOL.FREEHAND && pixelPoints.length > 2;
  return [
    {
      strokeId: String(stroke?.id || ""),
      point: pixelPoints[0],
      allowSelfConnect
    },
    {
      strokeId: String(stroke?.id || ""),
      point: pixelPoints[pixelPoints.length - 1],
      allowSelfConnect
    }
  ];
}

export function pairNearbyBoundaryEndpoints(endpoints, maxDistance) {
  if (!Array.isArray(endpoints) || endpoints.length < 2 || maxDistance <= 0) {
    return [];
  }
  const candidates = [];
  for (let leftIndex = 0; leftIndex < endpoints.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < endpoints.length; rightIndex += 1) {
      const left = endpoints[leftIndex];
      const right = endpoints[rightIndex];
      const sameStroke = left.strokeId && left.strokeId === right.strokeId;
      if (sameStroke && !(left.allowSelfConnect && right.allowSelfConnect)) {
        continue;
      }
      const distance = Math.hypot(left.point[0] - right.point[0], left.point[1] - right.point[1]);
      if (distance <= maxDistance) {
        candidates.push({ leftIndex, rightIndex, distance });
      }
    }
  }
  candidates.sort((left, right) => left.distance - right.distance);
  const used = new Set();
  const pairs = [];
  for (const candidate of candidates) {
    if (used.has(candidate.leftIndex) || used.has(candidate.rightIndex)) {
      continue;
    }
    used.add(candidate.leftIndex);
    used.add(candidate.rightIndex);
    pairs.push([
      endpoints[candidate.leftIndex].point,
      endpoints[candidate.rightIndex].point
    ]);
  }
  return pairs;
}

export function buildBoundaryMaskFromStrokes(strokes, width, height, { gapPx = 0, lineWidth = DRAWING_STROKE_WIDTH } = {}) {
  const canvas = createOffscreenCanvas(width, height);
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    return null;
  }

  context.clearRect(0, 0, width, height);
  const boundaryStrokes = Array.isArray(strokes) ? strokes.filter(isFillBoundaryStroke) : [];
  for (const stroke of boundaryStrokes) {
    drawLineStroke(context, stroke, width, height, {
      color: "#000000",
      lineWidth,
      alpha: 1
    });
  }

  if (gapPx > 0) {
    const connectors = pairNearbyBoundaryEndpoints(
      boundaryStrokes.flatMap((stroke) => getOpenBoundaryEndpoints(stroke, width, height)),
      Math.max(gapPx, lineWidth * 1.15)
    );
    if (connectors.length) {
      context.save();
      context.strokeStyle = "#000000";
      context.lineWidth = lineWidth;
      context.lineCap = "round";
      for (const [start, end] of connectors) {
        context.beginPath();
        context.moveTo(start[0], start[1]);
        context.lineTo(end[0], end[1]);
        context.stroke();
      }
      context.restore();
    }
  }

  const { data } = context.getImageData(0, 0, width, height);
  const mask = new Uint8Array(width * height);
  for (let index = 0; index < mask.length; index += 1) {
    mask[index] = data[index * 4 + 3] > 20 ? 1 : 0;
  }
  return mask;
}

export function findNearestOpenSeed(boundaryMask, width, height, seedX, seedY, maxRadius = 5) {
  const x = clamp(Math.round(seedX), 0, width - 1);
  const y = clamp(Math.round(seedY), 0, height - 1);
  for (let radius = 0; radius <= maxRadius; radius += 1) {
    let best = null;
    let bestDistance = Infinity;
    for (let dy = -radius; dy <= radius; dy += 1) {
      for (let dx = -radius; dx <= radius; dx += 1) {
        const px = x + dx;
        const py = y + dy;
        if (px < 0 || py < 0 || px >= width || py >= height) {
          continue;
        }
        if (boundaryMask[py * width + px]) {
          continue;
        }
        const distance = Math.hypot(dx, dy);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = [px, py];
        }
      }
    }
    if (best) {
      return best;
    }
  }
  return null;
}

export function floodFillInterior(boundaryMask, width, height, seedPoint) {
  const start = findNearestOpenSeed(boundaryMask, width, height, seedPoint[0], seedPoint[1]);
  if (!start) {
    return null;
  }

  const fillMask = new Uint8Array(width * height);
  const queue = new Int32Array(width * height);
  let head = 0;
  let tail = 0;
  const startIndex = start[1] * width + start[0];
  queue[tail++] = startIndex;
  fillMask[startIndex] = 1;
  let area = 0;
  let touchesEdge = false;

  while (head < tail) {
    const index = queue[head++];
    area += 1;
    const x = index % width;
    const y = (index / width) | 0;
    if (x === 0 || y === 0 || x === width - 1 || y === height - 1) {
      touchesEdge = true;
    }

    if (x > 0) {
      const leftIndex = index - 1;
      if (!boundaryMask[leftIndex] && !fillMask[leftIndex]) {
        fillMask[leftIndex] = 1;
        queue[tail++] = leftIndex;
      }
    }
    if (x + 1 < width) {
      const rightIndex = index + 1;
      if (!boundaryMask[rightIndex] && !fillMask[rightIndex]) {
        fillMask[rightIndex] = 1;
        queue[tail++] = rightIndex;
      }
    }
    if (y > 0) {
      const upIndex = index - width;
      if (!boundaryMask[upIndex] && !fillMask[upIndex]) {
        fillMask[upIndex] = 1;
        queue[tail++] = upIndex;
      }
    }
    if (y + 1 < height) {
      const downIndex = index + width;
      if (!boundaryMask[downIndex] && !fillMask[downIndex]) {
        fillMask[downIndex] = 1;
        queue[tail++] = downIndex;
      }
    }
  }

  return {
    mask: fillMask,
    area,
    touchesEdge,
    seed: start
  };
}

function polygonArea2d(points) {
  let area = 0;
  for (let index = 0, previous = points.length - 1; index < points.length; previous = index, index += 1) {
    area += points[previous][0] * points[index][1] - points[index][0] * points[previous][1];
  }
  return area / 2;
}

function removeDuplicatePolygonPoints(points) {
  const next = [];
  for (const point of points) {
    if (!next.length || !pointsEqual2d(next[next.length - 1], point)) {
      next.push(point);
    }
  }
  if (next.length > 1 && pointsEqual2d(next[0], next[next.length - 1])) {
    next.pop();
  }
  return next;
}

function removeCollinearPolygonPoints(points) {
  const loop = removeDuplicatePolygonPoints(points);
  if (loop.length < 3) {
    return loop;
  }
  const next = [];
  for (let index = 0; index < loop.length; index += 1) {
    const previous = loop[(index + loop.length - 1) % loop.length];
    const current = loop[index];
    const following = loop[(index + 1) % loop.length];
    const cross =
      (current[0] - previous[0]) * (following[1] - current[1]) -
      (current[1] - previous[1]) * (following[0] - current[0]);
    if (Math.abs(cross) > 1e-4) {
      next.push(current);
    }
  }
  return next.length >= 3 ? next : loop;
}

function downsamplePolygon(points, maxPoints = 160) {
  if (points.length <= maxPoints) {
    return points;
  }
  const step = points.length / maxPoints;
  const next = [];
  let cursor = 0;
  for (let index = 0; index < maxPoints; index += 1) {
    next.push(points[Math.floor(cursor) % points.length]);
    cursor += step;
  }
  return removeDuplicatePolygonPoints(next);
}

function pointKey(point) {
  return `${point[0]},${point[1]}`;
}

export function traceMaskLoops(mask, width, height) {
  const segments = [];
  const adjacency = new Map();
  const addSegment = (start, end) => {
    const index = segments.length;
    segments.push([start, end]);
    const key = pointKey(start);
    const entries = adjacency.get(key);
    if (entries) {
      entries.push(index);
      return;
    }
    adjacency.set(key, [index]);
  };

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (!mask[y * width + x]) {
        continue;
      }
      if (y === 0 || !mask[(y - 1) * width + x]) {
        addSegment([x, y], [x + 1, y]);
      }
      if (x === width - 1 || !mask[y * width + x + 1]) {
        addSegment([x + 1, y], [x + 1, y + 1]);
      }
      if (y === height - 1 || !mask[(y + 1) * width + x]) {
        addSegment([x + 1, y + 1], [x, y + 1]);
      }
      if (x === 0 || !mask[y * width + x - 1]) {
        addSegment([x, y + 1], [x, y]);
      }
    }
  }

  const used = new Uint8Array(segments.length);
  const loops = [];
  for (let index = 0; index < segments.length; index += 1) {
    if (used[index]) {
      continue;
    }
    const loop = [];
    let currentIndex = index;
    let guard = 0;
    while (currentIndex !== -1 && !used[currentIndex] && guard < segments.length + 4) {
      used[currentIndex] = 1;
      const [start, end] = segments[currentIndex];
      if (!loop.length) {
        loop.push(start);
      }
      loop.push(end);
      if (pointsEqual2d(end, loop[0])) {
        break;
      }
      const nextCandidates = adjacency.get(pointKey(end)) || [];
      currentIndex = nextCandidates.find((candidateIndex) => !used[candidateIndex]) ?? -1;
      guard += 1;
    }
    if (loop.length >= 4 && pointsEqual2d(loop[0], loop[loop.length - 1])) {
      const normalizedLoop = removeCollinearPolygonPoints(loop.slice(0, -1));
      if (normalizedLoop.length >= 3) {
        loops.push(normalizedLoop);
      }
    }
  }
  return loops;
}

export function normalizePolygonPoints(points, width, height) {
  return points.map((point) => ({
    x: clamp(point[0] / width, 0, 1),
    y: clamp(point[1] / height, 0, 1)
  }));
}

export function buildPolygonFromFilledMask(mask, width, height, seedPoint) {
  const loops = traceMaskLoops(mask, width, height);
  if (!loops.length) {
    return null;
  }
  const seed = [seedPoint[0] + 0.5, seedPoint[1] + 0.5];
  const containingLoops = loops.filter((loop) => pointInPolygon2d(seed, loop));
  const sourceLoops = containingLoops.length ? containingLoops : loops;
  const chosen = sourceLoops.reduce((best, current) => {
    if (!best) {
      return current;
    }
    return Math.abs(polygonArea2d(current)) > Math.abs(polygonArea2d(best)) ? current : best;
  }, null);
  if (!chosen) {
    return null;
  }
  const simplified = downsamplePolygon(removeCollinearPolygonPoints(chosen));
  return simplified.length >= 3 ? normalizePolygonPoints(simplified, width, height) : null;
}

function findNearestValidDistance(distances, index, direction) {
  for (let offset = 1; offset < distances.length; offset += 1) {
    const nextIndex = (index + direction * offset + distances.length) % distances.length;
    if (Number.isFinite(distances[nextIndex])) {
      return {
        value: distances[nextIndex],
        offset
      };
    }
  }
  return null;
}

export function buildGuessedFillPolygon(boundaryMask, width, height, seedPoint) {
  const start = findNearestOpenSeed(boundaryMask, width, height, seedPoint[0], seedPoint[1]);
  if (!start) {
    return null;
  }
  const maxDistance = Math.hypot(width, height);
  const distances = Array.from({ length: DRAWING_FILL_RAY_COUNT }, () => null);

  for (let index = 0; index < DRAWING_FILL_RAY_COUNT; index += 1) {
    const angle = (index / DRAWING_FILL_RAY_COUNT) * Math.PI * 2;
    const dx = Math.cos(angle);
    const dy = Math.sin(angle);
    for (let distance = 1; distance < maxDistance; distance += 1) {
      const x = Math.round(start[0] + dx * distance);
      const y = Math.round(start[1] + dy * distance);
      if (x < 0 || y < 0 || x >= width || y >= height) {
        break;
      }
      if (boundaryMask[y * width + x]) {
        distances[index] = Math.max(distance - 1.5, 1);
        break;
      }
    }
  }

  const validDistances = distances.filter(Number.isFinite);
  if (validDistances.length < Math.max(12, Math.floor(DRAWING_FILL_RAY_COUNT / 4))) {
    return null;
  }

  const orderedDistances = [...validDistances].sort((left, right) => left - right);
  const medianDistance = orderedDistances[Math.floor(orderedDistances.length / 2)] || 1;
  const resolvedDistances = distances.map((value, index) => {
    if (Number.isFinite(value)) {
      return value;
    }
    const previous = findNearestValidDistance(distances, index, -1);
    const next = findNearestValidDistance(distances, index, 1);
    if (previous && next) {
      const total = previous.offset + next.offset;
      return (previous.value * next.offset + next.value * previous.offset) / Math.max(total, 1);
    }
    if (previous) {
      return previous.value;
    }
    if (next) {
      return next.value;
    }
    return medianDistance;
  });

  let smoothedDistances = resolvedDistances;
  for (let pass = 0; pass < 2; pass += 1) {
    smoothedDistances = smoothedDistances.map((value, index) => {
      const previous = smoothedDistances[(index + smoothedDistances.length - 1) % smoothedDistances.length];
      const next = smoothedDistances[(index + 1) % smoothedDistances.length];
      return (previous + value * 2 + next) / 4;
    });
  }

  const polygon = smoothedDistances.map((distance, index) => {
    const angle = (index / DRAWING_FILL_RAY_COUNT) * Math.PI * 2;
    return [
      clamp(start[0] + Math.cos(angle) * distance, 0, width),
      clamp(start[1] + Math.sin(angle) * distance, 0, height)
    ];
  });
  const simplified = downsamplePolygon(removeCollinearPolygonPoints(polygon), DRAWING_FILL_RAY_COUNT);
  if (simplified.length < 3) {
    return null;
  }
  const area = Math.abs(polygonArea2d(simplified));
  if (area < DRAWING_FILL_MIN_REGION_PIXELS || area > width * height * DRAWING_FILL_MAX_REGION_RATIO) {
    return null;
  }
  return normalizePolygonPoints(simplified, width, height);
}

export function buildFillStrokeAtPoint(point, strokes, canvas) {
  const boundaryStrokes = Array.isArray(strokes) ? strokes.filter(isFillBoundaryStroke) : [];
  if (!boundaryStrokes.length) {
    return null;
  }

  const canvasWidth = canvas.width || 1;
  const canvasHeight = canvas.height || 1;
  const maxCanvasDimension = Math.max(canvasWidth, canvasHeight, 1);
  const analysisScale = Math.min(1, DRAWING_FILL_ANALYSIS_MAX_DIMENSION / maxCanvasDimension);
  const analysisWidth = Math.max(DRAWING_FILL_ANALYSIS_MIN_DIMENSION, Math.round(canvasWidth * analysisScale));
  const analysisHeight = Math.max(DRAWING_FILL_ANALYSIS_MIN_DIMENSION, Math.round(canvasHeight * analysisScale));
  const seedPoint = [point.x * (analysisWidth - 1), point.y * (analysisHeight - 1)];
  const lineWidth = Math.max(3, DRAWING_STROKE_WIDTH * analysisScale + 3);
  const gapStrategies = [
    { gapPx: 0, guessed: false },
    { gapPx: DRAWING_FILL_CONNECT_GAP_PX * 0.45 * analysisScale, guessed: true },
    { gapPx: DRAWING_FILL_CONNECT_GAP_PX * analysisScale, guessed: true }
  ];

  for (const strategy of gapStrategies) {
    const boundaryMask = buildBoundaryMaskFromStrokes(boundaryStrokes, analysisWidth, analysisHeight, {
      gapPx: strategy.gapPx,
      lineWidth
    });
    if (!boundaryMask) {
      continue;
    }
    const filledRegion = floodFillInterior(boundaryMask, analysisWidth, analysisHeight, seedPoint);
    if (!filledRegion || filledRegion.area < DRAWING_FILL_MIN_REGION_PIXELS) {
      continue;
    }
    if (filledRegion.touchesEdge || filledRegion.area > analysisWidth * analysisHeight * DRAWING_FILL_MAX_REGION_RATIO) {
      continue;
    }
    const fillPoints = buildPolygonFromFilledMask(
      filledRegion.mask,
      analysisWidth,
      analysisHeight,
      filledRegion.seed
    );
    if (fillPoints?.length >= 3) {
      return {
        tool: DRAWING_TOOL.FILL,
        points: [point],
        fillPoints,
        guessed: strategy.guessed
      };
    }
  }

  const fallbackBoundaryMask = buildBoundaryMaskFromStrokes(boundaryStrokes, analysisWidth, analysisHeight, {
    gapPx: DRAWING_FILL_CONNECT_GAP_PX * analysisScale,
    lineWidth
  });
  if (!fallbackBoundaryMask) {
    return null;
  }
  const fillPoints = buildGuessedFillPolygon(fallbackBoundaryMask, analysisWidth, analysisHeight, seedPoint);
  if (!fillPoints?.length || fillPoints.length < 3) {
    return null;
  }
  return {
    tool: DRAWING_TOOL.FILL,
    points: [point],
    fillPoints,
    guessed: true
  };
}

export function redrawDrawingCanvas(canvas, strokes, draftStroke = null) {
  if (!canvas) {
    return;
  }
  const context = canvas.getContext("2d");
  if (!context) {
    return;
  }
  const width = canvas.width;
  const height = canvas.height;
  context.clearRect(0, 0, width, height);

  const allStrokes = Array.isArray(strokes) ? strokes : [];
  for (const stroke of allStrokes) {
    if (!isFillStroke(stroke)) {
      continue;
    }
    drawFillStroke(context, stroke, width, height, {
      color: stroke?.guessed ? DRAWING_GUESSED_FILL_COLOR : DRAWING_FILL_COLOR,
      alpha: 1
    });
  }
  for (const stroke of allStrokes) {
    if (isSurfaceLineStroke(stroke)) {
      continue;
    }
    drawLineStroke(context, stroke, width, height, {
      color: DRAWING_STROKE_HALO,
      lineWidth: DRAWING_STROKE_HALO_WIDTH
    });
    drawLineStroke(context, stroke, width, height, {
      color: DRAWING_STROKE_COLOR,
      lineWidth: DRAWING_STROKE_WIDTH
    });
  }

  if (draftStroke) {
    drawLineStroke(context, draftStroke, width, height, {
      color: DRAWING_STROKE_HALO,
      lineWidth: DRAWING_STROKE_HALO_WIDTH,
      alpha: 0.78
    });
    drawLineStroke(context, draftStroke, width, height, {
      color: DRAWING_STROKE_COLOR,
      lineWidth: DRAWING_STROKE_WIDTH,
      alpha: 0.9
    });
  }
}
