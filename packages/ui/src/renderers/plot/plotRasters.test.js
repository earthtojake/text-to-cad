import assert from "node:assert/strict";
import test from "node:test";

import { fitPlotTransform, layoutPlot } from "@text-to-cad/core/lib/plot2d/index.js";
import { panTransform, zoomLimits, zoomTransform } from "@text-to-cad/core/lib/drawing2d/transform.js";
import { PATCH_LIMIT, SETTLE_MS, createPlotRasters } from "./plotRasters.js";

// The cache's contract, with canvases that record what is drawn on them and a clock the test
// turns by hand: the first frame is drawn at once, a pan is a whole-pixel move of what was
// drawn, a zoom is redrawn at its own scale once the view rests, and the cache stays bounded.

const PAYLOAD = { schemaVersion: 2, kind: "schematic", unrouted: null, sheets: [
  { name: "root", svg: "<svg/>", width: 297, height: 210, background: "#F5F4EF" },
  { name: "power", svg: "<svg/>", width: 297, height: 210, background: "#F5F4EF" }
] };
const SVGS = ["root-svg", "power-svg"];

function canvas(width, height) {
  const element = { width, height, draws: [] };
  element.getContext = () => ({
    canvas: element,
    save() {}, restore() {}, setTransform() {},
    fillRect() {},
    drawImage(image, x, y, w, h) { element.draws.push({ image, x, y, w, h }); }
  });
  return element;
}

function harness() {
  const layout = layoutPlot(PAYLOAD);
  const made = [];
  const timers = new Map();
  let next = 0;
  let changes = 0;
  const rasters = createPlotRasters({
    layout, images: SVGS,
    onChange: () => { changes += 1; },
    createCanvas: (width, height) => { const element = canvas(width, height); made.push(element); return element; },
    schedule: (callback, delay) => { next += 1; timers.set(next, { callback, delay }); return next; },
    cancel: (handle) => timers.delete(handle)
  });
  const screen = canvas(800 * 2, 600 * 2);
  const frame = (transform) => ({ transform, width: 800, height: 600, pixelRatio: 2 });
  const paint = (transform) => {
    screen.draws.length = 0;
    return rasters.paint(screen.getContext(), frame(transform));
  };
  const rest = () => {
    const pending = [...timers.values()];
    timers.clear();
    for (const { callback, delay } of pending) { assert.equal(delay, SETTLE_MS); callback(); }
    return pending.length;
  };
  return { layout, rasters, made, screen, paint, rest, get changes() { return changes; } };
}

test("the first frame is drawn at once, from the sheets' own SVGs, at the pane's device scale", () => {
  const { layout, made, screen, paint } = harness();
  const fitted = fitPlotTransform(layout, 800, 600);
  assert.equal(paint(fitted), true, "the first frame is final");
  assert.equal(made.length, 1);
  // The patch is the SVGs drawn into it, both sheets, nothing else.
  assert.deepEqual(made[0].draws.map((draw) => draw.image), SVGS);
  // And the pane shows that patch, at exactly its own size in device pixels.
  assert.equal(screen.draws.length, 1);
  const [{ image, w, h }] = screen.draws;
  assert.equal(image, made[0]);
  assert.ok(Math.abs(w * fitted.scale * 2 - made[0].width) < 1e-6 && Math.abs(h * fitted.scale * 2 - made[0].height) < 1e-6);
});

test("a pan moves the patch by whole device pixels and draws nothing again", () => {
  const { layout, made, screen, paint, rest } = harness();
  const fitted = fitPlotTransform(layout, 800, 600);
  const zoomed = zoomTransform(fitted, { x: 400, y: 300 }, 3, zoomLimits(fitted.scale));
  assert.equal(paint(zoomed), true, "a pane with nothing drawn yet draws at once");
  const patches = made.length;
  // A third of a CSS pixel is two thirds of a device pixel: the patch lands on the pixel grid.
  const panned = panTransform(zoomed, 10.33, -4);
  assert.equal(paint(panned), true, "inside the margin, a pan is still final");
  assert.equal(made.length, patches, "and nothing was rasterised for it");
  const crisp = screen.draws.at(-1);
  const deviceX = crisp.x * panned.scale * 2 + panned.offsetX * 2;
  assert.ok(Math.abs(deviceX - Math.round(deviceX)) < 1e-6, `the patch is blitted at ${deviceX}`);
});

test("a zoom shows what it has until the view rests, then draws the view at its own scale", () => {
  const harnessed = harness();
  const { layout, made, paint, rest } = harnessed;
  const fitted = fitPlotTransform(layout, 800, 600);
  paint(fitted);
  const zoomed = zoomTransform(fitted, { x: 200, y: 150 }, 4, zoomLimits(fitted.scale));
  assert.equal(paint(zoomed), false, "a scaled patch is not final");
  assert.equal(made.length, 1, "nothing is rasterised while the view moves");
  // Another tick of the wheel restarts the wait rather than adding a second one.
  const deeper = zoomTransform(zoomed, { x: 200, y: 150 }, 1.2, zoomLimits(fitted.scale));
  assert.equal(paint(deeper), false);
  assert.equal(rest(), 1);
  assert.equal(made.length, 2);
  assert.equal(harnessed.changes, 1, "the pane is asked to paint again");
  assert.equal(paint(deeper), true);
  // Zooming back out to the first view needs no new patch: it was kept.
  assert.equal(paint(fitted), true);
  assert.equal(made.length, 2);
});

test("the cache keeps a few patches, releases the rest, and a capture need not wait", () => {
  const { layout, rasters, made, paint, rest } = harness();
  const fitted = fitPlotTransform(layout, 800, 600);
  paint(fitted);
  for (const factor of [2, 3, 5, 8]) {
    paint(zoomTransform(fitted, { x: 400, y: 300 }, factor, zoomLimits(fitted.scale)));
    rest();
  }
  assert.equal(rasters.size, PATCH_LIMIT);
  assert.equal(made.filter((element) => element.width === 0 && element.height === 0).length, made.length - PATCH_LIMIT,
    "an evicted patch gives its memory back");
  // A view still waiting to rest is drawn on demand.
  const last = zoomTransform(fitted, { x: 400, y: 200 }, 13, zoomLimits(fitted.scale));
  assert.equal(paint(last), false);
  rasters.flush();
  assert.equal(paint(last), true);
  rasters.dispose();
  assert.ok(made.every((element) => element.width === 0), "disposing releases every patch");
  assert.equal(rest(), 0, "and leaves nothing scheduled");
});
