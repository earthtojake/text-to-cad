import assert from "node:assert/strict";
import { test } from "node:test";
import * as THREE from "three";

import { addFloor } from "../../common/renderOptions.js";

// Same shape renderMeshScene passes; only minFloorSize is read here.
const SCALE_SETTINGS = {
  cad: { minBoundsSpan: 1, minModelRadius: 1, minFloorSize: 100, minCameraDistance: 10, minCameraFar: 1000 }
};

function floorZFor(bounds, floor = {}) {
  const scene = new THREE.Scene();
  addFloor(
    scene,
    bounds,
    { floor: { mode: "grid", grid: { enabled: true }, ...floor } },
    "cad",
    SCALE_SETTINGS
  );
  const grid = scene.children.find((child) => child.isGridHelper || child.type === "GridHelper");
  assert.ok(grid, "grid floor should have been added");
  return grid.position.z;
}

const grounded = { min: [-2400, -1000, -0.55], max: [2300, 1000, 1150] };
const liftedOffFloor = { min: [-100, -100, 200], max: [100, 100, 400] };
const belowFloor = { min: [-100, -100, -350], max: [100, 100, 400] };

test("a grounded model rests on the floor", () => {
  // tyres at z ~= 0 -> floor within a hair of 0
  assert.ok(Math.abs(floorZFor(grounded)) < 1.0, "grounded model should sit on z=0");
});

test("a model authored above z=0 genuinely floats", () => {
  // The regression: gluing the floor to bounds.min[2] would put it at 200 and
  // make this look grounded, hiding a real authoring mistake.
  assert.ok(floorZFor(liftedOffFloor) > -1.0, "floor must stay at world z=0, not follow up to 200");
  assert.ok(Math.abs(floorZFor(liftedOffFloor)) < 1.0);
});

test("a grid-only canvas is pinned to world z=0 even for below-zero geometry", () => {
  // followModel is a floor-DEPENDENT trait: with no stage floor plane (grid
  // mode), it is inert, so the reference grid stays the true z=0 plane and
  // geometry authored below z=0 visibly extends below it.
  assert.ok(Math.abs(floorZFor(belowFloor)) < 1.0, "grid canvas must not chase the model down");
  assert.ok(Math.abs(floorZFor(belowFloor, { followModel: true })) < 1.0, "followModel is inert without a floor");
});

test("an enabled stage floor follows below-zero geometry down so nothing clips", () => {
  assert.ok(
    floorZFor(belowFloor, { enabled: true }) <= -350,
    "stage floor should follow the model downward"
  );
});

test("followModel:false pins an enabled floor to world z=0 regardless", () => {
  assert.ok(Math.abs(floorZFor(belowFloor, { enabled: true, followModel: false })) < 1.0);
});
