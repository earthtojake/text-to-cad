import {
  clampSceneModelRadius,
  VIEWER_SCENE_SCALE,
  getSceneScaleSettings
} from "./sceneScale.js";
import { BASE_VIEWER_THEME } from "./stageTheme.js";
import {
  DEFAULT_FLOOR_AXIS_SETTINGS,
  DEFAULT_FLOOR_GRID_SETTINGS,
  FLOOR_AXIS_RADIUS_MULTIPLE,
  MAX_FLOOR_GRID_DENSITY,
  MIN_FLOOR_GRID_DENSITY,
  THEME_FLOOR_MODES
} from "../themeSettings.js";
import { DEFAULT_AUTO_ZOOM_PADDING } from "./autoZoom.js";

// The grid is graph paper on the floor, in the manner of Tinkercad's workplane: thin minor lines
// at a round step (1, 2 or 5 x 10^n model units) and a heavier major line every 5 or 10 of them
// (so a major is 10^n or 5 x 10^n too), in one cool cyan-blue ink, with a red X axis and a green
// Y axis through the origin (the view cube's colours), all anti-aliased in one fragment shader on
// one quad. Each family of lines fades only once its cells crowd to a few pixels, so there is no
// moire at a grazing angle or zoomed out, and the whole sheet dissolves gently far from the
// origin, so it reaches the edges of the default view yet has no edge of its own.
//
// About twenty minor cells across the default framing at density 1; density scales the count.
export const GRID_TARGET_VISIBLE_CELLS = 20;
// Where the grid starts to fade, and where it has faded out, from the origin, in default framings
// (the model's diameter with the fit's padding): past the corners of the default view, so the
// paper fills it and only dissolves toward the horizon.
export const GRID_FADE_START_FRAMINGS = 1.5;
export const GRID_FADE_END_FRAMINGS = 6;
// The paper's ink: one colour, the majors' at full strength; the minors are the same ink, lighter.
// A light cyan-blue on a light backdrop; a cool steel blue that reads on a dark one without glowing.
export const GRID_LINE_DEFAULTS = Object.freeze({
  light: Object.freeze({ color: "#4ea8cc", opacity: 0.45 }),
  dark: Object.freeze({ color: "#5d9ac0", opacity: 0.35 })
});
// Line widths in drawing-buffer pixels, and how strong each family is beside the grid's opacity.
const MINOR_WIDTH = 0.75;
const MAJOR_WIDTH = 1.25;
const AXIS_WIDTH = 1.5;
const MINOR_STRENGTH = 0.6;
const AXIS_STRENGTH = 1.9;
// The pixel size of a cell below which its family starts to fade (it is gone at 2.5x less).
const MINOR_CROWD = 3.5;
const MAJOR_CROWD = 3.5;
// The axes in the view cube's colours, a shade deeper on a light backdrop to hold their contrast.
export const GRID_AXIS_COLORS = Object.freeze({
  light: Object.freeze({ x: "#e5484d", y: "#2f9e57", z: "#3d6fe8" }),
  dark: Object.freeze({ x: "#f2555a", y: "#4cc970", z: "#5b8cff" })
});
// The Axes setting's line is the third axis, Z, through the origin: blue, as on the view cube.
const GRID_Z_AXIS_COLOR = GRID_AXIS_COLORS.light.z;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeGridDensity(value) {
  const density = Number(value);
  return Number.isFinite(density)
    ? clamp(density, MIN_FLOOR_GRID_DENSITY, MAX_FLOOR_GRID_DENSITY)
    : DEFAULT_FLOOR_GRID_SETTINGS.density;
}

function resolveGridStyle(viewerTheme = {}, floorSettings = {}) {
  const gridSettings = floorSettings?.grid || {};
  return {
    color: gridSettings.color
      || gridSettings.centerColor
      || viewerTheme?.gridCenter
      || BASE_VIEWER_THEME.gridCenter,
    xAxisColor: gridSettings.xAxisColor || GRID_AXIS_COLORS.light.x,
    yAxisColor: gridSettings.yAxisColor || GRID_AXIS_COLORS.light.y,
    opacity: Number.isFinite(Number(gridSettings?.opacity))
      ? clamp(Number(gridSettings.opacity), 0, 1)
      : (viewerTheme?.gridOpacity ?? BASE_VIEWER_THEME.gridOpacity)
  };
}

// The round step (1, 2 or 5 x 10^n) at or above `minimumStep`, or with `nearest` the one nearest
// it, and its leading digit.
function roundStep(minimumStep, nearest = false) {
  if (!Number.isFinite(minimumStep) || minimumStep <= 0) {
    return { step: getSceneScaleSettings(VIEWER_SCENE_SCALE.CAD).minGridSize / 100, digit: 1 };
  }
  const exponent = Math.floor(Math.log10(minimumStep));
  const candidates = [1, 2, 5, 10].map(digit => ({ step: digit * 10 ** exponent, digit: digit === 10 ? 1 : digit }));
  if (nearest) {
    // Nearest on a log scale: the step whose ratio to the target is smallest.
    return candidates.reduce((best, next) =>
      Math.abs(Math.log(next.step / minimumStep)) < Math.abs(Math.log(best.step / minimumStep)) ? next : best);
  }
  return candidates.find(candidate => candidate.step >= minimumStep * (1 - 1e-9)) || candidates[3];
}

export function niceGridStep(minimumStep) {
  return roundStep(minimumStep).step;
}

/**
 * The grid for a model of `radius`: its minor step (`cellSize`), the minor cells per major
 * (`majorEvery`), and its reach — `fadeStart` and `fadeEnd` from the origin, and `size`, the
 * square that holds it, which a camera fits its depth range to.
 */
export function buildGridConfig(radius, sceneScaleMode, floorSettings = {}) {
  const gridDensity = normalizeGridDensity(floorSettings?.grid?.density);
  const safeRadius = clampSceneModelRadius(radius, sceneScaleMode);
  const framing = safeRadius * 2 * DEFAULT_AUTO_ZOOM_PADDING;
  const { step: cellSize, digit } = roundStep(framing / (GRID_TARGET_VISIBLE_CELLS * gridDensity), true);
  const majorEvery = digit === 2 ? 5 : 10;
  const fadeEnd = framing * GRID_FADE_END_FRAMINGS;
  return {
    size: fadeEnd * 2,
    cellSize,
    majorEvery,
    fadeStart: framing * GRID_FADE_START_FRAMINGS,
    fadeEnd
  };
}

const GRID_VERTEX_SHADER = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_vertex>
varying vec3 vWorld;
void main() {
  vec4 world = modelMatrix * vec4(position, 1.0);
  vWorld = world.xyz;
  gl_Position = projectionMatrix * viewMatrix * world;
  #include <logdepthbuf_vertex>
}
`;

const GRID_FRAGMENT_SHADER = /* glsl */ `
#include <common>
#include <logdepthbuf_pars_fragment>
uniform vec3 color;
uniform vec3 xAxisColor;
uniform vec3 yAxisColor;
uniform float opacity;
uniform float minorStep;
uniform float majorStep;
uniform float fadeStart;
uniform float fadeEnd;
varying vec3 vWorld;

// Lines every cell of \`coord\`; each direction fades out as its cells crowd under \`crowd\` pixels.
float gridLines(vec2 coord, float width, float crowd) {
  vec2 cellsPerPixel = max(fwidth(coord), vec2(1e-7));
  vec2 dist = abs(fract(coord - 0.5) - 0.5) / cellsPerPixel;
  vec2 cellPixels = 1.0 / cellsPerPixel;
  vec2 keep = smoothstep(vec2(crowd), vec2(crowd * 2.5), cellPixels);
  // A box filtered by the pixel: a line thinner than a pixel is fainter rather than broken.
  vec2 cover = clamp(vec2(0.5 * width + 0.5) - dist, 0.0, min(width, 1.0)) * keep;
  return max(cover.x, cover.y);
}

void main() {
  #include <logdepthbuf_fragment>
  vec2 plane = vWorld.xy;
  float minor = gridLines(plane / minorStep, ${MINOR_WIDTH.toFixed(2)}, ${MINOR_CROWD.toFixed(2)});
  float major = gridLines(plane / majorStep, ${MAJOR_WIDTH.toFixed(2)}, ${MAJOR_CROWD.toFixed(2)});
  // The axes: X runs along y = 0, Y along x = 0. They fade where the majors crowd, never smear.
  vec2 unitsPerPixel = max(fwidth(plane), vec2(1e-7));
  vec2 axisDistance = abs(plane.yx) / unitsPerPixel.yx;
  vec2 axisKeep = smoothstep(vec2(2.0), vec2(8.0), vec2(majorStep) / unitsPerPixel.yx);
  float halfAxis = 0.5 * ${AXIS_WIDTH.toFixed(2)} + 0.5;
  vec2 axis = clamp(vec2(halfAxis) - axisDistance, 0.0, 1.0) * axisKeep;

  float gridAlpha = max(minor * ${MINOR_STRENGTH.toFixed(2)}, major) * opacity;
  float axisAlpha = max(axis.x, axis.y) * min(1.0, opacity * ${AXIS_STRENGTH.toFixed(2)});
  vec3 axisColor = axis.x >= axis.y ? xAxisColor : yAxisColor;
  float alpha = axisAlpha + gridAlpha * (1.0 - axisAlpha);
  vec3 rgb = (axisColor * axisAlpha + color * gridAlpha * (1.0 - axisAlpha)) / max(alpha, 1e-5);

  // Dissolve far from the origin, and, gently, where the plane turns edge-on to the view.
  vec3 toEye = isOrthographic ? vec3(viewMatrix[0][2], viewMatrix[1][2], viewMatrix[2][2]) : normalize(cameraPosition - vWorld);
  alpha *= 1.0 - smoothstep(fadeStart, fadeEnd, length(plane));
  alpha *= smoothstep(0.01, 0.12, abs(toEye.z));
  if (alpha < 0.002) discard;
  gl_FragColor = vec4(rgb, alpha);
  #include <colorspace_fragment>
}
`;

function applyGridUniforms(material, config) {
  const uniforms = material.uniforms;
  uniforms.color.value.set(config.color);
  uniforms.xAxisColor.value.set(config.xAxisColor);
  uniforms.yAxisColor.value.set(config.yAxisColor);
  uniforms.opacity.value = config.opacity;
  uniforms.minorStep.value = config.cellSize;
  uniforms.majorStep.value = config.cellSize * config.majorEvery;
  uniforms.fadeStart.value = config.fadeStart;
  uniforms.fadeEnd.value = config.fadeEnd;
}

/**
 * The grid object for `config` (`buildGridConfig` with its colours): one quad in the XY plane,
 * centred on the origin. The viewer and the snapshot both draw this. `updateGridMesh` restyles it.
 */
export function createGridMesh(THREE, config) {
  const material = new THREE.ShaderMaterial({
    name: "cad-grid",
    uniforms: {
      color: { value: new THREE.Color() },
      xAxisColor: { value: new THREE.Color() },
      yAxisColor: { value: new THREE.Color() },
      opacity: { value: 1 },
      minorStep: { value: 1 },
      majorStep: { value: 10 },
      fadeStart: { value: 0 },
      fadeEnd: { value: 1 }
    },
    vertexShader: GRID_VERTEX_SHADER,
    fragmentShader: GRID_FRAGMENT_SHADER,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    // A model face on the grid's plane wins over it rather than fighting it.
    polygonOffset: true,
    polygonOffsetFactor: 1,
    polygonOffsetUnits: 1,
    toneMapped: false
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
  mesh.name = "cad-grid";
  mesh.userData.cadGrid = true;
  // Scene furniture: never what a pick lands on.
  mesh.raycast = () => {};
  updateGridMesh(mesh, config);
  return mesh;
}

export function updateGridMesh(mesh, config) {
  applyGridUniforms(mesh.material, config);
  mesh.scale.set(config.size, config.size, 1);
}

export function updateGridHelper(
  runtime,
  viewerTheme,
  radius,
  floorZ = 0,
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD,
  floorMode = THEME_FLOOR_MODES.STAGE,
  { disposeSceneObject = () => {}, floorSettings = {} } = {}
) {
  if (!runtime?.THREE || !runtime?.scene) {
    return;
  }
  runtime.gridRadius = radius;
  runtime.gridFloorZ = floorZ;
  const gridEnabled = floorSettings?.grid?.enabled === true || floorMode === THEME_FLOOR_MODES.GRID;
  runtime.floorMode = gridEnabled ? THEME_FLOOR_MODES.GRID : floorMode;
  if (!gridEnabled) {
    disposeSceneObject(runtime.gridHelper);
    runtime.gridHelper = null;
    runtime.gridConfig = null;
    return;
  }
  const nextConfig = {
    ...buildGridConfig(radius, sceneScaleMode, floorSettings),
    ...resolveGridStyle(viewerTheme, floorSettings)
  };
  // One grid for the runtime's life: a new size, step or colour is a uniform, not a new object.
  if (!runtime.gridHelper) {
    runtime.gridHelper = createGridMesh(runtime.THREE, nextConfig);
    runtime.scene.add(runtime.gridHelper);
  } else {
    updateGridMesh(runtime.gridHelper, nextConfig);
  }
  runtime.gridHelper.position.set(0, 0, floorZ);
  runtime.gridConfig = nextConfig;
}

function resolveAxisConfig(radius, viewerTheme = {}, floorSettings = {}) {
  const axisSettings = floorSettings?.axis || {};
  return {
    color: axisSettings.color || GRID_Z_AXIS_COLOR,
    opacity: clamp(
      Number.isFinite(Number(axisSettings.opacity))
        ? Number(axisSettings.opacity)
        : DEFAULT_FLOOR_AXIS_SETTINGS.opacity,
      0,
      1
    ),
    length: Math.max(radius, 1) * FLOOR_AXIS_RADIUS_MULTIPLE
  };
}

// A vertical line through the world origin, rising from the floor along +Z: the Z axis, beside
// the grid's red X and green Y. Kept separate from the grid so either shows on its own.
export function updateOriginAxis(
  runtime,
  viewerTheme,
  radius,
  floorZ = 0,
  { disposeSceneObject = () => {}, floorSettings = {} } = {}
) {
  if (!runtime?.THREE || !runtime?.scene) {
    return;
  }
  const THREE = runtime.THREE;
  if (floorSettings?.axis?.enabled !== true) {
    disposeSceneObject(runtime.originAxis);
    runtime.originAxis = null;
    runtime.originAxisConfig = null;
    return;
  }
  const nextConfig = resolveAxisConfig(radius, viewerTheme, floorSettings);
  const currentConfig = runtime.originAxisConfig;
  if (
    runtime.originAxis &&
    currentConfig &&
    currentConfig.color === nextConfig.color &&
    currentConfig.opacity === nextConfig.opacity &&
    currentConfig.length === nextConfig.length
  ) {
    runtime.originAxis.position.set(0, 0, floorZ);
    return;
  }

  disposeSceneObject(runtime.originAxis);
  const geometry = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(0, 0, -nextConfig.length),
    new THREE.Vector3(0, 0, nextConfig.length)
  ]);
  // Depth-tested like the grid: the axis is scene furniture, so any model
  // surface in front of it hides it rather than being drawn over.
  const material = new THREE.LineBasicMaterial({
    color: nextConfig.color,
    transparent: true,
    opacity: nextConfig.opacity,
    depthWrite: false,
    toneMapped: false
  });
  runtime.originAxis = new THREE.Line(geometry, material);
  runtime.originAxis.position.set(0, 0, floorZ);
  runtime.scene.add(runtime.originAxis);
  runtime.originAxisConfig = nextConfig;
}
