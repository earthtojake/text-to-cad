import assert from "node:assert/strict";
import test from "node:test";

import { createBoardIndex } from "./boardIndex.js";
import { nearestOnSegment, pointInPolygon } from "./geometry.js";
import { drawBoardOverlay } from "./boardOverlay.js";

// A 40 x 30 mm sheet cut from a page whose origin sits at sheet (5, 25): KiCad's (10, -5) is sheet (15, 20).
const rect = (cx, cy, w, h) => [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
const BOARD = {
  origin: [5, 25],
  nets: [{ name: "VIN", class: "Power" }, { name: "GND", class: "Default" }, { name: "OUT", class: "Default" }],
  parts: [
    { ref: "R1", value: "10k", footprint: "Resistor_SMD:R_0603_1608Metric", side: "top", at: [15, 20], rotation: 0,
      fields: { MPN: "RC0603" }, outline: rect(15, 20, 3, 1.4) },
    { ref: "U1", value: "AMP", footprint: "Test:SOT4", side: "bottom", at: [30, 10], rotation: 90, fields: {}, outline: rect(30, 10, 4, 3) },
  ],
  pads: [
    { part: "R1", number: "1", name: "~", net: "VIN", type: "passive", side: "top", at: [14.175, 20], polygon: rect(14.175, 20, 0.8, 0.95) },
    { part: "R1", number: "2", name: "~", net: "GND", type: "passive", side: "top", at: [15.825, 20], polygon: rect(15.825, 20, 0.8, 0.95) },
    { part: "U1", number: "2", name: "OUT", net: "OUT", type: "output", side: "bottom", at: [31.5, 9.05], polygon: rect(31.5, 9.05, 0.8, 0.95) },
    { part: "U1", number: "3", name: "GND", net: "GND", type: "passive", side: "bottom", at: [28.5, 10.95], polygon: rect(28.5, 10.95, 0.8, 0.95) },
    { part: "U1", number: "3", name: "GND", net: "GND", type: "passive", side: "bottom", at: [28.5, 9.05], polygon: rect(28.5, 9.05, 0.8, 0.95) },
  ],
  tracks: [{ net: "VIN", layer: "F.Cu", width: 0.5, points: [[14.175, 20], [14.175, 12]] }],
  vias: [{ net: "GND", at: [20, 15], diameter: 0.6, drill: 0.3 }],
  zones: [{ net: "GND", layer: "B.Cu", outline: [[0, 0], [40, 0], [40, 30], [0, 30]] }],
  holes: [{ at: [3, 3], diameter: 2.75 }],
  outline: [[[0, 0], [40, 0], [40, 30], [0, 30], [0, 0]]],
};

test("a reference's point is KiCad's frame, y down from the page origin, wherever the sheet is laid out", () => {
  const index = createBoardIndex(BOARD, { x: 2, y: 3 });
  assert.deepEqual(index.toScript([17, 23]), [10, -5]);
  assert.deepEqual(index.toPage([10, -5]), [17, 23]);
});

test("a press picks the most specific thing under it, filtered by the Select mode", () => {
  const index = createBoardIndex(BOARD);
  assert.equal(index.pick([14.175, 20]).selector, "#R1.1");
  assert.equal(index.pick([14.175, 20], { mode: "parts" }).selector, "#R1");
  assert.equal(index.pick([15.825, 20], { mode: "nets" }).selector, "#net:GND");
  // A track is its net at the nearest point of its centreline, to the hundredth of a millimetre.
  assert.equal(index.pick([14.3, 16]).selector, "#net:VIN@x9.18y-9");
  assert.equal(index.pick([20.1, 15]).selector.startsWith("#net:GND@"), true);
  // Bare board inside a pour is nothing under All, and the pour's net under Nets.
  assert.equal(index.pick([2, 28]), null);
  assert.equal(index.pick([2, 28], { mode: "nets" }).selector, "#net:GND");
  assert.equal(index.pointSelector([5, 25]), "#@x0y0");
});

test("a pin with two pads is one pin, and a pick on either names it", () => {
  const index = createBoardIndex(BOARD);
  assert.equal(index.pick([28.5, 9.05]).selector, "#U1.3");
  assert.equal(index.pick([28.5, 10.95]).selector, "#U1.3");
  assert.equal(index.nets.get("GND").pads.length, 2, "R1.2 and U1.3, each once");
});

test("the side looked at decides between what overlaps", () => {
  const board = { ...BOARD, parts: [...BOARD.parts, { ref: "C9", value: "1u", footprint: "x", side: "top", at: [30, 10], rotation: 0, fields: {}, outline: rect(30, 10, 1, 1) }] };
  const index = createBoardIndex(board);
  assert.equal(index.pick([30, 10], { mode: "parts" }).selector, "#C9");
  assert.equal(index.pick([30, 10], { mode: "parts", view: "bottom" }).selector, "#U1");
});

test("a reference resolves to what it names, or to nothing on a board that lacks it", () => {
  const index = createBoardIndex(BOARD);
  assert.equal(index.resolve("#U1.3").pad.net, "GND");
  assert.equal(index.resolve("U1").part.side, "bottom");
  assert.deepEqual(index.resolve("#net:GND").net.pads.map((pad) => `${pad.ref}.${pad.number}`), ["R1.2", "U1.3"]);
  const copper = index.resolve("#net:VIN@x9.18y-9");
  assert.equal(copper.item.kind, "track");
  assert.deepEqual(index.resolve("#@x1y2").page, [6, 27]);
  assert.equal(index.resolve("#C99"), null);
  assert.equal(index.resolve("#net:NOPE"), null);
  assert.equal(index.resolve("o1.f2"), null);
  assert.deepEqual(index.extent(index.resolve("#R1.1")).map((v) => Math.round(v * 1000) / 1000), [13.775, 19.525, 14.575, 20.475]);
});

test("a point in a polygon", () => {
  assert.ok(pointInPolygon([1, 1], [[0, 0], [2, 0], [2, 2], [0, 2]]));
});

// A context that keeps what was filled and stroked, in device pixels, through the transforms set.
export function recordingContext() {
  let matrix = [1, 0, 0, 1, 0, 0];
  let points = [];
  const stack = [];
  const marks = [];
  const apply = (x, y) => [matrix[0] * x + matrix[2] * y + matrix[4], matrix[1] * x + matrix[3] * y + matrix[5]];
  const ctx = {
    save() { stack.push(matrix); }, restore() { matrix = stack.pop(); },
    setTransform(a, b, c, d, e, f) { matrix = [a, b, c, d, e, f]; },
    beginPath() { points = []; }, closePath() {}, setLineDash() {},
    moveTo(x, y) { points.push(apply(x, y)); }, lineTo(x, y) { points.push(apply(x, y)); }, arc(x, y) { points.push(apply(x, y)); },
    fillRect() { marks.push({ op: "fillRect", style: ctx.fillStyle, points: [] }); },
    fill() { marks.push({ op: "fill", style: ctx.fillStyle, points }); },
    stroke() { marks.push({ op: "stroke", style: ctx.strokeStyle, points }); },
  };
  const boxOf = (list) => [Math.min(...list.map((p) => p[0])), Math.min(...list.map((p) => p[1])), Math.max(...list.map((p) => p[0])), Math.max(...list.map((p) => p[1]))];
  return { ctx, marks, filled: (style) => marks.filter((mark) => mark.op === "fill" && mark.style === style).map((mark) => boxOf(mark.points)) };
}

test("the overlay draws the selection where it is, and from the bottom where the mirror puts it", () => {
  const index = createBoardIndex(BOARD);
  const frame = { transform: { scale: 10, offsetX: 0, offsetY: 0 }, pixelRatio: 2, width: 400, height: 300 };
  const selected = (mirrorX = null) => {
    const { ctx, filled } = recordingContext();
    drawBoardOverlay(ctx, index, { ...frame, mirrorX, selection: [index.resolve("#R1.1")] });
    return filled("#8dc5ff");
  };
  // R1.1 spans x 13.775..14.575, y 19.525..20.475 mm: at 10 px/mm and a pixel ratio of 2, x 275.5..291.5.
  const [top] = selected();
  assert.deepEqual(top.map((v) => Math.round(v * 10) / 10), [275.5, 390.5, 291.5, 409.5]);
  // Seen from the bottom, mirrored about x = 20: x 25.425..26.225 mm.
  const [bottom] = selected(20);
  assert.deepEqual(bottom.map((v) => Math.round(v * 10) / 10), [508.5, 390.5, 524.5, 409.5]);
});

test("Placement draws the pads, the holes and airwires under the highlight; a poured net's only when selected", () => {
  const index = createBoardIndex(BOARD);
  const frame = { transform: { scale: 10, offsetX: 0, offsetY: 0 }, width: 400, height: 300 };
  const plain = recordingContext();
  drawBoardOverlay(plain.ctx, index, frame);
  assert.equal(plain.marks.length, 0, "without Placement the overlay draws nothing of its own");
  const airwire = (mark) => mark.op === "stroke" && mark.style === "rgba(232, 238, 245, 0.8)";
  // GND is two pins (R1.2 and U1.3, drawn as two pads), joined by its pour: no airwire until it is selected.
  const placed = recordingContext();
  drawBoardOverlay(placed.ctx, index, { ...frame, placement: true });
  // Seen from the top: U1's three bottom pads first, then R1's two; then the board's mounting hole.
  assert.equal(placed.filled("rgba(77, 127, 196, 0.9)").length, 3);
  assert.equal(placed.filled("rgba(200, 52, 52, 0.9)").length, 2);
  // The hole at (3, 3) mm, 2.75 mm across: recorded from its edge (x + r) round its centre, at 10 px/mm.
  assert.deepEqual(placed.filled("#000000"), [[30, 30, 43.75, 30]]);
  assert.equal(placed.marks.filter(airwire).length, 0);
  const { ctx, marks } = recordingContext();
  drawBoardOverlay(ctx, index, { ...frame, placement: true, dim: true, selection: [index.resolve("#net:GND")] });
  const dimmed = marks.findIndex((mark) => mark.op === "fillRect");
  assert.ok(dimmed > 0, "the board steps back behind the net in focus");
  assert.ok(marks.slice(dimmed).some((mark) => mark.op === "stroke" && mark.style === "#8dc5ff" && mark.points.length === 2),
    "GND's airwire drawn in the selection's colour");
});

test("a net is highlighted whole, and what is off screen left out", () => {
  const index = createBoardIndex(BOARD);
  const { ctx, marks, filled } = recordingContext();
  drawBoardOverlay(ctx, index, {
    transform: { scale: 10, offsetX: 0, offsetY: 0 }, width: 400, height: 300, dim: true,
    selection: [index.resolve("#net:GND")], hover: index.resolve("#U1.2"),
  });
  assert.equal(marks[0].op, "fillRect", "the rest of the board steps back first");
  // R1.2 and both pads of U1.3, and the via: GND's copper.
  assert.equal(filled("#8dc5ff").length, 4);
  assert.equal(filled("rgba(141, 197, 255, 0.55)").length, 1, "the hovered pad");
  // Zoomed in on the top-left corner, at 100 px/mm, R1 and U1 lie off screen: only the pour is drawn.
  const zoomed = recordingContext();
  drawBoardOverlay(zoomed.ctx, index, { transform: { scale: 100, offsetX: 0, offsetY: 0 }, width: 400, height: 300, selection: [index.resolve("#net:GND")] });
  assert.equal(zoomed.filled("#8dc5ff").length, 0);
  assert.equal(zoomed.filled("rgba(141, 197, 255, 0.12)").length, 1, "the pour reaches the corner");
});

// What a pick must answer, worked out the slow way: every item tested, none skipped.
function scanPick(index, at, { mode, view, tolerance }) {
  const facing = (side) => {
    const front = side === "top" || side === "front"; const back = side === "bottom" || side === "back";
    if (side === "both") return 0;
    return view === "bottom" ? (back ? 0 : front ? 2 : 1) : (front ? 0 : back ? 2 : 1);
  };
  const layerSide = (layer) => (layer.startsWith("F.") ? "front" : layer.startsWith("B.") ? "back" : "inner");
  const near = (polygon) => {
    if (pointInPolygon(at, polygon)) return 0;
    return Math.min(...polygon.map((p, i) => nearestOnSegment(at, p, polygon[(i + 1) % polygon.length]).distance));
  };
  const found = [];
  if (mode !== "parts") index.padShapes.forEach((shape, order) => {
    const distance = near(shape.polygon);
    if (distance <= tolerance) found.push({ rank: 0, side: facing(shape.side), size: shape.area, distance, order, selector: mode === "nets" ? (shape.net ? `#net:${shape.net}` : null) : `#${shape.ref}.${shape.number}` });
  });
  if (mode === "all" || mode === "nets") {
    index.vias.forEach((via, order) => {
      const distance = Math.hypot(at[0] - via.at[0], at[1] - via.at[1]) - via.diameter / 2;
      if (distance <= tolerance) found.push({ rank: 1, side: 0, size: via.diameter, distance: Math.max(0, distance), order, net: via.net });
    });
    index.tracks.forEach((track, order) => {
      const distance = Math.min(...track.points.slice(1).map((p, i) => nearestOnSegment(at, track.points[i], p).distance)) - track.width / 2;
      if (distance <= tolerance) found.push({ rank: 2, side: facing(layerSide(track.layer)), size: track.width, distance: Math.max(0, distance), order, net: track.net });
    });
  }
  if (mode === "all" || mode === "parts") [...index.parts.values()].forEach((part, order) => {
    if (part.outline.length > 2 && pointInPolygon(at, part.outline)) found.push({ rank: mode === "parts" ? 0 : 7, side: facing(part.side), size: part.area, distance: 0, order, selector: `#${part.ref}` });
  });
  // A pour by its outline under All; anywhere inside it for its net.
  if (mode === "nets" || mode === "all") index.zones.forEach((zone, order) => {
    const inside = mode === "nets" && pointInPolygon(at, zone.outline);
    const edge = Math.min(...zone.outline.map((p, i) => nearestOnSegment(at, p, zone.outline[(i + 1) % zone.outline.length]).distance));
    if (inside || edge <= tolerance) found.push({ rank: 6, side: facing(layerSide(zone.layer)), size: zone.area, distance: inside ? 0 : edge, order, net: zone.net });
  });
  found.sort((a, b) => a.side - b.side || a.rank - b.rank || a.distance - b.distance || a.size - b.size || a.order - b.order);
  for (const hit of found) {
    if (hit.selector !== undefined) { if (hit.selector) return hit.selector; continue; }
    if (hit.net) return mode === "nets" ? `#net:${hit.net}` : `#net:${hit.net}@`;
  }
  return null;
}

test("a pick answers what a scan of the whole board would", () => {
  // A seeded board of a few hundred pads and tracks, dense enough that most presses land on something.
  let state = 9;
  const random = () => { state = (state * 1664525 + 1013904223) >>> 0; return state / 4294967296; };
  const parts = []; const pads = []; const tracks = []; const vias = [];
  for (let at = 0; at < 60; at += 1) {
    const cx = 2 + random() * 56; const cy = 2 + random() * 36;
    parts.push({ ref: `U${at}`, side: at % 3 ? "top" : "bottom", at: [cx, cy], outline: rect(cx, cy, 3, 2) });
    for (let pin = 1; pin <= 4; pin += 1) pads.push({ part: `U${at}`, number: String(pin), net: `N${(at + pin) % 9}`, side: at % 3 ? "top" : "bottom", polygon: rect(cx - 1.5 + pin * 0.6, cy - 0.8, 0.4, 0.5) });
  }
  for (let at = 0; at < 200; at += 1) {
    const x = random() * 60; const y = random() * 40; const length = random() * 25;
    tracks.push({ net: at % 5 ? `N${at % 9}` : "", layer: at % 2 ? "F.Cu" : "B.Cu", width: 0.2 + random() * 0.3, points: [[x, y], [x + length * (random() - 0.5), y + length * (random() - 0.5)]] });
  }
  for (let at = 0; at < 40; at += 1) vias.push({ net: `N${at % 9}`, at: [random() * 60, random() * 40], diameter: 0.6 });
  const board = { origin: [0, 40], parts, pads, tracks, vias, zones: [{ net: "N0", layer: "B.Cu", outline: rect(30, 20, 50, 30) }], holes: [], outline: [] };
  const index = createBoardIndex(board);
  for (let press = 0; press < 250; press += 1) {
    const at = [random() * 60, random() * 40];
    for (const mode of ["all", "parts", "pads", "nets"]) {
      for (const [view, tolerance] of [["top", 0.3], ["bottom", 1.2], ["top", 0]]) {
        const picked = index.pick(at, { mode, view, tolerance })?.selector ?? null;
        const expected = scanPick(index, at, { mode, view, tolerance });
        assert.equal(expected?.endsWith("@") ? picked?.replace(/@x.*$/, "@") : picked, expected, JSON.stringify({ at, mode, view, tolerance }));
      }
    }
  }
});

test("past copper on no net, a pick takes what lies under it", () => {
  const board = { ...BOARD, tracks: [...BOARD.tracks, { net: "", layer: "F.Cu", width: 0.4, points: [[13, 20], [17, 20]] }],
    pads: [...BOARD.pads, { part: "R1", number: "3", name: "", net: "", type: "passive", side: "top", at: [15, 21], polygon: rect(15, 21, 0.4, 0.4) }] };
  const index = createBoardIndex(board);
  // Under All, the net-less track over R1's body is no answer: R1 is.
  assert.equal(index.pick([15, 20]).selector, "#R1");
  // Under Nets, a pad on no net inside the ground pour is the pour's net.
  assert.equal(index.pick([15, 21], { mode: "nets" }).selector, "#net:GND");
});

test("Measure's ends snap to pad, via and hole centres, track ends and outline corners, within its reach", () => {
  const index = createBoardIndex(BOARD);
  assert.deepEqual(index.snap([14.3, 20.1], { tolerance: 0.3 }), { point: [14.175, 20], kind: "center", what: "pad" });
  assert.deepEqual(index.snap([20.1, 15.1], { tolerance: 0.3 }), { point: [20, 15], kind: "center", what: "via" });
  assert.deepEqual(index.snap([3.2, 2.9], { tolerance: 0.3 }), { point: [3, 3], kind: "center", what: "hole" });
  assert.deepEqual(index.snap([14.2, 12.1], { tolerance: 0.3 }), { point: [14.175, 12], kind: "vertex", what: "track" });
  assert.deepEqual(index.snap([39.9, 29.9], { tolerance: 0.3 }), { point: [40, 30], kind: "vertex", what: "outline" });
  // The nearest wins; nothing that near, nothing at all.
  assert.equal(index.snap([14.5, 20], { tolerance: 1 }).point[0], 14.175);
  assert.equal(index.snap([10, 25], { tolerance: 0.3 }), null);
});

test("a pick takes what its kinds tick: no pads takes the copper or the part under them", () => {
  const index = createBoardIndex(BOARD);
  assert.equal(index.pick([14.175, 20], { kinds: { pads: false, copper: true, parts: true } }).selector, "#net:VIN@x9.18y-5");
  assert.equal(index.pick([15.825, 20], { kinds: { pads: false, copper: true, parts: true } }).selector, "#R1");
  assert.equal(index.pick([15.825, 20], { kinds: { pads: false, copper: false, parts: false } }), null);
});

// The board above as KiCad saves it today: every item by its uuid, the texts and the dimensions in
// the index, the graphics in the plot's layers (what the viewer picks them from).
const T = (n) => `7a1c0000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const SAVED = {
  ...BOARD,
  tracks: [{ ...BOARD.tracks[0], id: T(1) }],
  vias: [{ ...BOARD.vias[0], id: T(2), layers: ["F.Cu", "B.Cu"], type: "through" }],
  zones: [{ ...BOARD.zones[0], id: T(3), name: "GND pour", filled: 1200 }, { ...BOARD.zones[0], layer: "F.Cu", id: T(3), name: "GND pour" }],
  texts: [
    { id: T(4), text: "R1", layer: "F.SilkS", at: [15, 17.5], angle: 0, size: 1, part: "R1", polygon: rect(15, 17.5, 1.6, 1.2) },
    { id: T(5), text: "blinky", layer: "F.SilkS", at: [30, 25], angle: 0, size: 1.5, polygon: rect(30, 25, 6, 1.8) },
  ],
  dimensions: [{ id: T(6), type: "aligned", layer: "Dwgs.User", value: "40 mm", lines: [[[0, 0], [0, -3]], [[0, -3], [40, -3]], [[40, -3], [40, 0]]], polygon: rect(20, -4, 6, 1.2) }],
};
const SHEET = { x: 0, y: 0, layers: [
  { id: "F.SilkS", kind: "silk", side: "front", items: [
    { t: "path", pts: [[13.7, 19.5], [16.3, 19.5]], w: 0.12, ref: "#R1", id: T(7) },
    { t: "path", pts: [[25, 5], [35, 5]], w: 0.2, id: T(8) },
  ] },
  { id: "Edge.Cuts", kind: "outline", side: "both", items: [{ t: "path", pts: [[0, 0], [40, 0], [40, 30], [0, 30]], w: 0.1, closed: true, id: T(9), shape: "rect" }] },
] };

test("an item is picked by the uuid KiCad saved it with: a track, a via, a text, a graphic, a pour by its outline", () => {
  const index = createBoardIndex(SAVED, SHEET);
  assert.equal(index.pick([14.3, 16]).selector, `#track:${T(1)}`);
  assert.equal(index.pick([20.1, 15]).selector, `#via:${T(2)}`);
  assert.equal(index.pick([30, 25]).selector, `#text:${T(5)}`);
  // A part's own text before the part; its own graphics are the part's, unless Graphics is the filter.
  assert.equal(index.pick([15, 17.5], { tolerance: 0.1 }).selector, `#text:${T(4)}`);
  assert.equal(index.pick([15, 19.5], { tolerance: 0.1 }).selector, "#R1");
  assert.equal(index.pick([15, 19.5], { mode: "shapes", tolerance: 0.1 }).selector, `#shape:${T(7)}`);
  assert.equal(index.pick([30, 5.05], { tolerance: 0.1 }).selector, `#shape:${T(8)}`);
  // Under All, a pour by its outline alone: bare board inside it is nothing; Zones takes it anywhere inside.
  assert.equal(index.pick([2, 28]), null);
  assert.equal(index.pick([0.05, 15], { kinds: { zones: true } , tolerance: 0.1 }).selector, `#zone:${T(3)}`);
  assert.equal(index.pick([2, 28], { mode: "zones" }).selector, `#zone:${T(3)}`);
  assert.equal(index.pick([20, -3], { mode: "dimensions", tolerance: 0.1 }).selector, `#dimension:${T(6)}`);
  // A layer the view does not draw is not picked from.
  assert.equal(index.pick([30, 25], { layers: new Set(["F.Cu", "B.Cu", "vias"]) }), null);
  assert.equal(index.pick([20.1, 15], { layers: new Set(["F.Cu"]) }), null, "no vias drawn");
});

test("an item resolves by its uuid; a point and an area keep their layer", () => {
  const index = createBoardIndex(SAVED, SHEET);
  const zone = index.resolve(`#zone:${T(3).toUpperCase()}`);
  assert.deepEqual([zone.kind, zone.item.layers, zone.item.filled], ["zone", ["B.Cu", "F.Cu"], 1200]);
  assert.equal(index.resolve(`#shape:${T(9)}`).item.shape, "rect");
  assert.equal(index.resolve(`#text:${T(4)}`).item.part, "R1");
  assert.equal(index.resolve(`#dimension:${T(6)}`).item.value, "40 mm");
  assert.equal(index.resolve(`#track:${T(99)}`), null);
  assert.deepEqual(index.resolve("#F.Cu@x1y2"), { kind: "point", at: [1, 2], layer: "F.Cu", page: [6, 27], selector: "#F.Cu@x1y2" });
  const area = index.resolve("#B.Cu@x10y-10..x0y0");
  assert.deepEqual([area.kind, area.layer, area.box], ["area", "B.Cu", [5, 15, 15, 25]]);
  assert.deepEqual(index.extent(area), [5, 15, 15, 25]);
  assert.equal(index.pointSelector([5, 25], "F.Cu"), "#F.Cu@x0y0");
  assert.equal(index.pointSelector([5, 25], "vias"), "#@x0y0", "the plot's own layers are no layer a reference names");
  assert.equal(index.areaSelector([25, 35], [5, 15], "F.SilkS"), "#F.SilkS@x0y-10..x20y10");
});

test("one of the copies of a footprint that share uuids is named under its footprint's uuid", () => {
  const F = (n) => `f1000000-0000-4000-8000-00000000000${n}`;
  const sheet = { layers: [{ id: "F.SilkS", kind: "silk", side: "front", items: [
    { t: "path", pts: [[1, 1], [2, 1]], w: 0.1, id: `${F(1)}/${T(7)}` }, { t: "path", pts: [[5, 1], [6, 1]], w: 0.1, id: `${F(2)}/${T(7)}` }] }] };
  const index = createBoardIndex({ ...BOARD, parts: [] }, sheet);
  assert.equal(index.pick([5.5, 1], { mode: "shapes", tolerance: 0.1 }).selector, `#shape:${F(2)}/${T(7)}`);
  assert.deepEqual(index.resolve(`#shape:${F(1)}/${T(7)}`).item.points[0], [1, 1]);
  assert.equal(index.resolve(`#shape:${T(7)}`), null, "the uuid alone names two");
});

test("an area holds what lies wholly inside it, on its layer alone when it names one", () => {
  const index = createBoardIndex(SAVED, SHEET);
  const held = (box, layer) => Object.fromEntries(Object.entries(index.within(box, layer)).map(([key, list]) => [key, list.length]));
  // Round R1 (13.5..16.5 x 19.3..20.7, its pads, its text above it and its silkscreen line).
  assert.deepEqual(held([12, 16, 18, 21]), { parts: 1, pads: 2, tracks: 0, vias: 0, zones: 0, texts: 1, dimensions: 0, shapes: 1, holes: 0 });
  assert.deepEqual(held([12, 16, 18, 21], "F.Cu"), { parts: 1, pads: 2, tracks: 0, vias: 0, zones: 0, texts: 0, dimensions: 0, shapes: 0, holes: 0 });
  // U1 is on the bottom: the bottom's area holds it, and its pads.
  assert.equal(index.within([27, 7, 33, 13], "B.Cu").parts[0].ref, "U1");
  assert.equal(index.within([27, 7, 33, 13], "F.Cu").parts.length, 0);
  assert.equal(index.within([-1, -1, 41, 31], "B.Cu").vias.length, 1, "a through via is on every copper layer");
});

test("the overlay lights a text's box, a graphic's ink, an area and the box being dragged", () => {
  const index = createBoardIndex(SAVED, SHEET);
  const frame = { transform: { scale: 10, offsetX: 0, offsetY: 0 }, width: 400, height: 300 };
  const { ctx, marks, filled } = recordingContext();
  drawBoardOverlay(ctx, index, { ...frame, selection: [index.resolve(`#text:${T(5)}`), index.resolve("#@x0y-10..x10y0")],
    hover: index.resolve(`#shape:${T(8)}`), draft: [30, 1, 35, 4] });
  // The draft first, then the text's box (27..33 x 24.1..25.9 mm at 10 px/mm) and the area (KiCad's 0..10 x -10..0 is page 5..15 x 15..25).
  assert.deepEqual(filled("rgba(141, 197, 255, 0.16)").map((box) => box.map((v) => Math.round(v))), [[300, 10, 350, 40], [270, 241, 330, 259], [50, 150, 150, 250]]);
  assert.ok(marks.some((mark) => mark.op === "stroke" && mark.style === "rgba(141, 197, 255, 0.55)"), "the hovered graphic's stroke");
});
