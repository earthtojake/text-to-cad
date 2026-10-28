import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { createSurfaceLook } from "./surfaceLook.js";

const INSPECT = Object.freeze({
  defaultColor: "#8fa3b5", fillColors: ["#8fa3b5"], cycleColors: false, overrideSourceColors: false,
  tintStrength: 0, roughness: 0.92, metalness: 0.03, clearcoat: 0, clearcoatRoughness: 0.2, envMapIntensity: 0.4, emissiveIntensity: 0.02
});

function scene() {
  const texture = new THREE.Texture();
  const shared = new THREE.MeshStandardMaterial({ color: "#336699", roughness: 0.2, metalness: 1, map: texture, side: THREE.FrontSide });
  const glass = new THREE.MeshStandardMaterial({ color: "#ffffff", transparent: true, opacity: 0.5, depthWrite: false });
  const unlit = new THREE.MeshBasicMaterial({ color: "#ff0000" });
  const root = new THREE.Group();
  const a = new THREE.Mesh(new THREE.BoxGeometry(), shared);
  const b = new THREE.Mesh(new THREE.BoxGeometry(), shared);
  const c = new THREE.Mesh(new THREE.BoxGeometry(), [glass, unlit]);
  root.add(a, b, c);
  return { root, a, b, c, shared, glass, unlit, texture };
}

test("Inspect wears the viewer's finish and keeps colour, map and opacity; authored restores the file", () => {
  const { root, a, b, c, unlit, texture } = scene();
  const look = createSurfaceLook(THREE, root);
  assert.equal(look.meshCount, 3);
  assert.notEqual(a.material, b.material, "a shared material is un-shared so a palette can colour each mesh");

  const authoredA = a.material;
  look.apply({ materialSettings: INSPECT, authored: false, surface: { style: "shaded", opacity: 1 } });
  assert.notEqual(a.material, authoredA, "Inspect wears a stand-in; the authored material is left as written");
  assert.deepEqual([authoredA.roughness, authoredA.metalness], [0.2, 1]);
  for (const mesh of [a, b]) {
    assert.equal(mesh.material.isMeshPhysicalMaterial, true, "the viewer's surface has a clear coat, which a standard material cannot carry");
    assert.deepEqual([mesh.material.roughness, mesh.material.metalness, mesh.material.clearcoat], [0.92, 0.03, 0]);
    assert.deepEqual([mesh.material.emissive.getHexString(), mesh.material.emissiveIntensity], ["336699", 0.02]);
    assert.equal(mesh.material.color.getHexString(), "336699");
    assert.equal(mesh.material.map, texture);
    assert.equal(mesh.material.side, THREE.DoubleSide);
  }
  assert.equal(c.material[0].opacity, 0.5);
  assert.equal(c.material[1], unlit, "an unlit authored material is left alone");

  look.apply({ materialSettings: INSPECT, authored: true, surface: { style: "shaded", opacity: 1 } });
  assert.equal(a.material, authoredA);
  assert.deepEqual([a.material.roughness, a.material.metalness, a.material.side], [0.2, 1, THREE.FrontSide]);
  // Toggling back and forth never loses the authored values.
  look.apply({ materialSettings: INSPECT, authored: false, surface: { style: "shaded", opacity: 1 } });
  look.apply(null);
  assert.deepEqual([b.material.roughness, b.material.metalness, b.material.side], [0.2, 1, THREE.FrontSide]);
});

test("colour modes: a single colour and a per-mesh palette override source colours and maps, Original brings them back", () => {
  const { root, a, b, c, texture } = scene();
  const look = createSurfaceLook(THREE, root);
  const single = { ...INSPECT, overrideSourceColors: true, defaultColor: "#ff8800", fillColors: ["#ff8800"] };
  look.apply({ materialSettings: single, authored: false, surface: { style: "shaded", opacity: 1 } });
  assert.deepEqual([a, b].map(mesh => mesh.material.color.getHexString()), ["ff8800", "ff8800"]);
  assert.equal(a.material.map, null, "a texture would tint the chosen colour");

  const palette = { ...INSPECT, overrideSourceColors: true, cycleColors: true, defaultColor: "#ff0000", fillColors: ["#ff0000", "#00ff00", "#0000ff"] };
  look.apply({ materialSettings: palette, authored: true, surface: { style: "shaded", opacity: 1 } });
  assert.deepEqual([a.material, b.material, c.material[0]].map(material => material.color.getHexString()), ["ff0000", "00ff00", "0000ff"]);
  assert.equal(a.material.roughness, 0.2, "Render keeps the authored finish under a palette");

  look.apply({ materialSettings: INSPECT, authored: false, surface: { style: "shaded", opacity: 1 } });
  assert.equal(a.material.color.getHexString(), "336699");
  assert.equal(a.material.map, texture);
});

test("a mesh that names its place in the palette takes that colour, whatever the traversal order", () => {
  const { root, a, b, c } = scene();
  [a, b, c].forEach((mesh, index) => { mesh.userData.cadFillIndex = 2 - index; });
  const look = createSurfaceLook(THREE, root);
  const palette = { ...INSPECT, overrideSourceColors: true, cycleColors: true, defaultColor: "#ff0000", fillColors: ["#ff0000", "#00ff00", "#0000ff"] };
  look.apply({ materialSettings: palette, authored: false, surface: { style: "shaded", opacity: 1 } });
  assert.deepEqual([a.material, b.material, c.material[0]].map(material => material.color.getHexString()), ["0000ff", "00ff00", "ff0000"]);
});

test("a material that carries no source colour takes the viewer's surface colour in Inspect only", () => {
  const { root, a, shared } = scene();
  shared.userData.cadSourceColor = false;
  const look = createSurfaceLook(THREE, root);
  look.apply({ materialSettings: INSPECT, authored: false, surface: { style: "shaded", opacity: 1 } });
  assert.equal(a.material.color.getHexString(), "8fa3b5");
  look.apply({ materialSettings: INSPECT, authored: true, surface: { style: "shaded", opacity: 1 } });
  assert.equal(a.material.color.getHexString(), "336699");
});

test("a part that authored its own glow keeps it in Inspect", () => {
  const root = new THREE.Group();
  const lamp = new THREE.Mesh(new THREE.BoxGeometry(), new THREE.MeshStandardMaterial({ color: "#222222", emissive: "#ff0000", emissiveIntensity: 2 }));
  root.add(lamp);
  createSurfaceLook(THREE, root).apply({ materialSettings: INSPECT, authored: false, surface: { style: "shaded", opacity: 1 } });
  assert.deepEqual([lamp.material.emissive.getHexString(), lamp.material.emissiveIntensity], ["ff0000", 2]);
});

test("opacity scales the authored opacity; Flat swaps in an unlit stand-in and Shaded swaps back", () => {
  const { root, a, c } = scene();
  const look = createSurfaceLook(THREE, root);
  look.apply({ materialSettings: INSPECT, authored: false, surface: { style: "shaded", opacity: 1 } });
  const lit = a.material;
  look.apply({ materialSettings: INSPECT, authored: false, surface: { style: "flat", opacity: 0.5 } });
  assert.equal(a.material.isMeshBasicMaterial, true);
  assert.equal(a.material.color.getHexString(), "336699");
  assert.deepEqual([a.material.opacity, a.material.transparent, a.material.depthWrite], [0.5, true, false]);
  assert.equal(c.material[0].opacity, 0.25);
  look.apply({ materialSettings: INSPECT, authored: false, surface: { style: "shaded", opacity: 1 } });
  assert.equal(a.material, lit);
  assert.deepEqual([lit.opacity, lit.transparent, lit.depthWrite], [1, false, true]);
});

test("dispose restores the authored scene and releases only what the look created", () => {
  const { root, a, b, shared } = scene();
  let sharedDisposed = 0;
  shared.dispose = () => { sharedDisposed += 1; };
  const look = createSurfaceLook(THREE, root);
  const clone = b.material;
  let cloneDisposed = 0;
  clone.dispose = () => { cloneDisposed += 1; };
  look.apply({ materialSettings: INSPECT, authored: false, surface: { style: "flat", opacity: 1 } });
  const standIn = a.material;
  let standInDisposed = 0;
  standIn.dispose = () => { standInDisposed += 1; };
  look.dispose();
  assert.equal(a.material, shared);
  assert.deepEqual([shared.roughness, shared.metalness], [0.2, 1]);
  assert.deepEqual([sharedDisposed, cloneDisposed, standInDisposed], [0, 1, 1]);
});

test("a look's surface model: its stand-ins compile OCCT's lighting after three's, an authored look and none keep three's", () => {
  const { root, a } = scene();
  const authored = a.material;
  const look = createSurfaceLook(THREE, root);
  look.apply({ materialSettings: INSPECT, authored: false, surface: { style: "shaded", opacity: 1 }, brdf: "occt" });
  const standIn = a.material;
  assert.equal(standIn.customProgramCacheKey(), "surface-brdf:occt", "one program per model, shared by every stand-in");
  const shader = { fragmentShader: THREE.ShaderLib.physical.fragmentShader, uniforms: {} };
  standIn.onBeforeCompile(shader);
  const at = (text) => shader.fragmentShader.indexOf(text);
  assert.ok(at("#include <lights_physical_pars_fragment>") < at("#define RE_Direct RE_Direct_Occt"), "after three's own functions");
  assert.ok(at("#define RE_IndirectSpecular RE_IndirectSpecular_Occt") > 0);
  assert.ok(at("#include <lights_physical_fragment>") < at("material.roughness = clamp( roughnessFactor, 0.01, 1.0 );"));
  assert.ok(at("material.roughness = clamp( roughnessFactor, 0.01, 1.0 );") < at("#include <lights_fragment_begin>"),
    "the roughness set before the lights read it");
  assert.equal(shader.uniforms.occtEnvironmentTable.value.image.width, 32, "OCCT's split-sum table, not three's");
  assert.throws(() => look.apply({ materialSettings: INSPECT, authored: false, surface: { style: "shaded", opacity: 1 }, brdf: "phong" }),
    /a surface model is one of occt, not "phong"/);

  look.apply({ materialSettings: INSPECT, authored: true, surface: { style: "shaded", opacity: 1 }, brdf: "occt" });
  assert.equal(a.material, authored);
  assert.equal(authored.onBeforeCompile, THREE.Material.prototype.onBeforeCompile, "an authored material is never touched");
  look.apply({ materialSettings: INSPECT, authored: false, surface: { style: "shaded", opacity: 1 } });
  assert.equal(a.material, standIn);
  assert.equal(standIn.onBeforeCompile, THREE.Material.prototype.onBeforeCompile, "no model named: three's own");
  assert.equal(standIn.customProgramCacheKey, THREE.Material.prototype.customProgramCacheKey);
});


test("authored Standard and Physical finishes survive shaded modes, with reversible Parts and X-ray overrides", () => {
  for (const physical of [false, true]) {
    const texture = new THREE.Texture();
    const material = physical ? new THREE.MeshPhysicalMaterial({ color: "#336699", map: texture,
      metalness: 1, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.15, transmission: 0.8,
      thickness: 0.006, attenuationDistance: 50, opacity: 0.7, transparent: true })
      : new THREE.MeshStandardMaterial({ color: "#336699", map: texture, metalness: 1, roughness: 0.3, opacity: 0.7, transparent: true });
    material.userData.cadAuthoredFinish = true;
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(), material), root = new THREE.Group(); root.add(mesh);
    const surface = createSurfaceLook(THREE, root);
    const original = { materialSettings: INSPECT, authored: false, surface: { style: "shaded", opacity: 1 } };
    const check = () => {
      assert.deepEqual([mesh.material.metalness, mesh.material.roughness, mesh.material.clearcoat], [1, 0.3, physical ? 1 : 0]);
      assert.equal(mesh.material.map, texture);
      assert.deepEqual([mesh.material.color.getHexString(), mesh.material.opacity, mesh.material.transparent], ["336699", 0.7, true]);
      assert.deepEqual([mesh.material.emissive.getHexString(), mesh.material.emissiveIntensity], ["336699", 0.02], "non-emitting authored finishes retain the existing small Inspect lift");
      assert.equal(mesh.material.transmission, physical ? 0.8 : 0);
      assert.equal(mesh.material.attenuationDistance, physical ? 50 : Infinity);
    };
    surface.apply(original); check();
    surface.apply({ ...original, materialSettings: { ...INSPECT, overrideSourceColors: true, defaultColor: "#ff8800", fillColors: ["#ff8800"] } });
    assert.deepEqual([mesh.material.color.getHexString(), mesh.material.metalness, mesh.material.roughness, mesh.material.transmission], ["ff8800", 0.03, 0.92, 0]);
    assert.equal(mesh.material.map, null);
    surface.apply({ ...original, finishes: false, surface: { style: "shaded", opacity: 0.22 } });
    assert.equal(mesh.material.opacity, 0.7 * 0.22);
    assert.equal(mesh.material.transmission, 0);
    surface.apply(original); check();
    assert.deepEqual([material.metalness, material.roughness, material.opacity], [1, 0.3, 0.7], "authored material stays unchanged");
    surface.dispose(); mesh.geometry.dispose(); material.dispose(); texture.dispose();
  }
});


test("an emitting authored finish restores its own glow after X-ray without changing the non-emitting Inspect lift", () => {
  const root = new THREE.Group();
  const emitting = new THREE.MeshPhysicalMaterial({ color: "#336699", metalness: 1, roughness: 0.3,
    emissive: "#ff8800", emissiveIntensity: 2 });
  const neutral = new THREE.MeshPhysicalMaterial({ color: "#336699", metalness: 1, roughness: 0.3 });
  for (const material of [emitting, neutral]) material.userData.cadAuthoredFinish = true;
  const lamp = new THREE.Mesh(new THREE.BoxGeometry(), emitting), plate = new THREE.Mesh(new THREE.BoxGeometry(), neutral);
  root.add(lamp, plate);
  const surface = createSurfaceLook(THREE, root);
  const original = { authored: false, materialSettings: INSPECT, surface: { style: "shaded", opacity: 1 } };
  const check = () => {
    assert.deepEqual([lamp.material.emissive.getHexString(), lamp.material.emissiveIntensity], ["ff8800", 2]);
    assert.deepEqual([plate.material.emissive.getHexString(), plate.material.emissiveIntensity], ["336699", 0.02]);
  };
  surface.apply(original); check();
  const single = { ...original, materialSettings: { ...INSPECT, overrideSourceColors: true, defaultColor: "#ff0000", fillColors: ["#ff0000"] } };
  surface.apply(single);
  const direct = [lamp.material.color.getHexString(), lamp.material.emissive.getHexString(), lamp.material.emissiveIntensity];
  assert.deepEqual(direct, ["ff0000", "ff8800", 2], "Single color keeps the authored glow");
  surface.apply({ ...original, finishes: false, surface: { style: "shaded", opacity: 0.22 } });
  assert.deepEqual([lamp.material.emissive.getHexString(), lamp.material.emissiveIntensity], ["336699", 0.02]);
  surface.apply(single);
  assert.deepEqual([lamp.material.color.getHexString(), lamp.material.emissive.getHexString(), lamp.material.emissiveIntensity], direct,
    "X-ray → Single color matches direct Single color, independent of the previous mode");
  surface.apply(original); check();
  assert.deepEqual([emitting.emissive.getHexString(), emitting.emissiveIntensity], ["ff8800", 2]);
  assert.deepEqual([neutral.emissive.getHexString(), neutral.emissiveIntensity], ["000000", 1]);
  surface.dispose(); lamp.geometry.dispose(); plate.geometry.dispose(); emitting.dispose(); neutral.dispose();
});
