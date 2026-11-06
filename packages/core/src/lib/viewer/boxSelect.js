// Box selection's screen geometry, Select's Box select tool: a drag over the view draws a box, and
// what is visible in it is taken -- anything the box touches, even where only part of it lies
// inside, whichever way it was drawn. Everything here is in one frame of pixels (client or
// viewport-local, as long as the box and the points share it), so it unit-tests without a scene.
// A scene's `pickBox` (`../xbf/xbfScene.js`) casts the rays.

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

export function pointInBox(box, x, y) {
  return x >= box.left && x <= box.right && y >= box.top && y <= box.bottom;
}

/**
 * The part of the segment from (ax, ay) to (bx, by) that lies in the box, as the span [t0, t1] of
 * it (0 at a, 1 at b), or null where it misses the box (Liang–Barsky).
 */
export function segmentInBox(box, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay;
  let t0 = 0, t1 = 1;
  for (const [p, q] of [[-dx, ax - box.left], [dx, box.right - ax], [-dy, ay - box.top], [dy, box.bottom - ay]]) {
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
