import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";

import {
  applyAnimationFrameToEffects,
  createAnimationFrame,
  evaluateAnimationClip,
  normalizeAnimationClips
} from "./animationRuntime.js";

const MESH_DATA = {
  parts: [
    { id: "o1.1", label: "base" },
    { id: "o1.2", label: "arm" },
    { id: "o1.3", label: "arm" }
  ]
};

function through(matrix, point) {
  return new THREE.Vector3(...point).applyMatrix4(matrix).toArray().map((v) => Math.round(v * 1e6) / 1e6);
}

test("clips normalize with defaults and drop non-functions", () => {
  const clips = normalizeAnimationClips({
    demo: { duration: 8, update() {} },
    bare: { update() {} },
    broken: { duration: 2 }
  });
  assert.deepEqual(Object.keys(clips), ["demo", "bare"]);
  assert.equal(clips.demo.duration, 8);
  assert.equal(clips.bare.duration, 1);
  assert.equal(clips.demo.loop, true);
});

test("a handle addresses every part sharing its label", () => {
  const frame = createAnimationFrame(THREE, MESH_DATA);
  frame.model.get("arm").translate([5, 0, 0]);
  assert.equal(frame.matrices.has("o1.2"), true);
  assert.equal(frame.matrices.has("o1.3"), true);
  assert.equal(frame.matrices.has("o1.1"), false);
});

test("an unknown label throws with the known labels listed", () => {
  const frame = createAnimationFrame(THREE, MESH_DATA);
  assert.throws(() => frame.model.get("wrist"), /no occurrence labeled "wrist".*arm, base/);
});

test("successive calls premultiply: spin rides a later orbit", () => {
  const frame = createAnimationFrame(THREE, MESH_DATA);
  const handle = frame.model.get("base");
  handle.rotate([0, 0, 1], 90, [10, 0, 0]); // spin about own center
  handle.rotate([0, 0, 1], 90, [0, 0, 0]); // then orbit the origin
  // The center (10,0,0) is fixed by the spin, then orbits to (0,10,0).
  assert.deepEqual(through(frame.matrices.get("o1.1"), [10, 0, 0]), [0, 10, 0]);
});

test("styles collect opacity and visibility per part", () => {
  const frame = createAnimationFrame(THREE, MESH_DATA);
  frame.model.get("base").opacity(0.25).visible(false);
  assert.deepEqual(frame.styles.get("o1.1"), { opacity: 0.25, visible: false });
});

test("evaluation is a pure function of t with looping", () => {
  const seen = [];
  const clip = {
    duration: 2,
    loop: true,
    update(t, m) {
      seen.push(t);
      m.get("base").translate([t, 0, 0]);
    }
  };
  const early = evaluateAnimationClip(THREE, MESH_DATA, clip, 0.5);
  const wrapped = evaluateAnimationClip(THREE, MESH_DATA, clip, 2.5);
  assert.deepEqual(seen, [0.5, 0.5]);
  assert.deepEqual(
    through(early.matrices.get("o1.1"), [0, 0, 0]),
    through(wrapped.matrices.get("o1.1"), [0, 0, 0])
  );
  const clamped = evaluateAnimationClip(THREE, MESH_DATA, { ...clip, loop: false }, 99);
  assert.deepEqual(through(clamped.matrices.get("o1.1"), [0, 0, 0]), [2, 0, 0]);
});

test("occurrence-id refs and comma lists resolve with subtree containment", () => {
  const frame = createAnimationFrame(THREE, {
    parts: [
      { id: "o1.3.1.5", label: "" },
      { id: "o1.3.1.6", label: "" },
      { id: "o1.3.2", label: "" },
      { id: "o1.3.2.4", label: "" },
      { id: "o1.7", label: "" }
    ]
  });
  frame.model.get("#o1.3.1.5,o1.3.2").translate([1, 0, 0]);
  assert.deepEqual([...frame.matrices.keys()].sort(), ["o1.3.1.5", "o1.3.2", "o1.3.2.4"]);
});

test("frame effects premultiply onto an existing pose matrix", () => {
  // Pose put the part at x=10; the clip then orbits the origin by 90deg. The
  // animation must act on the ALREADY-POSED part (world space), not under it.
  const effectsByPartId = new Map([
    ["o1.1", {
      matrix: new THREE.Matrix4().makeTranslation(10, 0, 0),
      style: null,
      visible: null,
      highlighted: false
    }]
  ]);
  const frame = createAnimationFrame(THREE, MESH_DATA);
  frame.model.get("base").rotate([0, 0, 1], 90, [0, 0, 0]);
  const transformCount = applyAnimationFrameToEffects(THREE, effectsByPartId, frame);
  assert.equal(transformCount, 1);
  assert.deepEqual(through(effectsByPartId.get("o1.1").matrix, [0, 0, 0]), [0, 10, 0]);
});

test("frame effects open records for untouched parts and merge styles", () => {
  const effectsByPartId = new Map();
  const frame = createAnimationFrame(THREE, MESH_DATA);
  frame.model.get("base").opacity(0.5);
  frame.model.get("arm").visible(false);
  assert.equal(applyAnimationFrameToEffects(THREE, effectsByPartId, frame), 0);
  assert.deepEqual(effectsByPartId.get("o1.1").style, { opacity: 0.5 });
  assert.equal(effectsByPartId.get("o1.2").visible, false);
  assert.equal(effectsByPartId.get("o1.1").matrix, null);
});
