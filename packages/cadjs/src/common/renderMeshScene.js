import * as THREE from "three";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import {
  resolveThemeDisplayEdgeSettings
} from "./themeSettings.js";
import {
  displayModeForcesEdges,
  displayModeIsWireframe,
  displayModeShowsEdges,
  displayModeShowsThroughEdges,
  normalizeDisplaySettings
} from "./displaySettings.js";
import {
  buildModel
} from "./cadScene.js";
import {
  resolveTopologyDisplayEdgeRuntimes,
  shouldRenderTopologyDisplayEdges,
  shouldUseRecordTopologyEdgeTransforms
} from "./topologyDisplayEdgeRuntime.js";
import {
  syncScreenSpaceLineMaterialResolution
} from "./renderEdges.js";
import {
  syncTopologyDisplayEdgeLine
} from "../lib/viewer/topologyDisplayEdgeLine.js";
import {
  addFloor as addSharedFloor,
  applyEnvironment as applySharedEnvironment,
  applyLighting as applySharedLighting,
  boundsCorners as sharedBoundsCorners,
  boundsFromVertices as sharedBoundsFromVertices,
  centerAndRadiusFromBounds as sharedCenterAndRadiusFromBounds,
  colorTextureFromBackground as sharedColorTextureFromBackground,
  configurePngRenderer,
  createSharedRenderOptions,
  drawBurnedInLabel as drawSharedBurnedInLabel,
  fitPerspectiveCamera as fitSharedPerspectiveCamera,
  fitOrthographicCamera,
  frameHalfHeightForView as sharedFrameHalfHeightForView,
  framePadding as sharedFramePadding,
  inferRenderSceneScale,
  lockedFrameHalfHeight as sharedLockedFrameHalfHeight,
  normalizeRenderSceneScale as normalizeSharedRenderSceneScale,
  outputSize as sharedOutputSize,
  RENDER_SCENE_SCALE,
  RENDER_VIEW_PRESETS,
  rendererDataUrlWithOptionalLabel as sharedRendererDataUrlWithOptionalLabel,
  resolveRenderView,
  resolveAppearanceSettings,
  shouldBurnInViewLabels as sharedShouldBurnInViewLabels
} from "./renderOptions.js";
import {
  cameraSpecUsesPerspectiveProjection
} from "./camera.js";

const DEFAULT_RENDER_SCALE = 1;
const DEFAULT_RENDER_THEME_ID = "workbench";
const RENDER_SCENE_SCALE_SETTINGS = Object.freeze({
  [RENDER_SCENE_SCALE.CAD]: Object.freeze({
    minBoundsSpan: 1,
    minModelRadius: 1,
    minFloorSize: 100,
    minCameraDistance: 10,
    minCameraFar: 1000
  }),
  [RENDER_SCENE_SCALE.URDF]: Object.freeze({
    minBoundsSpan: 0.05,
    minModelRadius: 0.05,
    minFloorSize: 0.5,
    minCameraDistance: 0.5,
    minCameraFar: 10
  })
});

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}

function normalizeBoolean(value, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

function normalizeRenderSceneScale(value) {
  return normalizeSharedRenderSceneScale(value);
}

function resolveRenderSceneScale(job = {}, meshData = {}) {
  const explicit = String(job.render?.scale || job.render?.sceneScale || job.render?.sceneScaleMode || job.scale || job.sceneScale || "").trim().toLowerCase();
  return inferRenderSceneScale({
    explicit,
    kind: job.resolved?.kind || job.kind,
    parts: meshData?.parts
  });
}

function resolveAppearance(job = {}) {
  return resolveAppearanceSettings(job, { defaultThemeId: DEFAULT_RENDER_THEME_ID });
}

function resolveView(camera = "iso") {
  return resolveRenderView(camera, RENDER_VIEW_PRESETS, { strict: true });
}

function boundsFromVertices(vertices) {
  return sharedBoundsFromVertices(vertices);
}

function centerAndRadiusFromBounds(bounds, sceneScale = RENDER_SCENE_SCALE.CAD) {
  return sharedCenterAndRadiusFromBounds(bounds, sceneScale, RENDER_SCENE_SCALE_SETTINGS);
}

function colorTextureFromBackground(background, width, height) {
  return sharedColorTextureFromBackground(background, width, height);
}

async function applyEnvironment(scene, themeSettings, warnings) {
  return applySharedEnvironment(scene, themeSettings, warnings);
}

function applyLighting(scene, themeSettings) {
  return applySharedLighting(scene, themeSettings);
}

function mergeBoundsList(boundsList) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  let count = 0;
  for (const bounds of Array.isArray(boundsList) ? boundsList : []) {
    if (!bounds || !Array.isArray(bounds.min) || !Array.isArray(bounds.max)) {
      continue;
    }
    count += 1;
    for (let axis = 0; axis < 3; axis += 1) {
      min[axis] = Math.min(min[axis], toFiniteNumber(bounds.min[axis]));
      max[axis] = Math.max(max[axis], toFiniteNumber(bounds.max[axis]));
    }
  }
  return count > 0 && min.every(Number.isFinite) && max.every(Number.isFinite) ? { min, max } : null;
}

function addFloor(scene, bounds, themeSettings, sceneScale = RENDER_SCENE_SCALE.CAD) {
  return addSharedFloor(scene, bounds, themeSettings, sceneScale, RENDER_SCENE_SCALE_SETTINGS);
}

function boundsCorners(bounds) {
  return sharedBoundsCorners(bounds);
}

function framePadding(job = {}) {
  return sharedFramePadding(job);
}

function frameHalfHeightForView(view, bounds, width, height, padding = 0.12, sceneScale = RENDER_SCENE_SCALE.CAD) {
  return sharedFrameHalfHeightForView(view, bounds, width, height, padding, sceneScale, RENDER_SCENE_SCALE_SETTINGS);
}

function fitCamera(camera, view, bounds, width, height, lockedHalfHeight = null, padding = 0.12, sceneScale = RENDER_SCENE_SCALE.CAD) {
  return fitOrthographicCamera(camera, view, bounds, width, height, {
    lockedHalfHeight,
    padding,
    sceneScale,
    settingsByScale: RENDER_SCENE_SCALE_SETTINGS
  });
}

function fitPerspectiveCamera(camera, cameraSpec, bounds, width, height, sceneScale = RENDER_SCENE_SCALE.CAD) {
  return fitSharedPerspectiveCamera(camera, cameraSpec, bounds, width, height, {
    sceneScale,
    settingsByScale: RENDER_SCENE_SCALE_SETTINGS,
    strict: true
  });
}

function lockedFrameHalfHeight(outputs, bounds, width, height, job, sceneScale = RENDER_SCENE_SCALE.CAD) {
  return sharedLockedFrameHalfHeight(outputs, bounds, width, height, job, sceneScale, RENDER_SCENE_SCALE_SETTINGS);
}

function outputSize(output, job) {
  return sharedOutputSize(output, job);
}

function configureRenderer(width, height, job, themeSettings) {
  return configurePngRenderer(width, height, job, themeSettings, { defaultRenderScale: DEFAULT_RENDER_SCALE });
}

function shouldBurnInViewLabels(job = {}) {
  return sharedShouldBurnInViewLabels(job);
}

function drawBurnedInLabel(context, label, width, height, {
  corner = "top-left",
  fill = "#111827",
  background = "rgba(255, 255, 255, 0.9)",
  border = "rgba(17, 24, 39, 0.42)"
} = {}) {
  return drawSharedBurnedInLabel(context, label, width, height, {
    corner,
    fill,
    background,
    border
  });
}

function rendererDataUrlWithOptionalLabel(renderer, label, job) {
  return sharedRendererDataUrlWithOptionalLabel(renderer, label, job);
}

function tightFrameEnabled(job = {}) {
  return normalizeBoolean(job.render?.tightFrame, normalizeBoolean(job.tightFrame, true));
}

export function projectedVisibleGeometryFrame(records, camera) {
  const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize();
  const screenUp = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize();
  const point = new THREE.Vector3();
  const min = { x: Infinity, y: Infinity };
  const max = { x: -Infinity, y: -Infinity };
  let count = 0;

  for (const record of Array.isArray(records) ? records : []) {
    const mesh = record?.mesh;
    const position = mesh?.geometry?.getAttribute?.("position");
    if (!mesh?.visible || !position || position.count <= 0) {
      continue;
    }
    mesh.updateWorldMatrix?.(true, false);
    for (let index = 0; index < position.count; index += 1) {
      point.fromBufferAttribute(position, index).applyMatrix4(mesh.matrixWorld);
      const x = point.dot(right);
      const y = point.dot(screenUp);
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        continue;
      }
      min.x = Math.min(min.x, x);
      min.y = Math.min(min.y, y);
      max.x = Math.max(max.x, x);
      max.y = Math.max(max.y, y);
      count += 1;
    }
  }

  if (!count || ![min.x, min.y, max.x, max.y].every(Number.isFinite)) {
    return null;
  }

  return {
    centerX: (min.x + max.x) / 2,
    centerY: (min.y + max.y) / 2,
    spanX: Math.max(max.x - min.x, 1e-6),
    spanY: Math.max(max.y - min.y, 1e-6),
    count
  };
}

function applyTightOrthographicFrame(camera, records, width, height, padding, zoom = 1) {
  camera.updateMatrixWorld(true);
  const frame = projectedVisibleGeometryFrame(records, camera);
  if (!frame) {
    return null;
  }

  const aspect = Math.max(width / Math.max(height, 1), 0.01);
  const safeContentScale = Math.max(1 - (padding * 2), 0.1);
  const halfHeight = Math.max(
    frame.spanY / (2 * safeContentScale),
    frame.spanX / (2 * aspect * safeContentScale),
    1e-6
  ) / Math.max(toFiniteNumber(zoom, 1), 1e-6);
  const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize();
  const screenUp = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize();
  const currentCenterX = camera.position.dot(right);
  const currentCenterY = camera.position.dot(screenUp);
  camera.position
    .addScaledVector(right, frame.centerX - currentCenterX)
    .addScaledVector(screenUp, frame.centerY - currentCenterY);
  camera.top = halfHeight;
  camera.bottom = -halfHeight;
  camera.left = -halfHeight * aspect;
  camera.right = halfHeight * aspect;
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  return {
    ...frame,
    halfHeight
  };
}

function resolveSectionPlane(section = {}) {
  const plane = String(section.plane || "XY").toUpperCase();
  if (Array.isArray(section.normal) && section.normal.length >= 3) {
    const normal = new THREE.Vector3(section.normal[0], section.normal[1], section.normal[2]).normalize();
    const at = Array.isArray(section.at) && section.at.length >= 3
      ? new THREE.Vector3(section.at[0], section.at[1], section.at[2])
      : new THREE.Vector3();
    const helper = Math.abs(normal.z) < 0.9 ? new THREE.Vector3(0, 0, 1) : new THREE.Vector3(0, 1, 0);
    const u = new THREE.Vector3().crossVectors(helper, normal).normalize();
    const v = new THREE.Vector3().crossVectors(normal, u).normalize();
    return { normal, at, u, v };
  }
  const offset = toFiniteNumber(section.offset, 0);
  if (plane === "XZ") {
    return {
      normal: new THREE.Vector3(0, 1, 0),
      at: new THREE.Vector3(0, offset, 0),
      u: new THREE.Vector3(1, 0, 0),
      v: new THREE.Vector3(0, 0, 1)
    };
  }
  if (plane === "YZ") {
    return {
      normal: new THREE.Vector3(1, 0, 0),
      at: new THREE.Vector3(offset, 0, 0),
      u: new THREE.Vector3(0, 1, 0),
      v: new THREE.Vector3(0, 0, 1)
    };
  }
  return {
    normal: new THREE.Vector3(0, 0, 1),
    at: new THREE.Vector3(0, 0, offset),
    u: new THREE.Vector3(1, 0, 0),
    v: new THREE.Vector3(0, 1, 0)
  };
}

function sectionSegments(meshData, section = {}) {
  const vertices = meshData.vertices || new Float32Array(0);
  const indices = meshData.indices || new Uint32Array(0);
  const { normal, at, u, v } = resolveSectionPlane(section);
  const point = new THREE.Vector3();
  const tri = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
  const segments = [];
  const signedDistance = (candidate) => normal.dot(new THREE.Vector3().subVectors(candidate, at));
  const project = (candidate) => {
    const relative = new THREE.Vector3().subVectors(candidate, at);
    return [relative.dot(u), relative.dot(v)];
  };
  for (let index = 0; index + 2 < indices.length; index += 3) {
    for (let corner = 0; corner < 3; corner += 1) {
      const vertexIndex = Number(indices[index + corner]) * 3;
      tri[corner].set(vertices[vertexIndex], vertices[vertexIndex + 1], vertices[vertexIndex + 2]);
    }
    const distances = tri.map((corner) => signedDistance(corner));
    const intersections = [];
    for (const [a, b] of [[0, 1], [1, 2], [2, 0]]) {
      const da = distances[a];
      const db = distances[b];
      if (Math.abs(da) < 1e-7) {
        intersections.push(tri[a].clone());
      }
      if ((da < 0 && db > 0) || (da > 0 && db < 0)) {
        const t = da / (da - db);
        point.copy(tri[a]).lerp(tri[b], t);
        intersections.push(point.clone());
      }
    }
    if (intersections.length >= 2) {
      segments.push([project(intersections[0]), project(intersections[1])]);
    }
  }
  return segments;
}

function sectionBounds(segments) {
  const xs = [];
  const ys = [];
  for (const segment of segments) {
    for (const point of segment) {
      xs.push(point[0]);
      ys.push(point[1]);
    }
  }
  if (!xs.length) {
    return { minX: -1, minY: -1, maxX: 1, maxY: 1 };
  }
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys)
  };
}

function sectionPlaneLabel(section = {}) {
  const plane = String(section.plane || "XY").toUpperCase();
  const offset = toFiniteNumber(section.offset, 0);
  if (Array.isArray(section.normal) && section.normal.length >= 3) {
    const normal = section.normal.map((value) => Number(value).toFixed(3)).join(", ");
    const at = Array.isArray(section.at) && section.at.length >= 3
      ? section.at.map((value) => Number(value).toFixed(3)).join(", ")
      : "0.000, 0.000, 0.000";
    return `CUT N[${normal}] @ [${at}]`;
  }
  const axis = plane === "YZ" ? "X" : plane === "XZ" ? "Y" : "Z";
  return `SECTION ${plane} @ ${axis}=${offset.toFixed(3)}`;
}

function segmentEndpointKey(point, precision = 1000) {
  return `${Math.round(point[0] * precision)}:${Math.round(point[1] * precision)}`;
}

function loopsFromSegments(segments) {
  const edges = segments.map((segment, index) => ({
    index,
    a: segment[0],
    b: segment[1],
    aKey: segmentEndpointKey(segment[0]),
    bKey: segmentEndpointKey(segment[1])
  }));
  const byKey = new Map();
  for (const edge of edges) {
    for (const key of [edge.aKey, edge.bKey]) {
      if (!byKey.has(key)) {
        byKey.set(key, []);
      }
      byKey.get(key).push(edge);
    }
  }
  const used = new Set();
  const loops = [];
  for (const edge of edges) {
    if (used.has(edge.index)) {
      continue;
    }
    used.add(edge.index);
    const startKey = edge.aKey;
    let currentKey = edge.bKey;
    const points = [edge.a, edge.b];
    for (let guard = 0; guard < edges.length; guard += 1) {
      if (currentKey === startKey) {
        break;
      }
      const next = (byKey.get(currentKey) || []).find((candidate) => !used.has(candidate.index));
      if (!next) {
        break;
      }
      used.add(next.index);
      const nextPoint = next.aKey === currentKey ? next.b : next.a;
      currentKey = next.aKey === currentKey ? next.bKey : next.aKey;
      points.push(nextPoint);
    }
    if (points.length >= 3 && currentKey === startKey) {
      loops.push(points);
    }
  }
  return loops;
}

function sectionTransform(segments, width, height, paddingRatio = 0.12) {
  const { minX, minY, maxX, maxY } = sectionBounds(segments);
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const padding = Math.max(20, Math.min(width, height) * paddingRatio);
  const scale = Math.min((width - padding * 2) / spanX, (height - padding * 2) / spanY);
  const ox = (width - spanX * scale) / 2 - minX * scale;
  const oy = (height + spanY * scale) / 2 + minY * scale;
  return { minX, minY, maxX, maxY, spanX, spanY, scale, ox, oy };
}

function traceSectionLoops(context, loops, transform) {
  for (const loop of loops) {
    if (!loop.length) {
      continue;
    }
    context.moveTo(loop[0][0] * transform.scale + transform.ox, transform.oy - loop[0][1] * transform.scale);
    for (let index = 1; index < loop.length; index += 1) {
      context.lineTo(loop[index][0] * transform.scale + transform.ox, transform.oy - loop[index][1] * transform.scale);
    }
    context.closePath();
  }
}

function drawSectionHatching(context, width, height) {
  context.save();
  context.strokeStyle = "rgba(17, 24, 39, 0.2)";
  context.lineWidth = 1;
  const spacing = 14;
  for (let offset = -height; offset < width + height; offset += spacing) {
    context.beginPath();
    context.moveTo(offset, height);
    context.lineTo(offset + height, 0);
    context.stroke();
  }
  context.restore();
}

function drawSectionCenterlines(context, transform, width, height) {
  const centerX = ((transform.minX + transform.maxX) / 2) * transform.scale + transform.ox;
  const centerY = transform.oy - ((transform.minY + transform.maxY) / 2) * transform.scale;
  context.save();
  context.strokeStyle = "rgba(239, 68, 68, 0.75)";
  context.lineWidth = 1.5;
  context.setLineDash([10, 8, 2, 8]);
  context.beginPath();
  context.moveTo(Math.max(0, centerX), 0);
  context.lineTo(Math.max(0, centerX), height);
  context.moveTo(0, Math.max(0, centerY));
  context.lineTo(width, Math.max(0, centerY));
  context.stroke();
  context.restore();
}

function drawSectionLocator(context, section, bounds, width, height) {
  const plane = resolveSectionPlane(section);
  const corners = boundsCorners(bounds);
  const values = corners.map((corner) => corner.dot(plane.normal));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const atValue = plane.at.dot(plane.normal);
  const locatorWidth = Math.max(170, Math.min(width * 0.24, 260));
  const locatorHeight = Math.max(78, Math.min(height * 0.16, 130));
  const margin = Math.max(18, Math.round(Math.min(width, height) * 0.024));
  const x = width - margin - locatorWidth;
  const y = height - margin - locatorHeight;
  const pad = 16;
  const trackX = x + pad;
  const trackY = y + locatorHeight / 2;
  const trackWidth = locatorWidth - pad * 2;
  const t = clamp((atValue - min) / Math.max(max - min, 1e-9), 0, 1);
  const cutX = trackX + t * trackWidth;
  context.save();
  context.fillStyle = "rgba(255, 255, 255, 0.92)";
  context.strokeStyle = "rgba(17, 24, 39, 0.42)";
  context.lineWidth = 1;
  context.beginPath();
  context.roundRect(x, y, locatorWidth, locatorHeight, 8);
  context.fill();
  context.stroke();
  context.fillStyle = "#111827";
  context.font = "700 13px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
  context.fillText("CUT LOCATOR", x + pad, y + 10);
  context.strokeStyle = "#9ca3af";
  context.lineWidth = 8;
  context.lineCap = "round";
  context.beginPath();
  context.moveTo(trackX, trackY);
  context.lineTo(trackX + trackWidth, trackY);
  context.stroke();
  context.strokeStyle = "#ef4444";
  context.lineWidth = 3;
  context.beginPath();
  context.moveTo(cutX, trackY - 22);
  context.lineTo(cutX, trackY + 22);
  context.stroke();
  context.font = "600 12px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
  context.fillStyle = "#ef4444";
  context.fillText(sectionPlaneLabel(section).replace(/^SECTION\s+/, ""), x + pad, y + locatorHeight - 22);
  context.restore();
}

function renderSectionSvg(segments, edgeColor = "#132232") {
  const { minX, minY, maxX, maxY } = sectionBounds(segments);
  const padding = 4;
  const viewBox = [
    minX - padding,
    minY - padding,
    Math.max(maxX - minX + padding * 2, 1),
    Math.max(maxY - minY + padding * 2, 1)
  ].map((value) => Number(value).toFixed(4)).join(" ");
  const lines = segments.map((segment) => (
    `<path d="M ${segment[0][0].toFixed(4)} ${segment[0][1].toFixed(4)} L ${segment[1][0].toFixed(4)} ${segment[1][1].toFixed(4)}"/>`
  )).join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" fill="none" stroke="${edgeColor}" stroke-width="0.8" stroke-linecap="round" stroke-linejoin="round">${lines}</svg>`;
}

function renderSectionPng(segments, width, height, themeSettings, {
  transparent = false,
  section = {},
  bounds = null,
  viewLabels = false
} = {}) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  const background = themeSettings.background || {};
  if (!transparent) {
    context.fillStyle = background.solidColor || "#ffffff";
    context.fillRect(0, 0, width, height);
  }
  const transform = sectionTransform(segments, width, height);
  const loops = loopsFromSegments(segments);
  if (loops.length) {
    context.save();
    context.beginPath();
    traceSectionLoops(context, loops, transform);
    context.fillStyle = "rgba(209, 213, 219, 0.72)";
    context.fill("evenodd");
    context.clip("evenodd");
    drawSectionHatching(context, width, height);
    context.restore();
  }
  drawSectionCenterlines(context, transform, width, height);
  context.strokeStyle = resolveThemeDisplayEdgeSettings(themeSettings).color || "#132232";
  context.lineWidth = 3;
  context.lineCap = "round";
  context.lineJoin = "round";
  for (const segment of segments) {
    context.beginPath();
    context.moveTo(segment[0][0] * transform.scale + transform.ox, transform.oy - segment[0][1] * transform.scale);
    context.lineTo(segment[1][0] * transform.scale + transform.ox, transform.oy - segment[1][1] * transform.scale);
    context.stroke();
  }
  if (bounds) {
    drawSectionLocator(context, section, bounds, width, height);
  }
  if (viewLabels) {
    drawBurnedInLabel(context, sectionPlaneLabel(section), width, height);
  }
  return canvas.toDataURL("image/png");
}

export function listRenderableParts(meshData) {
  return toArray(meshData.parts).map((part, index) => ({
    id: String(part?.id || part?.occurrenceId || `part:${index}`),
    occurrenceId: String(part?.occurrenceId || part?.id || ""),
    name: String(part?.name || part?.label || part?.id || `Part ${index + 1}`),
    label: String(part?.label || part?.name || part?.id || `Part ${index + 1}`),
    triangleCount: Math.max(0, Math.floor(toFiniteNumber(part?.triangleCount, 0))),
    vertexCount: Math.max(0, Math.floor(toFiniteNumber(part?.vertexCount, 0))),
    bounds: part?.bounds || null
  }));
}

export function renderJobContext(meshData, job = {}) {
  const mode = String(job.mode || "view").trim().toLowerCase();
  const theme = resolveAppearance(job);
  const sceneScale = resolveRenderSceneScale(job, meshData);
  const sourceKind = String(job.resolved?.kind || job.kind || meshData?.sourceFormat || "").trim().toLowerCase();
  const stepDisplayEnabled = sourceKind === "step" || sourceKind === "stp";
  const displaySettings = stepDisplayEnabled
    ? normalizeDisplaySettings(job.display)
    : normalizeDisplaySettings();
  const displayMode = displaySettings.mode;
  const bounds = meshData.bounds || boundsFromVertices(meshData.vertices || []);
  const outputs = toArray(job.outputs).length ? toArray(job.outputs) : [{ path: job.output || "", camera: job.camera || "iso" }];
  const warnings = [];
  const sharedRenderOptions = createSharedRenderOptions({
    themeSettings: theme,
    display: displaySettings,
    sceneScale,
    clip: displaySettings.clip,
    selection: job.selection || null,
    floor: theme.floor || null,
    background: theme.background || null,
    lighting: theme.lighting || null,
    renderScale: job.render?.renderScale ?? job.renderScale ?? DEFAULT_RENDER_SCALE
  });
  const baseEdgeSettings = resolveThemeDisplayEdgeSettings(theme);
  const edgeSettings = {
    ...baseEdgeSettings,
    enabled: displayModeForcesEdges(displayMode) ? true : baseEdgeSettings.enabled,
    depthTest: displayModeShowsThroughEdges(displayMode) ? false : baseEdgeSettings.depthTest
  };
  const wireframeMode = displayModeIsWireframe(displayMode);
  const edgesVisible = stepDisplayEnabled && displayModeShowsEdges(displayMode, edgeSettings);
  const selectorRuntime = job.stepParameters?.selectorRuntime || job.selectorRuntime || null;
  const displayEdgeRuntime = job.stepParameters?.displayEdgeRuntime || job.displayEdgeRuntime || null;
  const topologyDisplayEdgesVisible = shouldRenderTopologyDisplayEdges({
    edgesVisible,
    wireframeMode,
    cadEdgeSource: stepDisplayEnabled,
    displayEdgeRuntime,
    selectorRuntime,
    edgeSettings
  });
  const sceneTheme = topologyDisplayEdgesVisible
    ? {
        ...theme,
        edges: {
          ...edgeSettings,
          enabled: false
        }
      }
    : {
        ...theme,
        edges: edgesVisible
          ? edgeSettings
          : {
              ...edgeSettings,
              enabled: false
            }
      };
  return {
    mode,
    theme,
    sceneTheme,
    sceneScale,
    sourceKind,
    stepDisplayEnabled,
    displaySettings,
    displayMode,
    wireframeMode,
    edgesVisible,
    bounds,
    outputs,
    warnings,
    sharedRenderOptions,
    edgeSettings,
    selectorRuntime,
    displayEdgeRuntime,
    topologyDisplayEdgesVisible
  };
}

export function modelOptionsForRenderJob(context, job = {}) {
  return {
    theme: context.sceneTheme,
    displayMode: context.displayMode,
    applyDisplayModeEdgePolicy: !context.topologyDisplayEdgesVisible,
    scale: context.sceneScale,
    clip: context.sharedRenderOptions.clip,
    silhouette: context.topologyDisplayEdgesVisible && context.edgeSettings.silhouette === true,
    renderPartsIndividually: true,
    selection: {
      ...(job.selection || {}),
      showEdges: context.edgesVisible
    },
    edgeRendering: {
      mode: "screen-space",
      Line2,
      LineGeometry,
      LineSegments2,
      LineSegmentsGeometry,
      LineMaterial
    },
    callbacks: {
      onWarning: (warning) => {
        const message = String(warning?.message || warning?.title || "").trim();
        if (message) {
          context.warnings.push(message);
        }
      }
    }
  };
}

export function renderModel(_THREE, model, viewportOptions = {}) {
  if (!model?.root) {
    throw new Error("renderModel requires a model returned by buildModel");
  }
  const job = viewportOptions.job || {};
  const context = viewportOptions.context || renderJobContext(model.meshData, job);
  const sceneBuildStarted = performance.now();
  const firstSize = outputSize(context.outputs[0] || {}, job);
  const renderer = configureRenderer(firstSize.width, firstSize.height, job, context.theme);
  const scene = new THREE.Scene();
  if (normalizeBoolean(job.render?.transparent, false) || context.theme.background?.type === "transparent") {
    scene.background = null;
    renderer.setClearColor(new THREE.Color("#000000"), 0);
  } else {
    scene.background = colorTextureFromBackground(context.theme.background || {}, firstSize.width, firstSize.height);
  }
  const ready = applyEnvironment(scene, context.theme, context.warnings);
  applyLighting(scene, context.theme);
  Object.assign(model.runtime, {
    Line2,
    LineGeometry,
    LineSegments2,
    LineSegmentsGeometry,
    LineMaterial
  });
  scene.add(model.root);
  addFloor(scene, model.bounds || context.bounds, context.theme, context.sceneScale);
  const orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.001, 10000);
  const perspectiveCamera = new THREE.PerspectiveCamera(48, firstSize.width / Math.max(firstSize.height, 1), 0.1, 50000);
  return {
    THREE: _THREE || THREE,
    model,
    scene,
    renderer,
    orthographicCamera,
    perspectiveCamera,
    context,
    sceneBuildStarted,
    ready,
    dispose() {
      model.dispose?.();
      renderer.dispose?.();
    }
  };
}

function displayRecordPartIds(displayRecords = []) {
  return Array.from(new Set(
    toArray(displayRecords)
      .map((record) => String(record?.partId || "").trim())
      .filter((partId) => partId && partId !== "__model__")
  ));
}

function syncViewportTopologyDisplayEdges(viewport) {
  const { context, model } = viewport;
  const renderedPartIds = displayRecordPartIds(model.displayRecords);
  const baseEdgeRuntimes = resolveTopologyDisplayEdgeRuntimes({
    selectorRuntime: context.selectorRuntime,
    displayEdgeRuntime: context.displayEdgeRuntime,
    displayRecords: model.displayRecords,
    transformDisplayEdges: false
  });
  const transformByRecord = shouldUseRecordTopologyEdgeTransforms({
    transformDetected: baseEdgeRuntimes.transformCount > 0,
    topologyDisplayEdgesVisible: context.topologyDisplayEdgesVisible,
    displayEdgeRuntime: context.displayEdgeRuntime,
    displayRecords: model.displayRecords
  });
  const edgeRuntimes = transformByRecord
    ? baseEdgeRuntimes
    : resolveTopologyDisplayEdgeRuntimes({
        selectorRuntime: context.selectorRuntime,
        displayEdgeRuntime: context.displayEdgeRuntime,
        displayRecords: model.displayRecords
      });
  syncTopologyDisplayEdgeLine(
    model.runtime,
    transformByRecord ? context.displayEdgeRuntime : edgeRuntimes.topologyRuntime,
    {
      visible: context.topologyDisplayEdgesVisible,
      edgeSettings: renderedPartIds.length
        ? {
            ...context.edgeSettings,
            includePartIds: renderedPartIds
          }
        : context.edgeSettings,
      viewerTheme: model.runtime?.baseTheme,
      transformByRecord,
      displayRecords: model.displayRecords
    }
  );
}

export async function captureModel(viewport, captureOptions = {}) {
  const job = captureOptions.job || {};
  const context = viewport.context || renderJobContext(viewport.model.meshData, job);
  const meshData = viewport.model.meshData;
  const {
    mode,
    theme,
    sceneScale,
    bounds,
    outputs,
    warnings
  } = context;
  const modelBounds = viewport.model?.bounds || meshData.bounds || bounds;

  if (mode === "list") {
    return {
      ok: true,
      mode,
      parts: listRenderableParts(meshData),
      bounds: modelBounds,
      warnings
    };
  }

  if (mode === "section") {
    const section = job.section || {};
    const segments = sectionSegments(meshData, section);
    return {
      ok: true,
      mode,
      outputs: outputs.map((output) => {
        const { width, height } = outputSize(output, job);
        const format = String(output.format || job.section?.format || "").toLowerCase() || (
          String(output.path || "").toLowerCase().endsWith(".svg") ? "svg" : "png"
        );
        if (format === "svg") {
          return {
            path: String(output.path || ""),
            mimeType: "image/svg+xml",
            text: renderSectionSvg(segments, resolveThemeDisplayEdgeSettings(theme).color)
          };
        }
        return {
            path: String(output.path || ""),
            width,
            height,
            mimeType: "image/png",
            dataUrl: renderSectionPng(segments, width, height, theme, {
              transparent: normalizeBoolean(job.render?.transparent, false),
              section,
              bounds: modelBounds,
              viewLabels: shouldBurnInViewLabels(job)
            })
          };
        }),
      section: {
        segmentCount: segments.length
      },
      warnings
    };
  }

  await viewport.ready;
  const sceneBuildMs = performance.now() - viewport.sceneBuildStarted;
  const lockFraming = normalizeBoolean(job.render?.lockFraming, normalizeBoolean(job.lockFraming, false));
  const padding = framePadding(job);
  const boundsByOutput = new Map();
  const parametersForOutput = (output) => (
    output.stepParameters ||
    job.stepParameters ||
    null
  );
  for (const output of outputs) {
    const parameters = parametersForOutput(output);
    const effectiveBounds = parameters
      ? viewport.model.update({ stepParameters: parameters }).bounds
      : viewport.model.update({ stepParameters: null }).bounds;
    boundsByOutput.set(output, effectiveBounds);
  }
  const lockedBounds = lockFraming
    ? mergeBoundsList(outputs.map((output) => boundsByOutput.get(output))) || bounds
    : null;
  const firstSize = outputSize(outputs[0] || {}, job);
  const lockedHalfHeight = lockFraming ? lockedFrameHalfHeight(outputs, lockedBounds, firstSize.width, firstSize.height, job, sceneScale) : null;
  const renderedOutputs = [];
  const renderStarted = performance.now();
  for (const output of outputs) {
    const parameters = parametersForOutput(output);
    const { width, height } = outputSize(output, job);
    viewport.renderer.setSize(width, height, false);
    const outputBounds = parameters
      ? viewport.model.update({ stepParameters: parameters }).bounds
      : viewport.model.update({ stepParameters: null }).bounds;
    syncViewportTopologyDisplayEdges(viewport);
    syncScreenSpaceLineMaterialResolution(viewport.model.runtime.screenSpaceLineMaterials, width, height);
    const cameraSpec = output.camera || job.camera || "iso";
    const usePerspectiveCamera = cameraSpecUsesPerspectiveProjection(cameraSpec, {
      presets: RENDER_VIEW_PRESETS,
      strict: true
    });
    const cameraView = usePerspectiveCamera ? null : resolveView(cameraSpec);
    const resolvedCamera = usePerspectiveCamera
      ? fitPerspectiveCamera(viewport.perspectiveCamera, cameraSpec, lockedBounds || outputBounds, width, height, sceneScale)
      : fitCamera(viewport.orthographicCamera, cameraView, lockedBounds || outputBounds, width, height, lockedHalfHeight, padding, sceneScale);
    const renderCamera = usePerspectiveCamera ? viewport.perspectiveCamera : viewport.orthographicCamera;
    if (!usePerspectiveCamera && !lockFraming && tightFrameEnabled(job)) {
      viewport.scene.updateMatrixWorld(true);
      applyTightOrthographicFrame(renderCamera, viewport.model.displayRecords, width, height, padding, cameraView?.zoom);
    }
    viewport.renderer.render(viewport.scene, renderCamera);
    const viewLabel = String(output.viewLabel || output.label || resolvedCamera.name || "").toUpperCase();
    renderedOutputs.push({
      path: String(output.path || ""),
      camera: resolvedCamera.name,
      width,
      height,
      mimeType: "image/png",
      dataUrl: rendererDataUrlWithOptionalLabel(viewport.renderer, viewLabel, job)
    });
  }
  const renderMs = performance.now() - renderStarted;
  return {
    ok: true,
    mode,
    outputs: renderedOutputs,
    timings: {
      sceneBuildMs,
      renderMs,
      meshCount: viewport.model.displayRecords.length || listRenderableParts(meshData).length || 1
    },
    warnings
  };
}

export async function renderMeshJob(meshData, job = {}) {
  const context = renderJobContext(meshData, job);
  const model = buildModel(THREE, meshData, modelOptionsForRenderJob(context, job));
  if (context.mode === "list" || context.mode === "section") {
    try {
      return await captureModel({ model, context }, { job });
    } finally {
      model.dispose();
    }
  }
  const viewport = renderModel(THREE, model, { job, context });
  try {
    return await captureModel(viewport, { job });
  } finally {
    viewport.dispose();
  }
}
