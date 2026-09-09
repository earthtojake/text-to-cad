import assert from "node:assert/strict";
import test from "node:test";

import { THEME_FLOOR_MODES } from "../themeSettings.js";
import { DEFAULT_AUTO_ZOOM_PADDING } from "./autoZoom.js";
import { VIEWER_SCENE_SCALE, getSceneScaleSettings } from "./sceneScale.js";
import {
  buildGridConfig,
  DEFAULT_GRID_DIVISIONS,
  GRID_TARGET_VISIBLE_CELLS,
  niceGridStep,
  updateGridHelper
} from "./stageGrid.js";

class FakeGridHelper {
  constructor(size, divisions, centerColor, cellColor) {
    this.size = size;
    this.divisions = divisions;
    this.centerColor = centerColor;
    this.cellColor = cellColor;
    this.material = {};
    this.rotation = { x: 0 };
    this.position = {
      value: null,
      set: (...value) => {
        this.position.value = value;
      }
    };
  }
}

function createRuntime() {
  return {
    THREE: { GridHelper: FakeGridHelper },
    scene: {
      children: [],
      add(object) {
        this.children.push(object);
        object.parent = this;
      }
    }
  };
}

test("stage grid sizing uses nice CAD-scale steps and even divisions", () => {
  assert.equal(niceGridStep(0), getSceneScaleSettings(VIEWER_SCENE_SCALE.CAD).minGridSize / DEFAULT_GRID_DIVISIONS);
  assert.equal(niceGridStep(0.06), 0.1);
  assert.equal(niceGridStep(6), 10);

  const config = buildGridConfig(12, VIEWER_SCENE_SCALE.CAD);
  assert.ok(config.size > 0);
  assert.equal(config.divisions, DEFAULT_GRID_DIVISIONS);
  assert.equal(config.divisions % 2, 0);
});

test("stage grid cells scale with model radius near default framing", () => {
  const cadConfig = buildGridConfig(12, VIEWER_SCENE_SCALE.CAD);
  assert.equal(cadConfig.cellSize, (24 * DEFAULT_AUTO_ZOOM_PADDING) / GRID_TARGET_VISIBLE_CELLS);
  assert.equal(cadConfig.size, cadConfig.cellSize * cadConfig.divisions);
  const cadDefaultZoomCells = (12 * 2 * DEFAULT_AUTO_ZOOM_PADDING) / cadConfig.cellSize;
  assert.equal(cadDefaultZoomCells, GRID_TARGET_VISIBLE_CELLS);

  const urdfConfig = buildGridConfig(0.12, VIEWER_SCENE_SCALE.URDF);
  assert.equal(urdfConfig.cellSize, (0.24 * DEFAULT_AUTO_ZOOM_PADDING) / GRID_TARGET_VISIBLE_CELLS);
  const urdfDefaultZoomCells = (0.12 * 2 * DEFAULT_AUTO_ZOOM_PADDING) / urdfConfig.cellSize;
  assert.equal(urdfDefaultZoomCells, GRID_TARGET_VISIBLE_CELLS);
});

test("stage grid density changes cell count without changing the base model-relative span", () => {
  const normalConfig = buildGridConfig(12, VIEWER_SCENE_SCALE.CAD);
  const denseConfig = buildGridConfig(12, VIEWER_SCENE_SCALE.CAD, {
    grid: { density: 2 }
  });

  assert.equal(denseConfig.divisions, DEFAULT_GRID_DIVISIONS * 2);
  assert.equal(denseConfig.cellSize, normalConfig.cellSize / 2);
  assert.equal(denseConfig.size, normalConfig.size);
});

test("updateGridHelper creates, reuses, and disposes runtime grid helpers", () => {
  const runtime = createRuntime();
  const disposed = [];
  const disposeSceneObject = (object) => {
    if (object) {
      disposed.push(object);
    }
  };

  updateGridHelper(
    runtime,
    { gridCenter: "#111111", gridCell: "#222222", gridOpacity: 0.42 },
    10,
    -2,
    VIEWER_SCENE_SCALE.CAD,
    THEME_FLOOR_MODES.GRID,
    { disposeSceneObject }
  );

  const firstGrid = runtime.gridHelper;
  assert.ok(firstGrid instanceof FakeGridHelper);
  assert.equal(firstGrid.centerColor, "#111111");
  assert.equal(firstGrid.cellColor, "#222222");
  assert.equal(firstGrid.material.opacity, 0.42);
  assert.deepEqual(firstGrid.position.value, [0, 0, -2]);
  assert.equal(runtime.scene.children[0], firstGrid);

  updateGridHelper(
    runtime,
    { gridCenter: "#111111", gridCell: "#222222", gridOpacity: 0.42 },
    10,
    3,
    VIEWER_SCENE_SCALE.CAD,
    THEME_FLOOR_MODES.GRID,
    { disposeSceneObject }
  );

  assert.equal(runtime.gridHelper, firstGrid);
  assert.deepEqual(firstGrid.position.value, [0, 0, 3]);
  assert.deepEqual(disposed, []);

  updateGridHelper(
    runtime,
    { gridCenter: "#111111", gridCell: "#222222", gridOpacity: 0.42 },
    10,
    4,
    VIEWER_SCENE_SCALE.CAD,
    THEME_FLOOR_MODES.GRID,
    {
      disposeSceneObject,
      floorSettings: {
        grid: {
          centerColor: "#333333",
          cellColor: "#444444",
          opacity: 0.5,
          density: 1.5
        }
      }
    }
  );

  const themedGrid = runtime.gridHelper;
  assert.ok(themedGrid instanceof FakeGridHelper);
  assert.notEqual(themedGrid, firstGrid);
  assert.equal(themedGrid.centerColor, "#333333");
  assert.equal(themedGrid.cellColor, "#444444");
  assert.equal(themedGrid.material.opacity, 0.5);
  assert.ok(themedGrid.divisions > firstGrid.divisions);
  assert.deepEqual(disposed, [firstGrid]);

  updateGridHelper(
    runtime,
    {},
    10,
    0,
    VIEWER_SCENE_SCALE.CAD,
    THEME_FLOOR_MODES.STAGE,
    { disposeSceneObject }
  );

  assert.equal(runtime.gridHelper, null);
  assert.equal(runtime.gridConfig, null);
  assert.deepEqual(disposed, [firstGrid, themedGrid]);
});

test("updateGridHelper renders grid independently from stage floor mode", () => {
  const runtime = createRuntime();

  updateGridHelper(
    runtime,
    { gridCenter: "#111111", gridCell: "#222222", gridOpacity: 0.42 },
    10,
    -2,
    VIEWER_SCENE_SCALE.CAD,
    THEME_FLOOR_MODES.STAGE,
    {
      floorSettings: {
        enabled: true,
        grid: {
          enabled: true,
          centerColor: "#333333",
          cellColor: "#444444",
          opacity: 0.5
        }
      }
    }
  );

  assert.ok(runtime.gridHelper instanceof FakeGridHelper);
  assert.equal(runtime.gridHelper.centerColor, "#333333");
  assert.equal(runtime.gridHelper.cellColor, "#444444");
  assert.equal(runtime.gridHelper.material.opacity, 0.5);
  assert.deepEqual(runtime.gridHelper.position.value, [0, 0, -2]);
  assert.equal(runtime.floorMode, THEME_FLOOR_MODES.GRID);
});
