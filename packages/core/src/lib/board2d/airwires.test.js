import assert from "node:assert/strict";
import test from "node:test";

import { boardAirwires } from "./airwires.js";
import { createBoardIndex } from "./boardIndex.js";

const rect = (cx, cy, w, h) => [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
const pad = (part, number, net, at, side = "top") => ({ part, number, name: "", net, type: "passive", side, at, polygon: rect(at[0], at[1], 1, 1) });
// GND joins four pins in a row and an L: A.1 (0, 0), B.1 (10, 0), C.1 (20, 0) and D.1 (10, 5).
// D's pin 1 is drawn as two pads (a tab); OUT is one pin, so it has no airwire.
const BOARD = {
  origin: [0, 0],
  nets: [{ name: "GND" }, { name: "OUT" }],
  parts: ["A", "B", "C", "D"].map((ref, at) => ({ ref, value: "", footprint: "", side: "top", at: [at * 5, 0], rotation: 0, fields: {}, outline: [] })),
  pads: [
    pad("A", "1", "GND", [0, 0]), pad("B", "1", "GND", [10, 0]), pad("C", "1", "GND", [20, 0]),
    pad("D", "1", "GND", [10, 5], "bottom"), pad("D", "1", "GND", [10, 6], "bottom"), pad("A", "2", "OUT", [0, 3]),
  ],
  tracks: [{ net: "GND", layer: "F.Cu", width: 0.25, points: [[0, 0], [10, 0]] }],
  vias: [], zones: [], holes: [], outline: [], findings: [],
};
const key = ([[ax, ay], [bx, by]]) => [`${ax},${ay}`, `${bx},${by}`].sort().join(" ");

test("a net's airwires are its pins' shortest tree, one end per pin, routed or not", () => {
  const index = createBoardIndex(BOARD);
  const wires = boardAirwires(index);
  // Four pins, three lines, each to its nearest: B-A, B-D, B-C. The track A-B does not remove A-B.
  assert.deepEqual(wires.map((wire) => wire.net), ["GND", "GND", "GND"]);
  assert.deepEqual(wires.map((wire) => key(wire.points)).sort(), ["0,0 10,0", "10,0 10,5", "10,0 20,0"]);
  assert.deepEqual(wires.find((wire) => key(wire.points) === "10,0 10,5").box, [10, 0, 10, 5]);
  assert.equal(boardAirwires(index), wires, "made once per index");
  assert.deepEqual(boardAirwires(null), []);
});
