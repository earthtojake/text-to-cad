import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import * as THREE from "three";
import { createRealOrbitRuntime } from "./harness/realOrbit.js";
import { applyPerspectiveSnapshot, stepCameraTransition, transitionCameraToViewPreset } from "./runtimeCamera.js";
import { createZoomPivotGate, createZoomPivotReanchor } from "./zoomPivotReanchor.js";

function fixture() {
  const camera = new THREE.PerspectiveCamera();
  camera.position.set(0, 0, 20);
  camera.lookAt(0, 0, 0);
  const modelGroup = new THREE.Group();
  modelGroup.position.z = 5;
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshBasicMaterial());
  modelGroup.add(mesh);
  modelGroup.updateMatrixWorld(true);
  const calls = { raycasts: 0 };
  mesh.raycast = function (...args) {
    calls.raycasts += 1;
    return THREE.Mesh.prototype.raycast.apply(this, args);
  };
  return {
    runtime: { camera, controls: { target: new THREE.Vector3(), minDistance: 0, maxDistance: Infinity },
      modelBounds: { min: [0, 0, 0], max: [0, 0, 2] }, modelGroup, raycaster: new THREE.Raycaster() },
    calls,
    dispose() { mesh.geometry.dispose(); mesh.material.dispose(); }
  };
}

test("Every display style retains exact surface-hit zoom depth and falls back to model bounds after a miss", () => {
  const f = fixture();
  try {
    const anchor = createZoomPivotReanchor(THREE);
    anchor.apply(f.runtime);
    assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 5.5]);
    assert.equal(f.calls.raycasts, 1);
    anchor.pointer.set(10, 10);
    anchor.apply(f.runtime);
    assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 6]);
  } finally { f.dispose(); }
});

test("Zoom uses the existing target for missing bounds and respects pivot distance limits", () => {
  const f = fixture();
  try {
    const anchor = createZoomPivotReanchor(THREE);
    anchor.pointer.set(10, 10);
    for (const bounds of [null, { min: [NaN, 0, 0], max: [1, 1, 1] }]) {
      f.runtime.modelBounds = bounds;
      f.runtime.controls.target.set(4, 3, 8);
      anchor.apply(f.runtime);
      assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 8]);
    }
    f.runtime.controls.maxDistance = 5;
    anchor.apply(f.runtime);
    assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 15]);
    f.runtime.controls.target.z = 30;
    f.runtime.controls.minDistance = 2;
    anchor.apply(f.runtime);
    assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 18]);
    assert.ok(f.calls.raycasts > 0);
    f.runtime.camera = new THREE.OrthographicCamera();
    anchor.apply(f.runtime);
    assert.deepEqual(f.runtime.controls.target.toArray(), [0, 0, 18]);
  } finally { f.dispose(); }
});

// The gate decides which `change` of a REAL OrbitControls may re-anchor the pivot; the events
// reach it in the order the browser delivers them (our capture listener, three's, ours after).
function gatedControls(options) {
  const runtime = createRealOrbitRuntime(options);
  const gate = createZoomPivotGate();
  let reanchors = 0;
  runtime.controls.addEventListener("change", () => { if (gate.consumeChange()) reanchors += 1; });
  runtime.element.addEventListener("wheel", () => gate.wheelStart(), { capture: true });
  runtime.element.addEventListener("wheel", () => gate.wheelEnd());
  return { runtime, reanchors: () => reanchors };
}

test("a wheel zoom's change re-anchors the pivot once", () => {
  const { runtime, reanchors } = gatedControls({ position: [50, 0, 0], maxDistance: 100 });
  runtime.wheel(-100);
  assert.equal(reanchors(), 1);
  runtime.controls.update();
  assert.equal(reanchors(), 1, "and a later settling update is not another zoom");
});

test("a wheel the controls clamp leaves no pending re-anchor for the next camera change", () => {
  const { runtime, reanchors } = gatedControls({ position: [100, 0, 0], maxDistance: 100 });
  runtime.wheel(100);
  assert.equal(reanchors(), 0, "zooming out past the limit changes nothing");
  assert.equal(applyPerspectiveSnapshot(runtime, { position: [60, 30, 10], target: [0, 0, 0], up: [0, 0, 1] }), true);
  assert.equal(reanchors(), 0, "a setCamera after it is not a zoom along the old pointer ray");
  assert.equal(transitionCameraToViewPreset(runtime, { direction: [1, 0, 0], up: [0, 0, 1] }), true);
  stepCameraTransition(runtime, runtime.cameraTransition.startTime + 10_000);
  runtime.controls.update();
  assert.equal(reanchors(), 0, "nor is the last frame of an eased move");
});

// The wiring itself, as `useViewerRuntime.js` writes it: the source from the gate's creation to the
// last wheel listener (before the context-loss ones) is lifted out of the hook and run against a REAL OrbitControls, with every
// collaborator it does not depend on stubbed. Reverting that wiring (the change handler, the
// capture listener or the bubble-phase `wheelEnd`) fails here.
const runtimeSource = fs.readFileSync(new URL("../viewport/useViewerRuntime.js", import.meta.url), "utf8");
const wiringStart = runtimeSource.indexOf("const zoomReanchor = createZoomPivotReanchor(THREE);");
const wiringEnd = runtimeSource.indexOf('renderer.domElement.addEventListener("webglcontextlost"');
assert.ok(wiringStart > 0 && wiringEnd > wiringStart, "the zoom pivot wiring is in useViewerRuntime.js");
const wire = Function("scope", `with (scope) { ${runtimeSource.slice(wiringStart, wiringEnd)} }`);

function wiredControls(options) {
  const runtime = createRealOrbitRuntime(options);
  let reanchors = 0;
  const real = {
    THREE, controls: runtime.controls, renderer: { domElement: runtime.element },
    createZoomPivotGate,
    createZoomPivotReanchor: () => ({ pointer: { set() {} }, apply() { reanchors += 1; } }),
    runtimeRef: { current: runtime },
    isPinchWheelEvent: () => false, isTrackpadLikeWheelEvent: () => false, getPinchZoomSpeed: () => 1,
    ACCELERATED_WHEEL_ZOOM_SPEED: 1, WHEEL_PINCH_DELTA_BOOST: 10
  };
  // Everything else the hook closes over (render scheduling, events, interaction bookkeeping) is a no-op.
  const scope = new Proxy(real, {
    has: (target, key) => typeof key === "string" && (key in target || !(key in globalThis)) && key !== "scope",
    get: (target, key) => (key in target ? target[key] : () => {})
  });
  wire(scope);
  return { runtime, reanchors: () => reanchors };
}

test("useViewerRuntime's wiring: a wheel the controls clamp, then a setCamera, re-anchors nothing", () => {
  const { runtime, reanchors } = wiredControls({ position: [100, 0, 0], maxDistance: 100 });
  runtime.wheel(100);
  assert.equal(applyPerspectiveSnapshot(runtime, { position: [60, 30, 10], target: [0, 0, 0], up: [0, 0, 1] }), true);
  assert.equal(reanchors(), 0);
});

test("useViewerRuntime's wiring: a wheel the controls act on re-anchors once", () => {
  const { runtime, reanchors } = wiredControls({ position: [50, 0, 0], maxDistance: 100 });
  runtime.wheel(-100);
  assert.equal(reanchors(), 1);
});
