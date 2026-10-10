/**
 * A uniform grid over page millimetres, for what an index asks on every pointer move: which items
 * lie near a point. Each item is filed under every cell its box touches, so a question about a
 * point reads the few cells around it rather than every pad and track of a board. An item whose
 * box would fill a great many cells (a pour, a board-wide part) is kept aside and always visited:
 * there are few of them, and filing them would cost a cell entry each.
 *
 * Built once per index; plain typed arrays, no allocation per query.
 */

/** How many items a cell should hold on average, and the most cells one item is filed under. */
const ITEMS_PER_CELL = 4;
const MAX_CELLS_PER_ITEM = 256;
const MAX_CELLS = 1 << 20;

const finite = (box) => Boolean(box) && Number.isFinite(box[0]) && Number.isFinite(box[1]) && Number.isFinite(box[2]) && Number.isFinite(box[3]);

/**
 * @param {ReadonlyArray<readonly [number, number, number, number] | null>} boxes  Each item's
 *   `[minX, minY, maxX, maxY]`, by its index; null (or a box with a non-finite side) for an item
 *   with no place, which is never visited.
 * @returns {{ visit(minX: number, minY: number, maxX: number, maxY: number, fn: (item: number) => void): void }}
 *   `visit` calls `fn` once for every item whose box may meet the query box: every one that does,
 *   and perhaps a few near it. Callers test each item themselves.
 */
export function createSpatialGrid(boxes) {
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  let placed = 0;
  for (const box of boxes) {
    if (!finite(box)) continue;
    placed += 1;
    if (box[0] < minX) minX = box[0];
    if (box[1] < minY) minY = box[1];
    if (box[2] > maxX) maxX = box[2];
    if (box[3] > maxY) maxY = box[3];
  }
  const marks = new Uint32Array(boxes.length);
  let stamp = 0;
  const next = () => {
    stamp += 1;
    if (stamp === 0xffffffff) { marks.fill(0); stamp = 1; }
    return stamp;
  };
  if (!placed) return Object.freeze({ visit() {} });

  const width = Math.max(maxX - minX, 1e-6);
  const height = Math.max(maxY - minY, 1e-6);
  let cell = Math.sqrt((width * height) / Math.max(1, placed / ITEMS_PER_CELL));
  if (!(cell > 0)) cell = Math.max(width, height);
  let cols = Math.max(1, Math.ceil(width / cell));
  let rows = Math.max(1, Math.ceil(height / cell));
  while (cols * rows > MAX_CELLS) {
    cell *= 1.5;
    cols = Math.max(1, Math.ceil(width / cell));
    rows = Math.max(1, Math.ceil(height / cell));
  }
  const column = (x) => Math.min(cols - 1, Math.max(0, Math.floor((x - minX) / cell)));
  const row = (y) => Math.min(rows - 1, Math.max(0, Math.floor((y - minY) / cell)));

  // Two passes, compressed rows: how many items each cell holds, then the items themselves.
  const spans = new Int32Array(boxes.length * 4);
  const large = [];
  const counts = new Uint32Array(cols * rows + 1);
  boxes.forEach((box, item) => {
    if (!finite(box)) { spans[item * 4] = -1; return; }
    const c0 = column(box[0]); const r0 = row(box[1]); const c1 = column(box[2]); const r1 = row(box[3]);
    if ((c1 - c0 + 1) * (r1 - r0 + 1) > MAX_CELLS_PER_ITEM) { large.push(item); spans[item * 4] = -1; return; }
    spans.set([c0, r0, c1, r1], item * 4);
    for (let r = r0; r <= r1; r += 1) for (let c = c0; c <= c1; c += 1) counts[r * cols + c + 1] += 1;
  });
  for (let at = 1; at < counts.length; at += 1) counts[at] += counts[at - 1];
  const items = new Int32Array(counts[counts.length - 1]);
  const fill = counts.slice(0, -1);
  for (let item = 0; item < boxes.length; item += 1) {
    const c0 = spans[item * 4];
    if (c0 < 0) continue;
    const r0 = spans[item * 4 + 1]; const c1 = spans[item * 4 + 2]; const r1 = spans[item * 4 + 3];
    for (let r = r0; r <= r1; r += 1) for (let c = c0; c <= c1; c += 1) items[fill[r * cols + c]++] = item;
  }

  function visit(x0, y0, x1, y1, fn) {
    const mark = next();
    for (const item of large) { marks[item] = mark; fn(item); }
    if (x1 < minX || y1 < minY || x0 > maxX || y0 > maxY) return;
    const c0 = column(x0); const r0 = row(y0); const c1 = column(x1); const r1 = row(y1);
    for (let r = r0; r <= r1; r += 1) {
      for (let c = c0; c <= c1; c += 1) {
        const at = r * cols + c;
        for (let k = counts[at]; k < counts[at + 1]; k += 1) {
          const item = items[k];
          if (marks[item] === mark) continue;
          marks[item] = mark;
          fn(item);
        }
      }
    }
  }
  return Object.freeze({ visit });
}

/** The box of a list of points, `[minX, minY, maxX, maxY]`, grown by `margin` on every side; null for none. */
export function boxOf(points, margin = 0) {
  let minX = Infinity; let minY = Infinity; let maxX = -Infinity; let maxY = -Infinity;
  for (const [x, y] of points) {
    if (x < minX) minX = x; if (x > maxX) maxX = x;
    if (y < minY) minY = y; if (y > maxY) maxY = y;
  }
  return Number.isFinite(minX) && Number.isFinite(minY) ? [minX - margin, minY - margin, maxX + margin, maxY + margin] : null;
}

/** Whether point `at` is within `reach` of box `box`. */
export function nearBox(box, [x, y], reach) {
  return Boolean(box) && x >= box[0] - reach && x <= box[2] + reach && y >= box[1] - reach && y <= box[3] + reach;
}
