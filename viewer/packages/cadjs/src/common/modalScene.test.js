import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync, existsSync } from "node:fs";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

import { isModalGltfJson, parseModalGltf, isModalGlbBuffer } from "./modalScene.js";

test("isModalGltfJson detects modal mesh extras", () => {
  assert.equal(isModalGltfJson({ meshes: [{ extras: { modes: [{ index: 1 }] } }] }), true);
  assert.equal(isModalGltfJson({ meshes: [{ extras: { modes: [] } }] }), false);
  assert.equal(isModalGltfJson({ meshes: [{}] }), false);
  assert.equal(isModalGltfJson({}), false);
});

// Parse a real modal GLB if one has been generated next to the repo.
const CANDIDATES = [
  "/tmp/modal-pages/spring_pla.glb",
  "/tmp/modal-workbench/spring_pla.glb",
];
const GLB = CANDIDATES.find((p) => existsSync(p));

test("isModalGlbBuffer detects a modal GLB from its bytes", { skip: !GLB }, () => {
  const buffer = readFileSync(GLB);
  const ab = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
  assert.equal(isModalGlbBuffer(ab), true);
  assert.equal(isModalGlbBuffer(new ArrayBuffer(8)), false);
});

test("parseModalGltf extracts morph mesh + modes from a real modal GLB", { skip: !GLB }, async () => {
  const buffer = readFileSync(GLB);
  const ab = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
  const gltf = await new Promise((resolve, reject) =>
    new GLTFLoader().parse(ab, "", resolve, reject),
  );
  const payload = parseModalGltf(gltf);
  assert.equal(payload.isModal, true);
  assert.ok(payload.mesh && payload.mesh.morphTargetInfluences.length >= 3);
  assert.equal(payload.mesh.morphTargetInfluences.length, payload.modes.length);
  assert.ok(payload.modes.every((m) => Number.isFinite(m.frequencyHz)));
  assert.ok(payload.damping > 0);
});
