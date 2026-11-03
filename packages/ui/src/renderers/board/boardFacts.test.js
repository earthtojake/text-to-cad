import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { createBoardIndex } from "@cad/core/lib/board2d/boardIndex.js";
import { layoutPlot } from "@cad/core/lib/plot2d/index.js";
import { describeBoardReference } from "./boardFacts.js";
import { boardPickKinds, boardWorkingLayer, readBoardFilter, BOARD_DEFAULT_FILTER, BOARD_SELECT_KINDS } from "./boardPick.js";

// The committed payload (`__fixtures__/README.md`): the Python suite's test board as the engine plots it,
// every item with the uuid KiCad saves it with. What each kind's card says, read as its chip's hover box shows it.
const PLOT = layoutPlot(JSON.parse(readFileSync(new URL("./__fixtures__/board.plot.json", import.meta.url), "utf8")));
const SHEET = PLOT.sheets[0];
const index = createBoardIndex(PLOT.board, SHEET);
const card = (selector) => {
  const described = describeBoardReference(index.resolve(selector), index);
  return { name: described.name, icon: described.icon, ...Object.fromEntries(described.facts.map(({ label, value }) => [label, value])) };
};
const ID = (n) => `7a1c0000-0000-4000-8000-00000000000${n}`;

test("each kind's card says what it is, in KiCad's millimetres", () => {
  assert.deepEqual(card(`#track:${ID(1)}`), { name: "VBUS · track", icon: "track", Net: "VBUS", Layer: "F.Cu", Width: "1 mm", Length: "29.175 mm" });
  assert.deepEqual(card(`#via:${ID(3)}`), { name: "GND · via", icon: "via", Net: "GND", Diameter: "0.6 mm", Drill: "0.3 mm", Layers: "F.Cu – B.Cu", Type: "through" });
  assert.deepEqual(card(`#zone:${ID(4)}`), { name: "GND pour", icon: "zone", Net: "GND", Layers: "B.Cu", Priority: "0", Filled: "216 mm²" });
  assert.deepEqual(card(`#text:${ID(5)}`), { name: "“blinky”", icon: "text", Text: "blinky", Layer: "F.SilkS", Size: "1.5 mm" });
  assert.deepEqual(card(`#shape:${ID(6)}`), { name: "rectangle on Edge.Cuts", icon: "shape", Shape: "rectangle", Layer: "Edge.Cuts", Width: "0.1 mm" });
  const reference = index.texts.find((text) => text.part === "R1" && text.layer === "F.SilkS");
  assert.deepEqual(card(`#text:${reference.id}`), { name: "“R1”", icon: "text", Text: "R1", Layer: "F.SilkS", Size: "1 mm", Part: "R1" });
  const silk = index.shapes.find((shape) => shape.part === "J1" && shape.layer === "F.SilkS");
  assert.equal(card(`#shape:${silk.id}`).Part, "J1");
  assert.deepEqual(card("#F.Cu@x12.5y20"), { name: "point 12.5, 20", icon: undefined, Position: "x 12.5, y 20", Layer: "F.Cu" });
  // R1, its pads and its text inside: on F.Cu, the part and its pads; on every layer its texts and lines too.
  assert.deepEqual(card("#F.Cu@x32y12..x38y18"), { name: "area 6 × 6 mm", icon: "area", Box: "x 32–38, y 12–18", Layer: "F.Cu",
    "Parts inside": "R1", Holds: "Pads 2" });
  assert.match(card("#@x32y12..x38y18").Holds, /^Pads 2 · Text 3 · Graphics 4$/);
  assert.equal(card("#@x0.2y0.2..x1y1")["Parts inside"], "Nothing");
});

test("Select's filter is KiCad's grid: its boxes are the index's kinds, All items as KiCad picks, Locked items off as a board opens", () => {
  // All items: the most specific thing, a footprint's graphics its part's, a pour by its outline; no locked items.
  assert.deepEqual(boardPickKinds(BOARD_DEFAULT_FILTER), { parts: true, pads: true, tracks: true, vias: true, texts: true, dimensions: true,
    shapes: true, footprintShapes: false, zones: true, ruleAreas: true, zoneFill: false, nets: false, locked: false });
  assert.equal(boardPickKinds([...BOARD_SELECT_KINDS, "locked"]).locked, true);
  // Graphics without Footprints takes a footprint's own graphics; the zones alone, a zone anywhere inside it.
  assert.equal(boardPickKinds(["graphics", "pads"]).footprintShapes, true);
  assert.equal(boardPickKinds(["graphics", "parts"]).footprintShapes, false);
  assert.deepEqual([boardPickKinds(["zones"]).zoneFill, boardPickKinds(["zones", "ruleAreas"]).zoneFill, boardPickKinds(["zones", "vias"]).zoneFill],
    [true, true, false]);
  assert.equal(boardPickKinds([]), null);
  assert.equal(boardPickKinds(["locked"]), null, "Locked items is no kind");
  // The earlier filter's Nets and Point or area are dropped; the rest keeps the grid's order.
  assert.deepEqual(readBoardFilter(["nets"]), []);
  assert.deepEqual(readBoardFilter(["points", "vias", "parts", "locked"]), ["parts", "vias", "locked"]);
  assert.equal(readBoardFilter(undefined), BOARD_DEFAULT_FILTER);
});

test("an area's layer is the working layer: the copper nearest the eye, else what is printed", () => {
  const ids = SHEET.layers.map((layer) => layer.id);
  assert.equal(boardWorkingLayer(SHEET, ids, "top"), "F.Cu");
  assert.equal(boardWorkingLayer(SHEET, ids, "bottom"), "B.Cu");
  assert.equal(boardWorkingLayer(SHEET, ["B.Cu", "Edge.Cuts", "vias"], "top"), "B.Cu", "the copper isolated");
  assert.equal(boardWorkingLayer(SHEET, ["F.SilkS", "F.Fab", "F.CrtYd", "Edge.Cuts"], "top"), "F.SilkS", "Assembly's");
  assert.equal(boardWorkingLayer(SHEET, ["Edge.Cuts", "vias", "drills"], "top"), null);
});
