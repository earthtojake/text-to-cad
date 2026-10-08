import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";

import { normalizeAnimationClips } from "./animationRuntime.js";
import { CORD_RADIUS, distanceFromCurl, tubeSkinsFixture } from "./__tests__/tubeSkinsFixture.js";
import { applyRecordTubeSkin, attachTubeSkins, decodeTubeSkins, tubeSkinPose } from "./tubeSkin.js";
import { tubeMaterialStage, TUBE_SKIN_STAGE } from "./tubeMaterialShader.js";

// cadgen's skins for a 20 mm cord its clip curls into a quarter circle
// (`fixtures/tube_skins`), played on a bare record the way the scene plays one.

function curl() {
  const { animation, buffer } = tubeSkinsFixture();
  const clips = normalizeAnimationClips(animation);
  attachTubeSkins(clips, decodeTubeSkins(buffer));
  return clips.curl;
}

/** A record of the cord as the scene makes one: its component geometry at rest. */
function cordRecord(binding, { gpu = false } = {}) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(binding.positions.slice(), 3));
  geometry.setAttribute("normal", new THREE.BufferAttribute(binding.normals.slice(), 3));
  geometry.setIndex(new THREE.BufferAttribute(binding.indices, 1));
  const material = new THREE.MeshStandardMaterial();
  const mesh = new THREE.Mesh(geometry, material);
  return { partId: "o1.1", mesh, material, geometry, gpuTubeSkinAllowed: gpu, baseTransform: null, partBounds: null };
}

const wall = (points) => distanceFromCurl(points).map((distance) => Math.abs(distance - CORD_RADIUS));

test("cadgen's skins attach to the track that bends the cord, and a track they do not pose cannot play", () => {
  const clip = curl();
  const [track] = clip.tracks;
  assert.equal(track.skin.joints, 11);
  assert.equal(track.skin.keys.length, track.times.length * 11 * 7);
  assert.deepEqual([...track.skin.byOccurrence.keys()], ["o1.1"]);
  const { animation, buffer } = tubeSkinsFixture();
  const clips = normalizeAnimationClips({ clips: [{ ...animation.clips[0], id: "other" }] });
  assert.throws(() => attachTubeSkins(clips, decodeTubeSkins(buffer)), /clip "other" track 0 bends a tube its skins do not pose/);
});

test("a cord skinned at the clip's end lies on the quarter circle, and straightens back to its rest", () => {
  const [track] = curl().tracks;
  const binding = track.skin.byOccurrence.get("o1.1");
  const record = cordRecord(binding);
  const rest = record.mesh.geometry;
  applyRecordTubeSkin(THREE, record, tubeSkinPose(track, "o1.1", track.times.length - 1, 0));
  const posed = record.mesh.geometry.attributes.position.array;
  assert.notEqual(record.mesh.geometry, rest, "the record shows the skin");
  assert.ok(Math.max(...wall(posed)) < 0.02, String(Math.max(...wall(posed))));
  // The pose's bounds hold every posed point.
  const box = new THREE.Box3(new THREE.Vector3(...record.partBounds.min), new THREE.Vector3(...record.partBounds.max));
  for (let point = 0; point < posed.length; point += 3) assert.ok(box.containsPoint(new THREE.Vector3().fromArray(posed, point)));
  // Straight again, it keeps the skin's geometry (a publish resets every pose before
  // bending it again), drawn at rest.
  const skinned = record.mesh.geometry;
  applyRecordTubeSkin(THREE, record, null);
  assert.equal(record.mesh.geometry, skinned);
  assert.deepEqual([...skinned.attributes.position.array], [...record.tubeSkinState.binding.positions]);
  assert.equal(record.tubeSkinState.active, false);
});

test("between two keys the joints blend as glTF's LINEAR sampler does, and the cord follows the clip", () => {
  const [track] = curl().tracks;
  const record = cordRecord(track.skin.byOccurrence.get("o1.1"));
  // Halfway between the 0.5 s and 0.6 s keys: the clip curls 0.55 of the quarter circle.
  applyRecordTubeSkin(THREE, record, tubeSkinPose(track, "o1.1", 5, 0.5));
  const posed = record.mesh.geometry.attributes.position.array;
  const off = distanceFromCurl(posed, 0.55 * Math.PI / 2).map((distance) => Math.abs(distance - CORD_RADIUS));
  assert.ok(Math.max(...off) < 0.05, String(Math.max(...off)));
});

test("on the GPU the record keeps its rest points and draws from a joint texture; a pick poses them", () => {
  const [track] = curl().tracks;
  const record = cordRecord(track.skin.byOccurrence.get("o1.1"), { gpu: true });
  applyRecordTubeSkin(THREE, record, tubeSkinPose(track, "o1.1", track.times.length - 1, 0));
  const state = record.tubeSkinState;
  const geometry = record.mesh.geometry;
  assert.ok(tubeMaterialStage(record.material, TUBE_SKIN_STAGE), "the material skins");
  assert.equal(state.gpu.uniforms.cadTubeJointCount.value, 11);
  assert.equal(state.gpu.texture.image.data.length, 11 * 12);
  assert.deepEqual([...geometry.attributes.position.array], [...state.binding.positions], "nothing posed on the CPU yet");
  // A ray down through the bent cord's far end asks for the exact surface.
  const raycaster = new THREE.Raycaster(new THREE.Vector3(40 / Math.PI, 40 / Math.PI, 5), new THREE.Vector3(0, 0, -1));
  record.mesh.updateMatrixWorld(true);
  assert.equal(record.mesh.userData.cadBeforeRaycast(raycaster), true);
  assert.ok(Math.max(...wall(geometry.attributes.position.array)) < 0.02);
  // A ray nowhere near it is turned away before any posing.
  assert.equal(record.mesh.userData.cadBeforeRaycast(new THREE.Raycaster(new THREE.Vector3(500, 500, 5), new THREE.Vector3(0, 0, -1))), false);
});

test("a bent cord's faces are still the component's: each refined triangle names the face it refines", () => {
  const [track] = curl().tracks;
  const binding = track.skin.byOccurrence.get("o1.1");
  const record = cordRecord(binding);
  const triangles = binding.indices.length / 3;
  // A face id per component triangle (here every triangle its own face, numbered from 1).
  record.mesh.userData.faceIds = Uint32Array.from({ length: Math.max(...binding.sourceTriangles) + 1 }, (_, index) => index + 1);
  applyRecordTubeSkin(THREE, record, tubeSkinPose(track, "o1.1", 4, 0));
  const faceIds = record.mesh.userData.faceIds;
  assert.equal(faceIds.length, triangles);
  assert.ok(binding.sourceTriangles.every((source, triangle) => faceIds[triangle] === source + 1));
  applyRecordTubeSkin(THREE, record, null);
  assert.equal(record.mesh.userData.faceIds, faceIds, "straight again, the skin's triangles are still the ones drawn");
});

test("the same pose again leaves the record as it is", () => {
  const [track] = curl().tracks;
  const record = cordRecord(track.skin.byOccurrence.get("o1.1"));
  const pose = tubeSkinPose(track, "o1.1", 3, 0.25);
  applyRecordTubeSkin(THREE, record, pose);
  applyRecordTubeSkin(THREE, record, tubeSkinPose(track, "o1.1", 3, 0.25));
  assert.equal(record.tubeSkinState.lastPose, pose, "an equal pose is not a new bend");
});
