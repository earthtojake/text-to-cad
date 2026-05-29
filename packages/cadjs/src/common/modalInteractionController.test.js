import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import {
  vertexModeDeltas,
  nearestFaceVertex,
  vertexMobility,
  maxMeshMobility,
  ModalInteractionController,
} from "./modalInteractionController.js";

// A unit quad in the z=0 plane with two morph targets:
//   mode 0: pushes every vertex +z by 0.5
//   mode 1: pushes every vertex +x by 0.5
function buildQuad() {
  const geometry = new THREE.BufferGeometry();
  const base = new Float32Array([
    -1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0,
  ]);
  geometry.setAttribute("position", new THREE.BufferAttribute(base, 3));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  geometry.computeVertexNormals();
  const dz = new Float32Array([0, 0, 0.5, 0, 0, 0.5, 0, 0, 0.5, 0, 0, 0.5]);
  const dx = new Float32Array([0.5, 0, 0, 0.5, 0, 0, 0.5, 0, 0, 0.5, 0, 0]);
  geometry.morphAttributes.position = [
    new THREE.BufferAttribute(dz, 3),
    new THREE.BufferAttribute(dx, 3),
  ];
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  mesh.morphTargetInfluences = [0, 0];
  mesh.updateMatrixWorld(true);
  return mesh;
}

function topDownCamera() {
  // Looking straight down -Z at the quad.
  const cam = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  cam.position.set(0, 0, 5);
  cam.lookAt(0, 0, 0);
  cam.updateMatrixWorld(true);
  return cam;
}

test("vertexModeDeltas reads per-target displacement of a vertex", () => {
  const mesh = buildQuad();
  assert.deepEqual(vertexModeDeltas(mesh, 0), [[0, 0, 0.5], [0.5, 0, 0]]);
});

test("nearestFaceVertex picks the closest face corner", () => {
  const mesh = buildQuad();
  const face = { a: 0, b: 1, c: 2 };
  const near = nearestFaceVertex(THREE, mesh, face, new THREE.Vector3(0.95, 0.95, 0));
  assert.equal(near, 2); // (1,1,0)
});

test("pick + drag deforms toward the cursor; release rings and decays", () => {
  const mesh = buildQuad();
  const camera = topDownCamera();
  const controller = new ModalInteractionController({
    THREE, camera, mesh, frequencies: [10, 40], damping: 0.05, slowdown: 50,
  });

  // Pick near the center of the quad (NDC 0,0 ray hits z=0 plane at origin).
  assert.equal(controller.pickAtNDC(0, 0), true);
  assert.equal(controller.state, "dragging");

  // Drag: with a top-down camera the drag plane is z=0, so moving the cursor
  // can only command in-plane (x/y) motion -> mode 1 (x) should activate.
  const q = controller.dragToNDC(0.2, 0);
  assert.equal(q.length, 2);
  assert.ok(Math.abs(mesh.morphTargetInfluences[1]) > 1e-3, "x-mode should engage");

  // Release -> ringing; influences should be nonzero then decay over time.
  controller.release();
  assert.equal(controller.state, "ringing");
  const before = Math.abs(mesh.morphTargetInfluences[1]);
  let ringing = true;
  for (let i = 0; i < 5; i += 1) ringing = controller.update(0.05);
  // Energy must have dropped from the initial pluck.
  assert.ok(controller.superposition === null || controller.superposition.energyFraction() < 1,
    "vibration should decay");
  assert.ok(before > 0);
});

test("stationary (clamped) vertices are not grabbable", () => {
  // Quad where vertex 0 is fixed (zero modal motion) and the rest move.
  const geometry = new THREE.BufferGeometry();
  const base = new Float32Array([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0]);
  geometry.setAttribute("position", new THREE.BufferAttribute(base, 3));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  geometry.computeVertexNormals();
  // Mode pushes +z everywhere EXCEPT the clamped vertex 0.
  const dz = new Float32Array([0, 0, 0, 0, 0, 0.5, 0, 0, 0.5, 0, 0, 0.5]);
  geometry.morphAttributes.position = [new THREE.BufferAttribute(dz, 3)];
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial());
  mesh.morphTargetInfluences = [0];
  mesh.updateMatrixWorld(true);

  assert.equal(vertexMobility(vertexModeDeltas(mesh, 0)), 0);   // clamped
  assert.ok(maxMeshMobility(mesh) > 0);

  const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 100);
  camera.position.set(0, 0, 5); camera.lookAt(0, 0, 0); camera.updateMatrixWorld(true);
  const controller = new ModalInteractionController({ THREE, camera, mesh, frequencies: [10] });

  // Aim just inside the clamped corner (nearest face vertex = clamped #0).
  const corner = new THREE.Vector3(-0.8, -0.8, 0).project(camera);
  assert.equal(controller.pickAtNDC(corner.x, corner.y), false); // refused
  assert.equal(controller.state, "idle");

  // Just inside a mobile corner (nearest face vertex = #2) is grabbable.
  const mobile = new THREE.Vector3(0.8, 0.8, 0).project(camera);
  assert.equal(controller.pickAtNDC(mobile.x, mobile.y), true);
});

test("reset clears influences and state", () => {
  const mesh = buildQuad();
  const controller = new ModalInteractionController({
    THREE, camera: topDownCamera(), mesh, frequencies: [10, 40],
  });
  controller.pickAtNDC(0, 0);
  controller.dragToNDC(0.3, 0);
  controller.reset();
  assert.equal(controller.state, "idle");
  assert.deepEqual(Array.from(mesh.morphTargetInfluences), [0, 0]);
});
