/**
 * Flood fill for a sketch: the region around a point, bounded by drawn ink,
 * as a polygon. A person indicating "this area" rarely closes the outline, so
 * an open region is retried with nearby stroke ends joined, and finally guessed
 * from what the ink does enclose.
 *
 * Everything here works on a boundary MASK (1 = ink) in analysis pixels and
 * returns polygons normalized to 0..1 of that mask; the caller owns rendering
 * the ink into a mask and mapping the polygon back into its own coordinates.
 */

export const FILL_ANALYSIS_MAX_DIMENSION = 420;
/** Stroke ends closer than this, in display pixels, are one outline with a gap in it. */
export const FILL_CONNECT_GAP_PX = 40;
// Between neighbouring rays, 5 degrees apart: a side or a corner never grows this fast.
const FILL_GAP_JUMP_RATIO = 1.6;
const FILL_RAY_COUNT = 72;
const FILL_MIN_REGION_PIXELS = 56;
const FILL_MAX_REGION_RATIO = 0.92;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function pointsEqual2d(a, b, epsilon = 1e-4) {
  return Math.abs(a[0] - b[0]) <= epsilon && Math.abs(a[1] - b[1]) <= epsilon;
}

function pointInPolygon2d(point, polygon) {
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index, index += 1) {
    const a = polygon[index];
    const b = polygon[previous];
    const intersects =
      (a[1] > point[1]) !== (b[1] > point[1]) &&
      point[0] < ((b[0] - a[0]) * (point[1] - a[1])) / (b[1] - a[1] || 1e-9) + a[0];
    if (intersects) {
      inside = !inside;
    }
  }
  return inside;
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
  const distances = Array.from({ length: FILL_RAY_COUNT }, () => null);

  for (let index = 0; index < FILL_RAY_COUNT; index += 1) {
    const angle = (index / FILL_RAY_COUNT) * Math.PI * 2;
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

  // A ray that leaves through a gap in the outline reports whatever ink it meets
  // beyond it, or none. Around a gap the distance JUMPS, where along a drawn
  // side or corner it changes smoothly, so a short run of rays far beyond the
  // one before it is a gap: those rays are forgotten and bridged like misses.
  for (let index = 0; index < FILL_RAY_COUNT; index += 1) {
    const edge = distances[index];
    if (!Number.isFinite(edge)) continue;
    const escaped = [];
    for (let step = 1; step <= FILL_RAY_COUNT / 3; step += 1) {
      const next = (index + step) % FILL_RAY_COUNT;
      if (Number.isFinite(distances[next]) && distances[next] <= edge * FILL_GAP_JUMP_RATIO) break;
      escaped.push(next);
    }
    if (escaped.length && escaped.length < FILL_RAY_COUNT / 3) for (const next of escaped) distances[next] = null;
  }

  const validDistances = distances.filter(Number.isFinite);
  if (validDistances.length < Math.max(12, Math.floor(FILL_RAY_COUNT / 4))) {
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
    const angle = (index / FILL_RAY_COUNT) * Math.PI * 2;
    return [
      clamp(start[0] + Math.cos(angle) * distance, 0, width),
      clamp(start[1] + Math.sin(angle) * distance, 0, height)
    ];
  });
  const simplified = downsamplePolygon(removeCollinearPolygonPoints(polygon), FILL_RAY_COUNT);
  if (simplified.length < 3) {
    return null;
  }
  const area = Math.abs(polygonArea2d(simplified));
  if (area < FILL_MIN_REGION_PIXELS || area > width * height * FILL_MAX_REGION_RATIO) {
    return null;
  }
  return normalizePolygonPoints(simplified, width, height);
}

/**
 * The fill polygon around `seed`, or `null` when there is nothing to fill.
 *
 * `buildMask(gapPx)` renders the ink, with stroke ends up to `gapPx` apart
 * joined, into a `width * height` mask. Strategies run from the outline as
 * drawn to the most generous guess; `guessed` says the outline was not closed.
 *
 * @returns {{ points: { x: number, y: number }[], guessed: boolean } | null}
 */
export function findFillRegion(buildMask, width, height, seed, { gapPx = FILL_CONNECT_GAP_PX } = {}) {
  for (const gap of [0, gapPx * 0.45, gapPx]) {
    const boundaryMask = buildMask(gap);
    if (!boundaryMask) continue;
    const region = floodFillInterior(boundaryMask, width, height, seed);
    if (!region || region.area < FILL_MIN_REGION_PIXELS) continue;
    // Reaching the edge of the analysis frame is ink that did not contain the fill.
    if (region.touchesEdge || region.area > width * height * FILL_MAX_REGION_RATIO) continue;
    const points = buildPolygonFromFilledMask(region.mask, width, height, region.seed);
    if (points?.length >= 3) return { points, guessed: gap > 0 };
  }
  const boundaryMask = buildMask(gapPx);
  const points = boundaryMask ? buildGuessedFillPolygon(boundaryMask, width, height, seed) : null;
  return points?.length >= 3 ? { points, guessed: true } : null;
}
