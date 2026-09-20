import assert from "node:assert/strict";
import test from "node:test";

import {
  reframeReason,
  runtimeFramingBounds,
  sameZeroPoseBounds,
  VIEWING_MODE,
  VIEW_PLANE_FACES,
  viewPlaneCameraBasis,
  viewportFitScale
} from "./viewportCameraKit.js";

// The framed area of a viewport with a top bar and no side sheets, then the same
// window with a sheet open. Only the ratio between two scales is used, so these
// read as "how much further back the camera has to sit than it did before".
const wide = { aspect: 1120 / 756 };
const narrow = { aspect: 355 / 756 };

test("perspective fit scale is fixed while the framed area stays wider than tall", () => {
  // The vertical field of view is what frames the model, so extra width changes
  // nothing -- and a resize that only adds width must not move the camera.
  const square = viewportFitScale({ fov: 48, aspect: 1 });
  assert.ok(Math.abs(viewportFitScale({ fov: 48, aspect: 2.4 }) - square) < 1e-9);
  assert.ok(Math.abs(viewportFitScale({ fov: 48, aspect: 1.4 }) - square) < 1e-9);
  assert.ok(Math.abs(square - 1 / Math.sin((48 * Math.PI) / 360)) < 1e-9);
});

test("perspective fit scale grows once the framed area is taller than wide", () => {
  const half = viewportFitScale({ fov: 48, aspect: 0.5 });
  assert.ok(half > viewportFitScale({ fov: 48, aspect: 1 }));
  // Width is the limiting dimension now, so halving it pulls the camera back
  // by close to 2x -- exactly 2x only in the small-angle limit.
  assert.ok(half / viewportFitScale({ fov: 48, aspect: 1 }) > 1.8);
});

test("orthographic fit scale tracks the smaller viewport dimension", () => {
  // R / min(width, height) per unit height, expressed per unit radius.
  assert.ok(Math.abs(viewportFitScale({ orthographic: true, ...wide }) - 1) < 1e-9);
  assert.ok(Math.abs(viewportFitScale({ orthographic: true, ...narrow }) - 756 / 355) < 1e-9);
});

test("closing a sheet undoes the scale change that opening it made", () => {
  // Reframing is applied as a ratio, so a viewport that comes back to where it
  // started has to leave the camera where it started.
  const opened = viewportFitScale({ orthographic: true, ...narrow }) / viewportFitScale({ orthographic: true, ...wide });
  const closed = viewportFitScale({ orthographic: true, ...wide }) / viewportFitScale({ orthographic: true, ...narrow });
  assert.ok(opened > 2);
  assert.ok(Math.abs(opened * closed - 1) < 1e-12);
});

test("degenerate viewports fall back instead of producing a non-finite scale", () => {
  for (const metrics of [
    {},
    { aspect: 0 },
    { aspect: Number.NaN },
    { orthographic: true, aspect: 0 },
    { orthographic: true, aspect: Number.NaN },
    { fov: 0, aspect: 1 },
    { fov: Number.NaN, aspect: 1 }
  ]) {
    const scale = viewportFitScale(metrics);
    assert.ok(Number.isFinite(scale) && scale > 0, `bad scale for ${JSON.stringify(metrics)}`);
  }
});

// --- view-plane camera basis -------------------------------------------------------------
//
// A "top" view that is not top-down is the bug these cover. Orthographic projects parallel,
// so vertical faces that should collapse to nothing acquire width at even a degree of tilt;
// the offset used to be 0.02 (1.146 degrees, 20px across a 1000px viewport).

const WORLD_UP_AXIS = [0, 0, 1];

function degreesFromAxis(direction, axis) {
  const d = Math.abs(direction[0] * axis[0] + direction[1] * axis[1] + direction[2] * axis[2]);
  return (Math.acos(Math.min(1, d)) * 180) / Math.PI;
}

test("every view-plane preset orbits about world up", () => {
  // The invariant that lets the pole offset exist at all: `up` never varies, so OrbitControls
  // orbits about the same axis from every view and no drag can snap the roll. A preset that
  // declares its own up (the poles declare [0,1,0]) may steer the offset, never the axis.
  for (const face of VIEW_PLANE_FACES) {
    const basis = viewPlaneCameraBasis(face, WORLD_UP_AXIS);
    assert.deepEqual(basis.up, WORLD_UP_AXIS, `${face.id} must orbit about world up`);
  }
});

test("a declared up that is not world up still does not become the orbit axis", () => {
  // Guards the invariant against the presets changing: even asked directly for a Y-up pole
  // view, the basis orbits about world up and expresses the request through the offset.
  const basis = viewPlaneCameraBasis({ direction: [0, 0, 1], up: [0, 1, 0] }, WORLD_UP_AXIS);
  assert.deepEqual(basis.up, WORLD_UP_AXIS);
  assert.ok(basis.direction[1] < 0, "the offset leans toward the declared screen up");
});

test("axis views are axis-aligned to well under a pixel", () => {
  // 0.0057 degrees is a tenth of a pixel across a 1000px viewport. The four side views are
  // exact; only the poles carry an offset at all.
  for (const face of VIEW_PLANE_FACES) {
    const basis = viewPlaneCameraBasis(face, WORLD_UP_AXIS);
    const error = degreesFromAxis(basis.direction, face.direction);
    assert.ok(error < 0.01, `${face.id} is ${error.toFixed(4)} deg off its own axis`);
  }
});

test("the pole offset stays clear of Spherical.makeSafe", () => {
  // OrbitControls calls makeSafe() on every update, clamping phi to [1e-6, PI-1e-6]. An offset
  // at or below that gets clamped and the azimuth stops being well defined, so the view would
  // drift on the first drag. Keep a wide margin.
  const MAKE_SAFE_EPS = 1e-6;
  for (const face of VIEW_PLANE_FACES) {
    const basis = viewPlaneCameraBasis(face, WORLD_UP_AXIS);
    const alignment = Math.abs(
      basis.direction[0] * WORLD_UP_AXIS[0]
      + basis.direction[1] * WORLD_UP_AXIS[1]
      + basis.direction[2] * WORLD_UP_AXIS[2]
    );
    const phi = Math.acos(Math.min(1, alignment));   // angle off the orbit axis
    if (phi < 1e-9) {
      assert.fail(`${face.id} sits exactly on the orbit axis; lookAt has no basis there`);
    }
    assert.ok(phi > MAKE_SAFE_EPS * 10, `${face.id} phi ${phi} is too close to makeSafe EPS`);
  }
});

test("a malformed preset is refused rather than producing a broken camera", () => {
  assert.equal(viewPlaneCameraBasis(null, WORLD_UP_AXIS), null);
  assert.equal(viewPlaneCameraBasis({ direction: [0, 0, 0], up: [0, 1, 0] }, WORLD_UP_AXIS), null);
  assert.equal(viewPlaneCameraBasis({ direction: [0, 0, 1], up: [0, 0, 0] }, WORLD_UP_AXIS), null);
});

// Reset and fit are grounded on the model's zero pose. `modelBounds` is the live
// pose -- what lighting, the floor and clipping follow -- and framing against it
// is what made the zoom move when the kinematics did.
const ZERO_POSE = { min: [0, 0, 0], max: [10, 4, 2] };
const POSED = { min: [-6, 0, 0], max: [10, 4, 30] };

test("reset and fit frame the zero pose, never the pose on screen", () => {
  assert.deepEqual(
    runtimeFramingBounds({ zeroPoseBounds: ZERO_POSE, modelBounds: POSED }),
    ZERO_POSE
  );
});

test("before adoption only authored fallback bounds can define the zoom ruler", () => {
  const fallback = { min: [1, 1, 1], max: [2, 2, 2] };
  assert.deepEqual(runtimeFramingBounds({ modelBounds: POSED }, fallback), fallback);
  assert.deepEqual(runtimeFramingBounds({}, fallback), fallback);
  assert.equal(runtimeFramingBounds(null), null);
  assert.equal(runtimeFramingBounds({ modelBounds: POSED }), null, "never use live bounds to define the original zoom");
});

// A model is framed once per viewing mode, on its zero pose. These are the only
// four things that reopen that decision, and a pose is never one of them.
const SMALL = { min: [0, 0, 0], max: [10, 4, 2] };
const GREW = { min: [0, 0, 0], max: [40, 4, 2] };
const FRAMED = {
  modelKey: "hinge.step",
  framedModelKey: "hinge.step",
  framedCompleteModelKey: "hinge.step",
  mode: VIEWING_MODE.INSPECT,
  framedMode: VIEWING_MODE.INSPECT,
  modelComplete: true,
  zeroPoseBounds: SMALL,
  framedZeroPoseBounds: SMALL
};

test("a different model always fits, even over a camera the user took", () => {
  assert.equal(reframeReason({ ...FRAMED, modelKey: "other.step", userMovedCamera: true }), "model");
  assert.equal(reframeReason({ modelKey: "hinge.step" }), "model", "nothing framed yet is a new model");
});

test("a progressive load fits again when the last component lands, once", () => {
  const loading = { ...FRAMED, framedCompleteModelKey: "", modelComplete: false };
  assert.equal(reframeReason(loading), "", "a partial publish keeps the first frame");
  assert.equal(reframeReason({ ...loading, modelComplete: true }), "complete");
  assert.equal(reframeReason(FRAMED), "", "and not on every publish after that");
});

test("a rebuild whose zero pose changed fits again; another publish of the same one does not", () => {
  assert.equal(reframeReason({ ...FRAMED, zeroPoseBounds: GREW }), "revision");
  assert.equal(reframeReason({ ...FRAMED, zeroPoseBounds: SMALL }), "");
});

test("a pose is never a reason to re-fit", () => {
  // Posing leaves zeroPoseBounds alone by construction (cadScene.restBounds), so
  // the live box can be anywhere and the decision must not notice.
  assert.equal(reframeReason({ ...FRAMED, zeroPoseBounds: { ...SMALL } }), "",
    "an equal box published as a new object is the same zero pose");
});

test("the user's own camera stands through a completion and a rebuild", () => {
  assert.equal(reframeReason({ ...FRAMED, framedCompleteModelKey: "", userMovedCamera: true }), "");
  assert.equal(reframeReason({ ...FRAMED, zeroPoseBounds: GREW, userMovedCamera: true }), "");
});

test("entering a viewing mode fits that mode's own camera, over one the user took", () => {
  const entered = { ...FRAMED, mode: VIEWING_MODE.RENDER };
  assert.equal(reframeReason(entered), "mode", "Render does not inherit Inspect's framing");
  assert.equal(reframeReason({ ...entered, userMovedCamera: true }), "mode",
    "a hand-framed Inspect view does not follow the model into Render");
  assert.equal(
    reframeReason({ ...FRAMED, mode: VIEWING_MODE.INSPECT, framedMode: VIEWING_MODE.RENDER }),
    "mode",
    "and back again"
  );
});

test("staying in a mode is not a reason to re-fit", () => {
  assert.equal(reframeReason(FRAMED), "");
  assert.equal(reframeReason({ ...FRAMED, mode: VIEWING_MODE.RENDER, framedMode: VIEWING_MODE.RENDER }), "");
  assert.equal(
    reframeReason({ ...FRAMED, mode: VIEWING_MODE.RENDER, framedMode: VIEWING_MODE.RENDER, zeroPoseBounds: GREW, userMovedCamera: true }),
    "",
    "an in-mode revision still stands down for the camera the user took"
  );
});

test("a different model opened in another mode is the model's own fit", () => {
  assert.equal(
    reframeReason({ ...FRAMED, modelKey: "other.step", mode: VIEWING_MODE.RENDER, userMovedCamera: true }),
    "model"
  );
});

test("a detail swap's float-level drift is the same zero pose, a millimetre is not", () => {
  const drifted = { min: [0, 0, 0], max: [10 + 1e-7, 4, 2] };
  assert.equal(sameZeroPoseBounds(drifted, SMALL), true);
  assert.equal(sameZeroPoseBounds({ min: [0, 0, 0], max: [10.01, 4, 2] }, SMALL), false);
  assert.equal(sameZeroPoseBounds(null, SMALL), false, "no box is not the same box");
});
