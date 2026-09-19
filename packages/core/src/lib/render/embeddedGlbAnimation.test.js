import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import {
  buildGlbDocumentFromBuffer,
  detachGlbDocumentScene,
  disposeGlbDocument,
  isPlayableGlbAnimationClip,
  shouldUseNativeGlbScene
} from "./glbMeshData.js";
import { writeGlb } from "../glb/writeGlb.js";
import { createGlbAnimationRuntime, disposeGlbAnimationRuntime, setGlbAnimationTime } from "./glbAnimationRuntime.js";

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
  const bytes = writeGlb({
    primitives: [{
      name: "triangle",
      node: "animated",
      positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0])
    }]
  }, {
    preset: "export",
    animations: [{
      name: "travel",
      times: new Float32Array([0, 1]),
      channels: [{ node: "animated", translation: new Float32Array([0, 0, 0, 2, 0, 0]) }]
    }]
  });
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const document = await buildGlbDocumentFromBuffer(buffer);
  assert.equal(document.clips.length, 1);
  let retainedMesh = null;
  document.scene.traverse((object) => { if (object.isMesh) retainedMesh = object; });
  assert.ok(retainedMesh, "native mesh hierarchy is retained");
  assert.equal(retainedMesh.position.x, 0, "bounds sampling restores the authored rest pose");
  assert.ok(document.animatedBounds.max[0] > document.restBounds.max[0]);
  assert.deepEqual(document.meshData.bounds, document.animatedBounds);
  disposeGlbDocument(document);
});

test("interactive GLB parsing retains a static native hierarchy for Render only", async () => {
  const bytes = writeGlb({
    primitives: [{
      name: "finished-part",
      positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      material: { roughness: 0.18, metalness: 0.72 }
    }]
  }, { preset: "export" });
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const document = await buildGlbDocumentFromBuffer(buffer);
  assert.equal(document.clips.length, 0);
  assert.ok(document.scene, "static native hierarchy remains document-owned");
  assert.equal(shouldUseNativeGlbScene(document), false);
  assert.equal(shouldUseNativeGlbScene(document, { renderMode: true }), true);
  assert.equal(shouldUseNativeGlbScene(document, { clip: {} }), true);
  let material = null;
  document.scene.traverse((object) => { if (object.isMesh) material = object.material; });
  assert.equal(material.roughness, 0.18);
  assert.equal(material.metalness, 0.72);
  disposeGlbDocument(document);
});

test("static native GLB resources survive Render to Inspect to Render and dispose once", () => {
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

  const present = (renderMode) => {
    detachGlbDocumentScene(document);
    if (shouldUseNativeGlbScene(document, { renderMode })) host.add(scene);
  };
  present(true);
  assert.equal(scene.parent, host);
  present(false);
  assert.equal(scene.parent, null);
  present(true);
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
