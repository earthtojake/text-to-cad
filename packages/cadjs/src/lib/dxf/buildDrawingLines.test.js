import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildDxfDrawingLineGroups,
  drawingHasRenderableGeometry,
  drawingLineBounds
} from "./buildDrawingLines.js";

const DRAWING = {
  geometry: {
    lines: [
      { layer: "OUTLINE", kind: "cut", start: [0, 0], end: [600, 0] },
      { layer: "OUTLINE", kind: "cut", start: [600, 0], end: [600, 400] },
      { layer: "CENTRELINES", kind: "reference", start: [300, -25], end: [300, 425] }
    ],
    circles: [{ layer: "HIDDEN-EDGES", kind: "reference", center: [50, 220], radius: 4 }],
    arcs: [{ layer: "OUTLINE", center: [0, 0], radius: 10, startAngle: 0, endAngle: 90 }],
    texts: [{ layer: "TITLEBLOCK", text: "CABINET SIDE PANEL", position: [8, -222] }]
  }
};

test("a drawing's entities become line segments grouped by layer", () => {
  const { layers } = buildDxfDrawingLineGroups(DRAWING);
  const names = layers.map((layer) => layer.name).sort();
  assert.deepEqual(names, ["CENTRELINES", "HIDDEN-EDGES", "OUTLINE"]);
  // Grouping is what lets the viewer colour and hide layers without re-sampling.
  const outline = layers.find((layer) => layer.name === "OUTLINE");
  assert.ok(outline.positions instanceof Float32Array);
  // Two straight lines plus a sampled quarter arc, all as xyz PAIRS.
  assert.equal(outline.positions.length % 6, 0);
  assert.ok(outline.positions.length / 6 > 2, "the arc must contribute segments");
});

test("the sheet lies in the same plane as a flat pattern's mesh", () => {
  // y is out of the sheet, so a drawing and a cut layout share one camera fit.
  const { layers } = buildDxfDrawingLineGroups(DRAWING, { elevation: 0 });
  for (const layer of layers) {
    for (let index = 1; index < layer.positions.length; index += 3) {
      assert.equal(layer.positions[index], 0);
    }
  }
  const raised = buildDxfDrawingLineGroups(DRAWING, { elevation: 2.5 });
  assert.equal(raised.layers[0].positions[1], 2.5);
});

test("a line's endpoints survive unchanged", () => {
  const { layers } = buildDxfDrawingLineGroups({
    geometry: { lines: [{ layer: "A", start: [1, 2], end: [3, 4] }] }
  });
  assert.deepEqual([...layers[0].positions], [1, 0, 2, 3, 0, 4]);
});

test("a full circle closes", () => {
  const { layers } = buildDxfDrawingLineGroups({
    geometry: { circles: [{ layer: "H", center: [10, 10], radius: 5 }] }
  });
  const positions = layers[0].positions;
  const first = [positions[0], positions[2]];
  const last = [positions[positions.length - 3], positions[positions.length - 1]];
  assert.ok(Math.hypot(first[0] - last[0], first[1] - last[1]) < 1e-6, "circle must close");
  // Every sampled point sits on the circle.
  for (let index = 0; index < positions.length; index += 3) {
    const distance = Math.hypot(positions[index] - 10, positions[index + 2] - 10);
    assert.ok(Math.abs(distance - 5) < 1e-6, `point off the circle: ${distance}`);
  }
});

test("an arc sweeps the short way round, not the long way", () => {
  // 350 -> 10 degrees is a 20 degree sweep across zero, not 340 degrees back.
  const { layers } = buildDxfDrawingLineGroups({
    geometry: { arcs: [{ layer: "A", center: [0, 0], radius: 1, startAngle: 350, endAngle: 10 }] }
  });
  const positions = layers[0].positions;
  const angles = [];
  for (let index = 0; index < positions.length; index += 3) {
    angles.push((Math.atan2(positions[index + 2], positions[index]) * 180) / Math.PI);
  }
  for (const angle of angles) {
    const normalized = angle < 0 ? angle + 360 : angle;
    assert.ok(normalized >= 349.9 || normalized <= 10.1, `angle ${normalized} is off the arc`);
  }
});

test("degenerate entities are skipped rather than emitted as NaN", () => {
  const { layers } = buildDxfDrawingLineGroups({
    geometry: {
      lines: [{ layer: "A", start: [0, 0] }, { layer: "A", start: [0, 0], end: [1, 1] }],
      circles: [{ layer: "A", center: [0, 0], radius: 0 }, { layer: "A", center: [0, 0] }],
      arcs: [{ layer: "A", center: [0, 0], radius: 5, startAngle: "x", endAngle: 10 }]
    }
  });
  assert.equal(layers.length, 1);
  for (const value of layers[0].positions) {
    assert.ok(Number.isFinite(value), "no NaN may reach a buffer");
  }
  assert.deepEqual([...layers[0].positions], [0, 0, 0, 1, 0, 1]);
});

test("a drawing with nothing drawable says so, instead of rendering an empty scene", () => {
  assert.equal(drawingHasRenderableGeometry(DRAWING), true);
  assert.equal(drawingHasRenderableGeometry({ geometry: { texts: [{ text: "only text" }] } }), false);
  assert.equal(drawingHasRenderableGeometry(null), false);
});

test("bounds cover the drawing, for fitting a camera with no mesh to measure", () => {
  const bounds = drawingLineBounds(buildDxfDrawingLineGroups(DRAWING));
  assert.equal(bounds.min[0], 0);
  assert.equal(bounds.max[0], 600);
  assert.equal(bounds.min[2], -25);
  assert.equal(bounds.max[2], 425);
  assert.equal(drawingLineBounds({ layers: [] }), null);
});
