import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { isKitScene, sceneFramingBounds } from "../kit/scene.js";
import { createGlbScene } from "./glbScene.js";

const INSPECT = Object.freeze({
  defaultColor: "#b6c4ce", fillColors: ["#b6c4ce", "#f4a7a7", "#f8c77e"], cycleColors: false, overrideSourceColors: false,
  tintStrength: 0, roughness: 0.58, metalness: 0.02, clearcoat: 0.12, clearcoatRoughness: 0.42, envMapIntensity: 0.42, emissiveIntensity: 0.02
});
const look = (patch = {}) => ({ materialSettings: { ...INSPECT, ...patch.materialSettings }, authored: patch.authored === true,
  surface: { style: "shaded", opacity: 1, ...patch.surface } });

function glbDocument({ animatedBounds = null } = {}) {
  const scene = new THREE.Group();
  const texture = new THREE.Texture();
  const steel = new THREE.MeshStandardMaterial({ color: "#336699", roughness: 0.2, metalness: 1, map: texture });
  const plain = new THREE.MeshStandardMaterial({ color: "#dddddd" });
  plain.userData.cadSourceColor = false;
  const body = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), steel);
  const lid = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), plain);
  const skinned = new THREE.SkinnedMesh(new THREE.BoxGeometry(1, 1, 1), steel);
  const lamp = new THREE.PointLight("#ffffff", 5);
  scene.add(body, lid, skinned, lamp);
  return { document: { scene, clips: [], cadRootMatrix: new THREE.Matrix4().makeScale(1000, 1000, 1000).toArray(),
    restBounds: { min: [-500, -500, -500], max: [500, 500, 500] }, animatedBounds }, body, lid, skinned, lamp, steel, plain, texture };
}

test("the scene is the file's native hierarchy in CAD space, under the kit's contract", () => {
  const { document, body, skinned, lamp } = glbDocument();
  const scene = createGlbScene(THREE, document);
  assert.equal(isKitScene(scene), true);
  assert.equal(document.scene.parent, scene.object3D, "the native scene is adopted, never flattened");
  assert.deepEqual(scene.object3D.matrix.elements.slice(0, 1), [1000]);
  assert.deepEqual(sceneFramingBounds(scene), document.restBounds);
  assert.equal(lamp.visible, false, "the viewer owns the one lighting rig");
  assert.equal(body.castShadow, true);
  assert.deepEqual([body.frustumCulled, skinned.frustumCulled], [true, false], "a deforming mesh outgrows its rest-pose culling box");
  assert.equal(scene.meshCount, 3);
});

test("a file with clips is framed and lit on the box sampled over every pose", () => {
  const animatedBounds = { min: [-500, -500, -500], max: [2500, 500, 500] };
  const scene = createGlbScene(THREE, glbDocument({ animatedBounds }).document);
  assert.deepEqual([scene.bounds, scene.restBounds], [animatedBounds, animatedBounds]);
});

test("Inspect wears the viewer's finish and keeps colour, map and opacity; Render restores the authored finish", () => {
  const { document, body, lid, steel, texture } = glbDocument();
  const scene = createGlbScene(THREE, document);
  scene.setSurfaceLook(look());
  assert.deepEqual([body.material.roughness, body.material.metalness, body.material.clearcoat], [0.58, 0.02, 0.12]);
  assert.equal(body.material.map, texture);
  assert.equal(lid.material.color.getHexString(), new THREE.Color("#b6c4ce").getHexString(), "an uncoloured part takes the viewer's surface colour");
  scene.setSurfaceLook(look({ authored: true }));
  assert.equal(body.material, steel);
  assert.deepEqual([steel.roughness, steel.metalness, steel.color.getHexString()], [0.2, 1, "336699"]);
  assert.equal(lid.material.color.getHexString(), "dddddd", "Render shows the file as written");
});

test("colour modes and surface style apply to the native scene and are fully reversible", () => {
  const { document, body, lid, skinned, steel, texture } = glbDocument();
  const scene = createGlbScene(THREE, document);
  scene.setSurfaceLook(look({ materialSettings: { overrideSourceColors: true, defaultColor: "#ff8800", fillColors: ["#ff8800"] } }));
  assert.deepEqual([body, lid, skinned].map(mesh => mesh.material.color.getHexString()), ["ff8800", "ff8800", "ff8800"]);
  assert.equal(body.material.map, null);
  scene.setSurfaceLook(look({ materialSettings: { overrideSourceColors: true, cycleColors: true } }));
  assert.equal(new Set([body, lid, skinned].map(mesh => mesh.material.color.getHexString())).size, 3, "a palette colour per mesh, even where the file shared one material");
  scene.setSurfaceLook(look({ surface: { style: "flat", opacity: 0.4 } }));
  assert.deepEqual([body.material.isMeshBasicMaterial, body.material.opacity, body.material.transparent], [true, 0.4, true]);
  scene.setSurfaceLook(look({ authored: true }));
  assert.equal(body.material, steel);
  assert.deepEqual([steel.map, steel.opacity, steel.transparent, steel.color.getHexString()], [texture, 1, false, "336699"]);
});

test("dispose releases the document once: geometry, materials and textures, and the look's own stand-ins", () => {
  const { document, body, steel, texture } = glbDocument();
  const released = { geometry: 0, material: 0, texture: 0, standIn: 0 };
  body.geometry.dispose = () => { released.geometry += 1; };
  steel.dispose = () => { released.material += 1; };
  texture.dispose = () => { released.texture += 1; };
  const scene = createGlbScene(THREE, document);
  const host = new THREE.Group();
  host.add(scene.object3D);
  scene.setSurfaceLook(look());
  body.material.dispose = () => { released.standIn += 1; };
  scene.dispose();
  scene.dispose();
  assert.equal(scene.object3D.parent, null);
  assert.equal(body.material, steel, "the authored material is back before it is released");
  assert.deepEqual(released, { geometry: 1, material: 1, texture: 1, standIn: 1 });
  assert.doesNotThrow(() => scene.setSurfaceLook(look()), "a late look from the viewport is ignored, never applied to released materials");
});
