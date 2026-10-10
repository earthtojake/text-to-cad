import assert from "node:assert/strict";
import test from "node:test";

import { createBoardIndex } from "./boardIndex.js";
import { nearestOnSegment, pointInPolygon } from "./geometry.js";
import { drawBoardOverlay } from "./boardOverlay.js";

// A 40 x 30 mm sheet whose script origin sits at sheet (5, 25): script (10, 5) is sheet (15, 20).
const rect = (cx, cy, w, h) => [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
const BOARD = {
  origin: [5, 25],
  nets: [{ name: "VIN", class: "Power" }, { name: "GND", class: "Default" }, { name: "OUT", class: "Default" }],
  parts: [
    { ref: "R1", value: "10k", footprint: "Resistor_SMD:R_0603_1608Metric", side: "top", at: [15, 20], rotation: 0,
      fields: { MPN: "RC0603" }, script: "board.py:12", outline: rect(15, 20, 3, 1.4) },
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
  findings: [{ check: "drc", severity: "warning", type: "silk_overlap", description: "Silkscreen clearance",
    items: [{ text: "Reference field of R1", ref: "#R1", at: [15, 20] }, { text: "Segment", ref: null, at: null }] }],
};

test("the script frame is y up from the board's origin, wherever the sheet is laid out", () => {
  const index = createBoardIndex(BOARD, { x: 2, y: 3 });
  assert.deepEqual(index.toScript([17, 23]), [10, 5]);
  assert.deepEqual(index.toPage([10, 5]), [17, 23]);
});

test("a press picks the most specific thing under it, filtered by the Select mode", () => {
  const index = createBoardIndex(BOARD);
  assert.equal(index.pick([14.175, 20]).selector, "#R1.1");
  assert.equal(index.pick([14.175, 20], { mode: "parts" }).selector, "#R1");
  assert.equal(index.pick([15.825, 20], { mode: "nets" }).selector, "#net:GND");
  // A track is its net at the nearest point of its centreline, to the hundredth of a millimetre.
  assert.equal(index.pick([14.3, 16]).selector, "#net:VIN@x9.18y9");
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
  const copper = index.resolve("#net:VIN@x9.18y9");
  assert.equal(copper.item.kind, "track");
  assert.deepEqual(index.resolve("#@x1y2").page, [6, 23]);
  assert.equal(index.resolve("#C99"), null);
  assert.equal(index.resolve("#net:NOPE"), null);
  assert.equal(index.resolve("o1.f2"), null);
  assert.deepEqual(index.extent(index.resolve("#R1.1")).map((v) => Math.round(v * 1000) / 1000), [13.775, 19.525, 14.575, 20.475]);
});

test("a measurement snaps to pad centres, vias, holes and the outline", () => {
  const index = createBoardIndex(BOARD);
  assert.equal(index.snap([14.2, 20.1], { tolerance: 0.5 }).label, "R1.1");
  assert.equal(index.snap([14.2, 20.1], { tolerance: 0.5 }).selector, "#R1.1");
  assert.equal(index.snap([3.1, 3], { tolerance: 0.5 }).kind, "hole");
  assert.equal(index.snap([39.9, 29.9], { tolerance: 0.5, kinds: ["outline"] }).kind, "outline");
  assert.equal(index.snap([10, 10], { tolerance: 0.5 }), null);
});

test("checks keep their items' references and places", () => {
  const index = createBoardIndex(BOARD);
  assert.equal(index.findings[0].type, "silk_overlap");
  assert.deepEqual(index.findings[0].items.map((item) => item.ref), ["#R1", ""]);
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

test("a net is highlighted whole, a check rung, and what is off screen left out", () => {
  const index = createBoardIndex(BOARD);
  const { ctx, marks, filled } = recordingContext();
  drawBoardOverlay(ctx, index, {
    transform: { scale: 10, offsetX: 0, offsetY: 0 }, width: 400, height: 300, dim: true,
    selection: [index.resolve("#net:GND")], hover: index.resolve("#U1.2"), markers: [[15, 20]],
    measure: { points: [[14.175, 20]], draft: [20, 15] },
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

// What a pick and a snap must answer, worked out the slow way: every item tested, none skipped.
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
    if (part.outline.length > 2 && pointInPolygon(at, part.outline)) found.push({ rank: mode === "parts" ? 0 : 3, side: facing(part.side), size: part.area, distance: 0, order, selector: `#${part.ref}` });
  });
  if (mode === "nets") index.zones.forEach((zone, order) => {
    if (pointInPolygon(at, zone.outline)) found.push({ rank: 4, side: facing(layerSide(zone.layer)), size: zone.area, distance: 0, order, net: zone.net });
  });
  found.sort((a, b) => a.side - b.side || a.rank - b.rank || a.distance - b.distance || a.size - b.size || a.order - b.order);
  for (const hit of found) {
    if (hit.selector !== undefined) { if (hit.selector) return hit.selector; continue; }
    if (hit.net) return mode === "nets" ? `#net:${hit.net}` : `#net:${hit.net}@`;
  }
  return null;
}

test("a pick and a snap answer what a scan of the whole board would", () => {
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
  const board = { origin: [0, 40], parts, pads, tracks, vias, zones: [{ net: "N0", layer: "B.Cu", outline: rect(30, 20, 50, 30) }], holes: [], outline: [], findings: [] };
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
    const snapped = index.snap(at, { tolerance: 1.5 });
    const targets = [...index.pads.values()].map((pad) => pad.at).concat(index.vias.map((via) => via.at), index.tracks.flatMap((track) => [track.points[0], track.points.at(-1)]));
    const nearest = Math.min(...targets.map((target) => Math.hypot(at[0] - target[0], at[1] - target[1])));
    assert.equal(snapped ? snapped.distance : null, nearest <= 1.5 ? nearest : null, JSON.stringify(at));
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

test("a finding reads its summary, and KiCad's words when a payload has none", () => {
  const index = createBoardIndex({ ...BOARD, findings: [
    { check: "drc", severity: "error", type: "clearance", description: "Clearance violation", summary: "The SDA track and the SCL track are 0.15 mm apart; the rules need 0.2 mm", items: [] },
    { check: "drc", severity: "error", type: "clearance", description: "Clearance violation", items: [] },
  ] });
  assert.equal(index.findings[0].summary, "The SDA track and the SCL track are 0.15 mm apart; the rules need 0.2 mm");
  assert.equal(index.findings[1].summary, "Clearance violation");
});
