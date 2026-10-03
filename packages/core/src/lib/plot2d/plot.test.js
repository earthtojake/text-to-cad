import assert from "node:assert/strict";
import test from "node:test";

import { zoomLimits, zoomTransform } from "../drawing2d/transform.js";
import {
  PLOT_SHEET_GAP,
  drawPlot,
  fitPlotTransform,
  layoutPlot,
  pageToScreen,
  screenToPage,
  sheetImages,
  visiblePageRect
} from "./plot.js";
import { loadSheetImages } from "./images.js";

const sheet = (name, width, height, background = "#F5F4EF") => ({ name, svg: "<svg/>", width, height, background });
const BOARD = { schemaVersion: 1, kicadVersion: "10.0.6", kind: "board", unrouted: 2, sheets: [sheet("blinky", 40, 30, "#001023")] };
const SCHEMATIC = { schemaVersion: 1, kind: "schematic", unrouted: null, sheets: [sheet("root", 297, 210), sheet("small", 210, 148), sheet("power", 297, 210)] };

test("a schematic's sheets stack top to bottom, root first, each centred on the widest", () => {
  const layout = layoutPlot(SCHEMATIC);
  const gap = 297 * PLOT_SHEET_GAP;
  assert.deepEqual(layout.sheets.map(({ name, x, y }) => [name, x, y]), [
    ["root", 0, 0],
    ["small", (297 - 210) / 2, 210 + gap],
    ["power", 0, 210 + gap + 148 + gap]
  ]);
  const height = 210 + 148 + 210 + 2 * gap;
  assert.deepEqual(layout.bounds, [0, 0, 297, height]);
  // drawing2d's model space is the page with y negated: the same box, flipped.
  assert.deepEqual(layout.modelBounds, [0, -height, 297, 0]);
  assert.equal(layout.kind, "schematic");
  assert.equal(layout.unrouted, null);
});

test("a board is one sheet, and nothing in the layout depends on the tool's version", () => {
  const { kicadVersion: _version, ...withoutVersion } = BOARD;
  const layout = layoutPlot(withoutVersion);
  assert.deepEqual(layout.bounds, [0, 0, 40, 30]);
  assert.deepEqual(layout.sheets.map(({ x, y, background }) => [x, y, background]), [[0, 0, "#001023"]]);
  assert.equal(layout.unrouted, 2);
});

test("the fit frames the page the right way up: its top-left corner is the picture's", () => {
  const layout = layoutPlot(SCHEMATIC);
  const transform = fitPlotTransform(layout, 600, 1000);
  const [left, top] = pageToScreen(transform, 0, 0);
  const [right, bottom] = pageToScreen(transform, ...layout.bounds.slice(2));
  assert.ok(top < bottom, `page y grows downwards on screen: ${top} -> ${bottom}`);
  // Centred, inside drawing2d's 16 px gutter, the tight axis touching it.
  assert.ok(Math.abs((left + right) / 2 - 300) < 1e-9 && Math.abs((top + bottom) / 2 - 500) < 1e-9);
  assert.ok(Math.abs(bottom - top - 968) < 1e-9, `height is the binding axis: ${bottom - top}`);
  // screen = page * scale + offset, on both axes.
  assert.deepEqual(pageToScreen(transform, 10, 20), [10 * transform.scale + transform.offsetX, 20 * transform.scale + transform.offsetY]);
});

test("screenToPage inverts pageToScreen, under a zoom about a point too", () => {
  const layout = layoutPlot(SCHEMATIC);
  const fitted = fitPlotTransform(layout, 800, 600);
  const zoomed = zoomTransform(fitted, { x: 610, y: 77 }, 6.5, zoomLimits(fitted.scale));
  for (const transform of [fitted, zoomed]) {
    for (const [x, y] of [[0, 0], [297, 210], [12.5, 400.25]]) {
      const [px, py] = screenToPage(transform, ...pageToScreen(transform, x, y));
      assert.ok(Math.abs(px - x) < 1e-9 && Math.abs(py - y) < 1e-9, `round trip lost (${x}, ${y})`);
    }
  }
  assert.deepEqual(visiblePageRect({ scale: 2, offsetX: -10, offsetY: 4 }, 100, 50), [5, -2, 55, 23]);
});

test("a payload this build does not understand is refused by name", () => {
  assert.throws(() => layoutPlot(null), /plot payload object/);
  assert.throws(() => layoutPlot({ ...BOARD, schemaVersion: 2 }), /schemaVersion 2.*Update cadgen and the app together/);
  assert.throws(() => layoutPlot({ ...BOARD, sheets: [] }), /non-empty array/);
  assert.throws(() => layoutPlot({ ...BOARD, sheets: [{ ...BOARD.sheets[0], svg: "" }] }), /"blinky".*no SVG/);
  assert.throws(() => layoutPlot({ ...BOARD, sheets: [{ ...BOARD.sheets[0], width: 0 }] }), /positive width and height/);
  assert.throws(() => layoutPlot({ ...BOARD, sheets: [{ ...BOARD.sheets[0], background: "navy" }] }), /#rrggbb/);
});

/** A 2D context that records what it is asked to do, on a canvas of a given device size. */
function recorder(width, height) {
  const calls = [];
  const ctx = {
    canvas: { width, height },
    save() { calls.push(["save"]); },
    restore() { calls.push(["restore"]); },
    setTransform(...args) { calls.push(["setTransform", ...args]); },
    fillRect(...args) { calls.push(["fillRect", this.fillStyle, ...args]); },
    drawImage(image, ...args) { calls.push(["drawImage", image, ...args]); },
    fillStyle: ""
  };
  return { ctx, calls };
}

test("a frame is each visible sheet in its background, then the images over them, in page space", () => {
  const layout = layoutPlot(SCHEMATIC);
  // Zoomed onto the root sheet: the two below it are off the canvas.
  const transform = { scale: 2, offsetX: 0, offsetY: 0 };
  const { ctx, calls } = recorder(1200, 800);
  drawPlot(ctx, layout, { transform, pixelRatio: 2, images: sheetImages(layout, ["root-svg", "small-svg", null]) });
  assert.deepEqual(calls, [
    ["save"],
    ["setTransform", 4, 0, 0, 4, 0, 0],
    ["fillRect", "#F5F4EF", 0, 0, 297, 210],
    ["drawImage", "root-svg", 0, 0, 297, 210],
    ["restore"]
  ]);
});

test("the whole plot fitted draws every sheet, and an image without a sheet's place is skipped", () => {
  const layout = layoutPlot(SCHEMATIC);
  const transform = fitPlotTransform(layout, 400, 800);
  const { ctx, calls } = recorder(400, 800);
  drawPlot(ctx, layout, { transform, images: [...sheetImages(layout, ["a", "b", "c"]), { image: "d", x: 0, y: 0, width: 0, height: 5 }] });
  assert.deepEqual(calls.filter(([name]) => name === "fillRect").length, 3);
  assert.deepEqual(calls.filter(([name]) => name === "drawImage").map(([, image]) => image), ["a", "b", "c"]);
  assert.throws(() => drawPlot(ctx, layout, { transform: { scale: 0, offsetX: 0, offsetY: 0 } }), /positive scale/);
});

test("sheet images decode once each, their URLs are released, and a sheet that will not decode is named", async () => {
  const layout = layoutPlot(SCHEMATIC);
  const created = [], revoked = [];
  const URL = { createObjectURL: (blob) => { created.push(blob); return `blob:${created.length}`; }, revokeObjectURL: (url) => revoked.push(url) };
  class Blob { constructor(parts, options) { this.parts = parts; this.type = options.type; } }
  class Image { decode() { return this.src === "blob:2" ? Promise.reject(new Error("bad XML")) : Promise.resolve(); } }
  await assert.rejects(loadSheetImages(layout, { Image, URL, Blob }), /Sheet 2 of this plot, “small”, is not an SVG this browser can draw \(bad XML\)/);
  assert.deepEqual(created.map((blob) => blob.type), ["image/svg+xml", "image/svg+xml", "image/svg+xml"]);
  assert.deepEqual(revoked.sort(), ["blob:1", "blob:2", "blob:3"]);

  class GoodImage { decode() { return Promise.resolve(); } }
  const images = await loadSheetImages(layout, { Image: GoodImage, URL, Blob });
  assert.equal(images.length, 3);
  assert.ok(images.every((image) => image instanceof GoodImage && image.decoding === "async"));
  const aborted = new AbortController();
  aborted.abort();
  await assert.rejects(loadSheetImages(layout, { Image: GoodImage, URL, Blob, signal: aborted.signal }), { name: "AbortError" });
});
