import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import * as THREE from "three";
import {
  buildGlbDocumentFromBuffer,
  detachGlbDocumentScene,
  disposeGlbDocument,
  isPlayableGlbAnimationClip
} from "./glbMeshData.js";
import { createGlbAnimationRuntime, disposeGlbAnimationRuntime, setGlbAnimationTime } from "./glbAnimationRuntime.js";

// cadgen's exports of a polished base and a rider (`fixtures/README.md`): static, and with
// the clip that slides the rider 60 mm along +X under its pivot.
function fixture(name) {
  const bytes = readFileSync(new URL(`./fixtures/${name}`, import.meta.url));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

function applyClip(root, clip, time = 0.5) {
  const mixer = new THREE.AnimationMixer(root);
  const action = mixer.clipAction(clip);
  action.play();
  mixer.setTime(time);
  return { mixer, action };
}

test("native GLB transform, skeletal, and morph clips drive their authored objects", () => {
  const root = new THREE.Group();
  const moved = new THREE.Object3D();
  moved.name = "moved";
  root.add(moved);

  const bone = new THREE.Bone();
  bone.name = "joint";
  const skeleton = new THREE.Skeleton([bone]);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([0, 0, 0, 1, 0, 0, 0, 1, 0], 3));
  geometry.setAttribute("skinIndex", new THREE.Uint16BufferAttribute([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 4));
  geometry.setAttribute("skinWeight", new THREE.Float32BufferAttribute([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0], 4));
  geometry.morphAttributes.position = [new THREE.Float32BufferAttribute([0, 0, 0, 0, 1, 0, 0, 0, 0], 3)];
  geometry.morphTargetsRelative = true;
  const mesh = new THREE.SkinnedMesh(geometry, new THREE.MeshBasicMaterial());
  mesh.name = "deformed";
  mesh.add(bone);
  mesh.bind(skeleton);
  mesh.updateMorphTargets();
  root.add(mesh);

  const clip = new THREE.AnimationClip("combined", 1, [
    new THREE.VectorKeyframeTrack("moved.position", [0, 1], [0, 0, 0, 2, 0, 0]),
    new THREE.QuaternionKeyframeTrack("joint.quaternion", [0, 1], [0, 0, 0, 1, 0, 0, 1, 0]),
    new THREE.NumberKeyframeTrack("deformed.morphTargetInfluences", [0, 1], [0, 1])
  ]);
  assert.equal(isPlayableGlbAnimationClip(clip), true);
  const { mixer, action } = applyClip(root, clip);
  assert.equal(moved.position.x, 1);
  assert.ok(Math.abs(bone.quaternion.z) > 0.6);
  assert.equal(mesh.morphTargetInfluences[0], 0.5);
  action.stop();
  mixer.uncacheRoot(root);
  geometry.dispose();
  mesh.material.dispose();
});

test("embedded GLB animation gate rejects tracks outside glTF transform and weights", () => {
  const clip = new THREE.AnimationClip("material", 1, [
    new THREE.NumberKeyframeTrack("mesh.material.opacity", [0, 1], [1, 0])
  ]);
  assert.equal(isPlayableGlbAnimationClip(clip), false);
});

test("absolute GLB scrub reactivates a LoopOnce action after its endpoint", () => {
  const root = new THREE.Group();
  const node = new THREE.Object3D();
  node.name = "node";
  root.add(node);
  const clip = new THREE.AnimationClip("move", 1, [
    new THREE.VectorKeyframeTrack("node.position", [0, 1], [0, 0, 0, 2, 0, 0])
  ]);
  const runtime = createGlbAnimationRuntime(THREE, root, clip);
  setGlbAnimationTime(runtime, 1);
  assert.equal(node.position.x, 2);
  assert.equal(runtime.action.paused, true);
  setGlbAnimationTime(runtime, 0.25);
  assert.equal(node.position.x, 0.5);
  disposeGlbAnimationRuntime(runtime);
});

test("interactive GLB parsing retains the native animated hierarchy and CAD-space framing estimate", async () => {
  const document = await buildGlbDocumentFromBuffer(fixture("pair.slide.glb"));
  assert.equal(document.clips.length, 1);
  const rider = document.scene.getObjectByName("rider");
  assert.ok(rider?.isMesh, "native mesh hierarchy is retained");
  // The clip keys the rider's pivot; sampling its travel for the bounds leaves it where it rests.
  assert.ok(rider.parent.parent.position.distanceTo(new THREE.Vector3(0.035, 0.005, 0.005)) < 1e-6,
    "bounds sampling restores the authored rest pose");
  assert.ok(document.animatedBounds.max[0] > document.restBounds.max[0]);
  assert.equal(document.meshData, undefined, "the viewer's document is the native scene, never a flattened mesh");
  disposeGlbDocument(document);
});

test("interactive GLB parsing retains a static native hierarchy with its authored finish", async () => {
  const document = await buildGlbDocumentFromBuffer(fixture("pair.glb"));
  assert.equal(document.clips.length, 0);
  assert.ok(document.scene, "static native hierarchy remains document-owned");
  assert.deepEqual([document.restBounds.min, document.restBounds.max].map(corner => corner.map(Math.round)), [[0, -20, 0], [40, 0, 20]],
    "rest bounds are in CAD space: millimetres, Z up");
  assert.equal(document.animatedBounds, null);
  const finishes = [];
  document.scene.traverse((object) => { if (object.isMesh) finishes.push([object.material.roughness, object.material.metalness]); });
  assert.ok(finishes.some(([roughness, metalness]) => roughness === 0.05 && metalness === 1), JSON.stringify(finishes));
  disposeGlbDocument(document);
});

test("detaching a native GLB scene is not disposal: resources survive re-hosting and dispose once", () => {
  const scene = new THREE.Group();
  const geometry = new THREE.BufferGeometry();
  const texture = new THREE.Texture();
  const material = new THREE.MeshStandardMaterial({ map: texture });
  scene.add(new THREE.Mesh(geometry, material));
  const document = { scene };
  const host = new THREE.Group();
  const released = { geometry: 0, material: 0, texture: 0 };
  geometry.dispose = () => { released.geometry += 1; };
  material.dispose = () => { released.material += 1; };
  texture.dispose = () => { released.texture += 1; };

  host.add(scene);
  detachGlbDocumentScene(document);
  assert.equal(scene.parent, null);
  host.add(scene);
  assert.equal(scene.parent, host);
  assert.deepEqual(released, { geometry: 0, material: 0, texture: 0 });

  disposeGlbDocument(document);
  assert.deepEqual(released, { geometry: 1, material: 1, texture: 1 });
});

test("interactive GLB disposal releases shared geometry, materials, textures, and skeleton once", () => {
  const scene = new THREE.Group();
  const geometry = new THREE.BufferGeometry();
  const texture = new THREE.Texture();
  const material = new THREE.MeshStandardMaterial({ map: texture });
  const mesh = new THREE.SkinnedMesh(geometry, material);
  const bone = new THREE.Bone();
  mesh.add(bone);
  mesh.bind(new THREE.Skeleton([bone]));
  scene.add(mesh);
  const released = { geometry: 0, material: 0, texture: 0, skeleton: 0 };
  geometry.dispose = () => { released.geometry += 1; };
  material.dispose = () => { released.material += 1; };
  texture.dispose = () => { released.texture += 1; };
  mesh.skeleton.dispose = () => { released.skeleton += 1; };
  disposeGlbDocument({ scene });
  assert.deepEqual(released, { geometry: 1, material: 1, texture: 1, skeleton: 1 });
});
