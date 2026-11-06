import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { createBoardIndex } from "../board2d/boardIndex.js";
import { createBoardStage, outlineRings } from "./boardStage.js";

// A 40 x 30 mm board with a part on each side (the index's own test board, cut down).
const rect = (cx, cy, w, h) => [[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]];
const BOARD = {
  origin: [0, 0],
  nets: [{ name: "VIN" }, { name: "OUT" }],
  parts: [
    { ref: "R1", value: "10k", footprint: "R", side: "top", at: [15, 20], rotation: 0, fields: {}, outline: rect(15, 20, 3, 1.4) },
    { ref: "U1", value: "AMP", footprint: "U", side: "bottom", at: [30, 10], rotation: 0, fields: {}, outline: rect(30, 10, 4, 3) },
  ],
  pads: [
    { part: "R1", number: "1", net: "VIN", side: "top", at: [14.175, 20], polygon: rect(14.175, 20, 0.8, 0.95) },
    { part: "U1", number: "2", net: "OUT", side: "bottom", at: [31.5, 9.05], polygon: rect(31.5, 9.05, 0.8, 0.95) },
  ],
  outline: [[[0, 0], [40, 0], [40, 30], [0, 30], [0, 0]], [[20, 2], [24, 2], [24, 6], [20, 6], [20, 2]]],
};
const LAYOUT = { sheets: [{ x: 0, y: 0, width: 40, height: 30, layers: [] }] };

const ray = (origin, direction) => new THREE.Ray(new THREE.Vector3(...origin), new THREE.Vector3(...direction).normalize());

test("the outline's largest ring is the board and the rings inside it its cut-outs", () => {
  const rings = outlineRings(BOARD.outline, LAYOUT.sheets[0]);
  assert.equal(rings.outer.length, 4);
  assert.equal(rings.holes.length, 1);
});

test("a pick through a ray is the 2D view's pick at the point it meets, from the side it meets: front pads from above, back pads from below", () => {
  const index = createBoardIndex(BOARD);
  const stage = createBoardStage(THREE, { layout: LAYOUT, outline: BOARD.outline, thickness: 1.6, theme: "dark",
    pickAt: located => index.pick(located.page, { view: located.side, tolerance: 0.2 }) });
  assert.deepEqual(stage.bounds, { min: [0, -30, -1.6], max: [40, 0, 0] });
  // R1's pad 1 at sheet (14.175, 20): world (14.175, -20), seen from above at an angle.
  const fromAbove = stage.pick(ray([14.175, -60, 40], [0, 40, -40]));
  assert.equal(fromAbove.id, "#R1.1");
  assert.ok(Math.abs(fromAbove.point.z) < 1e-9);
  // U1's pad 2 is on the back: a ray from below meets the back face there and picks it, as the 2D view from the back does.
  const fromBelow = stage.pick(ray([31.5, -9.05, -50], [0, 0, 1]));
  assert.equal(fromBelow.id, "#U1.2");
  assert.ok(Math.abs(fromBelow.point.z + 1.6) < 1e-9);
  // Off the board, and in its cut-out, a ray meets nothing.
  assert.equal(stage.locate(ray([50, -10, 20], [0, 0, -1])), null);
  assert.equal(stage.locate(ray([22, -4, 20], [0, 0, -1])), null);
  stage.dispose();
});

test("the faces are drawn once a renderer takes them, through one scratch canvas, the back only once it is seen, within the budget", () => {
  const made = [];
  const context = new Proxy({}, { get: (_target, key) => (key === "canvas" ? undefined : key === "measureText" ? () => ({ width: 1 }) : () => {}) });
  const createCanvas = () => { const canvas = { width: 0, height: 0, getContext: () => context }; made.push(canvas); return canvas; };
  const uploads = [];
  const renderer = { capabilities: { maxTextureSize: 4096 }, initTexture: texture => uploads.push(texture.image) };
  const stage = createBoardStage(THREE, { layout: LAYOUT, outline: BOARD.outline, theme: "dark", createCanvas });
  stage.setLook({ display: { mode: "board", side: "top", poured: true, others: "shown" }, theme: "dark" });
  assert.equal(uploads.length, 0, "nothing is drawn before there is a renderer");
  stage.setRenderer(renderer);
  assert.deepEqual(stage.stats().drawnSides, ["top"]);
  stage.see("bottom");
  assert.deepEqual(stage.stats().drawnSides, ["top", "bottom"]);
  // A change of side alone is no redraw; a change of the Display redraws both faces.
  const before = uploads.length;
  stage.setLook({ display: { mode: "board", side: "bottom", poured: true, others: "shown" }, theme: "dark" });
  assert.equal(uploads.length, before);
  stage.setLook({ display: { mode: "copper", side: "bottom", poured: true, others: "shown" }, theme: "dark" });
  assert.equal(uploads.length, before + 2);
  assert.equal(made.length, 1, "one scratch canvas for every face drawn");
  const { texturePixels } = stage.stats();
  assert.ok(texturePixels <= 2 * 8_000_000 && texturePixels > 0, `${texturePixels}`);
  stage.setOverlay(() => false);
  assert.equal(made.length, 2, "and one for the overlays");
  stage.dispose();
  assert.ok(made.every(canvas => canvas.width === 0), "disposing frees the canvases");
});
