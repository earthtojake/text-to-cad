import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { createMeshScene } from "../render/meshScene.js";
import { createSceneClip } from "./sceneClip.js";
import { GLB_SCENE_UNITS } from "./sceneUnits.js";

// Two 10 mm boxes, one at the origin and one 20 mm along X: a scene of the mesh family's builder.
function twoBoxes(units) {
  const box = x => { const geometry = new THREE.BoxGeometry(10, 10, 10); geometry.translate(x + 5, 5, 5); return geometry; };
  return createMeshScene(THREE, [{ name: "a", geometry: box(0), color: null, paletteIndex: 0, path: [1] },
    { name: "b", geometry: box(20), color: null, paletteIndex: 1, path: [2] }], units ? { units } : undefined);
}
const planesOf = scene => scene.object3D.children.map(mesh => mesh.material.clippingPlanes?.length ?? 0);
const stencils = scene => scene.object3D.children.flatMap(mesh => mesh.children.filter(child => child.name === "Section stencil")).length;

test("Clip cuts every surface a scene drew at the plane its settings place in the framed box, caps the cut, and takes it all away", () => {
  const stage = new THREE.Scene();
  const scene = twoBoxes();
  stage.add(scene.object3D);
  const clip = createSceneClip(THREE, { stage });
  // No `at`: the middle of the model at rest (x 0..30), the lower side kept.
  const [plane] = clip.sync(scene, { enabled: true, axis: "x", invert: false });
  assert.deepEqual([plane.normal.toArray().map(value => value + 0), plane.constant], [[-1, 0, 0], 15]);
  assert.deepEqual(planesOf(scene), [1, 1], "both boxes' materials are cut");
  assert.equal(stencils(scene), 0, "the plane runs between the boxes: nothing to cap");
  clip.sync(scene, { enabled: true, axis: "x", at: 5 });
  assert.equal(stencils(scene), 2, "only the box the plane passes through is capped (its two stencil passes)");
  assert.ok(stage.getObjectByName("Section fill"), "the cap's fill plane is the stage's");
  // A look put on later keeps the cut (the scene's own `setClipPlanes`).
  scene.setSurfaceLook({ materialSettings: { defaultColor: "#888888", fillColors: [] }, authored: false, surface: { style: "flat", opacity: 1 } });
  assert.deepEqual(planesOf(scene), [1, 1], "a new look's stand-ins are cut too");
  assert.deepEqual(clip.sync(scene, { enabled: false, axis: "x" }), []);
  assert.deepEqual([planesOf(scene), stencils(scene), Boolean(stage.getObjectByName("Section fill"))], [[0, 0], 0, false]);
  // A plane past the model's kept face cuts nothing, and costs nothing.
  assert.deepEqual(clip.sync(scene, { enabled: true, axis: "x", at: 40 }), []);
  clip.dispose();
  scene.dispose();
});

test("Clip's `at` is in the file's unit: a GLB's metres are its scene's millimetres", () => {
  const scene = twoBoxes(GLB_SCENE_UNITS);
  const clip = createSceneClip(THREE, { stage: new THREE.Scene() });
  const [plane] = clip.sync(scene, { enabled: true, axis: "x", at: 0.012 });
  assert.equal(Math.round(plane.constant * 1e6) / 1e6, 12, "0.012 m is 12 mm along X");
  clip.dispose();
  scene.dispose();
});

test('scene caps use normal look colors under highlights and update with a new look', () => {
  const scene = twoBoxes();
  const stage = new THREE.Scene(); stage.add(scene.object3D);
  const clip = createSceneClip(THREE,{stage});
  const settings={enabled:true,axis:'x',at:5};
  const look={materialSettings:{defaultColor:'#336699',fillColors:['#336699'],overrideSourceColors:true},authored:false,surface:{style:'flat',opacity:.2}};
  scene.setSurfaceLook(look);
  clip.sync(scene,settings);
  const cap=stage.getObjectByName('Section fill');
  assert.equal(cap.material.color.getHexString(),'336699');
  scene.setHighlight({selected:['o1']});
  clip.sync(scene,settings);
  assert.equal(cap.material.color.getHexString(),'336699','selection tint is excluded');
  assert.equal(cap.material.opacity,1);
  const nextLook={...look,materialSettings:{...look.materialSettings,defaultColor:'#aa4433',fillColors:['#aa4433']}};
  scene.setSurfaceLook(nextLook);
  clip.sync(scene,settings);
  assert.equal(cap.material.color.getHexString(),'aa4433');
  clip.sync(scene,{...settings,partColors:false});
  assert.equal(cap.material.color.getHex(),0xe9a451);
  clip.dispose(); scene.dispose();
});
