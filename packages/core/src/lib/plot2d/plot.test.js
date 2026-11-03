import assert from "node:assert/strict";
import test from "node:test";

import { zoomLimits, zoomTransform } from "../drawing2d/transform.js";
import {
  PLOT_HAIRLINE_CSS_PX,
  PLOT_SCHEMA_VERSION,
  drawPlot,
  drawPlotImages,
  fitPlotTransform,
  grownOutline,
  layoutPlot,
  mirrorPageX,
  pageToScreen,
  screenToPage,
  viewedLayers,
  visiblePageRect
} from "./plot.js";
import { DIM_OPACITY, HOLE_COLORS, NAME_COLORS, ZONE_OPACITY, layerColor, netnameColor } from "./theme.js";

// A tiny board in the payload's own shape (`docs/plot-payload.md`): a 40 x 30 mm sheet, its
// area, a courtyard, one pad on each copper layer, a track, a pour with its fill and outline, a via's
// rings and hole, a pad's hole, text, a pad's names.
const square = (cx, cy, w, h) => [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
const layer = (id, kind, side, items) => ({ id, kind, side, items });
const LAYERS = [
  layer("area", "area", "both", [{ t: "poly", pts: [[0, 0], [40, 0], [40, 30], [0, 30]], holes: [square(30, 25, 2, 2)] }]),
  layer("B.CrtYd", "courtyard", "back", [{ t: "path", pts: square(30, 10, 4, 3), w: 0.05, closed: true, ref: "#U1" }]),
  layer("B.Cu", "copper", "back", [
    { t: "poly", pts: [[1, 16], [20, 16], [20, 29], [1, 29]], net: "GND", pour: true },
    { t: "path", pts: [[0.5, 15.5], [20.5, 15.5], [20.5, 29.5], [0.5, 29.5]], w: 0, closed: true, net: "GND" },
    { t: "circle", at: [20, 15], r: 0.225, w: 0.15, net: "GND", via: "through" },
    { t: "poly", pts: square(2, 2, 1, 1), ref: "#U1.2", net: "GND" }
  ]),
  layer("Edge.Cuts", "outline", "both", [{ t: "path", pts: [[0, 0], [40, 0], [40, 30], [0, 30]], w: 0.1, closed: true }]),
  layer("F.Mask", "mask", "front", [{ t: "poly", pts: square(14.175, 20, 0.8, 0.95), w: 0.1, ref: "#R1.1" }]),
  layer("F.SilkS", "silk", "front", [{ t: "text", text: "R1", w: 0.15, strokes: [[[14, 18], [15, 18]], [[14, 18], [14, 19]]], ref: "#R1" }]),
  layer("F.Cu", "copper", "front", [
    { t: "path", pts: [[5, 15], [35, 15]], w: 1, net: "VIN" },
    { t: "circle", at: [20, 15], r: 0.225, w: 0.15, net: "GND", via: "through" },
    { t: "poly", pts: square(14.175, 20, 0.8, 0.95), ref: "#R1.1", net: "VIN" },
    { t: "label", kind: "pad", text: "VIN", at: [14.175, 20], size: [0.3, 0.27], angle: 90, w: 0.045, lod: 2.2 }
  ]),
  layer("drills", "drill", "both", [{ t: "circle", at: [2, 2], r: 0.5, w: 0.03, hole: "pad" }]),
  layer("vias", "via", "both", [{ t: "circle", at: [20, 15], r: 0.15, w: 0.03, hole: "via", via: "through" }]),
  layer("ratsnest", "ratsnest", "both", [{ t: "path", pts: [[14.175, 20], [30, 10]], w: 0 }]),
  layer("names", "names", "both", [{ t: "label", kind: "via", text: "GND", at: [20, 15], size: [0.22, 0.22], angle: 0, w: 0.02, lod: 60 }])
];
// A fab note past the board's right edge, as KiCad draws one: the sheet stays the outline's box, the note is drawn.
const NOTE = layer("F.Fab", "fab", "front", [{ t: "text", text: "REV A", w: 0.15, strokes: [[[41, 2], [46, 2]], [[41, 2], [41, 4]]] }]);
const INDEX = { origin: [20, 15], parts: [], pads: [] };
const BOARD = {
  schemaVersion: 4, kind: "board", generator: "pcbnew 10.99", unrouted: 1,
  sheets: [{ name: "blinky", width: 40, height: 30, background: "#001023", layers: LAYERS }], board: INDEX
};
const index = (id) => LAYERS.findIndex((entry) => entry.id === id);

test("a board is one sheet of layers at the page's origin, its index beside it", () => {
  const layout = layoutPlot(BOARD);
  assert.equal(PLOT_SCHEMA_VERSION, 4);
  assert.deepEqual(layout.bounds, [0, 0, 40, 30]);
  // drawing2d's model space is the page with y negated: the same box, flipped.
  assert.deepEqual(layout.modelBounds, [0, -30, 40, 0]);
  // The extent is everything drawn: the outline's stroke reaches a shade past the sheet.
  assert.deepEqual(layout.extent.map((v) => Math.round(v * 1000) / 1000), [-0.05, -0.05, 40.05, 30.05]);
  assert.deepEqual(layout.sheets.map(({ x, y, background, name }) => [x, y, background, name]), [[0, 0, "#001023", "blinky"]]);
  assert.deepEqual(layout.sheets[0].layers.map(({ id, kind, side }) => [id, kind, side]), LAYERS.map(({ id, kind, side }) => [id, kind, side]));
  assert.equal(layout.board, INDEX);
  assert.equal(layout.unrouted, 1);
  assert.equal(layout.generator, "pcbnew 10.99");
  // Every item knows its page box, for leaving it out when it is off screen; a label's is its laid-out strokes'.
  assert.deepEqual(layout.sheets[0].layers[index("F.Cu")].items[0].box, [4.5, 14.5, 35.5, 15.5]);
  assert.deepEqual(layout.sheets[0].layers[index("vias")].items[0].box, [19.835, 14.835, 20.165, 15.165]);
  const [left, top, right, bottom] = layout.sheets[0].layers[index("F.Cu")].items[3].box;
  assert.ok(bottom - top > right - left, "a label turned to read upwards stands taller than wide");
  const { generator: _generator, ...withoutGenerator } = BOARD;
  assert.equal(layoutPlot(withoutGenerator).generator, "");
});

test("the fit frames the sheet the right way up, whatever is drawn past it: its top-left corner is the picture's", () => {
  const layout = layoutPlot({ ...BOARD, sheets: [{ ...BOARD.sheets[0], layers: [...LAYERS, NOTE] }] });
  // The note lies outside the sheet: in the extent, not in what the fit frames.
  assert.deepEqual(layout.bounds, [0, 0, 40, 30]);
  assert.deepEqual(layout.extent.map((v) => Math.round(v * 1000) / 1000), [-0.05, -0.05, 46.075, 30.05]);
  const transform = fitPlotTransform(layout, 600, 1000);
  const [left, top] = pageToScreen(transform, 0, 0);
  const [right, bottom] = pageToScreen(transform, ...layout.bounds.slice(2));
  assert.ok(top < bottom, `page y grows downwards on screen: ${top} -> ${bottom}`);
  // Centred, inside drawing2d's 16 px gutter, the tight axis touching it.
  assert.ok(Math.abs((left + right) / 2 - 300) < 1e-9 && Math.abs((top + bottom) / 2 - 500) < 1e-9);
  assert.ok(Math.abs(right - left - 568) < 1e-9, `width is the binding axis: ${right - left}`);
  // screen = page * scale + offset, on both axes.
  assert.deepEqual(pageToScreen(transform, 10, 20), [10 * transform.scale + transform.offsetX, 20 * transform.scale + transform.offsetY]);
});

test("screenToPage inverts pageToScreen, under a zoom about a point too", () => {
  const layout = layoutPlot(BOARD);
  const fitted = fitPlotTransform(layout, 800, 600);
  const zoomed = zoomTransform(fitted, { x: 610, y: 77 }, 6.5, zoomLimits(fitted.scale));
  for (const transform of [fitted, zoomed]) {
    for (const [x, y] of [[0, 0], [40, 30], [12.5, 400.25]]) {
      const [px, py] = screenToPage(transform, ...pageToScreen(transform, x, y));
      assert.ok(Math.abs(px - x) < 1e-9 && Math.abs(py - y) < 1e-9, `round trip lost (${x}, ${y})`);
    }
  }
  assert.deepEqual(visiblePageRect({ scale: 2, offsetX: -10, offsetY: 4 }, 100, 50), [5, -2, 55, 23]);
  assert.equal(mirrorPageX(layout, 0, 12.5), 27.5);
  assert.equal(mirrorPageX(layout, 0, mirrorPageX(layout, 0, 3)), 3);
});

test("a payload this build does not understand is refused by name", () => {
  const sheet = (changes) => ({ ...BOARD, sheets: [{ ...BOARD.sheets[0], ...changes }] });
  const items = (list) => sheet({ layers: [layer("F.Cu", "copper", "front", list)] });
  assert.throws(() => layoutPlot(null), /plot payload object/);
  assert.throws(() => layoutPlot({ ...BOARD, schemaVersion: 3 }), /schemaVersion 3.*Update cad-server and the app together/);
  assert.throws(() => layoutPlot({ ...BOARD, sheets: [] }), /one board sheet/);
  assert.throws(() => layoutPlot(sheet({ layers: [] })), /"blinky".*carries no layers/);
  assert.throws(() => layoutPlot(sheet({ layers: [{ id: "F.Cu", kind: "copper", side: "top", items: [] }] })), /side "top"; a layer is front, back, both/);
  assert.throws(() => layoutPlot(items([{ t: "svg" }])), /items\[0\] is not a plot item/);
  assert.throws(() => layoutPlot(items([{ t: "poly", pts: [[0, 0], [1, 1]] }])), /\(poly\) needs 3 points or more/);
  assert.throws(() => layoutPlot(items([{ t: "path", pts: [[0, 0], [1, 1]], w: -1 }])), /no non-negative number/);
  assert.throws(() => layoutPlot(items([{ t: "circle", at: [0, 0], r: 0 }])), /positive radius/);
  assert.throws(() => layoutPlot(items([{ t: "text", text: "x", strokes: [[[0, 0]]] }])), /strokes of two points or more/);
  assert.throws(() => layoutPlot(items([{ t: "label", text: "1", at: [0, 0], size: [0, 1] }])), /\(label\) needs a string, a centre, a positive size/);
  assert.throws(() => layoutPlot(items([{ t: "poly", pts: square(0, 0, 1, 1), holes: [[[0, 0]]] }])), /holes that are no rings/);
  assert.throws(() => layoutPlot(items([{ t: "path", pts: [[0, 0], [1, 1], [2, 2]], w: 0, pairs: true }])), /pairs its points/);
  assert.throws(() => layoutPlot(sheet({ width: 0 })), /positive width and height/);
  assert.throws(() => layoutPlot(sheet({ background: "navy" })), /#rrggbb/);
});

test("a view chooses and orders the layers: every layer, named layers, or the board from below", () => {
  const [sheet] = layoutPlot(BOARD).sheets;
  const ids = (view) => viewedLayers(sheet, view).map((entry) => entry.id);
  // Without a view, every layer, as KiCad shows a board it opens: what a snapshot or a card draws.
  assert.deepEqual(ids(null), LAYERS.map(({ id }) => id));
  assert.deepEqual(ids({ side: "top" }), ids(null));
  assert.deepEqual(ids({ layers: ["F.Mask", "B.CrtYd", "F.Cu"] }), ["B.CrtYd", "F.Mask", "F.Cu"]);
  // From below the board's stack reverses; the board's area stays under it, what goes through on top.
  assert.deepEqual(ids({ side: "bottom" }), ["area", "F.Cu", "F.SilkS", "F.Mask", "Edge.Cuts", "B.Cu", "B.CrtYd", "drills", "vias", "ratsnest", "names"]);
});

/** A 2D context that records what it is asked to do, on a canvas of a given device size; `Path2D` is a recording double. */
function recorder(width, height) {
  const calls = [];
  const styles = () => ({ fill: ctx.fillStyle, stroke: ctx.strokeStyle, width: ctx.lineWidth, alpha: ctx.globalAlpha });
  const ctx = {
    canvas: { width, height },
    fillStyle: "", strokeStyle: "", lineWidth: 0, lineCap: "", lineJoin: "", globalAlpha: 1,
    save() { calls.push(["save"]); },
    restore() { calls.push(["restore"]); },
    setTransform(...args) { calls.push(["setTransform", ...args]); },
    fillRect(...args) { calls.push(["fillRect", this.fillStyle, ...args]); },
    beginPath() { calls.push(["beginPath"]); },
    rect(...args) { calls.push(["rect", ...args]); },
    clip() { calls.push(["clip"]); },
    moveTo() {}, lineTo() {}, arc() {}, closePath() {},
    fill(path, rule) { calls.push(["fill", typeof path === "object" ? path?.name ?? null : null, styles(), typeof path === "string" ? path : rule]); },
    stroke(path) { calls.push(["stroke", path?.name ?? null, styles()]); },
    drawImage(image, ...args) { calls.push(["drawImage", image, ...args]); }
  };
  class Path2D {
    constructor() { this.name = `path${Path2D.made += 1}`; }
    moveTo() {} lineTo() {} arc() {} closePath() {}
  }
  Path2D.made = 0;
  return { ctx, calls, Path2D };
}
const painted = (calls) => calls.filter(([name]) => name === "fill" || name === "stroke");

test("a frame is KiCad's canvas, then each layer's items as KiCad draws them", () => {
  const layout = layoutPlot(BOARD);
  const { ctx, calls, Path2D } = recorder(800, 600);
  const transform = { scale: 10, offsetX: 0, offsetY: 0 };
  drawPlot(ctx, layout, { transform, pixelRatio: 2, Path2D });
  // What the canvas shows filled with the board's background (400 x 300 CSS px at 10 px/mm: the sheet here).
  const zero = (value) => (value === 0 ? 0 : value);
  assert.deepEqual(calls.slice(0, 3).map((call) => call.map(zero)), [["save"], ["setTransform", 20, 0, 0, 20, 0, 0], ["fillRect", "#001023", 0, 0, 40, 30]]);
  assert.ok(!calls.some(([name]) => name === "clip"), "nothing is clipped to the sheet");
  const drawn = painted(calls);
  const find = (name, color, test = () => true) => drawn.filter(([kind, , style]) => kind === name && (name === "fill" ? style.fill : style.stroke) === color && test(style));
  const hairline = PLOT_HAIRLINE_CSS_PX / 10;
  // The board's area is filled with its cutout left open.
  assert.equal(drawn.find(([kind, , style]) => kind === "fill" && style.fill === layerColor("area"))[3], "evenodd");
  // A pour at KiCad's zone opacity, everything else opaque.
  assert.deepEqual(find("fill", layerColor("B.Cu")).map(([, , style]) => style.alpha), [ZONE_OPACITY, 1]);
  // A track keeps its width; a courtyard's 0.05 mm line is never thinner than a pixel; a pad is outlined a pixel.
  assert.equal(find("stroke", layerColor("F.Cu"), (style) => style.width === 1).length, 1);
  assert.equal(find("stroke", layerColor("B.CrtYd"), (style) => style.width === hairline).length, 1);
  assert.equal(find("stroke", layerColor("F.Cu"), (style) => style.width === hairline).length, 1);
  // A via is a ring on each copper, in the copper's own colour.
  assert.equal(find("stroke", layerColor("B.Cu"), (style) => style.width === 0.15).length, 1);
  assert.equal(find("stroke", layerColor("F.Cu"), (style) => style.width === 0.15).length, 1);
  // A pad's hole: its golden wall, then the board's background seen through; a via's: white wall, golden hole.
  const fills = drawn.filter(([kind]) => kind === "fill").map(([, , style]) => style.fill);
  const after = (first, second) => fills.indexOf(second, fills.indexOf(first)) > fills.indexOf(first);
  assert.ok(after(HOLE_COLORS.pad.wall, "#001023") && after(HOLE_COLORS.via.wall, HOLE_COLORS.via.fill));
  // A surface pad's names, on its copper in the copper's name colour, at their own stroke; the via's name waits
  // for a closer view (its level of detail is 60 px/mm).
  assert.equal(find("stroke", netnameColor("F.Cu"), (style) => style.width === 0.045).length, 1);
  assert.equal(find("stroke", NAME_COLORS.via).length, 0);
  const close = recorder(800, 600);
  drawPlot(close.ctx, layout, { transform: { scale: 100, offsetX: -1500, offsetY: -1200 }, Path2D: close.Path2D });
  assert.equal(painted(close.calls).filter(([kind, , style]) => kind === "stroke" && style.stroke === NAME_COLORS.via).length, 1);
  // So does the track's net name, which the payload does not carry (4 mm over its 1 mm width: 14.3 px/mm); then it
  // is written along the track in the copper's name colour, a pen a twelfth of the width.
  const trackName = (calls) => painted(calls).filter(([kind, , style]) => kind === "stroke" && style.stroke === netnameColor("F.Cu") && style.width === 1 / 12);
  assert.equal(trackName(calls).length, 0);
  assert.equal(trackName(close.calls).length, 1);
  // Each item's path is made once and kept: a second frame makes no new path.
  const made = Path2D.made;
  drawPlot(ctx, layout, { transform, pixelRatio: 2, Path2D });
  assert.equal(Path2D.made, made);
  assert.throws(() => drawPlot(ctx, layout, { transform: { scale: 0, offsetX: 0, offsetY: 0 }, Path2D }), /positive scale/);
});

test("a view draws the layers it names, the copper without its pours, or the board mirrored from below", () => {
  const layout = layoutPlot(BOARD);
  const draw = (view) => {
    const { ctx, calls, Path2D } = recorder(400, 300);
    drawPlot(ctx, layout, { transform: { scale: 10, offsetX: 0, offsetY: 0 }, view, Path2D });
    return calls;
  };
  const pours = (calls) => painted(calls).filter(([name, , style]) => name === "fill" && style.alpha === ZONE_OPACITY).length;
  assert.equal(pours(draw(null)), 1);
  assert.equal(pours(draw({ poured: false })), 0, "the pour's fill is left out; its outline stays");
  const masked = painted(draw({ layers: ["F.Mask"] }));
  assert.deepEqual(masked.map(([name, , style]) => [name, name === "fill" ? style.fill : style.stroke, style.width]),
    [["fill", layerColor("F.Mask"), 0], ["stroke", layerColor("F.Mask"), 0.1]], "a mask opening is filled and grown by its margin");
  // A via's copper goes with its hole, a pad's names with the names layer: a view without them draws neither.
  const copperOnly = painted(draw({ layers: ["F.Cu"] }));
  assert.ok(!copperOnly.some(([name, , style]) => name === "stroke" && style.width === 0.15), "no via ring without the vias layer");
  assert.ok(!copperOnly.some(([name, , style]) => name === "stroke" && style.stroke === netnameColor("F.Cu")), "no names without the names layer");
  assert.ok(painted(draw({ layers: ["F.Cu", "vias", "names"] })).some(([name, , style]) => name === "stroke" && style.width === 0.15));
  // From below, the board is mirrored about the sheet's vertical centre line (x -> 40 - x).
  const below = draw({ side: "bottom" });
  assert.ok(below.some(([name, a, , , d, e]) => name === "setTransform" && a === -10 && d === 10 && e === 400), "mirrored about x = 20");
  // What the canvas does not show is not drawn: zoomed onto the top-left corner, the via at (20, 15) is off it.
  const { ctx, calls, Path2D } = recorder(100, 100);
  drawPlot(ctx, layout, { transform: { scale: 100, offsetX: 0, offsetY: 0 }, Path2D });
  const colours = painted(calls).map(([name, , style]) => (name === "fill" ? style.fill : style.stroke));
  assert.ok(!colours.includes(HOLE_COLORS.via.fill), "the via is off the canvas");
  assert.ok(colours.includes(layerColor("Edge.Cuts")), "the outline reaches it");
});

test("knocked-out text is its box with the letters cut out, and a pad's clearance is outlined round it", () => {
  const knocked = { t: "text", text: "KO", w: 0.15, strokes: [[[1, 1], [2, 1]]], knockout: [[0.5, 0.5], [2.5, 0.5], [2.5, 1.5], [0.5, 1.5]] };
  const pad = { t: "poly", pts: square(5, 5, 1, 1), ref: "#U1.1", net: "A", clearance: 0.2 };
  const layout = layoutPlot({ ...BOARD, sheets: [{ ...BOARD.sheets[0], layers: [layer("F.SilkS", "silk", "front", [knocked]), layer("F.Cu", "copper", "front", [pad])] }] });
  const { ctx, calls, Path2D } = recorder(400, 300);
  drawPlot(ctx, layout, { transform: { scale: 10, offsetX: 0, offsetY: 0 }, Path2D });
  // Without a canvas of its own to cut on (this recording double), the letters are drawn in the board's background.
  const drawn = painted(calls).map(([name, , style]) => [name, name === "fill" ? style.fill : style.stroke]);
  assert.deepEqual(drawn.slice(0, 2), [["fill", layerColor("F.SilkS")], ["stroke", "#001023"]]);
  // The clearance outline: a hairline, then the pad.
  assert.deepEqual(painted(calls).slice(2).map(([name, , style]) => [name, style.width]), [["stroke", 0.1], ["fill", 0.1], ["stroke", 0.1]]);
  const grown = grownOutline(square(0, 0, 2, 1), 0.5);
  const xs = grown.map(([x]) => x);
  const ys = grown.map(([, y]) => y);
  assert.deepEqual([Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)].map((v) => Math.round(v * 1e6) / 1e6), [-1.5, 1.5, -1, 1]);
});

test("what the file draws past the outline is drawn, not clipped to the sheet, and from below it is mirrored too", () => {
  const layout = layoutPlot({ ...BOARD, sheets: [{ ...BOARD.sheets[0], layers: [...LAYERS, NOTE] }] });
  const strokesOf = (calls) => painted(calls).filter(([name, , style]) => name === "stroke" && style.stroke === layerColor("F.Fab"));
  // The pane shows x 0..50 mm: the sheet (0..40) and the note beside it (41..46).
  const whole = recorder(500, 300);
  drawPlot(whole.ctx, layout, { transform: { scale: 10, offsetX: 0, offsetY: 0 }, Path2D: whole.Path2D });
  assert.equal(strokesOf(whole.calls).length, 1, "the note past the edge is drawn");
  // A pane panned onto the note alone, past the sheet: the note is still drawn, and the sheet's rectangle is not filled on it.
  const beside = recorder(100, 100);
  drawPlot(beside.ctx, layout, { transform: { scale: 10, offsetX: -405, offsetY: 0 }, Path2D: beside.Path2D });
  assert.equal(strokesOf(beside.calls).length, 1, "the note is drawn where the sheet is not");
  // Showing nothing of the plot — 100 mm to its right — draws nothing at all.
  const away = recorder(100, 100);
  drawPlot(away.ctx, layout, { transform: { scale: 10, offsetX: -1000, offsetY: 0 }, Path2D: away.Path2D });
  assert.equal(painted(away.calls).length, 0);
  // From below the note mirrors to x -6..-1, left of the sheet: a pane there shows it.
  const mirrored = recorder(100, 100);
  drawPlot(mirrored.ctx, layout, { transform: { scale: 10, offsetX: 70, offsetY: 0 }, view: { side: "bottom" }, Path2D: mirrored.Path2D });
  assert.equal(strokesOf(mirrored.calls).length, 1, "the note is drawn at its mirrored place");
});

test("the pane's frame is the sheet's background and the rasters placed over it, in page space", () => {
  const layout = layoutPlot(BOARD);
  const { ctx, calls } = recorder(1200, 800);
  const transform = { scale: 2, offsetX: 0, offsetY: 0 };
  drawPlotImages(ctx, layout, { transform, pixelRatio: 2, images: [
    { image: "patch", x: 0, y: 0, width: 40, height: 30 },
    { image: "elsewhere", x: 500, y: 0, width: 40, height: 30 },
    { image: "empty", x: 0, y: 0, width: 0, height: 5 }
  ] });
  assert.deepEqual(calls, [
    ["save"], ["setTransform", 4, 0, 0, 4, 0, 0], ["fillRect", "#001023", 0, 0, 40, 30], ["drawImage", "patch", 0, 0, 40, 30], ["restore"]
  ]);
});

test("without a Path2D the items are drawn into the context afresh", () => {
  const layout = layoutPlot(BOARD);
  const { ctx, calls } = recorder(400, 300);
  drawPlot(ctx, layout, { transform: { scale: 10, offsetX: 0, offsetY: 0 }, Path2D: undefined });
  assert.ok(painted(calls).length > 0 && painted(calls).every(([, path]) => path === null));
});

test("the active layer tops the stack, Dim fades every other but the board's area, and the zones and tracks take their opacities", () => {
  const layout = layoutPlot(BOARD);
  const [sheet] = layout.sheets;
  const ids = (view) => viewedLayers(sheet, view).map((entry) => entry.id);
  // Active: drawn last of the board's stack, under what goes through the board; from below too.
  assert.deepEqual(ids({ active: "B.Cu" }).slice(-6), ["F.Cu", "B.Cu", "drills", "vias", "ratsnest", "names"]);
  assert.deepEqual(ids({ side: "bottom", active: "F.Mask" }).slice(-5), ["F.Mask", "drills", "vias", "ratsnest", "names"]);
  const alphas = (view) => {
    const { ctx, calls, Path2D } = recorder(800, 600);
    drawPlot(ctx, layout, { transform: { scale: 10, offsetX: 0, offsetY: 0 }, view, Path2D });
    return painted(calls).map(([name, , style]) => [name === "fill" ? style.fill : style.stroke, style.alpha, style.width]);
  };
  const at = (list, color, width) => list.filter(([paint, , w]) => paint === color && (width === undefined || w === width)).map(([, alpha]) => alpha);
  // The pour at the zones' opacity, the 1 mm VIN track at the tracks'.
  const set = alphas({ zones: 0.25, tracks: 0.5 });
  assert.deepEqual(at(set, layerColor("B.Cu")).slice(0, 1), [0.25]);
  assert.deepEqual(at(set, layerColor("F.Cu"), 1), [0.5]);
  // Dim with F.Cu active: F.Cu as it is, the back copper and the courtyard faded, the board's area not.
  const dimmed = alphas({ dim: "F.Cu" });
  assert.deepEqual(at(dimmed, layerColor("F.Cu"), 1), [1]);
  assert.deepEqual(at(dimmed, layerColor("B.CrtYd")), [DIM_OPACITY]);
  assert.deepEqual(at(dimmed, layerColor("area")), [1]);
  assert.deepEqual(at(dimmed, layerColor("B.Cu")).slice(0, 1), [DIM_OPACITY * ZONE_OPACITY]);
});
