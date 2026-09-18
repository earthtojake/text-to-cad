import assert from "node:assert/strict";
import test from "node:test";

import { drawingSheetFacts, paperSizeLabel } from "./drawingSheetFacts.js";

function sheet({ width = 420, height = 297, texts = [] } = {}) {
  const m = 10;
  const corners = [[m, m], [width - m, m], [width - m, height - m], [m, height - m]];
  return {
    geometry: {
      lines: corners.map((start, index) => ({
        layer: "SHEET", start, end: corners[(index + 1) % 4]
      })),
      texts
    }
  };
}

test("an A3 sheet with a full title block reports every fact", () => {
  const facts = drawingSheetFacts(sheet({
    texts: [
      { layer: "TITLE", value: "CLEVIS BRACKET", heightMm: 5 },
      { layer: "TITLE", value: "CLV-001 · 6061-T6 · text-to-cad", heightMm: 2.5 },
      { layer: "TITLE", value: "SCALE 1:2   MM   THIRD ANGLE", heightMm: 2.5 },
      { layer: "TITLE", value: "SHEET 1 OF 2   REV B   clevis_bracket_drawing", heightMm: 2.5 },
      { layer: "NOTES", value: "NOTES:  1. BREAK SHARP EDGES.", heightMm: 2.5 }
    ]
  }));
  assert.equal(facts.paper, "A3 · 420 × 297 mm");
  assert.equal(facts.scale, "1:2");
  assert.equal(facts.units, "mm");
  assert.equal(facts.projection, "third angle");
  assert.equal(facts.revision, "B");
  assert.equal(facts.sheet, "1 of 2");
  assert.equal(facts.title, "CLEVIS BRACKET");
  assert.equal(facts.partNumber, "CLV-001 · 6061-T6 · text-to-cad");
  assert.equal(facts.hasFrame, true);
  assert.equal(facts.hasTitleBlock, true);
});

test("a frame that is no ISO size is described in millimetres, portrait matches too", () => {
  assert.equal(paperSizeLabel({ widthMm: 190, heightMm: 277 }), "A4 · 210 × 297 mm");
  assert.equal(paperSizeLabel({ widthMm: 480, heightMm: 280 }), "500 × 300 mm");
  assert.equal(paperSizeLabel(null), "");
});

test("a drawing without a frame or title block states nothing", () => {
  const facts = drawingSheetFacts({ geometry: { lines: [{ layer: "CUT", start: [0, 0], end: [1, 0] }], texts: [] } });
  assert.equal(facts.paper, "");
  assert.equal(facts.hasFrame, false);
  assert.equal(facts.hasTitleBlock, false);
  assert.equal(facts.title, "");
  assert.deepEqual(drawingSheetFacts(null).hasFrame, false);
});
