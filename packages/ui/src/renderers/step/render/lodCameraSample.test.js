import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";
import { lodSceneMayMove, sampleLodCamera, resampleLodAfterViewportResize } from "./lodCameraSample.js";
import { createLodScheduler } from "./lodScheduler.js";
import { desiredLevel } from "@hardcore/core/lib/surf/lodPolicy.js";

const bounds = (min, max) => ({ min, max });
const cube = (x, y = 0, z = 0) => bounds([x - .5, y - .5, z - .5], [x + .5, y + .5, z + .5]);
function fixture(entries) {
  const camera = new THREE.OrthographicCamera(-5, 5, 5, -5, 1, 20);
  camera.position.set(0, 0, 10); camera.lookAt(0, 0, 0);
  const components = new Map();
  const displayRecords = entries.map(([cid, partBounds], index) => {
    if (!components.has(cid)) components.set(cid, { centers: [], diagonal: 2, level: 0 });
    components.get(cid).centers.push(partBounds.min.map((value, axis) => (value + partBounds.max[axis]) / 2));
    return { partId: `${cid}.${index}`, sourcePart: { componentId: cid }, partBounds,
      mesh: { visible: true }, material: { visible: true } };
  });
  return { runtime: { camera, modelGroup: new THREE.Group(), renderer: { domElement: { clientHeight: 1000 } }, displayRecords }, components };
}
function sample(f, options = {}) { return sampleLodCamera(THREE, f.runtime, { components: f.components, ...options }); }

test("full boxes crossing side/near/far planes remain eligible when their centers are outside", () => {
  const f = fixture([
    ["side", bounds([4.9, -.1, 0], [5.3, .1, 1])],
    ["near", bounds([-.1, -.1, 8.8], [.1, .1, 9.4])],
    ["far", bounds([-.1, -.1, -10.4], [.1, .1, -9.8])],
    ["offside", cube(8)], ["behind", cube(0, 0, 12)], ["beyond", cube(0, 0, -12)],
  ]);
  const s = sample(f);
  for (const cid of ["side", "near", "far"]) assert.ok(Number.isFinite(s.distanceFor(cid)), cid);
  for (const cid of ["offside", "behind", "beyond"]) {
    assert.equal(s.visibleFor(cid), false, cid);
    assert.ok(Number.isFinite(s.distanceFor(cid)), "retained distance supports pressure coarsening");
  }
  assert.equal(s.visibility.visibleComponents, 3); assert.equal(s.visibility.excludedComponents, 3);
});

test("a repeated component uses the nearest visible occurrence, ignoring display/material visibility flags", () => {
  const f = fixture([["same", cube(6, 0, 8)], ["same", cube(0)]]);
  f.runtime.displayRecords[1].mesh.visible = false;
  f.runtime.displayRecords[1].material.visible = false;
  f.runtime.displayRecords[1].effectVisible = false;
  const s = sample(f);
  assert.equal(s.distanceFor("same"), 10);
  assert.equal(s.visibility.visibleOccurrences, 1); assert.equal(s.visibility.excludedOccurrences, 1);
  assert.equal(s.visibility.excludedComponents, 0);
});

test("camera samples map live occurrence selection to component priority", () => {
  const f = fixture([["small", cube(0)], ["large", cube(1)]]);
  const selected = sample(f, { selectedPartIds: ["small"] });
  assert.equal(selected.selectedFor("small"), true);
  assert.equal(selected.selectedFor("large"), false);
  assert.equal(selected.visibility.selectedComponents, 1);
  const wholeModel = sample(f, { selectedPartIds: ["__model__"] });
  assert.equal(wholeModel.selectedFor("small"), true);
  assert.equal(wholeModel.selectedFor("large"), true);
});

test("occurrence bounds include base placement once; rotated mirrored/nonuniform group and parent transforms stay live", () => {
  const f = fixture([["part", cube(7)]]), r = f.runtime.displayRecords[0];
  r.baseTransform = new THREE.Matrix4().makeTranslation(100, 0, 0).toArray();
  const parent = new THREE.Group(); parent.add(f.runtime.modelGroup);
  f.runtime.modelGroup.scale.set(-2, .5, 3);
  f.runtime.modelGroup.rotation.z = Math.PI / 2;
  parent.position.y = 14;
  const s = sample(f);
  assert.ok(Number.isFinite(s.distanceFor("part")), "base placement must not be reapplied");
  assert.ok(Math.abs(s.distanceFor("part") - 10) < 1e-8);
  parent.position.x = 20;
  assert.equal(sample(f).visibleFor("part"), false);
  assert.equal(s.distanceFor("part"), 10, "the prior numeric camera sample is immutable");
});

test("missing, partial or invalid occurrence bounds use conservative summary fallback", () => {
  const f = fixture([["partial", cube(9)], ["partial", cube(0)], ["invalid", cube(0)], ["missing", cube(2)]]);
  f.runtime.displayRecords.splice(3, 1); f.runtime.displayRecords.splice(1, 1);
  f.runtime.displayRecords[1].partBounds = bounds([NaN, 0, 0], [1, 1, 1]);
  const s = sample(f);
  assert.equal(s.distanceFor("partial"), 10);
  for (const cid of f.components.keys()) assert.ok(Number.isFinite(s.distanceFor(cid)));
  assert.equal(s.visibility.fallbackComponents, 3);
  assert.equal(s.visibility.fallbackOccurrences, 1); assert.equal(s.visibility.pendingOccurrences, 2);
});

test("any joint/module capability, including paused or disabled state, fails open", () => {
  assert.equal(lodSceneMayMove(), false);
  for (const capability of [{ kinematics: { parameterValues: {} } },
    { kinematicsLoading: true }, { animation: { language: "javascript" } }, { exploded: true }]) {
    const f = fixture([["offscreen", cube(20)]]);
    const s = sample(f, { dynamicScene: lodSceneMayMove(capability) });
    assert.ok(Number.isFinite(s.distanceFor("offscreen")));
    assert.equal(s.visibility.dynamicFailOpen, 1); assert.equal(s.visibility.excludedComponents, 0);
  }
});

test("animated, collapsing, CPU and GPU deformed records fail open even without capability metadata", () => {
  for (const effect of [{ effectMatrix: new THREE.Matrix4().makeTranslation(30, 0, 0) },
    { explodedViewMatrix: new THREE.Matrix4().makeTranslation(30, 0, 0) },
    { effectDeformation: {} }, { tubeDeformationState: { active: true } }, { tubeGpuState: { active: true } }]) {
    const f = fixture([["posed", cube(20)], ["other", cube(-20)]]);
    Object.assign(f.runtime.displayRecords[0], effect);
    const s = sample(f);
    assert.ok(Number.isFinite(s.distanceFor("posed"))); assert.ok(Number.isFinite(s.distanceFor("other")));
    assert.equal(s.visibility.dynamicFailOpen, 1); assert.equal(s.visibility.excludedComponents, 0);
  }
});

test("perspective cameras also retain intersecting boxes and see camera-parent transforms", () => {
  const f = fixture([["center", cube(0)], ["offscreen", cube(20)]]);
  const camera = new THREE.PerspectiveCamera(45, 1, 1, 20);
  camera.position.set(0, 0, 10); camera.lookAt(0, 0, 0);
  const parent = new THREE.Group(); parent.add(camera); f.runtime.camera = camera;
  assert.equal(sample(f).distanceFor("center"), 10);
  assert.equal(sample(f).visibleFor("offscreen"), false);
  parent.position.x = 20;
  assert.equal(sample(f).distanceFor("offscreen"), 10);
  assert.equal(sample(f).visibleFor("center"), false);
});

test("camera samples preserve optical zoom and vertical view crops in projected LOD error", () => {
  const f = fixture([["part", cube(0)]]);
  const camera = new THREE.PerspectiveCamera(45, 1, 1, 20);
  camera.position.set(0, 0, 10); camera.lookAt(0, 0, 0); f.runtime.camera = camera;
  const levelFor = (result) => desiredLevel({
    diagonal: 2,
    cameraDistance: result.distanceFor("part"),
    camera: result.camera,
    viewportHeightPx: result.viewportHeightPx,
  });
  const base = sample(f);
  assert.equal(levelFor(base), 0);
  camera.zoom = 4; camera.updateProjectionMatrix();
  const zoomed = sample(f);
  assert.ok(Math.abs(zoomed.camera.fovYDeg - camera.getEffectiveFOV()) < 1e-12);
  assert.equal(levelFor(zoomed), 2, "optical zoom must refine like the equivalent narrower FOV");

  camera.zoom = 1;
  camera.setViewOffset(1000, 1000, 0, 0, 1000, 500);
  const cropped = sample(f);
  assert.ok(cropped.camera.fovYDeg < base.camera.fovYDeg);
  assert.equal(levelFor(cropped), 1, "a half-height view doubles vertical pixel density");

  const ortho = new THREE.OrthographicCamera(-5, 5, 5, -5, 1, 20);
  ortho.position.set(0, 0, 10); ortho.lookAt(0, 0, 0);
  ortho.setViewOffset(1000, 1000, 0, 0, 1000, 500); f.runtime.camera = ortho;
  assert.equal(sample(f).camera.visibleWorldHeight, 5);
});

test("visibility exclusion defers the floor until a camera resample reveals the component", async () => {
  const f = fixture([["offscreen", cube(20)], ["also-offscreen", cube(-20)]]);
  let timer; const loads = [];
  const scheduler = createLodScheduler({ minimumLevel: 1,
    setTimeoutFn: fn => { timer = fn; return 1; }, clearTimeoutFn: () => {},
    loadLevel: async (cid, level) => { loads.push([cid, level]); return {}; }, applyLevel: () => {} });
  scheduler.setComponents([...f.components].map(([cid, value]) => ({ cid, ...value })));
  scheduler.onCameraSample(sample(f)); timer();
  for (let i = 0; i < 20; i++) await Promise.resolve();
  assert.deepEqual(loads, []);
  assert.equal(scheduler.snapshot().belowMinimum, 0);
  assert.equal(scheduler.snapshot().scope, "visible-components");
  for (const cid of f.components.keys()) assert.equal(scheduler.levelOf(cid), 0);
  f.runtime.camera.left = -30; f.runtime.camera.right = 30; f.runtime.camera.updateProjectionMatrix();
  scheduler.onCameraSample(sample(f)); timer();
  for (let i = 0; i < 40; i++) await Promise.resolve();
  assert.deepEqual(loads, [["offscreen", 1], ["also-offscreen", 1]]);
  for (const cid of f.components.keys()) assert.equal(scheduler.levelOf(cid), 1);
  assert.equal(scheduler.busy(), false); scheduler.dispose();
});

test("pressure releases offscreen L3 first, while normal exclusion retains existing detail and pressure honors the floor", async () => {
  const f = fixture([["visible", cube(0)], ["offscreen", cube(20)]]);
  for (const pressure of [false, true]) {
    let timer; const loads = [];
    const scheduler = createLodScheduler({ minimumLevel: 1, memoryPressure: () => pressure,
      setTimeoutFn: fn => { timer = fn; return 1; }, clearTimeoutFn: () => {},
      loadLevel: async (cid, level) => { loads.push([cid, level]); return {}; }, applyLevel: () => {} });
    scheduler.setComponents([...f.components].map(([cid, value]) => ({ cid, ...value, level: 3 })));
    scheduler.onCameraSample(sample(f)); timer();
    for (let i = 0; i < 60; i++) await Promise.resolve();
    if (pressure) {
      assert.deepEqual(loads.slice(0, 2), [["offscreen", 2], ["offscreen", 1]]);
      assert.equal(scheduler.levelOf("offscreen"), 1);
      assert.equal(scheduler.levelOf("visible"), 1);
      assert.ok(loads.every(([, level]) => level >= 1));
    } else {
      assert.equal(scheduler.levelOf("offscreen"), 3);
      assert.ok(loads.every(([cid]) => cid !== "offscreen"));
    }
    scheduler.dispose();
  }
});

test("resize resamples newly visible parts even with unchanged framing/persisted perspective", () => {
  const f = fixture([["side", cube(7)]]);
  assert.equal(sample(f).visibleFor("side"), false);
  const events = [];
  f.runtime.camera.left = -10; f.runtime.camera.right = 10;
  f.runtime.camera.updateProjectionMatrix();
  let next;
  const callbacks = { syncFraming: () => false, syncZoom: () => events.push("zoom"),
    emitPerspective: () => events.push("perspective"), resample: () => { events.push("lod"); next = sample(f); } };
  resampleLodAfterViewportResize(f.runtime, callbacks);
  assert.equal(next.visibleFor("side"), true);
  assert.deepEqual(events, ["lod"]);
  events.length = 0;
  resampleLodAfterViewportResize(f.runtime, { ...callbacks, syncFraming: () => true });
  assert.deepEqual(events, ["zoom", "perspective", "lod"]);
});

test("live pose/post-transform order matches the displayed center without mutating bounds or transforms", () => {
  const f = fixture([["posed", cube(1)]]), r = f.runtime.displayRecords[0];
  r.baseTransform = new THREE.Matrix4().makeTranslation(100, 0, 0).toArray();
  r.effectMatrix = new THREE.Matrix4().makeRotationZ(Math.PI / 2);
  r.explodedViewMatrix = new THREE.Matrix4().makeTranslation(0, 3, 0);
  f.runtime.modelGroup.rotation.z = Math.PI / 2; f.runtime.modelGroup.position.x = 10;
  const before = JSON.stringify([r.partBounds, r.baseTransform, r.effectMatrix.elements, r.explodedViewMatrix.elements]);
  const s = sample(f);
  assert.ok(Math.abs(s.distanceFor("posed") - Math.sqrt(136)) < 1e-8);
  assert.equal(JSON.stringify([r.partBounds, r.baseTransform, r.effectMatrix.elements, r.explodedViewMatrix.elements]), before);
  assert.ok(Object.values(s.visibility).every(Number.isFinite), "diagnostics contain only numeric counts");
});

test("LOD retry key ignores component/group bounds but changes for actual camera pose, projection and viewport", () => {
  const f = fixture([["part", cube(0)]]);
  f.runtime.renderer.domElement.clientWidth = 1200;
  const initial = sample(f);
  assert.equal(typeof initial.cameraKey, "string");
  assert.equal(initial.viewportWidthPx, 1200);
  assert.ok(JSON.parse(initial.cameraKey).every(Number.isFinite), "captured retry identity retains only numeric intent");
  f.runtime.displayRecords[0].partBounds = cube(2);
  f.runtime.modelGroup.position.y = 3;
  const movedBounds = sample(f);
  assert.notEqual(movedBounds.distanceFor("part"), initial.distanceFor("part"));
  assert.equal(movedBounds.cameraKey, initial.cameraKey);
  f.runtime.camera.position.x = 1;
  const pan = sample(f);
  assert.notEqual(pan.cameraKey, initial.cameraKey);
  f.runtime.camera.zoom = 2; f.runtime.camera.updateProjectionMatrix();
  const zoom = sample(f);
  assert.notEqual(zoom.cameraKey, pan.cameraKey);
  f.runtime.renderer.domElement.clientWidth = 800;
  const width = sample(f);
  assert.notEqual(width.cameraKey, zoom.cameraKey, "width-only panel resize is meaningful camera intent");
  f.runtime.renderer.domElement.clientHeight = 600;
  assert.notEqual(sample(f).cameraKey, width.cameraKey);
  assert.equal(initial.cameraKey, movedBounds.cameraKey, "later native matrix changes cannot mutate a captured key");
});

test("geometry-derived clip distances preserve retry identity; physical projection intent changes it", () => {
  for (const kind of ["perspective", "orthographic"]) {
    const f = fixture([["part", cube(0)]]);
    if (kind === "perspective") {
      f.runtime.camera = new THREE.PerspectiveCamera(13, 1.333, .1, 2000);
      f.runtime.camera.position.set(0, 0, 10); f.runtime.camera.lookAt(0, 0, 0);
    }
    const camera = f.runtime.camera;
    const before = sample(f).cameraKey;
    const horizontalScales = new Set();
    for (const near of [.001, .003, 1, .0001234567, .0037913, .03123456789, .9173]) {
      camera.near = near; camera.far = 2000; camera.updateProjectionMatrix();
      horizontalScales.add(camera.projectionMatrix.elements[0]);
      assert.equal(sample(f).cameraKey, before, `${kind}: mesh-derived clip distances cannot reopen pressure ceiling`);
    }
    if (kind === "perspective") assert.ok(horizontalScales.size > 1, "actual Three x/y projection rounding changes with near");
    camera.far = 14500; camera.updateProjectionMatrix();
    assert.equal(sample(f).cameraKey, before);
    camera.zoom = 1.2; camera.updateProjectionMatrix();
    let previous = sample(f).cameraKey;
    assert.notEqual(previous, before);
    if (kind === "perspective") {
      for (const [field, value] of [["fov", 51], ["aspect", 1.8], ["filmGauge", 30], ["filmOffset", 2]]) {
        camera[field] = value; camera.updateProjectionMatrix();
        const next = sample(f).cameraKey; assert.notEqual(next, previous, field); previous = next;
      }
    } else {
      camera.left = -6; camera.updateProjectionMatrix();
      const next = sample(f).cameraKey; assert.notEqual(next, previous); previous = next;
    }
    camera.setViewOffset(1920, 1080, 100, 20, 960, 540);
    const offset = sample(f).cameraKey; assert.notEqual(offset, previous);
    camera.clearViewOffset();
    assert.notEqual(sample(f).cameraKey, offset);
  }
});

test("idle orbit roundoff keeps camera intent stable without swallowing accumulated movement", () => {
  const f = fixture([["part", cube(0)]]);
  const camera = f.runtime.camera;
  camera.position.set(34.579468148240665, -11.752075831556004, 19.551277953156657);
  const target = new THREE.Vector3(40.581657547652185, 0.3296735730581055, 1.999999999999993);
  camera.up.set(0, 0, 1); camera.lookAt(target);
  const initial = sample(f).cameraKey;
  for (let i = 0; i < 100; i++) {
    camera.position.z -= 1e-14;
    camera.lookAt(target);
    assert.equal(sample(f).cameraKey, initial, "idle camera matrix roundoff is not new retry intent");
  }
  for (let i = 0; i < 100; i++) {
    camera.position.x += 1e-10;
    sample(f);
  }
  assert.notEqual(sample(f).cameraKey, initial, "small movements accumulate against the retained baseline");
  const moved = sample(f).cameraKey;
  camera.zoom += 1e-5; camera.updateProjectionMatrix();
  assert.notEqual(sample(f).cameraKey, moved, "a real lens change remains new intent");
});

test("actual bounds/group publication resampling cannot reopen a pressure-coarsened rung", async () => {
  const f = fixture([["part", cube(0)]]);
  f.runtime.camera.zoom = 100; f.runtime.camera.updateProjectionMatrix();
  let timer, scheduler;
  const loads = [];
  scheduler = createLodScheduler({
    setTimeoutFn: fn => { timer = fn; return 1; }, clearTimeoutFn: () => {},
    memoryPressure: () => scheduler.levelOf("part") === 3,
    loadLevel: async (_cid, level) => { loads.push(level); assert.ok(loads.length < 7); return {}; }, applyLevel: () => true });
  scheduler.setComponents([{ cid: "part", diagonal: 2, level: 0 }]);
  scheduler.onCameraSample(sample(f)); timer();
  for (let i = 0; i < 30; i++) await Promise.resolve();
  assert.deepEqual(loads, [3, 2]);
  f.runtime.displayRecords[0].partBounds = bounds([-.6, -.6, -.6], [.6, .6, .6]);
  f.runtime.modelGroup.position.z = .1;
  f.runtime.camera.near = .0123; f.runtime.camera.far = 40.51; f.runtime.camera.updateProjectionMatrix();
  scheduler.onCameraSample(sample(f)); timer();
  for (let i = 0; i < 30; i++) await Promise.resolve();
  assert.deepEqual(loads, [3, 2]);
  f.runtime.camera.position.z = 9;
  scheduler.onCameraSample(sample(f)); timer();
  for (let i = 0; i < 30; i++) await Promise.resolve();
  assert.deepEqual(loads, [3, 2, 3, 2]);
  scheduler.dispose();
});
