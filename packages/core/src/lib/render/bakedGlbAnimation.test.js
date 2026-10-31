import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import validator from "gltf-validator";
import * as THREE from "three";
import { buildGlbDocumentFromBuffer, disposeGlbDocument } from "./glbMeshData.js";
import { createGlbAnimationRuntime, disposeGlbAnimationRuntime, setGlbAnimationTime } from "./glbAnimationRuntime.js";

// The engine's bakes of an `animation()` with every path, every interpolation and a pose
// (`animation.glb`) and of a motion, an AP242 configuration sequence (`motion.glb`): see
// `fixtures/README.md`.
function bytes(name) {
  return new Uint8Array(readFileSync(new URL(`./fixtures/${name}`, import.meta.url)));
}

function buffer(name) {
  const data = bytes(name);
  return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
}

for (const name of ["animation.glb", "motion.glb"]) {
  test(`the Khronos glTF-Validator finds no error and no warning in ${name}`, async () => {
    const report = await validator.validateBytes(bytes(name), { maxIssues: 50 });
    const loud = report.issues.messages.filter((issue) => issue.severity <= 1);
    assert.deepEqual(loud, [], JSON.stringify(loud, null, 1));
    assert.equal(report.issues.numErrors, 0);
    assert.equal(report.issues.numWarnings, 0);
  });
}

test("the viewer's mixer plays a baked animation's STEP and LINEAR channels as the baker wrote them", async () => {
  const document = await buildGlbDocumentFromBuffer(buffer("animation.glb"));
  const clip = document.clips.find((candidate) => candidate.name === "showcase");
  assert.ok(clip, document.clips.map((candidate) => candidate.name).join(", "));
  assert.equal(clip.duration, 2, "every sampler runs the whole animation");
  assert.deepEqual(clip.userData, { cadgen: { duration: 2 } });
  // three.js names a node as glTF does, less the characters a property path reserves (`feet/foot_1`: `feetfoot_1`).
  const node = (name) => document.scene.getObjectByName(THREE.PropertyBinding.sanitizeNodeName(name));
  const runtime = createGlbAnimationRuntime(THREE, document.scene, clip);
  const at = (t) => { setGlbAnimationTime(runtime, t); document.scene.updateMatrixWorld(true); };

  at(0.5);
  // LINEAR: the latch halfway out (20 mm at 1 s), a quarter into its one turn over 2 s. Its node
  // stands at its mesh's box centre, off its axis by up to the mesh's deflection (8 x 8 x 8 mm:
  // 24 / 300 * 0.25 = 0.02 mm).
  assert.ok(Math.abs(node("latch").position.x - 52) < 0.02, String(node("latch").position.x));
  assert.ok(Math.abs(new THREE.Euler().setFromQuaternion(node("latch").quaternion).z - Math.PI / 2) < 1e-3);
  // STEP: the knob holds its first key until 1 s; LINEAR scale: the first foot at 0.875.
  assert.ok(node("knob").quaternion.angleTo(new THREE.Quaternion()) < 1e-6);
  assert.ok(Math.abs(node("feet/foot_1").scale.x - 0.875) < 1e-5, node("feet/foot_1").scale.x);
  // Eased, keyed LINEAR within a tenth of a millimetre (cadgen's export/keys.py): the first foot has
  // dropped its 10 mm; the second has not begun.
  assert.ok(Math.abs(node("feet/foot_1").position.z + 14) < 0.11, String(node("feet/foot_1").position.z));
  assert.ok(Math.abs(node("feet/foot_2").position.z + 4) < 0.11, String(node("feet/foot_2").position.z));

  at(1.25);
  assert.ok(Math.abs(node("knob").quaternion.angleTo(new THREE.Quaternion()) - Math.PI / 2) < 1e-5);
  assert.equal(node("knob").scale.x, 1);
  // The lid, by the pose's forward kinematics, open about the hinge: lifted off the body.
  assert.ok(node("lid").position.z > 30, node("lid").position.z);
  at(1.75);
  assert.equal(node("knob").scale.x, 0, "hidden: a STEP of its scale to 0");

  disposeGlbAnimationRuntime(runtime);
  document.scene.updateMatrixWorld(true);
  assert.equal(node("knob").scale.x, 1, "stopping puts every node back at rest");
  assert.ok(Math.abs(node("latch").position.x - 42) < 1e-6);
  disposeGlbDocument(document);
});

test("the viewer plays a motion's clip in the same GLB the xbf's export writes", async () => {
  const document = await buildGlbDocumentFromBuffer(buffer("motion.glb"));
  assert.deepEqual(document.clips.map((clip) => clip.name), ["open_close"]);
  const runtime = createGlbAnimationRuntime(THREE, document.scene, document.clips[0]);
  const lid = document.scene.getObjectByName("lid");
  const rest = lid.quaternion.clone();
  setGlbAnimationTime(runtime, 1);
  // At 1 s the lid stands open: 100 degrees about the hinge.
  assert.ok(Math.abs(lid.quaternion.angleTo(rest) - 100 * Math.PI / 180) < 2e-3, lid.quaternion.angleTo(rest));
  disposeGlbAnimationRuntime(runtime);
  disposeGlbDocument(document);
});
