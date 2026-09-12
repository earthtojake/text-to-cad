import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildSurfaceLinePositions,
  pointOnSurfaceFromUv,
  projectPointToCylinder,
  projectPointToPlane,
  projectPointToSurfaceUv,
  surfaceNormalAtUv,
  SURFACE_LINE_UNSUPPORTED_TYPES
} from "./surfaceLineGeometry.js";

const EPSILON = 1e-6;

function assertNear(actual, expected, message = "") {
  assert.ok(Math.abs(actual - expected) < EPSILON, `${message} expected ${expected}, received ${actual}`);
}

function assertArrayNear(actual, expected, message = "") {
  assert.equal(actual.length, expected.length, `${message} length`);
  for (let index = 0; index < expected.length; index += 1) {
    assertNear(actual[index], expected[index], `${message}[${index}]`);
  }
}

const planeSurface = {
  type: "PLANE",
  origin: [10, 20, 30],
  xDir: [1, 0, 0],
  yDir: [0, 1, 0],
  normal: [0, 0, 2]
};

const cylinderSurface = {
  type: "CYLINDRICAL_SURFACE",
  origin: [0, 0, 0],
  axis: [0, 0, 1],
  xDir: [1, 0, 0],
  yDir: [0, 1, 0],
  radius: 2
};

test("surface line projection maps plane points to and from UV coordinates", () => {
  assertArrayNear(projectPointToPlane([13, 24, 30], planeSurface), [3, 4], "plane projection");
  assertArrayNear(projectPointToSurfaceUv(planeSurface, [13, 24, 30]), [3, 4], "surface plane projection");
  assertArrayNear(pointOnSurfaceFromUv(planeSurface, [3, 4]), [13, 24, 30], "plane point");
  assertArrayNear(surfaceNormalAtUv(planeSurface, [3, 4]), [0, 0, 1], "plane normal");
  assert.equal(projectPointToSurfaceUv({ type: "PLANE" }, [0, 0, 0]), null);
});

test("surface line projection maps cylindrical points to and from arc-length UV coordinates", () => {
  const point = [0, 2, 5];
  assertArrayNear(projectPointToCylinder(point, cylinderSurface), [Math.PI, 5], "cylinder projection");
  assertArrayNear(projectPointToSurfaceUv(cylinderSurface, point), [Math.PI, 5], "surface cylinder projection");
  assertArrayNear(pointOnSurfaceFromUv(cylinderSurface, [Math.PI, 5]), point, "cylinder point");
  assertArrayNear(surfaceNormalAtUv(cylinderSurface, [Math.PI, 5]), [0, 1, 0], "cylinder normal");
});

test("surface line cylindrical projection unwraps angles around the start angle", () => {
  const nearNegativePi = [2 * Math.cos(-Math.PI + 0.1), 2 * Math.sin(-Math.PI + 0.1), 0];
  const projected = projectPointToCylinder(nearNegativePi, cylinderSurface, Math.PI - 0.1);
  assertNear(projected[0] / 2, Math.PI + 0.1, "unwrapped angle");
});

test("surface line position builder offsets planar lines by their face normal", () => {
  assertArrayNear(buildSurfaceLinePositions({
    pickData: {
      surface: planeSurface,
      normal: [0, 0, 2]
    }
  }, {
    startPoint: [10, 20, 30],
    endPoint: [11, 20, 30]
  }, { offset: 0.25 }), [
    10, 20, 30.25,
    11, 20, 30.25
  ], "plane line positions");
});

test("surface line position builder tessellates cylindrical surface lines", () => {
  const positions = buildSurfaceLinePositions({
    pickData: {
      surface: cylinderSurface
    }
  }, {
    startUv: [0, 1],
    endUv: [Math.PI, 1]
  }, { segments: 4, offset: 0.5 });

  assert.equal(positions.length, 24);
  assertArrayNear(positions.slice(0, 6), [
    2.5, 0, 1,
    2.5 * Math.cos(Math.PI / 8), 2.5 * Math.sin(Math.PI / 8), 1
  ], "first cylinder segment");
});

test("surface line position builder falls back to saved endpoints and declares unsupported types", () => {
  assertArrayNear(buildSurfaceLinePositions({
    pickData: {
      surface: { type: "UNKNOWN" }
    }
  }, {
    startPoint: [1, 2, 3],
    endPoint: [4, 5, 6]
  }), [
    1, 2, 3,
    4, 5, 6
  ], "fallback line");
  assert.deepEqual([...SURFACE_LINE_UNSUPPORTED_TYPES], ["", "SPHERICAL_SURFACE", "TOROIDAL_SURFACE", "BSPLINE_SURFACE"]);
});
