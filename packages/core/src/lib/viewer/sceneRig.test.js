// A scene's own rig on a stage (`sceneRig.js`): its lights in place, its environment the scene's
// (one PMREM per image, shared by the rigs that light with it), its curve as three's
// CustomToneMapping, its exposure, the stage given back as it was by the last rig to go, and the
// scene drawn as the rig blends.
import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { recordingRenderer } from "./__tests__/recordingRenderer.js";
import {
  SCENE_RIG_TONE_CURVES, applySceneRig, compileWithSceneRig, drawnOverSurfaces, installSceneRigToneCurve, isSceneRig,
  renderWithSceneRig, sceneRigFor
} from "./sceneRig.js";

const IMAGE = Object.freeze({ width: 2, height: 1, data: new Float32Array([1, 1, 1, 1, 2, 2, 2, 1]) });
const RIG = Object.freeze({
  id: "test", ambient: null,
  lights: [{ name: "key", towards: [0, 0, 2], color: "#ffffff", intensity: 3 }, { name: "fill", towards: [1, 0, 0], color: "#ffeedd", intensity: 2 }],
  environment: { ...IMAGE, intensity: 0.5, rotation: [Math.PI / 2, 0, 0] }, exposure: 1, toneCurve: "clamp"
});

/** THREE with a PMREM generator that needs no WebGL: it records the images it turns into targets. */
function headless() {
  const made = [];
  class PMREMGenerator {
    fromEquirectangular(texture) {
      const target = { texture: new THREE.Texture(), disposed: false, source: texture, dispose() { this.disposed = true; } };
      made.push(target);
      return target;
    }
    dispose() {}
  }
  return { three: { ...THREE, PMREMGenerator }, made };
}

function stage() {
  const scene = new THREE.Scene();
  scene.environmentIntensity = 1;
  return { scene, renderer: { toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: 1.08 } };
}

test("a scene's rig for the look it wears: its rigFor's answer where it has one, else its rig, else none", () => {
  const other = { ...RIG, id: "other" };
  const look = { surface: { style: "shaded", opacity: 0.22 } };
  const asked = [];
  const scene = { rig: RIG, rigFor(found) { asked.push(found); return found === look ? other : RIG; } };
  assert.equal(sceneRigFor(scene, look), other);
  assert.equal(sceneRigFor(scene, null), RIG);
  assert.deepEqual(asked, [look, null]);
  assert.equal(sceneRigFor({ rig: RIG }, look), RIG);
  assert.equal(sceneRigFor({}, look), null);
  assert.equal(sceneRigFor(null, look), null);
});

test("the rig's curve is three's CustomToneMapping, once a page", () => {
  installSceneRigToneCurve(THREE, "clamp");
  const chunk = THREE.ShaderChunk.tonemapping_pars_fragment;
  assert.ok(chunk.includes(`vec3 CustomToneMapping( vec3 color ) { ${SCENE_RIG_TONE_CURVES.clamp} }`));
  installSceneRigToneCurve(THREE, "clamp");
  assert.equal(THREE.ShaderChunk.tonemapping_pars_fragment, chunk, "installing it again changes nothing");
  assert.throws(() => installSceneRigToneCurve(THREE, "filmic"), /tone curve is one of clamp/);
  assert.equal(isSceneRig({ ...RIG, toneCurve: "aces" }), false);
  assert.equal(isSceneRig({ ...RIG, environment: { ...RIG.environment, width: 3 } }), false, "an image its pixels do not fill");
});

test("a rig lights the stage in place of its own, its image the scene's environment, and gives the stage back", () => {
  const { three, made } = headless();
  const target = stage();
  const { scene, renderer } = target;
  const up = applySceneRig(three, target, RIG);
  assert.equal(target.sceneRig, up);
  assert.equal(up.group.parent, scene);
  const [key, fill] = up.group.children;
  assert.deepEqual([key.intensity, fill.intensity], [3, 2]);
  assert.deepEqual(key.position.toArray(), [0, 0, 1], "it shines from where `towards` points, its target the origin");
  assert.equal(fill.color.getHexString(), "ffeedd");
  assert.equal(key.castShadow || fill.castShadow, false);
  assert.equal(made.length, 1);
  assert.equal(made[0].source.mapping, THREE.EquirectangularReflectionMapping);
  assert.equal(made[0].source.type, THREE.HalfFloatType, "half floats, which WebGL filters");
  assert.deepEqual([scene.environment, scene.environmentIntensity], [made[0].texture, 0.5]);
  assert.deepEqual(scene.environmentRotation.toArray().slice(0, 3), [Math.PI / 2, 0, 0]);
  assert.deepEqual([renderer.toneMapping, renderer.toneMappingExposure], [THREE.CustomToneMapping, 1]);
  // The stage sets its own exposure; the rig puts its own back.
  renderer.toneMappingExposure = 1.2;
  up.restate();
  assert.equal(renderer.toneMappingExposure, 1);
  // The next version of the scene brings a rig of the same image: up before the first comes down,
  // it shares the first's PMREM, and the first going leaves the stage to it.
  const next = applySceneRig(three, target, { ...RIG, id: "next" });
  up.dispose();
  assert.equal(made.length, 1, "one PMREM for one image");
  assert.equal(made[0].disposed, false);
  assert.equal(up.group.parent, null);
  assert.deepEqual([scene.environment, renderer.toneMapping, target.sceneRig], [made[0].texture, THREE.CustomToneMapping, next]);
  next.dispose();
  assert.equal(made[0].disposed, true, "released with the last rig that lit with it");
  assert.deepEqual([scene.environment, scene.environmentIntensity, renderer.toneMapping, renderer.toneMappingExposure],
    [null, 1, THREE.ACESFilmicToneMapping, 1.08]);
  assert.deepEqual(scene.environmentRotation.toArray().slice(0, 3), [0, 0, 0]);
  assert.throws(() => applySceneRig(three, target, { ...RIG, lights: null }), /a scene rig has/);
});

// A rig that blends in linear light (an engine document's X-ray), lit by no image.
const LINEAR = Object.freeze({ ...RIG, id: "linear", environment: null, blend: "linear" });

/** A stage's scene as X-ray draws one: see-through surfaces, and edges three draws after them. */
function xray() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#f0f4f9");
  const surface = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshPhysicalMaterial({ transparent: true, opacity: 0.22 }));
  const cap = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshBasicMaterial());
  cap.renderOrder = 1002;
  const edges = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ transparent: true }));
  edges.renderOrder = 1;
  surface.add(edges);
  scene.add(surface, cap);
  return { scene, surface, cap, edges };
}

test("a rig that blends in linear light draws the surfaces into a half-float target, encodes them, and what goes over after", () => {
  assert.equal(isSceneRig(LINEAR), true);
  assert.equal(isSceneRig({ ...LINEAR, blend: "srgb" }), false, "a blend no stage knows");
  const { renderer, draws } = recordingRenderer();
  const { scene, surface, cap, edges } = xray();
  const camera = new THREE.PerspectiveCamera();
  const up = applySceneRig(THREE, { scene, renderer }, LINEAR);
  const lights = up.group.children;
  renderWithSceneRig(up, renderer, scene, camera);
  const linear = up.frame.target;
  assert.equal(linear.texture.type, THREE.HalfFloatType);
  assert.equal(linear.texture.colorSpace, THREE.LinearSRGBColorSpace, "written in linear light");
  assert.equal(linear.isXRRenderTarget, true, "drawn as the canvas is: each fragment under the rig's tone curve");
  assert.deepEqual([linear.width, linear.height, linear.samples], [800, 600, 4], "the drawing buffer's size, multisampled as the canvas is");
  assert.equal(draws.length, 3);
  const [surfaces, encode, over] = draws;
  assert.deepEqual([surfaces.scene, surfaces.target, surfaces.autoClear, surfaces.background], [scene, linear, true, scene.background]);
  assert.deepEqual(surfaces.drawn, [surface, cap], "the surfaces, and what three draws before them, in linear light");
  assert.deepEqual(surfaces.viewport.toArray(), [0, 0, 800, 600]);
  assert.deepEqual([encode.target, encode.autoClear], [null, false], "encoded onto the canvas, over every pixel of the view");
  const material = encode.scene.children[0].material;
  assert.deepEqual([material.blending, material.toneMapped, material.depthFunc, material.depthWrite],
    [THREE.NoBlending, false, THREE.AlwaysDepth, true], "the scene's depth with it");
  assert.match(material.fragmentShader, /linearToOutputTexel/, "in the canvas's colour space");
  assert.deepEqual([over.scene, over.target, over.autoClear, over.background, over.shadows], [scene, null, false, null, false]);
  assert.deepEqual(over.drawn, [edges], "then the edges, over the encoded picture, as three draws them on the canvas");
  assert.ok(lights.every(light => light.layers.test(camera.layers)) && lights.every(light => light.layers.isEnabled(31)),
    "lit by the rig's lights in both");
  assert.deepEqual([edges.layers.mask, camera.layers.mask, scene.background.getHexString()], [1, 1, "f0f4f9"], "and put back");
  assert.deepEqual([renderer.getRenderTarget(), renderer.autoClear, renderer.shadowMap.autoUpdate], [null, true, true], "the stage as it was");
  // Part of the canvas (a library card's picture): drawn there in the target and filled there alone,
  // even where three floors the canvas's viewport when it is the target again.
  draws.length = 0;
  renderer.setViewport(new THREE.Vector4(0, 0, 150.25, 100));
  renderWithSceneRig(up, renderer, scene, camera);
  assert.deepEqual(draws.map(draw => draw.viewport.toArray()), [[0, 0, 301, 200], [0, 0, 301, 200], [0, 0, 301, 200]]);
  // Nothing over the surfaces: no third pass.
  draws.length = 0;
  edges.removeFromParent();
  renderWithSceneRig(up, renderer, scene, camera);
  assert.equal(draws.length, 2);
  let released = false;
  linear.addEventListener("dispose", () => { released = true; });
  up.dispose();
  assert.equal(released, true, "its target goes with the rig");
  assert.throws(() => up.frame.render(renderer, scene, camera), /disposed/);
});

test("what goes over the surfaces is what three draws after them: transparent, of a later order, seen by the camera", () => {
  const camera = new THREE.PerspectiveCamera();
  const line = (order, material = new THREE.LineBasicMaterial({ transparent: true })) => {
    const object = new THREE.LineSegments(new THREE.BufferGeometry(), material);
    object.renderOrder = order;
    return object;
  };
  assert.equal(drawnOverSurfaces(line(1), camera), true);
  assert.equal(drawnOverSurfaces(line(0), camera), false, "a see-through surface's own order");
  assert.equal(drawnOverSurfaces(line(5, new THREE.LineBasicMaterial()), camera), false, "opaque: drawn before every surface");
  const unseen = line(1);
  unseen.layers.set(2);
  assert.equal(drawnOverSurfaces(unseen, camera), false);
  const highlighted = new THREE.Mesh(new THREE.BufferGeometry(), [new THREE.MeshBasicMaterial(), new THREE.MeshBasicMaterial({ transparent: true })]);
  highlighted.renderOrder = 23;
  assert.equal(drawnOverSurfaces(highlighted, camera), true);
  const group = new THREE.Group();
  group.renderOrder = 4;
  assert.equal(drawnOverSurfaces(group, camera), false, "only what is drawn");
});

test("every other rig, a stage with none and a renderer without half floats draw the scene as three does", () => {
  const camera = new THREE.PerspectiveCamera();
  const { renderer, draws } = recordingRenderer();
  const { scene } = xray();
  const up = applySceneRig(THREE, { scene, renderer }, { ...RIG, environment: null });
  assert.equal(up.frame, null);
  assert.equal(up.group.children.some(light => light.layers.isEnabled(31)), false);
  renderWithSceneRig(up, renderer, scene, camera);
  renderWithSceneRig(null, renderer, scene, camera);
  up.dispose();
  const plain = recordingRenderer({ halfFloats: false });
  const linear = applySceneRig(THREE, { scene, renderer: plain.renderer }, LINEAR);
  renderWithSceneRig(linear, plain.renderer, scene, camera);
  assert.equal(linear.frame.target, null, "no target made");
  linear.dispose();
  for (const draw of [...draws, ...plain.draws]) {
    assert.deepEqual([draw.scene, draw.target, draw.drawn.length], [scene, null, 3], "one draw of everything, on the canvas");
  }
  assert.equal(draws.length + plain.draws.length, 3);
});

test("what a stage compiles before it draws is what it draws: the surfaces' programs into the target, the rest onto the canvas", async () => {
  const { renderer, draws } = recordingRenderer();
  const { scene, edges } = xray();
  const camera = new THREE.PerspectiveCamera();
  const up = applySceneRig(THREE, { scene, renderer }, LINEAR);
  await compileWithSceneRig(up, renderer, scene, camera);
  assert.deepEqual(draws.map(draw => [draw.compiled, draw.target]), [[scene, up.frame.target], [edges, null], [draws[2].compiled, null]]);
  assert.equal(draws[2].compiled.children[0].material.name, "Scene rig linear frame");
  assert.equal(renderer.getRenderTarget(), null);
  up.dispose();
  draws.length = 0;
  await compileWithSceneRig(null, renderer, scene, camera);
  assert.deepEqual(draws, [{ compiled: scene, target: null }]);
});
