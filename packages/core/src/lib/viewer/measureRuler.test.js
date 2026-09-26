import assert from "node:assert/strict";
import test from "node:test";

import {
  OrthographicCamera,
  PerspectiveCamera
} from "three";

import {
  projectWorldPointToClient
} from "./measureRuler.js";

function makePerspectiveCamera() {
  const camera = new PerspectiveCamera(60, 1, 0.1, 100);
  camera.position.set(0, 0, 5);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  camera.updateProjectionMatrix();
  return camera;
}

function makeOrthographicCamera() {
  const camera = new OrthographicCamera(-1, 1, 1, -1, 0.1, 100);
  camera.position.set(0, 0, 5);
  camera.lookAt(0, 0, 0);
  camera.updateMatrixWorld(true);
  camera.updateProjectionMatrix();
  return camera;
}

test("projects a world point at the camera target to the rect center", () => {
  const client = projectWorldPointToClient([0, 0, 0], makePerspectiveCamera(), {
    left: 0,
    top: 0,
    width: 800,
    height: 600
  });
  assert.deepEqual(client, { x: 400, y: 300 });
});

test("projects world offsets along the camera axes into client space", () => {
  const client = projectWorldPointToClient([1, 0, 0], makePerspectiveCamera(), {
    left: 0,
    top: 0,
    width: 800,
    height: 600
  });
  assert.ok(client.x > 400);
  assert.equal(client.y, 300);
});

test("returns null for points behind the camera", () => {
  assert.equal(
    projectWorldPointToClient([0, 0, 10], makePerspectiveCamera(), {
      left: 0,
      top: 0,
      width: 800,
      height: 600
    }),
    null
  );
});

test("projects points with an orthographic camera", () => {
  const client = projectWorldPointToClient([0.5, 0, 0], makeOrthographicCamera(), {
    left: 10,
    top: 20,
    width: 400,
    height: 300
  });
  assert.deepEqual(client, { x: 10 + 300, y: 20 + 150 });
});

test("returns null for invalid inputs", () => {
  const camera = makePerspectiveCamera();
  const rect = { left: 0, top: 0, width: 800, height: 600 };
  assert.equal(projectWorldPointToClient(null, camera, rect), null);
  assert.equal(projectWorldPointToClient("point", camera, rect), null);
  assert.equal(projectWorldPointToClient([NaN, 0, 0], camera, rect), null);
  assert.equal(projectWorldPointToClient([1, 2], camera, rect), null);
  assert.equal(projectWorldPointToClient([0, 0, 0], null, rect), null);
  assert.equal(projectWorldPointToClient([0, 0, 0], { matrixWorldInverse: null }, rect), null);
});

test("projection falls back to a normalized rect when no rect is provided", () => {
  assert.ok(projectWorldPointToClient([0, 0, 0], makePerspectiveCamera(), null) instanceof Object);
});

test("projection maps into a zero-origin device-pixel rect for local canvas drawing (DPR regression)", () => {
  const local = projectWorldPointToClient([0, 0, 0], makePerspectiveCamera(), {
    left: 0,
    top: 0,
    width: 1600,
    height: 1200
  });
  assert.deepEqual(local, { x: 800, y: 600 });
});

test("projection adds client offsets, which must not reach a local canvas rect (DPR regression)", () => {
  const client = projectWorldPointToClient([0, 0, 0], makePerspectiveCamera(), {
    left: 200,
    top: 100,
    width: 800,
    height: 600
  });
  assert.deepEqual(client, { x: 600, y: 400 });
});

test("projection vector usage stays independent of camera instance reuse", () => {
  const camera = makePerspectiveCamera();
  const first = projectWorldPointToClient([0, 0, 0], camera, {
    left: 0,
    top: 0,
    width: 800,
    height: 600
  });
  const second = projectWorldPointToClient([1, 1, 0], camera, {
    left: 0,
    top: 0,
    width: 800,
    height: 600
  });
  assert.deepEqual(first, { x: 400, y: 300 });
  assert.ok(second.x > 400);
  assert.ok(second.y < 300);
});
