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
    arcs: [{ layer: "OUTLINE", center: [0, 0], radius: 10, startAngleDeg: 0, sweepAngleDeg: 90 }],
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
  // 350 degrees start plus a 20 degree sweep crosses zero, not 340 degrees back.
  const { layers } = buildDxfDrawingLineGroups({
    geometry: { arcs: [{ layer: "A", center: [0, 0], radius: 1, startAngleDeg: 350, sweepAngleDeg: 20 }] }
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
      arcs: [{ layer: "A", center: [0, 0], radius: 5, startAngleDeg: "x", sweepAngleDeg: 10 }]
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

function arcXRange(arc) {
  const groups = buildDxfDrawingLineGroups({ geometry: { arcs: [arc], lines: [], circles: [] } });
  const positions = groups.layers[0].positions;
  const xs = [];
  for (let index = 0; index < positions.length; index += 3) {
    xs.push(positions[index]);
  }
  return [Math.min(...xs), Math.max(...xs)];
}

// parseDxf and drawing_render.py both emit startAngleDeg/sweepAngleDeg — the
// one arc shape this renderer reads.
test("an arc in the parser's angle keys keeps its sweep", () => {
  const [minX, maxX] = arcXRange({
    layer: "DIMS", center: [0, 0], radius: 10, startAngleDeg: 0, sweepAngleDeg: 90,
  });

  assert.ok(minX >= -0.001, `quarter arc should stay in x >= 0, got ${minX}`);
  assert.ok(Math.abs(maxX - 10) < 0.001);
});

test("a full circle in the parser's angle keys still closes", () => {
  const [minX, maxX] = arcXRange({
    layer: "DIMS", center: [0, 0], radius: 10, startAngleDeg: 0, sweepAngleDeg: 360,
  });

  assert.ok(Math.abs(minX + 10) < 0.001);
  assert.ok(Math.abs(maxX - 10) < 0.001);
});

test("a clockwise (negative) sweep samples the arc's own side", () => {
  // Start at 0 and sweep -90: the arc lives in the fourth quadrant (y <= 0).
  const groups = buildDxfDrawingLineGroups({
    geometry: { arcs: [{ layer: "A", center: [0, 0], radius: 1, startAngleDeg: 0, sweepAngleDeg: -90 }] }
  });
  const positions = groups.layers[0].positions;
  for (let index = 0; index < positions.length; index += 3) {
    assert.ok(positions[index + 2] <= 1e-9, `clockwise arc point above the x axis: ${positions[index + 2]}`);
  }
});

test("an arc without the parser's angle keys is skipped, not guessed at", () => {
  const groups = buildDxfDrawingLineGroups({
    geometry: { arcs: [{ layer: "DIMS", center: [0, 0], radius: 10 }] }
  });

  assert.equal(groups.layers.length, 0);
});
