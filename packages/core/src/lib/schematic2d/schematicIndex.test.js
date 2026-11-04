import assert from "node:assert/strict";
import test from "node:test";

import { layoutPlot } from "../plot2d/plot.js";
import { SCHEMATIC_PICK_KINDS, createSchematicIndex, createSchematicPage } from "./schematicIndex.js";
import { drawSchematicOverlay } from "./schematicOverlay.js";

// A root sheet placing a child: a resistor R1 (its body, its pin 1 on +5V, its reference), a wire with a
// junction on +5V, a local label, the child sheet's symbol with its pin on /MID; and the child, its C1.
const box = (x0, y0, x1, y1) => [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]];
const SCHEMATIC = {
  root: "divider.kicad_sch",
  sheets: [
    { path: "/", name: "/", file: "divider.kicad_sch", page: "1", parent: null, id: "r", pins: [] },
    { path: "/Load/", name: "Load", file: "load.kicad_sch", page: "2", parent: "/", id: "s", at: [120, 40], size: [30, 20],
      pins: [{ name: "IN", shape: "input", at: [120, 50], net: "/MID", id: "sp" }] }
  ],
  parts: [
    { ref: "C1", value: "100n", footprint: "", units: [{ unit: 1, sheet: "/Load/", at: [50, 50], angle: 0, id: "c1" }], fields: {} },
    { ref: "R1", value: "10k", footprint: "R_0603", units: [{ unit: 1, sheet: "/", at: [100, 60], angle: 0, id: "b1" }], fields: {} }
  ],
  pins: [
    { part: "R1", number: "1", name: "", type: "passive", sheet: "/", at: [100, 55], net: "+5V", hidden: false },
    { part: "R1", number: "2", name: "", type: "passive", sheet: "/", at: [100, 65], net: "/MID", hidden: false },
    { part: "C1", number: "1", name: "", type: "passive", sheet: "/Load/", at: [50, 45], net: "/MID", hidden: false }
  ],
  wires: [{ kind: "wire", sheet: "/", points: [[100, 50], [100, 55]], net: "+5V", id: "a1" },
    { kind: "wire", sheet: "/", points: [[100, 65], [120, 65]], net: "/MID", id: "a2" }],
  junctions: [{ sheet: "/", at: [100, 50], net: "+5V", id: "a3" }],
  labels: [{ kind: "local", text: "MID", sheet: "/", at: [110, 65], angle: 0, net: "/MID", id: "a4" }],
  no_connects: [], bus_entries: [],
  nets: [{ name: "+5V", pins: ["R1.1"], sheets: ["/"] }, { name: "/MID", pins: ["C1.1", "R1.2"], sheets: ["/", "/Load/"] }]
};
const PAGE = {
  schemaVersion: 4, kind: "schematic", generator: "eeschema", schematic: SCHEMATIC,
  sheets: [{ name: "/", path: "/", width: 297, height: 210, background: "#F5F4EF", layers: [
    { id: "page", kind: "sheet", side: "both", items: [{ t: "path", pts: box(0, 0, 297, 210), w: 0, closed: true }] },
    { id: "sheets", kind: "sheet_box", side: "both", items: [
      { t: "path", pts: box(120, 40, 150, 60), w: 0.15, closed: true, ref: "#sheet:/Load/", id: "s" },
      { t: "path", pts: [[120, 49.5], [121, 50], [120, 50.5]], w: 0.15, closed: true, role: "pin", net: "/MID", ref: "#sheet:/Load/", id: "s" }] },
    { id: "symbols", kind: "symbol", side: "both", items: [
      { t: "poly", pts: box(99, 57.5, 101, 62.5), fill: "background", ref: "#R1", id: "b1" },
      { t: "path", pts: box(99, 57.5, 101, 62.5), w: 0.25, closed: true, ref: "#R1", id: "b1" }] },
    { id: "pins", kind: "pin", side: "both", items: [
      { t: "path", pts: [[100, 55], [100, 57.5]], w: 0.15, ref: "#R1.1", net: "+5V" },
      { t: "path", pts: [[100, 62.5], [100, 65]], w: 0.15, ref: "#R1.2", net: "/MID" }] },
    { id: "wires", kind: "wire", side: "both", items: [
      { t: "path", pts: [[100, 50], [100, 55]], w: 0.15, net: "+5V", id: "a1" },
      { t: "path", pts: [[100, 65], [120, 65]], w: 0.15, net: "/MID", id: "a2" }] },
    { id: "junctions", kind: "junction", side: "both", items: [{ t: "circle", at: [100, 50], r: 0.45, w: 0, net: "+5V", id: "a3" }] },
    { id: "fields", kind: "field", side: "both", items: [{ t: "text", text: "R1", w: 0.15, strokes: [[[103, 59], [105, 59], [105, 61]]], field: "Reference", ref: "#R1" }] },
    { id: "labels", kind: "label", side: "both", items: [{ t: "text", text: "MID", w: 0.15, strokes: [[[110, 64], [113, 64]], [[110, 63], [113, 63]]], label: "local", net: "/MID", id: "a4" }] }
  ] }]
};

test("the index resolves every kind of reference to what it names and the sheets it is on", () => {
  const index = createSchematicIndex(SCHEMATIC);
  assert.deepEqual(index.order, ["/", "/Load/"]);
  assert.equal(index.sheetName("/"), "divider");
  assert.deepEqual(index.childrenOf("/"), ["/Load/"]);
  assert.deepEqual(index.trail("/Load/"), ["/", "/Load/"]);
  const of = (selector) => { const found = index.resolve(selector); return found && [found.kind, found.selector, found.sheets]; };
  assert.deepEqual(of("#R1"), ["part", "#R1", ["/"]]);
  assert.deepEqual(of("#C1.1"), ["pin", "#C1.1", ["/Load/"]]);
  assert.deepEqual(of("#net:/MID"), ["net", "#net:/MID", ["/", "/Load/"]]);
  assert.deepEqual(of("#sheet:Load"), ["sheet", "#sheet:/Load/", ["/"]]);
  assert.deepEqual(of("#wire:a2"), ["wire", "#wire:a2", ["/"]]);
  assert.deepEqual(of("#label:a4"), ["label", "#label:a4", ["/"]]);
  assert.equal(index.resolve("#bus:a2"), null, "a wire is not a bus");
  for (const missing of ["#R9", "#R1.9", "#net:NOPE", "#sheet:/Power/", "#track:a1"]) assert.equal(index.resolve(missing), null, missing);
});

test("a press picks the most specific thing under it that the filter takes; a box takes what lies inside it", () => {
  const layout = layoutPlot(PAGE);
  const index = createSchematicIndex(layout.schematic);
  const page = createSchematicPage(index, layout.sheets[0]);
  const at = (x, y, kinds) => page.pick([x, y], { tolerance: 0.5, ...(kinds ? { kinds } : {}) })?.selector ?? null;
  assert.equal(at(100, 56), "#R1.1", "a pin before the wire it ends");
  assert.equal(at(100, 50), "#junction:a3", "a junction before its wire");
  assert.equal(at(100, 52), "#wire:a1");
  assert.equal(at(111, 63.5), "#label:a4");
  assert.equal(at(104, 59), "#R1", "a field is its part's");
  assert.equal(at(100, 60), "#R1", "inside the body");
  assert.equal(at(135, 45), "#sheet:/Load/", "inside the sheet's box");
  assert.equal(at(120.4, 50), "#net:/MID", "a sheet pin is its net");
  assert.equal(at(100, 57.7), "#R1.1", "a pin's end inside its body");
  assert.equal(at(100, 57.7, ["symbols"]), "#R1", "without Pins, the body round it");
  assert.equal(at(100, 52, ["labels"]), null);
  assert.equal(at(200, 150), null);
  assert.deepEqual(page.within([95, 45, 106, 66], { kinds: SCHEMATIC_PICK_KINDS }).sort(), ["#R1", "#R1.1", "#R1.2", "#junction:a3", "#wire:a1"].sort());
  assert.equal(page.sheetAt([130, 50]), "/Load/");
  assert.equal(page.sheetAt([10, 10]), null);
  assert.deepEqual(page.snap([100.2, 55.1], { tolerance: 0.5 }), { point: [100, 55], kind: "pin" });
  // What a reference names, drawn: a net's every piece on this sheet, a part's body, field and pins.
  const kinds = (selector) => page.itemsOf(index.resolve(selector)).map((entry) => entry.kind).sort();
  assert.deepEqual(kinds("#net:/MID"), ["label", "pin", "sheet_box", "wire"]);
  assert.deepEqual(kinds("#R1"), ["field", "pin", "pin", "symbol", "symbol"]);
  assert.deepEqual(page.extent(index.resolve("#wire:a2")).map((v) => Math.round(v * 100) / 100), [99.93, 64.93, 120.08, 65.08]);
  assert.equal(page.extent(index.resolve("#C1")), null, "C1 is not on this sheet");
});

test("the overlay steps the sheet back for a net and draws the selection in its blue over its shadow", () => {
  const layout = layoutPlot(PAGE);
  const index = createSchematicIndex(layout.schematic);
  const page = createSchematicPage(index, layout.sheets[0]);
  const calls = [];
  const ctx = {
    fillStyle: "", strokeStyle: "", lineWidth: 0,
    save() {}, restore() {}, setTransform() {}, beginPath() {}, moveTo() {}, lineTo() {}, arc() {}, closePath() {},
    fillRect(...args) { calls.push(["fillRect", this.fillStyle, ...args]); },
    fill() { calls.push(["fill", this.fillStyle]); },
    stroke() { calls.push(["stroke", this.strokeStyle]); },
    strokeRect() { calls.push(["strokeRect"]); }
  };
  const net = page.itemsOf(index.resolve("#net:+5V"));
  drawSchematicOverlay(ctx, layout.sheets[0], { transform: { scale: 4, offsetX: 0, offsetY: 0 }, selected: net, dim: true });
  assert.deepEqual(calls[0], ["fillRect", "rgba(245, 244, 239, 0.72)", 0, 0, 297, 210], "the paper over the rest");
  assert.deepEqual(calls.slice(1).map(([name, style]) => `${name} ${style}`), [
    "stroke rgba(31, 111, 235, 0.28)", "stroke rgba(31, 111, 235, 0.28)", "fill rgba(31, 111, 235, 0.28)", "stroke rgba(31, 111, 235, 0.28)",
    "stroke #1f6feb", "stroke #1f6feb", "fill #1f6feb"
  ]);
});
