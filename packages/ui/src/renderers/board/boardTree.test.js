import assert from "node:assert/strict";
import test from "node:test";
import { createBoardIndex } from "@cad/core/lib/board2d/boardIndex.js";
import { boardDetail, boardRowOwners, boardTreeAncestors, boardTreeNodeIds, buildBoardTree, partKind } from "./boardTree.js";
import { boardReferenceId, describeBoardReference } from "./boardFacts.js";

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

test("a board whose footprints record no sheet is its parts in blocks by kind; its nets are a list of their own", () => {
  const tree = buildBoardTree(index);
  assert.deepEqual(tree.parts.roots.map((node) => `${node.label} ${node.detail}`), ["ICs 1", "Capacitors 2"]);
  const [ics, caps] = tree.parts.roots;
  // A block selects every part in it; a part is a row with no pads under it.
  assert.deepEqual([ics, caps].map((node) => [node.kind, node.picks]), [["block", ["#U1"]], ["block", ["#C2", "#C10"]]]);
  assert.deepEqual(caps.children.map((node) => [node.label, node.children.length]), [["C2", 0], ["C10", 0]], "natural order");
  // KiCad's names for a pin on nothing are not nets anyone routes: they are kept together, after the nets,
  // under one group, shut as the list opens. Every net is counted, as KiCad counts them.
  assert.deepEqual(tree.nets.roots.map((node) => `${node.label} ${node.detail}`), ["GND 1 pad", "VIN 3 pads", "Unconnected pins 1"]);
  assert.deepEqual(tree.nets.roots[1].children, []);
  const loose = tree.nets.roots[2];
  assert.deepEqual([loose.id, loose.kind, loose.children.map((node) => node.label)], ["group:unconnected", "group", ["unconnected-(U1-NC-Pad4)"]]);
  assert.deepEqual(boardTreeAncestors(tree.nets, "net:unconnected-(U1-NC-Pad4)"), ["group:unconnected"]);
  // The Parts' search reads each part with its pads: a pin of two pads is one, saying its pin's name and net.
  const u1 = tree.partsSearch[0].children[0];
  assert.deepEqual(u1.children.map((node) => [node.label, node.detail, node.pick, node.selectionId]), [["2", "VO · VIN", "#U1.2", "U1.2"], ["4", "NC · unconnected-(U1-NC-Pad4)", "#U1.4", "U1.4"]]);
  // A second pin on nothing joins the first (the group is shut as the Nets open: `BoardSection.jsx`).
  const two = buildBoardTree(createBoardIndex({ ...BOARD, nets: [...BOARD.nets, { name: "unconnected-(U1-NC-Pad5)", class: "Default" }],
    pads: [...BOARD.pads, { ...BOARD.pads.at(-1), number: "5", net: "unconnected-(U1-NC-Pad5)", at: [17, 16], polygon: square(17, 16, 1, 1) }] }));
  assert.equal(two.nets.roots.at(-1).detail, "2");
  assert.equal(partKind("TP3"), "Test points");
  assert.equal(partKind("ZZ1"), "Other");
});

test("a board whose footprints record their schematic sheets is its parts in those blocks, a part that records none under Other", () => {
  const sheets = { C10: "power", C2: "power", U1: "regulator" };
  const tree = buildBoardTree(createBoardIndex({ ...BOARD, parts: [...BOARD.parts.map((part) => ({ ...part, sheet: sheets[part.ref] })),
    { ref: "R9", value: "1k", footprint: "R_0603", side: "top", at: [30, 5], rotation: 0, fields: {}, outline: square(30, 5, 1, 1) }] }));
  assert.deepEqual(tree.parts.roots.map((node) => [node.id, node.label, node.detail]),
    [["sheet:power", "power", "2"], ["sheet:regulator", "regulator", "1"], ["sheet:", "Other", "1"]]);
  assert.deepEqual(tree.parts.roots[0].picks, ["#C2", "#C10"]);
  assert.deepEqual(boardTreeAncestors(tree.parts, "part:U1"), ["sheet:regulator"]);
  // The search finds a part by its value, footprint name and MPN, and a net by its name.
  assert.deepEqual(tree.parts.nodesById.get("part:C10").searchAliases, ["1u", "C_0603"]);
});

test("a reference finds its row, a pad its part's and its net's, and what it picks in detail", () => {
  assert.deepEqual(boardTreeNodeIds("#U1"), ["part:U1"]);
  assert.deepEqual(boardTreeNodeIds("#U1.2"), []);
  assert.deepEqual(boardRowOwners(index, "#U1.2"), ["part:U1", "net:VIN"]);
  assert.deepEqual(boardRowOwners(index, "#U1"), []);
  // Copper on a net is under its net's row: a track, a via, a zone.
  const routed = createBoardIndex({ ...BOARD, tracks: [{ ...BOARD.tracks[0], id: "7a1c0000-0000-4000-8000-000000000001" }],
    vias: [{ ...BOARD.vias[0], id: "7a1c0000-0000-4000-8000-000000000003" }] });
  assert.deepEqual(boardRowOwners(routed, "#track:7a1c0000-0000-4000-8000-000000000001"), ["net:VIN"]);
  assert.deepEqual(boardRowOwners(routed, "#via:7a1c0000-0000-4000-8000-000000000003"), ["net:GND"]);
  assert.deepEqual(boardRowOwners(routed, "#track:7a1c0000-0000-4000-8000-00000000ffff"), []);
  assert.deepEqual(boardTreeNodeIds("#net:VIN@x1y2"), ["net:VIN"]);
  assert.deepEqual(boardTreeNodeIds('#net:"a b"'), ["net:a b"]);
  // A quoted name may hold what a point is spelled with.
  assert.deepEqual(boardTreeNodeIds('#net:"x@x1y2"@x3y4'), ["net:x@x1y2"]);
  assert.deepEqual(boardTreeNodeIds("#U 3"), []);
  assert.deepEqual(boardTreeNodeIds("#@x1y2"), []);
  // A part's detail: its pads, one a pin, each its number, name and net; a pad's, its part's.
  const part = boardDetail(index, "#U1");
  assert.deepEqual([part.label, part.detail, part.count, part.listLabel], ["U1", "AMS1117 · SOT-223", "2 pads", "Pads of U1"]);
  assert.deepEqual(part.rows.map((row) => [row.pick, row.label, row.detail]), [["#U1.2", "2", "VO · VIN"], ["#U1.4", "4", "NC · unconnected-(U1-NC-Pad4)"]]);
  assert.equal(boardDetail(index, "#U1.4").id, "part:U1");
  // A net's: its pads, each its part and number, in natural order; its copper's, the net's.
  const net = boardDetail(index, "#net:VIN");
  assert.deepEqual([net.label, net.count, net.rows.map((row) => [row.pick, row.label])], ["VIN", "3 pads", [["#C2.1", "C2.1"], ["#C10.1", "C10.1"], ["#U1.2", "U1.2"]]]);
  assert.equal(boardDetail(index, "#net:VIN@x10y25.8").id, "net:VIN");
  assert.equal(boardDetail(index, "#@x1y2"), null);
});

test("a chip names a part, a pad, a net, copper and a point, its card in KiCad's millimetres", () => {
  const fact = (described, label) => described.facts.find((row) => row.label === label)?.value;
  const part = describeBoardReference(index.resolve("#C10"), index);
  assert.deepEqual([part.name, part.glyph], ["C10", "solid"]);
  assert.equal(fact(part, "Value"), "1u");
  assert.equal(fact(part, "Position"), "x 5, y 25");
  assert.equal(fact(part, "Rotation"), "90°");
  assert.equal(fact(part, "LCSC"), "C15849");
  assert.equal(fact(part, "Script"), "hat.py:40");
  assert.equal(fact(describeBoardReference(index.resolve("#C2"), index), "DNP"), "Not assembled");
  const pad = describeBoardReference(index.resolve("#U1.2"), index);
  assert.deepEqual([pad.name, pad.glyph, fact(pad, "Net"), fact(pad, "Pin"), fact(pad, "Type")], ["U1.2", "face", "VIN", "VO", "power out"]);
  const net = describeBoardReference(index.resolve("#net:VIN"), index);
  assert.deepEqual([net.name, fact(net, "Class"), fact(net, "Pads")], ["net VIN", "Power", "3"]);
  const copper = describeBoardReference(index.resolve("#net:VIN@x10y25.8"), index);
  assert.deepEqual([copper.name, fact(copper, "Width"), fact(copper, "Length")], ["VIN · track", "1 mm", "17.8 mm"]);
  assert.equal(fact(describeBoardReference(index.resolve("#@x1y2"), index), "Position"), "x 1, y 2");
  assert.equal(boardReferenceId("#net:VIN@x10y25.8"), "net:VIN@x10y25.8");
});
