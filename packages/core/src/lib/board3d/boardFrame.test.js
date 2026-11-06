import assert from "node:assert/strict";
import test from "node:test";

import { cameraTurnedOver, headOnCamera, millimetresPerPixel, perspectiveHeadOn, planFromCamera, rayOnBoard, sheetToWorld, worldToSheet } from "./boardFrame.js";
import { faceBox, faceRaster, faceTransform, faceUv, faceView } from "./boardFaces.js";
import { fitBoardBounds } from "../plot2d/plot.js";
import { panTransform, zoomLimits, zoomTransform } from "../drawing2d/transform.js";

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

test("a 2D window round trips through its head-on camera exactly: the fit clear of the strip, zoomed and panned, either side, either lens", () => {
  // A 40 x 30 board in a 1184 x 864 pane under a 52px strip, as a board opens with the panel shown, and that
  // fit zoomed in and out about other points and panned.
  const [width, height, mirror] = [1184, 864, side => (side === "bottom" ? 20 : null)];
  const fit = fitBoardBounds([0, -30, 40, 0], width, height, { top: 52 });
  const zoomed = (anchor, factor) => zoomTransform(fit, anchor, factor, zoomLimits(fit.scale));
  const windows = [fit, panTransform(zoomed({ x: 900, y: 300 }, 2.25), 150, -90), panTransform(zoomed({ x: 200, y: 700 }, 0.67), -200, 60)];
  for (const transform of windows) {
    for (const side of ["top", "bottom"]) {
      const headOn = headOnCamera({ transform, width, height, side, mirrorX: mirror(side), thickness: 1.6, distance: 80 });
      for (const [lens, camera, halfHeight] of [["orthographic", headOn, headOn.orthographicHalfHeight],
        ["perspective", perspectiveHeadOn(headOn, 28.6), null]]) {
        // A perspective camera's half height at its target is its distance times tan(fov / 2).
        const half = halfHeight ?? Math.hypot(...camera.position.map((value, axis) => value - camera.target[axis])) * Math.tan((28.6 * Math.PI) / 360);
        const plan = planFromCamera({ position: camera.position, target: camera.target, halfHeight: half, perspective: lens === "perspective",
          width, height, mirrorX: mirror, thickness: 1.6 });
        assert.equal(plan.side, side);
        close([plan.transform.scale, plan.transform.offsetX, plan.transform.offsetY], [transform.scale, transform.offsetX, transform.offsetY],
          `${lens} from the ${side}, scale ${transform.scale}`);
      }
    }
  }
});

test("a camera turned off the face hands the 2D view the face point it centres, at the scale that point is drawn at: in perspective, not its target's", () => {
  // From the front, right and above, its target 8 mm over the front face, as Home frames a board whose parts stand on it.
  const [width, height, position, target] = [1000, 600, [60, -80, 50], [20, -30, 8]];
  const camera = { position, target, halfHeight: 20, width, height, mirrorX: () => null, thickness: 1.6 };
  // The line of sight meets the face past the target: at 50 / 42 of the target's depth.
  const along = 50 / 42;
  const face = [60 + (20 - 60) * along, -80 + (-30 + 80) * along];
  const orthographic = planFromCamera(camera), perspective = planFromCamera({ ...camera, perspective: true });
  for (const plan of [orthographic, perspective]) {
    const { scale, offsetX, offsetY } = plan.transform;
    close([(width / 2 - offsetX) / scale, (offsetY - height / 2) / scale], face, "the pane's centre is the face point");
  }
  // An orthographic lens draws every depth at the target's half height; a perspective one the face point, farther, smaller.
  close([orthographic.transform.scale], [height / 40], "orthographic");
  close([perspective.transform.scale], [height / (40 * along)], "perspective");
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
