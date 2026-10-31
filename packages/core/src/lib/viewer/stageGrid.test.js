import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { THEME_FLOOR_MODES } from "../themeSettings.js";
import { DEFAULT_AUTO_ZOOM_PADDING } from "./autoZoom.js";
import { VIEWER_SCENE_SCALE } from "./sceneScale.js";
import { viewGridDefaults } from "../../common/viewSettings.js";
import { resolveCadGridSettings } from "../../common/cadInk.js";
import {
  buildGridConfig,
  createGridMesh,
  GRID_FADE_END_FRAMINGS,
  GRID_FADE_START_FRAMINGS,
  GRID_LINE_DEFAULTS,
  GRID_TARGET_VISIBLE_CELLS,
  niceGridStep,
  updateGridHelper
} from "./stageGrid.js";

function createRuntime() {
  return { THREE, scene: new THREE.Scene() };
}

const style = { color: "#123456", xAxisColor: "#ff0000", yAxisColor: "#00ff00", opacity: 0.5 };
const hex = color => `#${color.getHexString()}`;

test("grid steps are round: 1, 2 or 5 x 10^n, a major every 10 minors (5 after a 2)", () => {
  assert.equal(niceGridStep(0.06), 0.1);
  assert.equal(niceGridStep(6), 10);
  assert.equal(niceGridStep(1.5), 2);
  for (const radius of [0.3, 4, 12, 75, 260, 3000]) {
    const { cellSize, majorEvery } = buildGridConfig(radius, VIEWER_SCENE_SCALE.CAD);
    const digit = Math.round(cellSize / 10 ** Math.floor(Math.log10(cellSize) + 1e-9));
    assert.ok([1, 2, 5].includes(digit), `${cellSize} is a round step`);
    assert.equal(majorEvery, digit === 2 ? 5 : 10);
  }
});

test("about twenty minor cells cross the default framing, at any scale; density scales the count", () => {
  for (const [radius, scale] of [[12, VIEWER_SCENE_SCALE.CAD], [480, VIEWER_SCENE_SCALE.CAD], [0.12, VIEWER_SCENE_SCALE.URDF]]) {
    const framing = radius * 2 * DEFAULT_AUTO_ZOOM_PADDING;
    const cells = framing / buildGridConfig(radius, scale).cellSize;
    // The nearest round step is within a factor of ~1.6 of the target.
    assert.ok(cells > GRID_TARGET_VISIBLE_CELLS / 1.6 && cells < GRID_TARGET_VISIBLE_CELLS * 1.6, `${cells} cells at radius ${radius}`);
  }
  const normal = buildGridConfig(12, VIEWER_SCENE_SCALE.CAD);
  const dense = buildGridConfig(12, VIEWER_SCENE_SCALE.CAD, { grid: { density: 4 } });
  assert.ok(dense.cellSize < normal.cellSize / 2);
  // Density changes the step, never the grid's reach.
  assert.equal(dense.size, normal.size);
});

test("the grid fills the default view and only dissolves far out; its square holds the whole fade", () => {
  const config = buildGridConfig(12, VIEWER_SCENE_SCALE.CAD);
  const framing = 24 * DEFAULT_AUTO_ZOOM_PADDING;
  // Full strength past the corners of the default framing, gone only several framings out.
  assert.ok(GRID_FADE_START_FRAMINGS >= 1, "no fade inside the default view");
  assert.ok(GRID_FADE_END_FRAMINGS >= GRID_FADE_START_FRAMINGS * 3, "a long, gentle fade");
  assert.equal(config.fadeStart, framing * GRID_FADE_START_FRAMINGS);
  assert.equal(config.fadeEnd, framing * GRID_FADE_END_FRAMINGS);
  assert.equal(config.size, config.fadeEnd * 2);
});

test("graph paper: a cool blue ink the viewer and the snapshot share, majors heavier than minors", () => {
  for (const appearance of ["light", "dark"]) {
    const { color, opacity } = GRID_LINE_DEFAULTS[appearance];
    const { r, g, b } = new THREE.Color(color);
    assert.ok(b > r && g > r, `${appearance} ${color} is a cyan-blue, not a grey`);
    const viewer = viewGridDefaults(appearance);
    assert.deepEqual([viewer.color, viewer.opacity], [color, opacity], `the viewer's ${appearance} grid`);
    const snapshot = resolveCadGridSettings({ enabled: true }, { colorMode: appearance });
    assert.deepEqual([snapshot.color, snapshot.opacity], [color, opacity], `the snapshot's ${appearance} grid`);
  }
  const { fragmentShader } = createGridMesh(THREE, { ...buildGridConfig(12, VIEWER_SCENE_SCALE.CAD), ...style }).material;
  const [, minorWidth] = fragmentShader.match(/gridLines\(plane \/ minorStep, ([\d.]+)/);
  const [, majorWidth] = fragmentShader.match(/gridLines\(plane \/ majorStep, ([\d.]+)/);
  assert.ok(Number(majorWidth) > Number(minorWidth));
});

test("the grid is one shader quad on the XY plane, drawn behind what is on its plane and never picked", () => {
  const config = { ...buildGridConfig(12, VIEWER_SCENE_SCALE.CAD), ...style };
  const grid = createGridMesh(THREE, config);
  assert.equal(grid.geometry.getAttribute("position").count, 4);
  assert.deepEqual([grid.scale.x, grid.scale.y], [config.size, config.size]);
  const { material } = grid;
  assert.equal(material.isShaderMaterial, true);
  assert.equal(material.transparent, true);
  assert.equal(material.depthWrite, false);
  assert.equal(material.polygonOffset, true);
  assert.ok(material.polygonOffsetFactor > 0);
  assert.equal(hex(material.uniforms.color.value), "#123456");
  assert.equal(hex(material.uniforms.xAxisColor.value), "#ff0000");
  assert.equal(hex(material.uniforms.yAxisColor.value), "#00ff00");
  assert.equal(material.uniforms.minorStep.value, config.cellSize);
  assert.equal(material.uniforms.majorStep.value, config.cellSize * config.majorEvery);
  // Anti-aliased with derivatives, faded by distance and by a grazing view.
  assert.match(material.fragmentShader, /fwidth/);
  assert.match(material.fragmentShader, /smoothstep\(fadeStart, fadeEnd/);
  const hits = [];
  grid.raycast(new THREE.Raycaster(), hits);
  assert.deepEqual(hits, []);
});

test("updateGridHelper keeps one grid, restyles it in place, and disposes it when the grid is off", () => {
  const runtime = createRuntime();
  const disposed = [];
  const disposeSceneObject = object => object && disposed.push(object);
  const draw = (floorZ, grid) => updateGridHelper(runtime, {}, 10, floorZ, VIEWER_SCENE_SCALE.CAD, THEME_FLOOR_MODES.NONE,
    { disposeSceneObject, floorSettings: { grid: { enabled: true, ...style, ...grid } } });

  draw(-2);
  const first = runtime.gridHelper;
  assert.equal(runtime.scene.children[0], first);
  assert.deepEqual(first.position.toArray(), [0, 0, -2]);
  assert.equal(runtime.floorMode, THEME_FLOOR_MODES.GRID);

  draw(3, { color: "#abcdef", opacity: 0.25, density: 2 });
  assert.equal(runtime.gridHelper, first);
  assert.deepEqual(first.position.toArray(), [0, 0, 3]);
  assert.equal(hex(first.material.uniforms.color.value), "#abcdef");
  assert.equal(first.material.uniforms.opacity.value, 0.25);
  assert.equal(first.material.uniforms.minorStep.value, runtime.gridConfig.cellSize);
  assert.deepEqual(disposed, []);

  updateGridHelper(runtime, {}, 10, 0, VIEWER_SCENE_SCALE.CAD, THEME_FLOOR_MODES.STAGE, { disposeSceneObject });
  assert.equal(runtime.gridHelper, null);
  assert.equal(runtime.gridConfig, null);
  assert.deepEqual(disposed, [first]);
});
