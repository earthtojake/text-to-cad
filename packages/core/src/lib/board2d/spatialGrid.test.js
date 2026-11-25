import assert from "node:assert/strict";
import test from "node:test";

import { createSpatialGrid } from "./spatialGrid.js";

// A seeded scatter of boxes: small ones, long thin ones, one as big as the page, and one with no place.
function scatter(count, seed = 5) {
  let state = seed;
  const random = () => { state = (state * 1664525 + 1013904223) >>> 0; return state / 4294967296; };
  const boxes = [];
  for (let at = 0; at < count; at += 1) {
    const x = random() * 100; const y = random() * 80;
    const w = at % 9 === 0 ? random() * 40 : random() * 2; const h = at % 7 === 0 ? random() * 30 : random() * 2;
    boxes.push([x, y, x + w, y + h]);
  }
  boxes.push([-10, -10, 120, 95], null, [Number.NaN, 0, 1, 1]);
  return boxes;
}
const meets = (box, [x0, y0, x1, y1]) => Boolean(box) && box.every(Number.isFinite) && box[0] <= x1 && box[2] >= x0 && box[1] <= y1 && box[3] >= y0;

test("a query visits every item whose box meets it, once, and never one with no place", () => {
  const boxes = scatter(3000);
  const grid = createSpatialGrid(boxes);
  const queries = [[50, 40, 50, 40], [0, 0, 3, 3], [99.5, 79.5, 101, 81], [-50, -50, -40, -40], [30, 10, 70, 60], [200, 200, 210, 210]];
  for (const query of queries) {
    const visited = [];
    grid.visit(...query, (item) => visited.push(item));
    assert.equal(new Set(visited).size, visited.length, `no item twice: ${query}`);
    const wanted = boxes.map((box, item) => (meets(box, query) ? item : -1)).filter((item) => item >= 0);
    const missing = wanted.filter((item) => !visited.includes(item));
    assert.deepEqual(missing, [], `every item that meets ${query}`);
    assert.ok(!visited.includes(boxes.length - 2) && !visited.includes(boxes.length - 1), "a box with no place is never visited");
  }
});

test("an empty grid visits nothing", () => {
  let visited = 0;
  createSpatialGrid([]).visit(0, 0, 10, 10, () => { visited += 1; });
  createSpatialGrid([null]).visit(0, 0, 10, 10, () => { visited += 1; });
  assert.equal(visited, 0);
});
