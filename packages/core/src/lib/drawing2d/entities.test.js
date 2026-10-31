import assert from "node:assert/strict";
import test from "node:test";

import { DRAWING_SCHEMA_VERSION, prepareDrawing } from "./drawing.js";
import { entityAt, flattenPath, snapAt } from "./entities.js";
import { planCamera, planProjection, planTransform } from "./planView.js";
import { modelToScreen } from "./transform.js";

class NullPath { moveTo() {} lineTo() {} quadraticCurveTo() {} bezierCurveTo() {} closePath() {} }

// A drawing of four entities: a line (2F), a circle as two half-arcs with its centre (30), a hatch
// under them (31), and a block reference (32) whose lines sit on two layers.
function drawing() {
  return prepareDrawing({
    schemaVersion: DRAWING_SCHEMA_VERSION,
    units: { insunits: 4, name: "Millimeters", toMillimetres: 1 },
    bounds: [0, 0, 100, 100],
    layers: [{ name: "CUT", color: null, entities: 3 }, { name: "HATCH", color: "#0000ff", entities: 1 }, { name: "CENTRE", color: null, entities: 1 }],
    entities: [
      { handle: "2F", type: "LINE", layer: "CUT" },
      { handle: "30", type: "CIRCLE", layer: "CUT", center: [50, 50], radius: 10 },
      { handle: "31", type: "HATCH", layer: "HATCH" },
      { handle: "32", type: "INSERT", layer: "CUT", block: "BOLT" }
    ],
    fonts: [],
    primitives: [
      { type: "filled-polygon", layer: "HATCH", color: "#0000ff", entity: "31", geometry: [[0, 0], [30, 0], [30, 30], [0, 30]] },
      { type: "lines", layer: "CUT", color: null, entity: "2F", geometry: [[0, 10, 30, 10]] },
      { type: "path", layer: "CUT", color: null, entity: "30", geometry: [["M", 60, 50], ["C", 60, 55.5, 55.5, 60, 50, 60], ["C", 44.5, 60, 40, 55.5, 40, 50]] },
      { type: "lines", layer: "CUT", color: null, entity: "32", geometry: [[80, 80, 90, 80]] },
      { type: "lines", layer: "CENTRE", color: null, entity: "32", geometry: [[85, 75, 85, 85]] }
    ]
  }, { Path2D: NullPath });
}

test("a pick finds the entity whose line-work is within reach, a block's lines as its INSERT", () => {
  const drawable = drawing();
  assert.equal(entityAt(drawable, [15, 10.5], 1), "2F");
  assert.equal(entityAt(drawable, [50, 59.8], 1), "30");
  assert.equal(entityAt(drawable, [85, 84], 1), "32");
  assert.equal(entityAt(drawable, [70, 20], 1), "");
});

test("the lines over a hatch are picked before the hatch, and inside it the hatch is", () => {
  const drawable = drawing();
  assert.equal(entityAt(drawable, [15, 10.5], 1), "2F");
  assert.equal(entityAt(drawable, [15, 20], 1), "31");
});

test("nothing on a hidden layer is picked or snapped to", () => {
  const drawable = drawing();
  const hiddenLayers = new Set(["HATCH", "CENTRE"]);
  assert.equal(entityAt(drawable, [15, 20], 1, { hiddenLayers }), "");
  assert.equal(entityAt(drawable, [85, 84], 1, { hiddenLayers }), "", "the INSERT's line on CENTRE is hidden; its CUT line is not there");
  assert.equal(entityAt(drawable, [85, 80.2], 1, { hiddenLayers }), "32");
  assert.equal(snapAt(drawable, [85, 85.3], 1, { hiddenLayers }).kind, "free");
});

test("a snap takes an end, then a centre, then a point on a line, else the point itself", () => {
  const drawable = drawing();
  assert.deepEqual(snapAt(drawable, [29.6, 10.3], 1), { point: [30, 10], kind: "vertex", handle: "2F" });
  assert.deepEqual(snapAt(drawable, [50.4, 49.7], 1), { point: [50, 50], kind: "center", handle: "30" });
  const edge = snapAt(drawable, [12, 10.4], 1);
  assert.equal(edge.kind, "edge");
  assert.deepEqual(edge.point, [12, 10]);
  assert.deepEqual(snapAt(drawable, [70, 20], 1), { point: [70, 20], kind: "free", handle: "" });
});

test("a path's runs flatten with their curves sampled and Z closing the run", () => {
  const [run] = flattenPath([["M", 0, 0], ["L", 1, 0], ["Q", 2, 0, 2, 1], ["Z"]]);
  assert.deepEqual(run[0], [0, 0]);
  assert.deepEqual(run[run.length - 1], [0, 0]);
  assert.deepEqual(run[run.length - 2], [2, 1]);
});

test("a plan camera and its transform are one view, and its matrices project as the transform does", () => {
  const transform = { scale: 4, offsetX: 30, offsetY: 500 };
  const camera = planCamera(transform, 800, 600);
  assert.deepEqual(camera.up, [0, 1, 0]);
  assert.equal(camera.target[2], 0);
  assert.ok(camera.position[2] > 0);
  assert.equal(camera.orthographicHalfHeight, 75);
  const back = planTransform(camera, 800, 600);
  for (const key of ["scale", "offsetX", "offsetY"]) assert.ok(Math.abs(back[key] - transform[key]) < 1e-9, key);
  // The matrices take a drawing point to clip space where the transform puts it on screen.
  const { projectionMatrix } = planProjection(transform, 800, 600);
  const e = projectionMatrix.elements;
  const [x, y] = [12, 34];
  const ndc = [e[0] * x + e[12], e[5] * y + e[13]];
  const [sx, sy] = modelToScreen(transform, x, y);
  assert.ok(Math.abs((ndc[0] + 1) / 2 * 800 - sx) < 1e-9);
  assert.ok(Math.abs((1 - ndc[1]) / 2 * 600 - sy) < 1e-9);
});
