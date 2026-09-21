import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { isKitScene, sceneFramingBounds } from "../../kit/scene.js";
import { createStepScene, stepSceneView } from "./stepScene.js";

const bounds = { min: [0, 0, 0], max: [4, 1, 1] };
function mesh(n) {
  return { vertices: new Float32Array([0, 0, 0, n, 0, 0, 0, 1, 0]),
    normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]), indices: new Uint32Array([0, 1, 2]), bounds,
    parts: [{ id: "surface", vertexCount: 3, triangleCount: 1 }] };
}
function source(values, extra = {}) {
  return { bounds, partTransformsBaked: false, ...extra, parts: values.map((value, i) => ({ id: `part${i}`, occurrenceId: `part${i}`,
    componentId: `cid${i}`, sourceMesh: value, sourceMeshKey: `${i}:${value.vertices[3]}`,
    bounds, vertexCount: 3, triangleCount: 1, transform: [1, 0, 0, i * 2, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1] })) };
}
const settings = { renderPartsIndividually: true, callbacks: { faceIdsForPart: () => ["face"] } };
const identity = { modelKey: "model", buildKey: '{"displayMode":"solid"}', viewerTheme: null };

test("an empty STEP scene already satisfies the kit contract, so the viewport can hold it before the first build", () => {
  const scene = createStepScene(THREE);
  assert.equal(isKitScene(scene), true);
  assert.deepEqual(scene.placedObjects(), []);
  assert.equal(scene.complete, true);
  assert.equal(scene.plan(identity).reuse, false);
});

test("progressive publishes and detail swaps land in ONE scene identity: the roots and the records' owner never change", () => {
  const scene = createStepScene(THREE);
  const roots = [scene.object3D, scene.edgesObject3D];
  const first = source([mesh(1)], { missingComponentIds: ["cid1"] });
  assert.equal(scene.plan(identity).reuse, false);
  const build = scene.build(first, identity, settings);
  assert.equal(scene.complete, false, "components are still to come");
  assert.equal(build.modelGroup.parent, scene.object3D);
  assert.equal(build.edgesGroup.parent, scene.edgesObject3D);
  const firstRecord = scene.displayRecords[0];

  // The next publish is handed to the live build: the record on screen is the same object.
  const whole = source([first.parts[0].sourceMesh, mesh(1.5)]);
  assert.deepEqual(scene.plan(identity), { reuse: true, sameModel: true, reason: "" });
  assert.equal(scene.update(whole, settings), build);
  assert.equal(scene.complete, true);
  assert.equal(scene.displayRecords.length, 2);
  assert.equal(scene.displayRecords[0], firstRecord, "an occurrence on screen keeps its record");
  assert.deepEqual([scene.object3D, scene.edgesObject3D], roots);
  assert.equal(scene.placedObjects(), scene.displayRecords, "the depth fit is told about the records themselves");
  assert.equal(scene.source, whole);
  assert.deepEqual(sceneFramingBounds(scene), bounds);
  scene.dispose();
});

test("a build setting that changes how records are made rebuilds under the same identity and says why; another model says so too", () => {
  const scene = createStepScene(THREE);
  scene.build(source([mesh(1)]), identity, settings);
  const wireframe = { ...identity, buildKey: '{"displayMode":"wireframe"}' };
  assert.deepEqual(scene.plan(wireframe), { reuse: false, sameModel: true, reason: "displayMode" });
  assert.deepEqual(scene.plan({ ...identity, modelKey: "other" }), { reuse: false, sameModel: false, reason: "model key" });
  assert.throws(() => scene.build(source([mesh(1)]), wireframe, settings), /release it first/);
  const root = scene.object3D;
  const released = scene.release({ releaseGpu: false, preserveModelIdentity: true });
  assert.ok(released, "the released source is named");
  assert.equal(scene.object3D.children.length, 0);
  const rebuilt = scene.build(source([mesh(1)]), wireframe, settings);
  assert.equal(scene.object3D, root);
  assert.equal(rebuilt.modelGroup.parent, root);
  scene.dispose();
});

test("shared component geometry is not the scene's to dispose: releasing one scene leaves another's buffers alone", () => {
  const shared = source([mesh(1), mesh(1.2)]);
  const one = createStepScene(THREE), two = createStepScene(THREE);
  one.build(shared, identity, settings);
  two.build(shared, identity, settings);
  const geometries = one.displayRecords.map(record => record.geometry);
  assert.deepEqual(two.displayRecords.map(record => record.geometry), geometries, "both scenes draw the same component geometry");
  const disposals = geometries.map(() => 0);
  geometries.forEach((geometry, index) => geometry.addEventListener("dispose", () => { disposals[index] += 1; }));
  one.dispose();
  assert.deepEqual(disposals, [0, 0], "the other scene still owns every buffer");
  two.dispose();
  assert.deepEqual(disposals, [1, 1], "the last owner frees them, once");
});

test("the look is worn once: the viewport's resolved look and STEP's own are the same settings", () => {
  const scene = createStepScene(THREE);
  const materialSettings = { defaultColor: "#8899aa" };
  const build = scene.build(source([mesh(1)]), identity, { ...settings, materialSettings, surfaceSettings: null });
  let updates = 0;
  const update = build.update.bind(build);
  build.update = (next) => { updates += 1; return update(next); };
  scene.setSurfaceLook({ materialSettings, authored: false, surface: null });
  assert.equal(updates, 0, "no context yet: nothing to dress with");
  const context = { theme: null, appearance: "light", materialSettings, materialOverrides: null, receiveShadows: false, surfaceSettings: null };
  assert.equal(scene.setLookContext(context), true);
  assert.equal(updates, 1);
  assert.equal(scene.setLookContext({ ...context }), false, "the same context again dresses nothing");
  scene.setSurfaceLook({ materialSettings: { defaultColor: "#8899aa" }, authored: false, surface: null });
  assert.equal(updates, 1, "the kit's look with the same content is already on");
  scene.setSurfaceLook({ materialSettings: { defaultColor: "#ff0000" }, authored: false, surface: null });
  assert.equal(updates, 2, "a look that differs is put on");
  assert.equal(scene.setLookContext({ ...context, appearance: "dark" }), true, "the edge ink follows the app appearance");
  assert.equal(updates, 3);
  scene.dispose();
});

test("dispose is not terminal: a development remount builds again in the same scene, and the view carries the authored-finish flag", () => {
  const scene = createStepScene(THREE);
  scene.build(source([mesh(1)]), identity, settings);
  scene.dispose();
  assert.equal(scene.cadScene, null);
  assert.equal(scene.plan(identity).reuse, false);
  scene.build(source([mesh(1)]), identity, settings);
  assert.equal(scene.displayRecords.length, 1);
  const view = stepSceneView(scene, true);
  assert.equal(view.keepsAuthoredFinish, true);
  assert.equal(view.object3D, scene.object3D);
  assert.equal(view.displayRecords, scene.displayRecords);
  assert.equal(isKitScene(view), true);
  assert.equal(scene.keepsAuthoredFinish, undefined);
  scene.dispose();
});
