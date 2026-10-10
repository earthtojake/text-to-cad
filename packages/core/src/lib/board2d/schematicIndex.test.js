import assert from "node:assert/strict";
import test from "node:test";

import { createSchematicIndex } from "./schematicIndex.js";
import { drawBoardOverlay } from "./boardOverlay.js";

// Two plotted sheets, the second laid out at page (10, 300), and a third the plot did not draw.
const rect = (cx, cy, w, h) => [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
const LAYOUT = [{ name: "amp", x: 0, y: 0 }, { name: "Power", x: 10, y: 300 }];
const SCHEMATIC = {
  sheets: [{ name: "amp", path: "/", file: "amp.kicad_sch", title: "Amp" }, { name: "Power", path: "/Power/", file: "power.kicad_sch" },
    { name: "Gone", path: "/Gone/", file: "gone.kicad_sch" }],
  parts: [
    { ref: "R1", value: "10k", lib: "Device:R", footprint: "Resistor_SMD:R_0603_1608Metric", fields: { MPN: "RC0603" }, script: "amp.py:12", dnp: false,
      units: [{ unit: 1, sheet: 0, at: [50, 50], rotation: 0, mirror: null, outline: rect(50, 50, 2, 5) }] },
    { ref: "U1", value: "AMP", lib: "Test:AMP", footprint: "Test:SOT4", fields: {}, script: null, dnp: false,
      units: [{ unit: 1, sheet: 0, at: [80, 50], rotation: 0, mirror: null, outline: rect(80, 50, 10, 10) },
        { unit: 2, sheet: 1, at: [30, 30], rotation: 90, mirror: "y", outline: rect(30, 30, 6, 6) }] },
    { ref: "X1", value: "XTAL", lib: "Device:Crystal", footprint: "", fields: {}, script: null, dnp: true,
      units: [{ unit: 1, sheet: 2, at: [20, 20], rotation: 0, mirror: null, outline: rect(20, 20, 4, 4) }] },
  ],
  pins: [
    { part: "R1", number: "1", name: "~", type: "passive", unit: 1, sheet: 0, net: "VIN", at: [50, 46.19], end: [50, 47.5], hidden: false },
    { part: "R1", number: "2", name: "~", type: "passive", unit: 1, sheet: 0, net: "GND", at: [50, 53.81], end: [50, 52.5], hidden: false },
    { part: "U1", number: "1", name: "IN", type: "input", unit: 1, sheet: 0, net: "VIN", at: [72.38, 50], end: [75, 50], hidden: false },
    // A pin common to both units, drawn by each.
    { part: "U1", number: "4", name: "VCC", type: "power_in", unit: 1, sheet: 0, net: "+5V", at: [80, 42.38], end: [80, 45], hidden: false },
    { part: "U1", number: "4", name: "VCC", type: "power_in", unit: 2, sheet: 1, net: "+5V", at: [30, 24.92], end: [30, 27], hidden: false },
    { part: "U1", number: "5", name: "NC", type: "no_connect", unit: 1, sheet: 0, net: "unconnected-(U1-NC-Pad5)", at: [87.62, 50], end: [85, 50], hidden: true },
  ],
  wires: [
    { net: "VIN", sheet: 0, points: [[50, 46.19], [50, 43.18]] },
    { net: "VIN", sheet: 0, points: [[50, 43.18], [72.38, 43.18]] },
    { net: "VIN", sheet: 0, points: [[72.38, 43.18], [72.38, 50]] },
    { net: "GND", sheet: 0, points: [[50, 53.81], [50, 57.15]] },
  ],
  labels: [
    { net: "VIN", sheet: 0, text: "VIN", kind: "global", at: [60, 43.18], outline: [[60, 42.5], [66, 42.5], [66, 43.86], [60, 43.86]] },
    { net: "GND", sheet: 0, text: "GND", kind: "power", at: [50, 57.15], outline: rect(50, 58.4, 2.6, 2.5) },
  ],
  junctions: [{ net: "VIN", sheet: 0, at: [50, 43.18] }],
  noConnects: [],
  nets: [{ name: "+5V", class: "Power" }, { name: "GND", class: "" }, { name: "VIN", class: "Power" }],
};

test("a press picks the most specific thing under it, filtered by the Select mode", () => {
  const index = createSchematicIndex(SCHEMATIC, LAYOUT);
  assert.equal(index.document, "schematic");
  assert.equal(index.pick([50, 47]).selector, "#R1.1", "a pin before its symbol");
  assert.equal(index.pick([50.6, 50]).selector, "#R1", "inside the body");
  assert.equal(index.pick([50, 47], { mode: "parts" }).selector, "#R1", "a pin is its symbol under Parts");
  assert.equal(index.pick([50.6, 50], { mode: "pads" }), null);
  assert.equal(index.pick([50, 47], { mode: "nets" }).selector, "#net:VIN");
  assert.equal(index.pick([61, 43.3]).selector, "#net:VIN", "a label is its net");
  assert.equal(index.pick([55, 43.2]).selector, "#net:VIN", "so is a wire");
  assert.equal(index.pick([50, 58.5]).selector, "#net:GND", "and a power symbol");
  assert.equal(index.pick([5, 5]), null);
  // A hidden pin is not on the sheet to press.
  assert.equal(index.pick([87, 50], { mode: "pads" }), null);
});

test("a symbol's units and a common pin are found on every sheet they are drawn on", () => {
  const index = createSchematicIndex(SCHEMATIC, LAYOUT);
  // Unit 2 is on the second sheet, laid out at page (10, 300).
  assert.equal(index.pick([40, 330]).selector, "#U1");
  assert.equal(index.pick([40, 325.5]).selector, "#U1.4");
  assert.equal(index.pick([80, 44]).selector, "#U1.4");
  assert.equal(index.pads.size, 5, "U1.4 is one pin");
  assert.equal(index.shapesOf(index.pads.get("U1.4")).length, 2);
  assert.deepEqual(index.nets.get("+5V").pads.map((pin) => `${pin.ref}.${pin.number}`), ["U1.4"]);
  // A sheet the plot did not draw holds nothing to point at.
  assert.equal(index.parts.get("X1").units.length, 0);
  assert.equal(index.pick([20, 20], { mode: "parts" }), null);
});

test("a reference resolves to what it names; points and copper belong to boards", () => {
  const index = createSchematicIndex(SCHEMATIC, LAYOUT);
  assert.equal(index.resolve("#U1").part.units.length, 2);
  assert.equal(index.resolve("#U1.1").pad.net, "VIN");
  const vin = index.resolve("#net:VIN").net;
  assert.equal(vin.class, "Power");
  assert.equal(vin.wires.length, 3);
  assert.equal(vin.labels.length, 1);
  assert.deepEqual(vin.pads.map((pin) => `${pin.ref}.${pin.number}`), ["R1.1", "U1.1"]);
  assert.equal(index.resolve("#net:VIN@x1y2"), null);
  assert.equal(index.resolve("#@x1y2"), null);
  assert.equal(index.resolve("#Z9"), null);
  assert.deepEqual(index.extent(index.resolve("#net:VIN")), [50, 42.5, 75, 50], "its pins whole: U1.1 reaches its body at x 75");
  assert.deepEqual(index.extent(index.resolve("#R1.2")), [50, 52.5, 50, 53.81]);
});

test("the overlay draws a schematic's selection on its paper", () => {
  const calls = [];
  const ctx = new Proxy({}, { get: (target, key) => (key in target ? target[key] : (...args) => calls.push(key)), set: (target, key, value) => { target[key] = value; calls.push(`${String(key)}=${value}`); return true; } });
  const index = createSchematicIndex(SCHEMATIC, LAYOUT);
  drawBoardOverlay(ctx, index, {
    transform: { scale: 4, offsetX: 0, offsetY: 0 }, width: 400, height: 300, dim: true,
    selection: [index.resolve("#net:VIN"), index.resolve("#U1")], hover: index.resolve("#R1.2"),
  });
  assert.ok(calls.includes("fillStyle=rgba(245, 244, 239, 0.72)"), "the rest is washed out, not darkened");
  assert.ok(calls.includes("strokeStyle=#1f6feb"));
  assert.ok(calls.filter((call) => call === "stroke").length > 8);
});

test("a schematic's ERC findings, each item on its sheet's page", () => {
  const index = createSchematicIndex({ ...SCHEMATIC, findings: [
    { check: "erc", severity: "error", type: "pin_not_connected", description: "Pin not connected", summary: "U2 pin 7 (VDD) isn't connected to anything",
      items: [{ text: "Symbol U2 Pin 7", ref: "#U2.7", at: [50.8, 25.4], sheet: 0 }, { text: "Symbol U9", ref: "#U9", at: null, sheet: null }, { text: "Symbol U3 Pin 1", ref: "#U3.1", at: [30, 24.92], sheet: 1 }] },
  ] }, LAYOUT);
  assert.equal(index.findings.length, 1);
  assert.equal(index.findings[0].summary, "U2 pin 7 (VDD) isn't connected to anything");
  assert.equal(index.findings[0].items[0].ref, "#U2.7");
  assert.deepEqual(index.findings[0].items[0].at, [50.8, 25.4]);
  assert.deepEqual(index.findings[0].items[2].at, [40, 324.92], "an item on the second sheet is offset by where that sheet is laid out");
  assert.equal(index.findings[0].items[1].at, null);
});

test("a schematic payload from before ERC has no findings", () => {
  assert.deepEqual([...createSchematicIndex(SCHEMATIC, LAYOUT).findings], []);
});
