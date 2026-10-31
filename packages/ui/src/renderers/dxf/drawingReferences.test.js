import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

import { prepareDrawing } from "@text-to-cad/core/lib/drawing2d/index.js";
import { parsePromptReference } from "@text-to-cad/core/prompt";
import {
  createDrawingScene, describeEntity, drawingHandleOf, drawingReferenceId, drawingUnits, layerRows, layersSectionShown
} from "./drawingReferences.js";

class NullPath { moveTo() {} lineTo() {} quadraticCurveTo() {} bezierCurveTo() {} closePath() {} }
const fixture = name => prepareDrawing(JSON.parse(fs.readFileSync(new URL(`./__fixtures__/${name}`, import.meta.url), "utf8")), { Path2D: NullPath });

test("a reference names an entity by its handle, and reads back as the prompt grammar's", () => {
  assert.equal(drawingReferenceId("2f"), "h2F");
  assert.equal(drawingHandleOf("h2F"), "2F");
  assert.equal(drawingHandleOf("f:plate.make_box1.2"), "");
  const reference = parsePromptReference("/models/panel.dxf#h2F");
  assert.deepEqual(reference.target, { kind: "cad-selector", selectors: ["h2F"] });
});

test("the scene a selection reads maps each reference to its entity, by type and layer", () => {
  const drawing = fixture("layered.drawing.json");
  let lit = null;
  const scene = createDrawingScene(drawing, { onHighlight: ink => { lit = ink; }, unit: "mm" });
  assert.equal(scene.hasPart("h90"), true);
  assert.equal(scene.hasPart("hFFFF"), false);
  assert.deepEqual(scene.describePart("h90"), describeEntity(drawing.entities.get("90"), "mm"));
  assert.equal(scene.describePart("h90").name, "Circle on CUT");
  assert.deepEqual(scene.describePart("h90").facts.map(fact => fact.label), ["Handle", "Type", "Layer", "Centre", "Radius"]);
  assert.equal(scene.describePart("h99").name, "Block M5_NUT on HARDWARE");
  scene.setHighlight({ hovered: ["h99"], selected: ["h90", "hFFFF"] });
  assert.deepEqual(lit, { hovered: ["99"], selected: ["90"] });
});

test("a drawing's unit is the one it declares, and bare drawing units when it declares none", () => {
  assert.deepEqual(drawingUnits({ insunits: 4, name: "Millimeters" }), { unit: "mm", declared: true });
  assert.deepEqual(drawingUnits({ insunits: 1, name: "Inches" }), { unit: "in", declared: true });
  assert.deepEqual(drawingUnits({ insunits: 0, name: "Unitless" }), { unit: "units", declared: false });
  assert.deepEqual(drawingUnits(null), { unit: "units", declared: false });
});

test("a Layers section is shown for several layers or any block reference, never for a flat pattern's few", () => {
  const drawing = fixture("layered.drawing.json");
  assert.equal(layersSectionShown(drawing), true);
  assert.equal(layersSectionShown(fixture("sample.drawing.json")), false);
  const flat = { layers: [{ name: "CUT" }, { name: "BEND" }, { name: "ENGRAVE" }], entities: new Map([["1", { type: "LINE" }]]) };
  assert.equal(layersSectionShown(flat), false);
  assert.equal(layersSectionShown({ ...flat, layers: [...flat.layers, { name: "NOTES" }] }), true);
  assert.equal(layersSectionShown({ layers: [{ name: "0" }], entities: new Map([["9", { type: "INSERT" }]]) }), true);
  const hardware = layerRows(drawing).find(row => row.name === "HARDWARE");
  assert.deepEqual(hardware.inserts, [{ handle: "99", block: "M5_NUT" }, { handle: "9B", block: "M5_NUT" }]);
});
