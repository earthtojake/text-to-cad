import assert from "node:assert/strict";
import test from "node:test";

import { findFillRegion, pairNearbyBoundaryEndpoints } from "./fillRegion.js";

/** The Fill tool: the area someone points at, whether or not they closed its outline. */

const SIZE = 120;
// A mask painter: thick axis-aligned segments, and connectors for the gaps the caller allows.
function ink(segments, ends = []) {
  return gapPx => {
    const mask = new Uint8Array(SIZE * SIZE);
    const stroke = ([x0, y0], [x1, y1]) => {
      const steps = Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0), 1);
      for (let step = 0; step <= steps; step += 1) {
        const x = Math.round(x0 + (x1 - x0) * step / steps), y = Math.round(y0 + (y1 - y0) * step / steps);
        for (let dy = -1; dy <= 1; dy += 1) for (let dx = -1; dx <= 1; dx += 1) {
          if (x + dx >= 0 && y + dy >= 0 && x + dx < SIZE && y + dy < SIZE) mask[(y + dy) * SIZE + x + dx] = 1;
        }
      }
    };
    segments.forEach(([from, to]) => stroke(from, to));
    pairNearbyBoundaryEndpoints(ends.map((point, index) => ({ point, strokeId: `s${index >> 1}`, allowSelfConnect: true })), gapPx)
      .forEach(([from, to]) => stroke(from, to));
    return mask;
  };
}
const bounds = points => ({
  minX: Math.min(...points.map(point => point.x)) * SIZE, maxX: Math.max(...points.map(point => point.x)) * SIZE,
  minY: Math.min(...points.map(point => point.y)) * SIZE, maxY: Math.max(...points.map(point => point.y)) * SIZE,
});
const box = [[[30, 30], [90, 30]], [[90, 30], [90, 90]], [[90, 90], [30, 90]], [[30, 90], [30, 30]]];

test("fills a closed outline up to its ink, from anywhere inside it", () => {
  const region = findFillRegion(ink(box), SIZE, SIZE, [70, 40]);
  assert.equal(region.guessed, false);
  const { minX, maxX, minY, maxY } = bounds(region.points);
  for (const [value, expected] of [[minX, 32], [maxX, 89], [minY, 32], [maxY, 89]]) assert.ok(Math.abs(value - expected) <= 2, `${value} ~ ${expected}`);
});

test("joins the ends of an outline that was not quite closed, and says it guessed", () => {
  // The last side stops 14 px short of the corner it was heading for.
  const open = [...box.slice(0, 3), [[30, 90], [30, 44]]];
  const ends = [[30, 44], [30, 30]];
  assert.equal(findFillRegion(ink(open), SIZE, SIZE, [60, 60], { gapPx: 0 })?.guessed ?? true, true, "as drawn, the fill escapes through the gap");
  const region = findFillRegion(ink(open, ends), SIZE, SIZE, [60, 60]);
  assert.equal(region.guessed, true);
  const { minX, maxX, minY, maxY } = bounds(region.points);
  for (const [value, expected] of [[minX, 32], [maxX, 89], [minY, 32], [maxY, 89]]) assert.ok(Math.abs(value - expected) <= 3, `${value} ~ ${expected}`);
});

test("guesses the area a wide-open outline indicates rather than flooding the page", () => {
  // Three sides of a box: no pair of ends is close enough to join.
  const region = findFillRegion(ink(box.slice(0, 3), [[30, 30], [30, 90]]), SIZE, SIZE, [70, 60]);
  assert.equal(region.guessed, true);
  const { minX, maxX, minY, maxY } = bounds(region.points);
  assert.ok(maxX <= 91 && minY >= 29 && maxY <= 91, "bounded by the three drawn sides");
  assert.ok(minX >= 5, "and not the whole frame on the open side");
});

test("a gap too wide to join does not let the guess run out to whatever ink lies beyond it", () => {
  // The left side stops 46 px short; far beyond that gap there is unrelated ink.
  const gapped = [...box.slice(0, 3), [[30, 90], [30, 76]], [[4, 20], [4, 60]]];
  const region = findFillRegion(ink(gapped, [[30, 76], [30, 30]]), SIZE, SIZE, [60, 60], { gapPx: 20 });
  assert.equal(region.guessed, true);
  const { minX, maxX, minY, maxY } = bounds(region.points);
  assert.ok(minX >= 24, `the gap is bridged along the outline, not followed out to x=4 (${minX})`);
  assert.ok(maxX <= 91 && minY >= 29 && maxY <= 91);
});

test("fills nothing where no ink encloses the point", () => {
  assert.equal(findFillRegion(ink([]), SIZE, SIZE, [60, 60]), null);
  assert.equal(findFillRegion(ink([[[10, 100], [110, 100]]]), SIZE, SIZE, [60, 20]), null);
  assert.equal(findFillRegion(ink(box), SIZE, SIZE, [10, 10]), null, "outside the outline");
});
