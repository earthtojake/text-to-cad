import assert from "node:assert/strict";
import test from "node:test";

import { zoomLimits, zoomTransform } from "../drawing2d/transform.js";
import {
  PLOT_SCHEMA_VERSION,
  PLOT_SHEET_GAP,
  drawPlot,
  fitPlotTransform,
  layerImages,
  layoutPlot,
  mirrorPageX,
  pageToScreen,
  screenToPage,
  sheetImages,
  visiblePageRect
} from "./plot.js";
import { loadSheetImages } from "./images.js";

const sheet = (name, width, height, background = "#F5F4EF") => ({ name, svg: "<svg/>", width, height, background });
const layer = (id, kind, side, unpoured) => ({ id, kind, side, svg: `<svg id="${id}"/>`, ...(unpoured ? { unpoured: `<svg id="${id}-bare"/>` } : {}) });
const LAYERS = [
  layer("B.Fab", "fab", "back"), layer("B.Cu", "copper", "back", true), layer("F.Cu", "copper", "front"),
  layer("F.SilkS", "silk", "front"), layer("Edge.Cuts", "outline", "both"), layer("drills", "drill", "both")
];
const INDEX = { origin: [20, 15], parts: [], pads: [], findings: [] };
const BOARD = {
  schemaVersion: 2, kicadVersion: "10.0.6", kind: "board", unrouted: 2,
  sheets: [{ name: "blinky", width: 40, height: 30, background: "#001023", layers: LAYERS }], board: INDEX
};
const SCHEMATIC = { schemaVersion: 2, kind: "schematic", unrouted: null, sheets: [sheet("root", 297, 210), sheet("small", 210, 148), sheet("power", 297, 210)] };

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

test("a board is one sheet of layers, its index beside it, and nothing depends on the tool's version", () => {
  const { kicadVersion: _version, ...withoutVersion } = BOARD;
  const layout = layoutPlot(withoutVersion);
  assert.equal(PLOT_SCHEMA_VERSION, 2);
  assert.deepEqual(layout.bounds, [0, 0, 40, 30]);
  assert.deepEqual(layout.sheets.map(({ x, y, background, svg }) => [x, y, background, svg]), [[0, 0, "#001023", null]]);
  assert.deepEqual(layout.sheets[0].layers.map(({ id, kind, side, unpoured }) => [id, kind, side, unpoured]), [
    ["B.Fab", "fab", "back", null], ["B.Cu", "copper", "back", '<svg id="B.Cu-bare"/>'], ["F.Cu", "copper", "front", null],
    ["F.SilkS", "silk", "front", null], ["Edge.Cuts", "outline", "both", null], ["drills", "drill", "both", null]
  ]);
  assert.equal(layout.board, INDEX);
  assert.equal(layout.unrouted, 2);
  assert.equal(layoutPlot(SCHEMATIC).board, null);
  assert.equal(layoutPlot(SCHEMATIC).sheets[0].layers, null);
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
  assert.throws(() => layoutPlot({ ...BOARD, schemaVersion: 1 }), /schemaVersion 1.*Update cadgen and the app together/);
  assert.throws(() => layoutPlot({ ...BOARD, sheets: [] }), /non-empty array/);
  assert.throws(() => layoutPlot({ ...BOARD, sheets: [{ ...BOARD.sheets[0], layers: [] }] }), /"blinky".*no SVG and no layers/);
  assert.throws(() => layoutPlot({ ...SCHEMATIC, sheets: [{ ...SCHEMATIC.sheets[0], svg: "" }] }), /"root".*no SVG and no layers/);
  assert.throws(() => layoutPlot({ ...BOARD, sheets: [{ ...BOARD.sheets[0], layers: [{ ...LAYERS[0], svg: " " }] }] }), /layers\[0\] \(B\.Fab\) carries no SVG/);
  assert.throws(() => layoutPlot({ ...BOARD, sheets: [{ ...BOARD.sheets[0], layers: [{ ...LAYERS[0], side: "top" }] }] }), /side "top"; a layer is front, back, both/);
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
    translate(...args) { calls.push(["translate", ...args]); },
    scale(...args) { calls.push(["scale", ...args]); },
    fillRect(...args) { calls.push(["fillRect", this.fillStyle, ...args]); },
    drawImage(image, ...args) { calls.push(["drawImage", image, ...args]); },
    fillStyle: ""
  };
  return { ctx, calls };
}

/** A board's decoded layers, as loadSheetImages hands them over: names for pictures. */
const boardImages = () => [LAYERS.map(({ id, unpoured }) => ({ id, poured: id, unpoured: unpoured ? `${id} bare` : null }))];
const drawnImages = (calls) => calls.filter(([name]) => name === "drawImage").map(([, image]) => image);

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

test("a board draws every layer back to front, poured, seen from the top: KiCad's picture", () => {
  const layout = layoutPlot(BOARD);
  const placed = sheetImages(layout, boardImages());
  assert.deepEqual(placed.map(({ layer, kind, sheet, x, y, width, height }) => [layer, kind, sheet, x, y, width, height]), LAYERS.map(({ id, kind }) => [id, kind, 0, 0, 0, 40, 30]));
  const { ctx, calls } = recorder(400, 300);
  drawPlot(ctx, layout, { transform: fitPlotTransform(layout, 400, 300), images: placed });
  assert.deepEqual(drawnImages(calls), ["B.Fab", "B.Cu", "F.Cu", "F.SilkS", "Edge.Cuts", "drills"]);
  assert.deepEqual(calls.filter(([name]) => name === "fillRect"), [["fillRect", "#001023", 0, 0, 40, 30]]);
  assert.ok(!calls.some(([name]) => name === "scale"), "nothing is mirrored from the top");
});

test("a view draws the layers it names, the copper without its pours, or the board from below", () => {
  const layout = layoutPlot(BOARD);
  const placed = sheetImages(layout, boardImages());
  const draw = (view) => {
    const { ctx, calls } = recorder(400, 300);
    drawPlot(ctx, layout, { transform: { scale: 10, offsetX: 0, offsetY: 0 }, images: placed, view });
    return calls;
  };
  assert.deepEqual(drawnImages(draw({ layers: ["F.Cu", "B.Cu", "drills"] })), ["B.Cu", "F.Cu", "drills"]);
  assert.deepEqual(drawnImages(draw({ poured: false })), ["B.Fab", "B.Cu bare", "F.Cu", "F.SilkS", "Edge.Cuts", "drills"]);
  // From below the stack reverses, what goes through the board stays on top, and every layer is
  // mirrored about the sheet's vertical centre line: x -> 2 * sheet.x + width - x.
  const below = draw({ side: "bottom" });
  assert.deepEqual(drawnImages(below), ["F.SilkS", "F.Cu", "B.Cu", "B.Fab", "Edge.Cuts", "drills"]);
  const first = below.findIndex(([name]) => name === "drawImage");
  assert.deepEqual(below.slice(first - 3, first + 2), [["save"], ["translate", 40, 0], ["scale", -1, 1], ["drawImage", "F.SilkS", 0, 0, 40, 30], ["restore"]]);
  assert.equal(mirrorPageX(layout, 0, 12.5), 27.5);
  assert.equal(mirrorPageX(layout, 0, mirrorPageX(layout, 0, 3)), 3);
  // A raster of a view (no layer) is drawn as it is, mirrored or not.
  const { ctx, calls } = recorder(400, 300);
  drawPlot(ctx, layout, { transform: { scale: 10, offsetX: 0, offsetY: 0 }, images: [{ image: "patch", x: 0, y: 0, width: 40, height: 30 }], view: { side: "bottom" } });
  assert.deepEqual(drawnImages(calls), ["patch"]);
  assert.ok(!calls.some(([name]) => name === "scale"));
});

test("courtyards are drawn only when a view names them", () => {
  const courtyards = [layer("B.CrtYd", "courtyard", "back"), ...LAYERS, layer("F.CrtYd", "courtyard", "front")];
  const board = { ...BOARD, sheets: [{ ...BOARD.sheets[0], layers: courtyards }] };
  const layout = layoutPlot(board);
  const images = courtyards.map(({ id, unpoured }) => ({ id, poured: id, unpoured: unpoured ? `${id} bare` : null }));
  const draw = (view) => {
    const { ctx, calls } = recorder(400, 300);
    drawPlot(ctx, layout, { transform: { scale: 10, offsetX: 0, offsetY: 0 }, images: sheetImages(layout, [images]), view });
    return drawnImages(calls);
  };
  // A snapshot or a card (no view), and a view choosing no layers: the board as it is made.
  assert.deepEqual(draw(null), ["B.Fab", "B.Cu", "F.Cu", "F.SilkS", "Edge.Cuts", "drills"]);
  assert.deepEqual(draw({ side: "top" }), ["B.Fab", "B.Cu", "F.Cu", "F.SilkS", "Edge.Cuts", "drills"]);
  assert.deepEqual(draw({ layers: ["F.CrtYd", "F.SilkS"] }), ["F.SilkS", "F.CrtYd"]);
});

test("layer images name each sheet's pictures by layer, a schematic sheet as one", () => {
  assert.deepEqual(layerImages(layoutPlot(BOARD), boardImages())[0].map(({ id, side, poured, unpoured }) => [id, side, poured, unpoured]), [
    ["B.Fab", "back", "B.Fab", null], ["B.Cu", "back", "B.Cu", "B.Cu bare"], ["F.Cu", "front", "F.Cu", null],
    ["F.SilkS", "front", "F.SilkS", null], ["Edge.Cuts", "both", "Edge.Cuts", null], ["drills", "both", "drills", null]
  ]);
  assert.deepEqual(layerImages(layoutPlot(SCHEMATIC), ["a", "b", "c"]).map((layers) => layers.map(({ id, kind, poured }) => [id, kind, poured])), [
    [[null, "sheet", "a"]], [[null, "sheet", "b"]], [[null, "sheet", "c"]]
  ]);
});

test("a board's layers decode with their unpoured pictures, and one that will not decode is named", async () => {
  const layout = layoutPlot(BOARD);
  const URL = { createObjectURL: (blob) => `blob:${blob.parts[0]}`, revokeObjectURL: () => {} };
  class Blob { constructor(parts, options) { this.parts = parts; this.type = options.type; } }
  class Image { decode() { return Promise.resolve(); } }
  const [layers] = await loadSheetImages(layout, { Image, URL, Blob });
  assert.deepEqual(layers.map(({ id, poured, unpoured }) => [id, poured.src, unpoured?.src ?? null]), LAYERS.map(({ id, unpoured }) => [
    id, `blob:<svg id="${id}"/>`, unpoured ? `blob:<svg id="${id}-bare"/>` : null
  ]));
  class BadImage { decode() { return this.src.includes("bare") ? Promise.reject(new Error("bad XML")) : Promise.resolve(); } }
  await assert.rejects(loadSheetImages(layout, { Image: BadImage, URL, Blob }), /Layer B\.Cu \(unpoured\) of sheet 1 of this plot, “blinky”, is not an SVG this browser can draw \(bad XML\)/);
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
