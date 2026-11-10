// Box selection's geometry: under Select a drag draws a box (a 3D view's Box select, a flat view's
// Select), and the box takes anything it touches, even where only part of it lies inside, whichever
// way it was drawn. Everything is in one frame (screen pixels, client or viewport-local, or a flat
// picture's own millimetres, as long as the box and the points share it), so it unit-tests without a
// scene, and every viewer's box is judged by these same tests: a 3D scene's `pickBox`
// (`../xbf/xbfScene.js`) casts the rays; a dimension is judged by `dimensionLayoutTouchesBox`
// (`measureDimension.js`), ink by the UI's `annotationsInBox` (its `annotation/geometry.js`), a board's
// items by its index's `pickBox` (`../board2d/boardIndex.js`), a schematic's by its page's
// (`../schematic2d/schematicIndex.js`) and a drawing's entities by `entitiesInBox`
// (`../drawing2d/entities.js`). A point is `{ x, y }` or `[x, y]`.

// The most rays a box casts on its grid: a large box is sampled on a coarser grid, never more
// densely than every BOX_SAMPLE_MIN_SPACING_PX.
export const BOX_SAMPLE_MAX = 4096;
export const BOX_SAMPLE_MIN_SPACING_PX = 3;

/**
 * The box a drag from `start` to `end` draws, normalized, whichever way it went.
 *
 * @param {{ x: number, y: number }} start
 * @param {{ x: number, y: number }} end
 */
export function boxFromDrag(start, end) {
  const left = Math.min(start.x, end.x), right = Math.max(start.x, end.x);
  const top = Math.min(start.y, end.y), bottom = Math.max(start.y, end.y);
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

/** A box from bounds `[minX, minY, maxX, maxY]`, as a flat picture's index keeps them. */
export function boxFromBounds([minX, minY, maxX, maxY]) {
  return { left: minX, top: minY, right: maxX, bottom: maxY, width: maxX - minX, height: maxY - minY };
}

export function pointInBox(box, x, y) {
  return x >= box.left && x <= box.right && y >= box.top && y <= box.bottom;
}

/** Whether bounds `[minX, minY, maxX, maxY]` overlap the box at all: a quick reject, or a rectangle's own test. */
export function boundsTouchBox(box, bounds) {
  return Boolean(bounds) && bounds[0] <= box.right && bounds[2] >= box.left && bounds[1] <= box.bottom && bounds[3] >= box.top;
}

/** Whether a disc of radius `r` about (cx, cy) touches the box. */
export function circleTouchesBox(box, cx, cy, r) {
  const dx = cx - Math.max(box.left, Math.min(cx, box.right)), dy = cy - Math.max(box.top, Math.min(cy, box.bottom));
  return dx * dx + dy * dy <= r * r;
}

/**
 * The part of the segment from (ax, ay) to (bx, by) that lies in the box, as the span [t0, t1] of
 * it (0 at a, 1 at b), or null where it misses the box (Liang–Barsky).
 */
export function segmentInBox(box, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay;
  let t0 = 0, t1 = 1;
  // The sides in turn, left, right, top, bottom: `p` the run towards the side, `q` the room before it.
  for (let side = 0; side < 4; side += 1) {
    const p = side === 0 ? -dx : side === 1 ? dx : side === 2 ? -dy : dy;
    const q = side === 0 ? ax - box.left : side === 1 ? box.right - ax : side === 2 ? ay - box.top : box.bottom - ay;
    if (p === 0) {
      if (q < 0) return null;
      continue;
    }
    const t = q / p;
    if (p < 0) {
      if (t > t1) return null;
      if (t > t0) t0 = t;
    } else {
      if (t < t0) return null;
      if (t < t1) t1 = t;
    }
  }
  return t0 <= t1 ? [t0, t1] : null;
}

/** Whether the segment from (ax, ay) to (bx, by) touches the box: an end inside it, or crossing it. */
export function segmentTouchesBox(box, ax, ay, bx, by) {
  return segmentInBox(box, ax, ay, bx, by) !== null;
}

function cross(ax, ay, bx, by, px, py) {
  return (bx - ax) * (py - ay) - (by - ay) * (px - ax);
}

function pointInTriangle(px, py, ax, ay, bx, by, cx, cy) {
  const d1 = cross(ax, ay, bx, by, px, py), d2 = cross(bx, by, cx, cy, px, py), d3 = cross(cx, cy, ax, ay, px, py);
  const negative = d1 < 0 || d2 < 0 || d3 < 0, positive = d1 > 0 || d2 > 0 || d3 > 0;
  return !(negative && positive);
}

/** Whether a screen triangle touches the box: one of its sides does, or it covers the box. */
export function triangleTouchesBox(box, ax, ay, bx, by, cx, cy) {
  if (segmentTouchesBox(box, ax, ay, bx, by) || segmentTouchesBox(box, bx, by, cx, cy) || segmentTouchesBox(box, cx, cy, ax, ay)) return true;
  return pointInTriangle(box.left, box.top, ax, ay, bx, by, cx, cy);
}

const xOf = point => (Array.isArray(point) ? point[0] : point.x);
const yOf = point => (Array.isArray(point) ? point[1] : point.y);

/** Whether (x, y) lies inside a closed polygon (even-odd: a self-crossing outline's holes are out). */
export function pointInPolygon(x, y, polygon) {
  let hit = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const ax = xOf(polygon[i]), ay = yOf(polygon[i]), bx = xOf(polygon[j]), by = yOf(polygon[j]);
    if ((ay > y) !== (by > y) && x < ((bx - ax) * (y - ay)) / (by - ay) + ax) hit = !hit;
  }
  return hit;
}

/**
 * Whether a line drawn through `points` touches the box: one of its segments does (the closing one
 * too when `closed`), a lone point lies in it. `radius` is half the line's drawn width: the box
 * reaches a wide line's edge, not only its middle.
 */
export function polylineTouchesBox(box, points, { closed = false, radius = 0 } = {}) {
  if (!points?.length) return false;
  const reach = radius > 0 ? { left: box.left - radius, top: box.top - radius, right: box.right + radius, bottom: box.bottom + radius } : box;
  if (points.length === 1) return pointInBox(reach, xOf(points[0]), yOf(points[0]));
  const last = closed ? points.length : points.length - 1;
  for (let index = 0; index < last; index += 1) {
    const a = points[index], b = points[(index + 1) % points.length];
    if (segmentTouchesBox(reach, xOf(a), yOf(a), xOf(b), yOf(b))) return true;
  }
  return false;
}

/** Whether a filled screen polygon touches the box: its outline does, or it covers the box. */
export function polygonTouchesBox(box, polygon) {
  return polylineTouchesBox(box, polygon, { closed: true }) || (polygon.length >= 3 && pointInPolygon(box.left, box.top, polygon));
}

// The polygon `points` ([x, y, x, y, ...]) cut to the side of a line where `inside(x, y)`, the line
// crossed where `cross(ax, ay, bx, by)` says (Sutherland-Hodgman's one step).
function clipPolygon(points, inside, cross) {
  const out = [];
  for (let at = 0; at < points.length; at += 2) {
    const ax = points[at], ay = points[at + 1];
    const bx = points[(at + 2) % points.length], by = points[(at + 3) % points.length];
    const aIn = inside(ax, ay), bIn = inside(bx, by);
    if (aIn) out.push(ax, ay);
    if (aIn !== bIn) out.push(...cross(ax, ay, bx, by));
  }
  return out;
}
const crossX = x => (ax, ay, bx, by) => [x, ay + ((by - ay) * (x - ax)) / (bx - ax)];
const crossY = y => (ax, ay, bx, by) => [ax + ((bx - ax) * (y - ay)) / (by - ay), y];
// A convex polygon's own point: its corners' mean, or null where it has no area.
function polygonPoint(points) {
  if (points.length < 6) return null;
  let area = 0, x = 0, y = 0;
  for (let at = 0; at < points.length; at += 2) {
    const ax = points[at], ay = points[at + 1], bx = points[(at + 2) % points.length], by = points[(at + 3) % points.length];
    area += ax * by - bx * ay;
    x += ax;
    y += ay;
  }
  return Math.abs(area) > 1e-9 ? { x: (x * 2) / points.length, y: (y * 2) / points.length } : null;
}
// How far apart a region's lattice points lie, in pixels, at the least; and about how many of them, at the most.
export const BOX_REGION_SPACING_PX = 2;
export const BOX_REGION_POINTS = 512;

/**
 * Points to look at a part of the screen through: of the screen triangles `triangles` (flat, `[ax, ay,
 * bx, by, cx, cy, ...]`), what lies inside the box. The points of an even lattice over the screen that
 * fall there, no closer than `spacing` pixels and about `max` of them however large it is, then one of
 * each triangle's own part there, so a sliver thinner than the lattice is still looked at: a box's grid
 * can pass between such a sliver (`../xbf/xbfScene.js`'s `pickBox`).
 *
 * @param {{ left: number, top: number, right: number, bottom: number }} box
 * @param {ArrayLike<number>} triangles
 * @param {{ spacing?: number, max?: number }} [options]
 * @returns {{ x: number, y: number }[]}
 */
export function trianglePoints(box, triangles, { spacing = BOX_REGION_SPACING_PX, max = BOX_REGION_POINTS } = {}) {
  const count = Math.floor(triangles.length / 6);
  // Each triangle's bounds, cut to the box.
  const bounds = new Float64Array(count * 4);
  let area = 0;
  for (let triangle = 0; triangle < count; triangle += 1) {
    const at = triangle * 6;
    const minX = Math.max(box.left, Math.min(triangles[at], triangles[at + 2], triangles[at + 4]));
    const maxX = Math.min(box.right, Math.max(triangles[at], triangles[at + 2], triangles[at + 4]));
    const minY = Math.max(box.top, Math.min(triangles[at + 1], triangles[at + 3], triangles[at + 5]));
    const maxY = Math.min(box.bottom, Math.max(triangles[at + 1], triangles[at + 3], triangles[at + 5]));
    bounds[triangle * 4] = minX; bounds[triangle * 4 + 1] = minY; bounds[triangle * 4 + 2] = maxX; bounds[triangle * 4 + 3] = maxY;
    if (maxX >= minX && maxY >= minY) area += (maxX - minX) * (maxY - minY);
  }
  const step = Math.max(spacing, Math.sqrt(area / Math.max(1, max)));
  const points = [], taken = new Set();
  for (let triangle = 0; triangle < count; triangle += 1) {
    const minX = bounds[triangle * 4], minY = bounds[triangle * 4 + 1], maxX = bounds[triangle * 4 + 2], maxY = bounds[triangle * 4 + 3];
    if (!(maxX >= minX && maxY >= minY)) continue;
    const at = triangle * 6;
    for (let row = Math.ceil(minY / step - 0.5); (row + 0.5) * step <= maxY; row += 1) {
      for (let column = Math.ceil(minX / step - 0.5); (column + 0.5) * step <= maxX; column += 1) {
        const x = (column + 0.5) * step, y = (row + 0.5) * step;
        if (!pointInBox(box, x, y) || !pointInTriangle(x, y, triangles[at], triangles[at + 1], triangles[at + 2], triangles[at + 3], triangles[at + 4], triangles[at + 5])) continue;
        const key = `${column},${row}`;
        if (taken.has(key)) continue;
        taken.add(key);
        points.push({ x, y });
      }
    }
  }
  for (let triangle = 0; triangle < count; triangle += 1) {
    const corners = Array.prototype.slice.call(triangles, triangle * 6, triangle * 6 + 6);
    let cut = clipPolygon(corners, x => x >= box.left, crossX(box.left));
    cut = clipPolygon(cut, x => x <= box.right, crossX(box.right));
    cut = clipPolygon(cut, (x, y) => y >= box.top, crossY(box.top));
    cut = clipPolygon(cut, (x, y) => y <= box.bottom, crossY(box.bottom));
    const point = polygonPoint(cut);
    if (point && pointInBox(box, point.x, point.y)) points.push(point);
  }
  return points;
}

/**
 * Where a box casts its rays: the centres of an even grid over it, at most `max` of them and no
 * closer than `minSpacing` pixels apart, and at least its centre however small it is.
 */
export function boxSamplePoints(box, { max = BOX_SAMPLE_MAX, minSpacing = BOX_SAMPLE_MIN_SPACING_PX } = {}) {
  const width = Math.max(0, box.right - box.left), height = Math.max(0, box.bottom - box.top);
  const spacing = Math.max(minSpacing, Math.sqrt((width * height) / Math.max(1, max)));
  const columns = Math.max(1, Math.floor(width / spacing)), rows = Math.max(1, Math.floor(height / spacing));
  const points = [];
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      points.push({ x: box.left + ((column + 0.5) * width) / columns, y: box.top + ((row + 0.5) * height) / rows });
    }
  }
  return points;
}
