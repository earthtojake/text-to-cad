import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { buildFieldScene, FIELD_CLIP_PLANES, fieldClipUniforms, writeFieldClip } from "./fieldScene.js";

// A field as the engine answers one, with nothing to march: enough to build its scene.
const payload = (extra = {}) => ({
  schema: 1, target: "glsl-es300", code: "", entry: { march: "gsl_march", field: "gsl_field" }, region: [-10, -10, -10, 10, 10, 10],
  uniformBlock: "Field", uniforms: [{ name: "time", type: "f32", offset: 0, value: [0] }],
  sliders: [{ name: "r", uniform: "u_r", type: "f32", offset: 4, value: 4, min: 2, max: 8 }], bodies: [], ...extra
});
const drawn = scene => scene.object3D.children[0];

test("a field's clock is its block's time, set in seconds, and played only where the model reads it", () => {
  const still = buildFieldScene(THREE, payload());
  assert.equal(still.timed, false);
  const timed = buildFieldScene(THREE, payload({ timed: true }));
  assert.equal(timed.timed, true);
  const clock = drawn(timed).material.uniformsGroups[0].uniforms[0];
  assert.equal(timed.setTime(1.5), true);
  assert.equal(clock.value, 1.5);
  assert.equal(timed.setTime(1.5), false, "the same second moves nothing");
  assert.equal(timed.setTime(Number.NaN), false);
  // A block with no time has no clock, whatever the engine said of the source.
  const none = buildFieldScene(THREE, payload({ timed: true, uniforms: [], sliders: [{ name: "r", uniform: "u_r", type: "f32", offset: 0, value: 4, min: 2, max: 8 }] }));
  assert.deepEqual([none.timed, none.setTime(2)], [false, false]);
});

test("a section's planes are written in the field's own frame", () => {
  const uniforms = fieldClipUniforms(THREE);
  assert.deepEqual([uniforms.uClip.value.length, uniforms.uClipCount.value], [FIELD_CLIP_PLANES, 0]);
  // The scene keeps x >= 5; the field stands 3 along x, so in its own frame that is x >= 2.
  const toLocal = new THREE.Matrix4().makeTranslation(-3, 0, 0);
  writeFieldClip(THREE, uniforms, [new THREE.Plane(new THREE.Vector3(1, 0, 0), -5)], toLocal);
  assert.equal(uniforms.uClipCount.value, 1);
  assert.deepEqual(uniforms.uClip.value[0].toArray().map(value => Math.round(value * 1e6) / 1e6), [1, 0, 0, -2]);
  writeFieldClip(THREE, uniforms, [], toLocal);
  assert.equal(uniforms.uClipCount.value, 0);
  // More planes than the shader holds: the first of them.
  writeFieldClip(THREE, uniforms, Array.from({ length: 6 }, () => new THREE.Plane(new THREE.Vector3(0, 0, 1), 0)), toLocal);
  assert.equal(uniforms.uClipCount.value, FIELD_CLIP_PLANES);
});

test("a field takes a section and is capped only where its library can say what is solid", () => {
  const scene = buildFieldScene(THREE, payload());
  assert.match(drawn(scene).material.fragmentShader, /^precision highp sampler3D;\n#define FIELD_CAPS\n/);
  assert.match(drawn(scene).material.fragmentShader, /fieldClipped\(origin, direction, tEntry, tExit, cap\)/);
  scene.setClipPlanes([new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)]);
  drawn(scene).onBeforeRender({ getCurrentViewport: target => target.set(0, 0, 10, 10) }, null, new THREE.PerspectiveCamera());
  assert.equal(drawn(scene).material.uniforms.uClipCount.value, 1);
  scene.setClipPlanes(null);
  drawn(scene).onBeforeRender({ getCurrentViewport: target => target.set(0, 0, 10, 10) }, null, new THREE.PerspectiveCamera());
  assert.equal(drawn(scene).material.uniforms.uClipCount.value, 0);
  const older = buildFieldScene(THREE, payload({ entry: { march: "gsl_march" } }));
  assert.doesNotMatch(drawn(older).material.fragmentShader, /#define FIELD_CAPS/);
});
