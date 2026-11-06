import assert from "node:assert/strict";
import test from "node:test";

import { cameraTurnedOver, headOnCamera, millimetresPerPixel, planFromCamera, rayOnBoard, sheetToWorld, worldToSheet } from "./boardFrame.js";
import { faceBox, faceRaster, faceTransform, faceUv, faceView } from "./boardFaces.js";

const close = (actual, expected, message) => actual.forEach((value, index) => assert.ok(Math.abs(value - expected[index]) < 1e-9, `${message}: ${actual} vs ${expected}`));

test("the sheet stands in the world with y negated: the 2D plan seen from the top", () => {
  assert.deepEqual(sheetToWorld([10, 5]), [10, -5, 0]);
  assert.deepEqual(worldToSheet([10, -5, 3]), [10, 5]);
});

test("a ray meets the face it enters: the front coming down, the back coming up, nothing along the board or behind the eye", () => {
  const down = rayOnBoard({ origin: [10, -5, 50], direction: [0, 0, -1] }, 1.6);
  assert.equal(down.side, "top");
  assert.deepEqual(down.page, [10, 5]);
  assert.equal(down.distance, 50);
  const up = rayOnBoard({ origin: [10, -5, -50], direction: [0, 0, 1] }, 1.6);
  assert.equal(up.side, "bottom");
  close(up.point, [10, -5, -1.6], "the back face");
  assert.equal(rayOnBoard({ origin: [0, 0, 5], direction: [1, 0, 0] }), null);
  assert.equal(rayOnBoard({ origin: [0, 0, -5], direction: [0, 0, -1] }), null);
});

test("a pixel's millimetres: an orthographic frustum's height over the pane's, a perspective camera's at its depth", () => {
  assert.equal(millimetresPerPixel({ orthographic: true, halfHeight: 50 }, 0, 500), 0.2);
  close([millimetresPerPixel({ orthographic: false, fov: 90 }, 100, 400)], [0.5], "perspective");
});

test("the 2D window is the 3D camera head on, from either side, and the camera back is the same window", () => {
  const view = { transform: { scale: 4, offsetX: 100, offsetY: 300 }, width: 800, height: 600, thickness: 1.6, distance: 500 };
  const top = headOnCamera({ ...view, side: "top", mirrorX: null });
  // The pane's centre (400, 300) is plan (75, 0): sheet (75, 0), world (75, 0, 0), seen from +z.
  close(top.target, [75, 0, 0], "target");
  close(top.position, [75, 0, 500], "eye");
  assert.equal(top.orthographicHalfHeight, 75);
  const mirror = side => (side === "bottom" ? 50 : null);
  const back = headOnCamera({ ...view, side: "bottom", mirrorX: 50 });
  // From the back the plan is mirrored about x = 50: plan x 75 is sheet x 25, on the back face, seen from -z.
  close(back.target, [25, 0, -1.6], "back target");
  close(back.position, [25, 0, -501.6], "back eye");
  for (const [camera, side] of [[top, "top"], [back, "bottom"]]) {
    const plan = planFromCamera({ position: camera.position, target: camera.target, halfHeight: camera.orthographicHalfHeight, width: 800, height: 600, mirrorX: mirror, thickness: 1.6 });
    assert.equal(plan.side, side);
    close([plan.transform.scale, plan.transform.offsetX, plan.transform.offsetY], [4, 100, 300], `the ${side} window back`);
  }
});

test("Front | Back turns the camera over the board's left-to-right axis, up kept: the back mirrored left to right, the world's up still up", () => {
  const turned = cameraTurnedOver({ position: [10, -40, 30], target: [10, 0, 0], up: [0, 0.6, 0.8] });
  close(turned.position, [10, 40, -30], "eye");
  close(turned.up, [0, 0.6, 0.8], "up");
  // From the 3D views' Home (front, right, above; the world's z up) the eye goes behind, right, below,
  // and the world's z is still up on screen.
  const home = cameraTurnedOver({ position: [2.1, -1.65, 1.08], target: [0, 0, 0], up: [0, 0, 1] });
  close(home.position, [2.1, 1.65, -1.08], "home's eye");
  close(home.up, [0, 0, 1], "home's up");
  // Head on, the back is the 2D back view: the eye under the board, the sheet's up still up.
  const flat = cameraTurnedOver({ position: [5, -5, 100], target: [5, -5, 0], up: [0, 1, 0] });
  close(flat.position, [5, -5, -100], "head on");
  close(flat.up, [0, 1, 0], "head on up");
});

test("a face's raster keeps to its budget and the GPU's largest texture, and maps the sheet onto it, mirrored from the back", () => {
  const sheet = { x: 0, y: 0, width: 300, height: 100 };
  const raster = faceRaster(sheet, { maxPixels: 3_000_000, maxSize: 16384 });
  assert.ok(raster.width * raster.height <= 3_000_000);
  assert.equal(raster.width, 3000);
  assert.equal(raster.scale, 10);
  const clamped = faceRaster(sheet, { maxPixels: 3_000_000, maxSize: 2048 });
  assert.equal(clamped.width, 2048);
  assert.ok(clamped.height <= 2048);
  assert.deepEqual(faceTransform({ x: 2, y: 3 }, 10), { scale: 10, offsetX: -20, offsetY: -30 });
  assert.deepEqual(faceUv([30, 25], sheet, "top"), [0.1, 0.75]);
  assert.deepEqual(faceUv([30, 25], sheet, "bottom"), [0.9, 0.75]);
});

test("a face's pictures cover what the file draws past the outline, both sides of the sheet's centre line, and no farther than half the sheet", () => {
  const sheet = { x: 0, y: 0, width: 100, height: 40 };
  // A dimension 12mm right of the board and 6mm under it: the box reaches as far on the left, so the
  // back's picture, mirrored about the sheet's centre line, lands in the same box.
  assert.deepEqual(faceBox({ extent: [0, 0, 112, 46] }, sheet), { x: -12, y: 0, width: 124, height: 46 });
  assert.deepEqual(faceBox({ extent: [0, 0, 100, 40] }, sheet), { x: 0, y: 0, width: 100, height: 40 });
  // A note far off is cut at half the sheet's longer side.
  assert.deepEqual(faceBox({ extent: [0, -500, 100, 40] }, sheet), { x: 0, y: -50, width: 100, height: 90 });
  const box = faceBox({ extent: [0, 0, 112, 46] }, sheet);
  assert.deepEqual(faceUv([-12, 0], box, "top"), [0, 1]);
  assert.deepEqual(faceUv([-12, 0], box, "bottom"), [1, 1]);
});

test("a face draws the Display from its own side", () => {
  const sheet = { x: 0, y: 0, width: 10, height: 10, layers: [{ id: "F.Cu", kind: "copper", side: "front", items: [] }, { id: "B.Cu", kind: "copper", side: "back", items: [] }] };
  const display = { mode: "board", side: "top", poured: true, others: "shown" };
  assert.equal(faceView(display, sheet, "bottom").side, "bottom");
  assert.equal(faceView(display, sheet, "top").side, "top");
});
