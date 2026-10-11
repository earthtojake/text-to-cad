import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";

import {
  applyAnimationFrameToEffects,
  evaluateAnimationClip,
  isAnimationClip,
  loadSourceAnimation,
  normalizeAnimationClips
} from "./animationRuntime.js";
import { animationClipList } from "./animationClock.js";
import { tubeSkinsFixture } from "./__tests__/tubeSkinsFixture.js";

// Keyframes written by hand, the way cadgen bakes them: a transform key is
// [d, q, d', q'], the track's pivot moved by d while the part turns by q about it,
// with their rates, which glTF's CUBICSPLINE sampler curves between. An oblique
// axis, so every term of the quaternion's matrix is exercised.
const AXIS = new THREE.Vector3(1, 2, 2).normalize();
const PIVOT = [10, 0, 0];
const radians = THREE.MathUtils.degToRad;

/** A transform key: the pivot moved by `d` at `rate` (mm/s), turned `deg` about AXIS and
 * turning on at `degPerSec`. */
function key(d, deg, rate = [0, 0, 0], degPerSec = 0) {
  const q = new THREE.Quaternion().setFromAxisAngle(AXIS, radians(deg));
  // d/dt of (axis sin(theta/2), cos(theta/2)).
  const half = radians(deg) / 2;
  const turning = radians(degPerSec) / 2;
  const spin = AXIS.clone().multiplyScalar(Math.cos(half) * turning);
  return [...d, q.x, q.y, q.z, q.w, ...rate, spin.x, spin.y, spin.z, -Math.sin(half) * turning];
}

/** glTF's CUBICSPLINE step written out, as the spec gives it. */
function cubic(a, b, span, u) {
  const h = [2 * u ** 3 - 3 * u ** 2 + 1, (u ** 3 - 2 * u ** 2 + u) * span, 3 * u ** 2 - 2 * u ** 3, (u ** 3 - u ** 2) * span];
  return Array.from({ length: 7 }, (_, n) => h[0] * a[n] + h[1] * a[7 + n] + h[2] * b[n] + h[3] * b[7 + n]);
}

/** The placement a key names, T(pivot + d) R T(-pivot), composed by three. */
function pose(d, deg) {
  return new THREE.Matrix4().makeTranslation(PIVOT[0] + d[0], PIVOT[1] + d[1], PIVOT[2] + d[2])
    .multiply(new THREE.Matrix4().makeRotationAxis(AXIS, radians(deg)))
    .multiply(new THREE.Matrix4().makeTranslation(-PIVOT[0], -PIVOT[1], -PIVOT[2]));
}

function assertPose(matrix, expected, label) {
  matrix.elements.forEach((value, index) => {
    assert.ok(Math.abs(value - expected.elements[index]) < 1e-9, `${label}: element ${index} is ${value}, not ${expected.elements[index]}`);
  });
}

const clip = (tracks, { duration = 4, loop = true } = {}) => ({ id: "demo", label: "Demo", duration, loop, tracks });
const transformTrack = (times, keys) => ({ targets: ["o1.2", "o1.3"], times, pivot: PIVOT, transform: keys });
const at = (animation, t) => evaluateAnimationClip(THREE, animation, t);

test("clips normalize by id in the order the model declares them", () => {
  const clips = normalizeAnimationClips({ clips: [
    { id: "zoom", label: "Zoom", duration: 2, loop: false, tracks: [] },
    { id: "approach", label: "Approach", duration: 1, loop: true, tracks: [] }
  ] });
  assert.deepEqual(Object.keys(clips), ["zoom", "approach"]);
  assert.deepEqual(clips.zoom, { id: "zoom", label: "Zoom", duration: 2, loop: false, tracks: [], order: 0 });
  assert.equal(isAnimationClip(clips.approach), true);
  // The retired module form, a clip with an update function, is not a clip.
  assert.equal(isAnimationClip({ duration: 1, update() {} }), false);
  assert.equal(isAnimationClip(null), false);
});

test("the clip list keeps the declared order, even for ids an object would reorder", () => {
  const clips = normalizeAnimationClips({ clips: [
    { id: "2", label: "Second", duration: 1, loop: true, tracks: [] },
    { id: "1", label: "First", duration: 1, loop: true, tracks: [] }
  ] });
  // An object lists integer-like keys first; the viewer must still open on "2".
  assert.deepEqual(Object.keys(clips), ["1", "2"]);
  assert.deepEqual(animationClipList(clips).map((clip) => clip.id), ["2", "1"]);
});

test("a sidecar's clips load as they are, and a sidecar with none loads as null", async () => {
  for (const sidecar of [{}, { animation: null }, { animation: { clips: [] } }]) {
    assert.equal(await loadSourceAnimation(sidecar), null);
  }
  const swing = { id: "swing", label: "Swing", duration: 4, loop: true, tracks: [transformTrack([0], [key([0, 0, 0], 0)])] };
  const { clips } = await loadSourceAnimation({ animation: { clips: [swing] } });
  assert.deepEqual(clips, { swing: { ...swing, order: 0 } });
  assert.notEqual(clips.swing.tracks[0], swing.tracks[0], "what a load attaches never reaches the sidecar");
  await assert.rejects(loadSourceAnimation({ animation: { clips: [swing] } }, { signal: AbortSignal.abort() }), { name: "AbortError" });
});

test("a clip that bends a tube plays cadgen's skins for it, read once at load", async () => {
  const { animation, buffer } = tubeSkinsFixture();
  const reads = [];
  const resources = { readBytes: async (url) => { reads.push(url); return buffer; } };
  const { clips } = await loadSourceAnimation({ animation }, { tubeSkinsUrl: "/__cad/tube-skins?file=cord.step", resources });
  assert.deepEqual(reads, ["/__cad/tube-skins?file=cord.step"]);
  const [track] = clips.curl.tracks;
  assert.equal(track.skin.joints, 11);
  // Each target is posed between the two keys either side of the time.
  const tube = at(clips.curl, 0.55).deformations.get("o1.1");
  assert.equal(tube.binding, track.skin.byOccurrence.get("o1.1"));
  assert.equal(tube.index, 5);
  assert.ok(Math.abs(tube.u - 0.5) < 1e-9, String(tube.u));
  await assert.rejects(loadSourceAnimation({ animation }), /bends a tube, and no tube skins were named for it/);
});

test("between keys every component follows glTF's cubic curve through the keys and their rates", () => {
  // 90 deg about AXIS through PIVOT while the pivot rises 5 mm, keyed two seconds apart.
  const keys = [key([0, 0, 0], 0, [0, 0, 2.5], 45), key([0, 0, 5], 90, [0, 0, 2.5], 45)];
  const screw = clip([transformTrack([0, 2], keys)]);
  for (const t of [0.5, 1, 1.6]) {
    const c = cubic(keys[0], keys[1], 2, t / 2);
    const q = new THREE.Quaternion(c[3], c[4], c[5], c[6]).normalize();
    const expected = new THREE.Matrix4().makeTranslation(PIVOT[0] + c[0], PIVOT[1] + c[1], PIVOT[2] + c[2])
      .multiply(new THREE.Matrix4().makeRotationFromQuaternion(q))
      .multiply(new THREE.Matrix4().makeTranslation(-PIVOT[0], -PIVOT[1], -PIVOT[2]));
    const { matrices } = at(screw, t);
    assertPose(matrices.get("o1.2"), expected, `t=${t}`);
    assert.deepEqual(matrices.get("o1.3").elements, matrices.get("o1.2").elements, "a track moves its targets alike");
    // A steady rise is exactly a steady rise, and the turn lands close to a steady one.
    assert.ok(Math.abs(c[2] - 2.5 * t) < 1e-12);
    assert.ok(q.angleTo(new THREE.Quaternion().setFromAxisAngle(AXIS, radians(45 * t))) < 1e-3);
  }
});

test("a key at its own time is exact, and a track holds its end keys outside its times", () => {
  const track = transformTrack([0, 1, 2], [key([0, 0, 0], 0), key([1, 2, 3], 45), key([4, 0, 0], 90)]);
  const swing = clip([track]);
  assertPose(at(swing, 0).matrices.get("o1.2"), pose([0, 0, 0], 0), "first key");
  assertPose(at(swing, 1).matrices.get("o1.2"), pose([1, 2, 3], 45), "interior key");
  assertPose(at(swing, 2).matrices.get("o1.2"), pose([4, 0, 0], 90), "last key");
  assertPose(at(swing, 3.5).matrices.get("o1.2"), pose([4, 0, 0], 90), "after the last key");
  assertPose(at(swing, -1).matrices.get("o1.2"), pose([0, 0, 0], 0), "before the first key");
  // A track of one key holds it for the whole clip.
  const held = clip([transformTrack([0], [key([0, 0, 7], 30)])]);
  for (const t of [0, 1.7, 3.99]) assertPose(at(held, t).matrices.get("o1.2"), pose([0, 0, 7], 30), `one key, t=${t}`);
});

test("a looping clip wraps its time, and one that does not clamps it", () => {
  const slide = [transformTrack([0, 2], [key([0, 0, 0], 0, [1, 0, 0]), key([2, 0, 0], 0, [1, 0, 0])])];
  assertPose(at(clip(slide, { duration: 2 }), 2.5).matrices.get("o1.2"), pose([0.5, 0, 0], 0), "looping");
  assertPose(at(clip(slide, { duration: 2, loop: false }), 99).matrices.get("o1.2"), pose([2, 0, 0], 0), "clamped");
});

test("opacity lerps between numbers and holds against null; visibility holds", () => {
  const fade = clip([
    { targets: ["o1.2"], times: [0, 1, 2, 3], opacity: [null, 0.25, 0.75, null] },
    { targets: ["o1.3"], times: [0, 1, 2], visible: [false, true, null] }
  ]);
  const styles = (t) => Object.fromEntries(at(fade, t).styles);
  // null is the material's own opacity and the part's rest visibility: no style at all.
  assert.deepEqual(styles(0.5), { "o1.3": { visible: false } });
  assert.deepEqual(styles(1.5), { "o1.2": { opacity: 0.5 }, "o1.3": { visible: true } });
  // A number before a null holds rather than fading toward the material's own.
  assert.deepEqual(styles(2.5), { "o1.2": { opacity: 0.75 } });
  assert.deepEqual(styles(3.5), {});
});

function through(matrix, point) {
  return new THREE.Vector3(...point).applyMatrix4(matrix).toArray().map((v) => Math.round(v * 1e6) / 1e6);
}

const frame = ({ matrices = [], styles = [] } = {}) => ({ matrices: new Map(matrices), styles: new Map(styles), deformations: new Map() });

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
  const orbit = frame({ matrices: [["o1.1", new THREE.Matrix4().makeRotationZ(Math.PI / 2)]] });
  const transformCount = applyAnimationFrameToEffects(THREE, effectsByPartId, orbit);
  assert.equal(transformCount, 1);
  assert.deepEqual(through(effectsByPartId.get("o1.1").matrix, [0, 0, 0]), [0, 10, 0]);
});

test("frame effects open records for untouched parts and merge styles", () => {
  const effectsByPartId = new Map();
  const styled = frame({ styles: [["o1.1", { opacity: 0.5 }], ["o1.2", { visible: false }]] });
  assert.equal(applyAnimationFrameToEffects(THREE, effectsByPartId, styled), 0);
  assert.deepEqual(effectsByPartId.get("o1.1").style, { opacity: 0.5 });
  assert.equal(effectsByPartId.get("o1.2").visible, false);
  assert.equal(effectsByPartId.get("o1.1").matrix, null);
});
