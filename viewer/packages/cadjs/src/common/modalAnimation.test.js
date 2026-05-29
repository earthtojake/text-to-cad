import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  parseModalClipName,
  extractModalModes,
  formatModeLabel,
  findMorphMesh,
  ModalPlayer,
} from "./modalAnimation.js";

test("parseModalClipName extracts index, frequency, label", () => {
  assert.deepEqual(parseModalClipName("mode 1 - 38.3189 Hz (x-translation)"), {
    index: 1,
    frequencyHz: 38.3189,
    label: "x-translation",
  });
  assert.deepEqual(parseModalClipName("mode 4 - 48.5 Hz"), {
    index: 4,
    frequencyHz: 48.5,
    label: "",
  });
  assert.equal(parseModalClipName("not a mode"), null);
});

test("extractModalModes prefers mesh extras and sorts by index", () => {
  const modes = extractModalModes({
    animations: [
      { name: "mode 2 - 95.2 Hz (rocking)" },
      { name: "mode 1 - 38.3 Hz (x-translation)" },
    ],
    meshExtras: { modes: [{ index: 1, frequencyHz: 38.31, label: "x-translation" }] },
  });
  assert.equal(modes.length, 2);
  assert.equal(modes[0].index, 1);
  assert.equal(modes[0].frequencyHz, 38.31); // from extras
  assert.equal(modes[1].index, 2);
  assert.equal(modes[1].frequencyHz, 95.2); // from name fallback
});

test("formatModeLabel renders frequency + label", () => {
  assert.equal(
    formatModeLabel({ index: 1, frequencyHz: 38.3, label: "x-translation" }),
    "Mode 1 — 38.30 Hz (x-translation)",
  );
});

function buildMorphMesh() {
  const geometry = new THREE.BufferGeometry();
  const base = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]);
  geometry.setAttribute("position", new THREE.BufferAttribute(base, 3));
  // Two morph targets (mode shapes).
  const d0 = new Float32Array([0.1, 0, 0, 0.1, 0, 0, 0.1, 0, 0]);
  const d1 = new Float32Array([0, 0, 0.2, 0, 0, 0.2, 0, 0, 0.2]);
  geometry.morphAttributes.position = [
    new THREE.BufferAttribute(d0, 3),
    new THREE.BufferAttribute(d1, 3),
  ];
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  mesh.name = "modal";
  mesh.morphTargetInfluences = [0, 0];
  return mesh;
}

function buildClip(meshName, modeIndex, numTargets) {
  // One sine loop on the given target's weight.
  const K = 9;
  const times = new Float32Array(K);
  const values = new Float32Array(K * numTargets);
  for (let k = 0; k < K; k += 1) {
    times[k] = k / (K - 1);
    values[k * numTargets + modeIndex] = Math.sin((2 * Math.PI * k) / (K - 1));
  }
  const track = new THREE.NumberKeyframeTrack(
    `${meshName}.morphTargetInfluences`,
    Array.from(times),
    Array.from(values),
  );
  return new THREE.AnimationClip(`mode ${modeIndex + 1} - ${modeIndex ? 95.2 : 38.3} Hz`, 1, [track]);
}

test("findMorphMesh locates the morph mesh", () => {
  const root = new THREE.Group();
  const mesh = buildMorphMesh();
  root.add(mesh);
  assert.equal(findMorphMesh(root), mesh);
});

test("ModalPlayer drives morph influences and respects amplitude", () => {
  const root = new THREE.Group();
  const mesh = buildMorphMesh();
  root.add(mesh);
  const animations = [buildClip("modal", 0, 2), buildClip("modal", 1, 2)];
  const player = new ModalPlayer({ THREE, root, animations });

  assert.equal(player.modes.length, 2);
  assert.equal(player.activeIndex, 1);

  player.play();
  player.update(0.25); // quarter of the 1s loop -> sine peak on mode 0
  const infA = mesh.morphTargetInfluences[0];
  assert.ok(Math.abs(infA) > 0.5, `expected mode-0 influence to ring, got ${infA}`);
  assert.ok(Math.abs(mesh.morphTargetInfluences[1]) < 1e-6);

  // Amplitude scales the visible deflection. Mode index 2 drives target 1.
  player.pause();
  player.setAmplitude(2);
  player.selectMode(2);
  player.play();
  player.update(0.25);
  assert.ok(Math.abs(mesh.morphTargetInfluences[1]) > 1.0, "amplitude>1 should exceed unit weight");
});
