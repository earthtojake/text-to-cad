import assert from "node:assert/strict";
import test from "node:test";
import { createBoardIndex } from "@text-to-cad/core/lib/board2d/boardIndex.js";
import { boardTreeAncestors, boardTreeNodeIds, buildBoardTree, partKind } from "./boardTree.js";
import { boardReferenceFacts } from "./boardFacts.js";

const square = (cx, cy, w, h) => [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
const BOARD = {
  origin: [0, 0],
  nets: [{ name: "VIN", class: "Power" }, { name: "GND", class: "Default" }, { name: "unconnected-(U1-NC-Pad4)", class: "Default" }],
  parts: [
    { ref: "C10", value: "1u", footprint: "Capacitor_SMD:C_0603", side: "top", at: [5, 25], rotation: 90, fields: { LCSC: "C15849" }, script: "hat.py:40", outline: square(5, 25, 1, 2) },
    { ref: "C2", value: "100n", footprint: "Capacitor_SMD:C_0603", side: "bottom", at: [8, 25], rotation: 0, fields: {}, outline: square(8, 25, 2, 1), dnp: true },
    { ref: "U1", value: "AMS1117", footprint: "Package_TO_SOT_SMD:SOT-223", side: "top", at: [20, 20], rotation: 0, fields: {}, outline: square(20, 20, 7, 7) },
  ],
  pads: [
    { part: "C10", number: "1", name: "~", net: "VIN", type: "passive", side: "top", at: [5, 25.8], polygon: square(5, 25.8, 0.8, 0.8) },
    { part: "C10", number: "2", name: "~", net: "GND", type: "passive", side: "top", at: [5, 24.2], polygon: square(5, 24.2, 0.8, 0.8) },
    { part: "C2", number: "1", name: "~", net: "VIN", type: "passive", side: "bottom", at: [7.2, 25], polygon: square(7.2, 25, 0.8, 0.8) },
    { part: "U1", number: "2", name: "VO", net: "VIN", type: "power_out", side: "top", at: [17, 20], polygon: square(17, 20, 1, 1) },
    { part: "U1", number: "2", name: "VO", net: "VIN", type: "power_out", side: "top", at: [23, 20], polygon: square(23, 20, 3, 2) },
    { part: "U1", number: "4", name: "NC", net: "unconnected-(U1-NC-Pad4)", type: "no_connect", side: "top", at: [17, 18], polygon: square(17, 18, 1, 1) },
  ],
  tracks: [{ net: "VIN", layer: "F.Cu", width: 1, points: [[5, 25.8], [17, 25.8], [17, 20]] }],
  vias: [{ net: "GND", at: [10, 10], diameter: 0.6, drill: 0.3 }], zones: [], holes: [], outline: [],
};
const index = createBoardIndex(BOARD);

test("the tree is parts by kind, then nets: what KiCad reported is the alert card's", () => {
  const tree = buildBoardTree(index);
  assert.deepEqual(tree.roots.map((node) => `${node.label} ${node.detail}`), ["Parts 3", "Nets 2"]);
  const parts = tree.roots[0].children;
  assert.deepEqual(parts.map((node) => node.label), ["ICs", "Capacitors"]);
  assert.deepEqual(parts[1].children.map((node) => node.label), ["C2", "C10"], "natural order");
  // A pin of two pads is one row; a pad row says its pin's name and net.
  assert.deepEqual(parts[0].children[0].children.map((node) => [node.label, node.detail]), [["2", "VO · VIN"], ["4", "NC · unconnected-(U1-NC-Pad4)"]]);
  // KiCad's names for a pin on nothing are not nets anyone routes.
  assert.deepEqual(tree.roots[1].children.map((node) => node.label), ["GND", "VIN"]);
  assert.deepEqual(tree.roots[1].children[1].children.map((node) => node.label), ["C2.1", "C10.1", "U1.2"]);
  assert.equal(partKind("TP3"), "Test points");
  assert.equal(partKind("ZZ1"), "Other");
});

test("a reference finds its rows, and a row its owners", () => {
  const tree = buildBoardTree(index);
  assert.deepEqual(boardTreeNodeIds("#U1.2"), ["pad:U1.2", "netpad:U1.2"]);
  assert.deepEqual(boardTreeNodeIds("#net:VIN@x1y2"), ["net:VIN"]);
  assert.deepEqual(boardTreeNodeIds('#net:"a b"'), ["net:a b"]);
  // A quoted name may hold what a point is spelled with.
  assert.deepEqual(boardTreeNodeIds('#net:"x@x1y2"@x3y4'), ["net:x@x1y2"]);
  assert.deepEqual(boardTreeNodeIds("#U 3"), []);
  assert.deepEqual(boardTreeNodeIds("#@x1y2"), []);
  assert.deepEqual(boardTreeAncestors(tree, "pad:U1.2"), ["group:parts", "kind:ICs", "part:U1"]);
});

test("the Reference reads a part, a pad, a net, copper and a point in KiCad's millimetres", () => {
  const row = (facts, label) => facts.rows.find(([name]) => name === label)?.[1];
  const part = boardReferenceFacts(index.resolve("#C10"), index);
  assert.equal(part.heading, "C10 · 1u");
  assert.equal(row(part, "Position"), "x 5, y 25");
  assert.equal(row(part, "Rotation"), "90°");
  assert.equal(row(part, "LCSC"), "C15849");
  assert.equal(row(boardReferenceFacts(index.resolve("#C2"), index), "DNP"), "Not assembled");
  const pad = boardReferenceFacts(index.resolve("#U1.2"), index);
  assert.equal(pad.heading, "U1 · pad 2 VO");
  assert.equal(row(pad, "Net"), "VIN");
  const net = boardReferenceFacts(index.resolve("#net:VIN"), index);
  assert.equal(row(net, "Parts"), "C10, C2, U1");
  assert.equal(row(net, "Tracks"), "1 · 17.8 mm");
  const copper = boardReferenceFacts(index.resolve("#net:VIN@x10y25.8"), index);
  assert.equal(copper.heading, "VIN · track");
  assert.equal(row(copper, "Width"), "1 mm");
  assert.equal(boardReferenceFacts(index.resolve("#@x1y2"), index).rows[0][1], "x 1, y 2");
});
