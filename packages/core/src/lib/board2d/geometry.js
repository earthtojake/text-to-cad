/**
 * The plane geometry a board's and a schematic's index point with (`boardIndex.js`,
 * `schematicIndex.js`): points, polygons and segments in page millimetres. Pure.
 */

/** `value` as a point `[x, y]` of numbers, or null when it is not one. */
export const point = (value) => (Array.isArray(value) && value.length >= 2 && Number.isFinite(Number(value[0])) && Number.isFinite(Number(value[1]))
  ? [Number(value[0]), Number(value[1])] : null);

/** Whether `[x, y]` lies inside a closed polygon (even-odd). */
export function pointInPolygon([x, y], polygon) {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** The nearest point of segment ab to p, and its distance. */
export function nearestOnSegment([px, py], [ax, ay], [bx, by]) {
  const dx = bx - ax;
  const dy = by - ay;
  const length = dx * dx + dy * dy;
  const t = length > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / length)) : 0;
  const nearest = [ax + t * dx, ay + t * dy];
  return { point: nearest, distance: Math.hypot(px - nearest[0], py - nearest[1]) };
}

/** The nearest point of a polyline to p, and its distance. */
export function nearestOnPolyline(p, points) {
  let best = null;
  for (let index = 1; index < points.length; index += 1) {
    const candidate = nearestOnSegment(p, points[index - 1], points[index]);
    if (!best || candidate.distance < best.distance) best = candidate;
  }
  return best || (points[0] ? { point: points[0], distance: Math.hypot(p[0] - points[0][0], p[1] - points[0][1]) } : null);
}

/** How far `at` is from a closed polygon's edge (0 inside it). */
export function polygonReach(at, polygon) {
  if (pointInPolygon(at, polygon)) return 0;
  let distance = Infinity;
  for (let i = 0; i < polygon.length; i += 1) {
    distance = Math.min(distance, nearestOnSegment(at, polygon[i], polygon[(i + 1) % polygon.length]).distance);
  }
  return distance;
}

/** A polygon's area (shoelace), for preferring the smallest of overlapping shapes. */
export function polygonArea(polygon) {
  let sum = 0;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) sum += polygon[j][0] * polygon[i][1] - polygon[i][0] * polygon[j][1];
  return Math.abs(sum) / 2;
}

/** The box `[minX, minY, maxX, maxY]` round `points` (infinite when there are none). */
export function bounds(points) {
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  for (const [x, y] of points) {
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
  }
  return [minX, minY, maxX, maxY];
}
