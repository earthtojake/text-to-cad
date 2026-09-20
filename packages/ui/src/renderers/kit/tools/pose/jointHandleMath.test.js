import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  PRISMATIC_HEAD_ON_LIMIT,
  REVOLUTE_EDGE_ON_LIMIT,
  advanceJointDrag,
  arcPoints,
  beginJointDrag,
  handleArmDirection,
  stablePerpendicular
} from "./jointHandleMath.js";

/** The Pose tool's drags: a pointer ray in, a joint value out. Limits are the handlers' business. */

const size = { width: 800, height: 600 };

// A real camera, so the rays and the projection are the ones the viewport makes.
function view(position, { orthographic = false, target = [0, 0, 0], up = [0, 0, 1] } = {}) {
  const camera = orthographic
    ? new THREE.OrthographicCamera(-4, 4, 3, -3, 0.1, 100)
    : new THREE.PerspectiveCamera(40, size.width / size.height, 0.1, 100);
  camera.up.fromArray(up);
  camera.position.fromArray(position);
  camera.lookAt(new THREE.Vector3().fromArray(target));
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix();
  const project = (point) => {
    const ndc = new THREE.Vector3().fromArray(point).project(camera);
    return [((ndc.x + 1) * size.width) / 2, ((1 - ndc.y) * size.height) / 2];
  };
  const raycaster = new THREE.Raycaster();
  const sampleAt = (pointer) => {
    raycaster.setFromCamera(new THREE.Vector2((pointer[0] / size.width) * 2 - 1, 1 - (pointer[1] / size.height) * 2), camera);
    return { ray: { origin: raycaster.ray.origin.toArray(), direction: raycaster.ray.direction.toArray() }, pointer, project };
  };
  // The pointer held exactly over a world point.
  return { project, sampleAt, sampleOver: (point) => sampleAt(project(point)) };
}

const onCircle = (radius, deg, z = 0) => [radius * Math.cos((deg * Math.PI) / 180), radius * Math.sin((deg * Math.PI) / 180), z];
const close = (actual, expected, tolerance = 1e-6) => assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} is not ${expected}`);

for (const orthographic of [false, true]) {
  const lens = orthographic ? "orthographic" : "perspective";

  test(`${lens}: a turning joint follows the pointer round its axis, and winds past 180 degrees`, () => {
    const { sampleOver } = view([3, -5, 6], { orthographic });
    const handle = { kind: "continuous", pivot: [0, 0, 0], axis: [0, 0, 1], value: 10, reach: 1 };
    let grab = beginJointDrag(handle, sampleOver(onCircle(1, 0)));
    assert.equal(grab.mode, "plane");
    for (let deg = 10; deg <= 450; deg += 10) {
      grab = advanceJointDrag(grab, sampleOver(onCircle(1, deg)));
      // Never a jump: every sample is the grab value plus the angle swept so far.
      close(grab.value, 10 + deg, 1e-6);
    }
    for (let deg = 440; deg >= -200; deg -= 10) grab = advanceJointDrag(grab, sampleOver(onCircle(1, deg)));
    close(grab.value, 10 - 200, 1e-6);
  });

  test(`${lens}: the angle is measured in the joint's plane, wherever on it the pointer is`, () => {
    const { sampleOver } = view([4, 2, 3], { orthographic, target: [1, 1, 1] });
    const axis = [1, 1, 0].map((value) => value / Math.SQRT2);
    const handle = { kind: "revolute", pivot: [1, 1, 1], axis, value: 0, reach: 0.5 };
    const arm = stablePerpendicular(axis);
    const at = (deg, radius) => arcPoints({ pivot: handle.pivot, axis, direction: arm, radius, fromDeg: deg, toDeg: deg })[0];
    let grab = beginJointDrag(handle, sampleOver(at(0, 0.5)));
    // Further out along a different ray of the same plane: only the angle counts.
    grab = advanceJointDrag(grab, sampleOver(at(-35, 1.7)));
    close(grab.value, -35, 1e-6);
  });

  test(`${lens}: a slider moves by the pointer's travel along its axis`, () => {
    const { sampleOver } = view([3, -5, 6], { orthographic });
    const axis = [1, 0, 0];
    const handle = { kind: "prismatic", pivot: [0.2, 0, 0.5], axis, value: 0.05, reach: 1 };
    let grab = beginJointDrag(handle, sampleOver([1, 0, 0.5]));
    assert.equal(grab.mode, "axis");
    grab = advanceJointDrag(grab, sampleOver([1.3, 0, 0.5]));
    close(grab.value, 0.35, 1e-6);
    grab = advanceJointDrag(grab, sampleOver([0.4, 0, 0.5]));
    close(grab.value, -0.55, 1e-6);
  });
}

test("a drag never clamps: limits belong to the handlers the value is handed to", () => {
  const { sampleOver } = view([0, 0, 8], { up: [0, 1, 0] });
  const handle = { kind: "revolute", pivot: [0, 0, 0], axis: [0, 0, 1], value: 0, min: 0, max: 90, reach: 1 };
  let grab = beginJointDrag(handle, sampleOver(onCircle(1, 0)));
  for (let deg = 15; deg <= 300; deg += 15) grab = advanceJointDrag(grab, sampleOver(onCircle(1, deg)));
  close(grab.value, 300, 1e-6);
});

test("edge-on, a turning joint is dragged by the near side of its ring: one arm length is one radian", () => {
  // Looking along +Y at a joint about Z: the rotation plane is a line on screen.
  const { sampleAt, project } = view([0, -8, 0], { orthographic: true });
  const handle = { kind: "revolute", pivot: [0, 0, 0], axis: [0, 0, 1], value: 5, reach: 0.5 };
  const armPixels = project([0.5, 0, 0])[0] - project([0, 0, 0])[0];
  const start = project([0.5, 0, 0]);
  let grab = beginJointDrag(handle, sampleAt(start));
  assert.equal(grab.mode, "screen");
  // The near side of a ring about +Z, seen from -Y, moves to screen right for a positive turn.
  grab = advanceJointDrag(grab, sampleAt([start[0] + armPixels, start[1] + 40]));
  close(grab.value, 5 + 180 / Math.PI, 1e-6);
  grab = advanceJointDrag(grab, sampleAt([start[0] - armPixels, start[1]]));
  close(grab.value, 5 - 180 / Math.PI, 1e-6);
});

test("head-on, a slider is dragged in screen pixels at its own depth: right or up is out", () => {
  const { sampleAt, project } = view([0, 0, 8], { orthographic: true, up: [0, 1, 0] });
  const handle = { kind: "prismatic", pivot: [0, 0, 0], axis: [0, 0, 1], value: 0.1, reach: 0.5 };
  const pixelsPerUnit = project([1, 0, 0])[0] - project([0, 0, 0])[0];
  const start = project([0, 0, 0.5]);
  let grab = beginJointDrag(handle, sampleAt(start));
  assert.equal(grab.mode, "screen");
  grab = advanceJointDrag(grab, sampleAt([start[0] + pixelsPerUnit * 0.3, start[1]]));
  close(grab.value, 0.4, 1e-6);
  grab = advanceJointDrag(grab, sampleAt([start[0] + pixelsPerUnit * 0.3, start[1] - pixelsPerUnit * 0.2]));
  close(grab.value, 0.6, 1e-6);
});

test("the fallbacks take over at their limits and agree with the exact mapping there", () => {
  // Camera elevation above a Z joint's plane, either side of the edge-on limit.
  const elevation = (Math.asin(REVOLUTE_EDGE_ON_LIMIT) * 180) / Math.PI;
  const turned = [elevation + 1, elevation - 1].map((deg) => {
    const { sampleOver } = view(onCircle(8, -90, 8 * Math.tan((deg * Math.PI) / 180)), { orthographic: true });
    const handle = { kind: "revolute", pivot: [0, 0, 0], axis: [0, 0, 1], value: 0, reach: 1 };
    // The knob on the near side of the ring, nudged along the ring.
    const grab = beginJointDrag(handle, sampleOver(onCircle(1, -90)));
    return { mode: grab.mode, value: advanceJointDrag(grab, sampleOver(onCircle(1, -80))).value };
  });
  assert.deepEqual(turned.map(({ mode }) => mode), ["plane", "screen"]);
  close(turned[0].value, 10, 1e-6);
  close(turned[1].value, 10, 0.5);

  // A slider's axis tilted either side of the head-on limit.
  const tilt = (Math.acos(PRISMATIC_HEAD_ON_LIMIT) * 180) / Math.PI;
  const modes = [tilt + 1, tilt - 1].map((deg) => {
    const { sampleOver } = view([0, 0, 8], { orthographic: true, up: [0, 1, 0] });
    const axis = [Math.sin((deg * Math.PI) / 180), 0, Math.cos((deg * Math.PI) / 180)];
    return beginJointDrag({ kind: "prismatic", pivot: [0, 0, 0], axis, value: 0, reach: 1 }, sampleOver([0, 0, 0])).mode;
  });
  assert.deepEqual(modes, ["axis", "screen"]);
});

test("a handle's arm: along a slider's axis, toward the child in a turning joint's plane", () => {
  assert.deepEqual(handleArmDirection({ kind: "prismatic", pivot: [0, 0, 0], axis: [0, 0, 2] }), [0, 0, 1]);
  const arm = handleArmDirection({ kind: "revolute", pivot: [1, 0, 0], axis: [0, 0, 1], toward: [1, 3, 9] });
  assert.deepEqual(arm.map((value) => Math.round(value * 1e9) / 1e9), [0, 1, 0]);
  // A child centred on the axis gives the plane no direction; the adapters supply one.
  assert.equal(handleArmDirection({ kind: "revolute", pivot: [0, 0, 0], axis: [0, 0, 1], toward: [0, 0, 4] }), null);
  assert.equal(handleArmDirection({ kind: "revolute", pivot: [0, 0, 0], axis: [0, 0, 1] }), null);
});

test("a travel arc runs from limit to limit about the axis, through the arm", () => {
  const points = arcPoints({ pivot: [0, 0, 1], axis: [0, 0, 1], direction: [1, 0, 0], radius: 2, fromDeg: -90, toDeg: 45 });
  const round = (point) => point.map((value) => Math.round(value * 1e6) / 1e6);
  assert.deepEqual(round(points[0]), [0, -2, 1]);
  assert.deepEqual(round(points.at(-1)), round([Math.SQRT2, Math.SQRT2, 1]));
  assert.ok(points.length > 20);
});
