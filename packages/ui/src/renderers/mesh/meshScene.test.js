import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { isKitScene, sceneFramingBounds } from "../kit/scene.js";
import { createMeshScene } from "./meshScene.js";

const INSPECT = Object.freeze({
  defaultColor: "#b6c4ce", fillColors: ["#b6c4ce", "#f4a7a7", "#f8c77e"], cycleColors: false, overrideSourceColors: false,
  tintStrength: 0, roughness: 0.58, metalness: 0.02, clearcoat: 0.12, clearcoatRoughness: 0.42, envMapIntensity: 0.42, emissiveIntensity: 0.02
});
const STUDIO = Object.freeze({ ...INSPECT, roughness: 0.34, metalness: 0, clearcoat: 0.3, emissiveIntensity: 0 });
const look = (patch = {}) => ({ materialSettings: { ...INSPECT, ...patch.materialSettings }, authored: patch.authored === true,
  surface: { style: "shaded", opacity: 1, ...patch.surface } });

function objects(colors = ["#d02020", null, "#2040d0"], paletteIndices = [0, 1, 2]) {
  return colors.map((color, index) => {
    const geometry = new THREE.BoxGeometry(10, 10, 10).translate(index * 20, 0, 0);
    geometry.computeBoundingBox();
    return { name: `object ${index}`, geometry, color: color ? new THREE.Color(color) : null, paletteIndex: paletteIndices[index] };
  });
}
const hex = mesh => mesh.material.color.getHexString();

test("the scene is one mesh per object and nothing else, under the kit's contract", () => {
  const source = objects();
  const scene = createMeshScene(THREE, source);
  assert.equal(isKitScene(scene), true);
  assert.deepEqual(scene.object3D.children.map(child => [child.isMesh, child.name, child.castShadow]),
    [[true, "object 0", true], [true, "object 1", true], [true, "object 2", true]]);
  assert.equal(scene.object3D.children[1].geometry, source[1].geometry, "the object's geometry, as built");
  assert.deepEqual(sceneFramingBounds(scene), { min: [-5, -5, -5], max: [45, 5, 5] });
  assert.equal(scene.bounds, scene.restBounds, "a mesh never moves");
  assert.equal(scene.meshCount, 3);
  assert.equal(scene.keepsAuthoredFinish, undefined, "no authored finish: Inspect needs no environment for it");
});

test("Original keeps an object's source colour; an object without one takes the viewer's surface colour", () => {
  const scene = createMeshScene(THREE, objects());
  const [red, plain, blue] = scene.object3D.children;
  scene.setSurfaceLook(look());
  assert.deepEqual([hex(red), hex(plain), hex(blue)], ["d02020", new THREE.Color("#b6c4ce").getHexString(), "2040d0"]);
  assert.deepEqual([red.material.userData.cadSourceColor, plain.material.userData.cadSourceColor], [true, false]);
  assert.deepEqual([red.material.roughness, red.material.metalness, red.material.clearcoat, red.material.side], [0.58, 0.02, 0.12, THREE.DoubleSide]);
});

test("Render is a look like Solid: the studio's surface over the same colours, nothing 'authored' kept", () => {
  const scene = createMeshScene(THREE, objects());
  const [red, plain] = scene.object3D.children;
  scene.setSurfaceLook({ ...look({ materialSettings: STUDIO }), authored: true });
  assert.deepEqual([red.material.roughness, red.material.clearcoat, red.material.emissiveIntensity], [0.34, 0.3, 0]);
  assert.deepEqual([hex(red), hex(plain)], ["d02020", new THREE.Color("#b6c4ce").getHexString()], "an uncoloured object is never the white it was built with");
  scene.setSurfaceLook(look());
  assert.deepEqual([red.material.roughness, red.material.clearcoat, red.material.emissiveIntensity], [0.58, 0.12, 0.02], "and back");
});

test("Single colour, Color by part, Flat and opacity apply per object and are reversible", () => {
  const scene = createMeshScene(THREE, objects(undefined, [2, 0, 1]));
  const meshes = scene.object3D.children;
  scene.setSurfaceLook(look({ materialSettings: { overrideSourceColors: true, defaultColor: "#ff8800", fillColors: ["#ff8800"] } }));
  assert.deepEqual(meshes.map(hex), ["ff8800", "ff8800", "ff8800"]);
  scene.setSurfaceLook(look({ materialSettings: { overrideSourceColors: true, cycleColors: true } }));
  const palette = INSPECT.fillColors.map(color => new THREE.Color(color).getHexString());
  assert.deepEqual(meshes.map(hex), [palette[2], palette[0], palette[1]], "the palette follows each object's palette index, not scene order");
  scene.setSurfaceLook(look({ surface: { style: "flat", opacity: 0.5 } }));
  assert.deepEqual([meshes[0].material.isMeshBasicMaterial, meshes[0].material.opacity, meshes[0].material.transparent, meshes[0].material.depthWrite], [true, 0.5, true, false]);
  scene.setSurfaceLook(look());
  assert.deepEqual([meshes[0].material.isMeshPhysicalMaterial, meshes[0].material.opacity, meshes[0].material.transparent, hex(meshes[0])], [true, 1, false, "d02020"]);
});

test("a single-object file takes the first palette colour in Color by part", () => {
  const scene = createMeshScene(THREE, objects([null], [0]));
  scene.setSurfaceLook(look({ materialSettings: { overrideSourceColors: true, cycleColors: true } }));
  assert.equal(hex(scene.object3D.children[0]), new THREE.Color(INSPECT.fillColors[0]).getHexString());
});

test("dispose releases geometries, materials and the look's stand-ins once, and ignores a late look", () => {
  const source = objects(["#d02020"], [0]);
  const released = { geometry: 0, standIn: 0 };
  source[0].geometry.dispose = () => { released.geometry += 1; };
  const scene = createMeshScene(THREE, source);
  const host = new THREE.Group();
  host.add(scene.object3D);
  scene.setSurfaceLook(look());
  scene.object3D.children[0].material.dispose = () => { released.standIn += 1; };
  scene.dispose();
  scene.dispose();
  assert.equal(scene.object3D.parent, null);
  assert.deepEqual(released, { geometry: 1, standIn: 1 });
  assert.doesNotThrow(() => scene.setSurfaceLook(look()));
});
