import assert from "node:assert/strict";
import test from "node:test";

import { CAMERA_TOUCH, boundsChanged, cameraUntouched, fitCamera, rebuildRefits, touchCamera } from "./cameraTouch.js";

const PLATE = { min: [-50, -30, 0], max: [50, 30, 4] };
const BRACKET = { min: [-50, -30, 0], max: [50, 30, 60] };

// A page opens on the viewer's fit, untouched; every way of taking the camera ends that, and a
// fit hands it back.
test("every kind of touch ends the untouched state, and a fit re-arms it", () => {
  for (const kind of Object.values(CAMERA_TOUCH)) {
    const runtime = {};
    assert.equal(cameraUntouched(runtime), true, "a page opens untouched");
    touchCamera(runtime, kind);
    assert.equal(cameraUntouched(runtime), false, `${kind} touches the camera`);
    assert.equal(rebuildRefits(runtime, PLATE, BRACKET), false, `a rebuild after ${kind} keeps the camera`);
    // The completion fit stands down for a hand on the camera, and restores again for a restored view.
    assert.equal(Boolean(runtime.userMovedCamera), kind !== CAMERA_TOUCH.RESTORE, `${kind}: the completion fit's flag`);
    fitCamera(runtime);
    assert.equal(cameraUntouched(runtime), true, `a fit after ${kind} is untouched again`);
    assert.equal(rebuildRefits(runtime, PLATE, BRACKET), true, `and a rebuild after that fit re-fits`);
  }
});

test("a touch stays until the fit, whatever follows it", () => {
  const runtime = {};
  touchCamera(runtime, CAMERA_TOUCH.WHEEL);
  touchCamera(runtime, CAMERA_TOUCH.DRAG);
  assert.equal(runtime.cameraTouch, "drag", "the last touch is the one recorded");
  assert.equal(cameraUntouched(runtime), false);
  touchCamera(runtime, "resize");
  assert.equal(runtime.cameraTouch, "drag", "what is not a touch (a resize) changes nothing");
  // A flag the completion fit set on its own (a recovered runtime's) is a touch too.
  assert.equal(cameraUntouched({ userMovedCamera: true }), false);
});

test("an untouched rebuild re-fits only when its box changed", () => {
  const runtime = {};
  assert.equal(rebuildRefits(runtime, PLATE, BRACKET), true, "a plate rebuilt into a bracket");
  assert.equal(rebuildRefits(runtime, BRACKET, PLATE), true, "and back");
  assert.equal(rebuildRefits(runtime, PLATE, { min: [...PLATE.min], max: [...PLATE.max] }), false, "the same box");
  assert.equal(rebuildRefits(runtime, PLATE, { min: [-50, -30, 0], max: [50, 30, 4.000001] }), false,
    "a box a rebuild tessellated a hair differently");
  assert.equal(rebuildRefits(runtime, null, PLATE), false, "nothing to compare with: the open's own fit");
  assert.equal(boundsChanged(PLATE, { min: [-50, -30, 0], max: [50, 31, 4] }), true);
  assert.equal(boundsChanged(PLATE, { min: [0, 0], max: [1, 1] }), false, "not a box");
});
