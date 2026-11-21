import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { buildFieldScene, FIELD_CLIP_PLANES, fieldClipUniforms, writeFieldClip } from "./fieldScene.js";

// A field as the engine answers one, with nothing to march: enough to build its scene.
const payload = (extra = {}) => ({
  schema: 1, target: "glsl-es300", code: "", entry: { march: "gsl_march", field: "gsl_field" }, region: [-10, -10, -10, 10, 10, 10],
  uniformBlock: "Field", uniforms: [{ name: "time", type: "f32", offset: 0, value: [0] }],
  sliders: [{ name: "r", uniform: "u_r", type: "f32", offset: 4, value: 4, min: 2, max: 8 }], bodies: [], ...extra
});
const drawn = scene => scene.object3D.children[0];

test("a field's clock is its block's time, set in seconds, and played only where the model reads it", () => {
  const still = buildFieldScene(THREE, payload());
  assert.equal(still.timed, false);
  const timed = buildFieldScene(THREE, payload({ timed: true }));
  assert.equal(timed.timed, true);
  const clock = drawn(timed).material.uniformsGroups[0].uniforms[0];
  assert.equal(timed.setTime(1.5), true);
  assert.equal(clock.value, 1.5);
  assert.equal(timed.setTime(1.5), false, "the same second moves nothing");
  assert.equal(timed.setTime(Number.NaN), false);
  // A block with no time has no clock, whatever the engine said of the source.
  const none = buildFieldScene(THREE, payload({ timed: true, uniforms: [], sliders: [{ name: "r", uniform: "u_r", type: "f32", offset: 0, value: 4, min: 2, max: 8 }] }));
  assert.deepEqual([none.timed, none.setTime(2)], [false, false]);
});

test("a section's planes are written in the field's own frame", () => {
  const uniforms = fieldClipUniforms(THREE);
  assert.deepEqual([uniforms.uClip.value.length, uniforms.uClipCount.value], [FIELD_CLIP_PLANES, 0]);
  // The scene keeps x >= 5; the field stands 3 along x, so in its own frame that is x >= 2.
  const toLocal = new THREE.Matrix4().makeTranslation(-3, 0, 0);
  writeFieldClip(THREE, uniforms, [new THREE.Plane(new THREE.Vector3(1, 0, 0), -5)], toLocal);
  assert.equal(uniforms.uClipCount.value, 1);
  assert.deepEqual(uniforms.uClip.value[0].toArray().map(value => Math.round(value * 1e6) / 1e6), [1, 0, 0, -2]);
  writeFieldClip(THREE, uniforms, [], toLocal);
  assert.equal(uniforms.uClipCount.value, 0);
  // More planes than the shader holds: the first of them.
  writeFieldClip(THREE, uniforms, Array.from({ length: 6 }, () => new THREE.Plane(new THREE.Vector3(0, 0, 1), 0)), toLocal);
  assert.equal(uniforms.uClipCount.value, FIELD_CLIP_PLANES);
});

test("a field takes a section and is capped only where its library can say what is solid", () => {
  const scene = buildFieldScene(THREE, payload());
  assert.match(drawn(scene).material.fragmentShader, /^precision highp sampler3D;\n#define FIELD_CAPS\n/);
  assert.match(drawn(scene).material.fragmentShader, /fieldClipped\(origin, direction, tEntry, tExit, cap\)/);
  scene.setClipPlanes([new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)]);
  drawn(scene).onBeforeRender({ getCurrentViewport: target => target.set(0, 0, 10, 10) }, null, new THREE.PerspectiveCamera());
  assert.equal(drawn(scene).material.uniforms.uClipCount.value, 1);
  scene.setClipPlanes(null);
  drawn(scene).onBeforeRender({ getCurrentViewport: target => target.set(0, 0, 10, 10) }, null, new THREE.PerspectiveCamera());
  assert.equal(drawn(scene).material.uniforms.uClipCount.value, 0);
  const older = buildFieldScene(THREE, payload({ entry: { march: "gsl_march" } }));
  assert.doesNotMatch(drawn(older).material.fragmentShader, /#define FIELD_CAPS/);
});

// --- a field lit by the stage ---------------------------------------------------------------

const litPayload = () => ({
  schema: 1, target: "glsl-es300", code: "// the library", entry: { march: "gsl_march", field: "gsl_field" },
  region: [-1, -1, -1, 1, 1, 1], uniformBlock: "Field", uniforms: [{ name: "time", type: "f32", offset: 0, value: [0] }], sliders: []
});

test("a lit field is three's physical material over the marched surface, and one shown alone shades itself", async () => {
  const { buildFieldScene: build } = await import("./fieldScene.js");
  const alone = build(THREE, litPayload());
  assert.equal(alone.lit, false);
  assert.equal(alone.object3D.children[0].material.isShaderMaterial, true);
  const scene = build(THREE, litPayload(), {}, { lit: true });
  const material = scene.object3D.children[0].material;
  assert.equal(scene.lit, true);
  assert.equal(material.isMeshPhysicalMaterial, true);
  assert.equal(material.uniformsGroups.length, 1);
  // Three's own program, as it compiles it, with the triangle's surface replaced by the field's.
  const shader = { uniforms: {}, vertexShader: THREE.ShaderLib.physical.vertexShader, fragmentShader: THREE.ShaderLib.physical.fragmentShader };
  material.onBeforeCompile(shader, null);
  assert.ok(shader.fragmentShader.startsWith("precision highp sampler3D;\n#define FIELD_CAPS\n// the library"));
  assert.match(shader.fragmentShader, /fieldSurface\(fieldPoint, fieldNormal, fieldDirection, fieldShape\);/);
  assert.match(shader.fragmentShader, /vec3 normal = fieldNormal;/);
  assert.match(shader.fragmentShader, /vec4 diffuseColor = vec4\( uSurface\[fieldShape % 8\], opacity \);/);
  assert.doesNotMatch(shader.fragmentShader, /#include <(clipping_planes_fragment|normal_fragment_begin)>/);
  assert.doesNotMatch(shader.fragmentShader, /varying vec3 vViewPosition;/);
  assert.match(shader.vertexShader, /gl_Position = vec4\( position\.xy, 0\.0, 1\.0 \);/);
  assert.equal(shader.uniforms.uSurface, material.uniforms.uSurface);
  // A three whose program has not the text a replacement names is refused by that text.
  assert.throws(() => material.onBeforeCompile({ uniforms: {}, vertexShader: "void main() {}", fragmentShader: "" }, null),
    /this three's has no `#include <project_vertex>`/);
  scene.dispose();
  alone.dispose();
});

test("a lit field wears a finish, is drawn see-through below full opacity, and takes a surface model", async () => {
  const { buildFieldScene: build } = await import("./fieldScene.js");
  const scene = build(THREE, litPayload(), {}, { lit: true });
  const material = scene.object3D.children[0].material;
  scene.setFinish({ roughness: 0.4, metalness: 0.1, specularIntensity: 0.5, envMapIntensity: 1, lift: 0.05, flat: true, opacity: 0.3 });
  assert.deepEqual([material.roughness, material.metalness, material.specularIntensity, material.opacity, material.transparent, material.depthWrite],
    [0.4, 0.1, 0.5, 0.3, true, false]);
  assert.deepEqual([material.uniforms.uLift.value, material.uniforms.uFlat.value], [0.05, 1]);
  const plain = material.customProgramCacheKey();
  let compiled = 0;
  scene.setFinish({ model: { onBeforeCompile: () => { compiled += 1; }, customProgramCacheKey: () => "model" } });
  assert.deepEqual([material.opacity, material.transparent, material.depthWrite, material.uniforms.uFlat.value], [1, false, true, 0]);
  assert.notEqual(material.customProgramCacheKey(), plain);
  material.onBeforeCompile({ uniforms: {}, vertexShader: THREE.ShaderLib.physical.vertexShader, fragmentShader: THREE.ShaderLib.physical.fragmentShader }, null);
  assert.equal(compiled, 1);
  // A field shown alone has no finish to wear.
  const alone = build(THREE, litPayload());
  alone.setFinish({ opacity: 0.3 });
  assert.equal(alone.object3D.children[0].material.transparent, false);
  scene.dispose();
  alone.dispose();
});

test("a look that dresses every lit material under a root leaves a lit field its own", async () => {
  const { buildFieldScene: build } = await import("./fieldScene.js");
  const { createSurfaceLook } = await import("../viewer/surfaceLook.js");
  const scene = build(THREE, litPayload(), {}, { lit: true });
  const root = new THREE.Group();
  const part = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshPhysicalMaterial());
  root.add(part, scene.object3D);
  const field = scene.object3D.children[0].material;
  const look = createSurfaceLook(THREE, root);
  look.apply({ authored: false, materialSettings: { roughness: 0.2 }, surface: { style: "flat", opacity: 1 } });
  assert.equal(part.material.isMeshBasicMaterial, true);
  assert.equal(scene.object3D.children[0].material, field);
  look.dispose();
  scene.dispose();
});
