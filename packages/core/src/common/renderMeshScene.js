import { createInspectEnvironmentResource, hasAuthoredMaterials } from "./inspectEnvironment.js";
import { resolveCadEdgeSettings } from "./cadInk.js";
import * as THREE from "three";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import {
  displayModeIsWireframe,
  CAMERA_PROJECTION,
  resolveDisplayEdgeSettings
} from "./displaySettings.js";
import {
  buildModel,
  normalizedSelectorValues
} from "./cadScene.js";
import {
  applyDisplayRecordTransform
} from "./displayRecordTransform.js";
import {
  resolveTopologyDisplayEdgeRuntimes,
  shouldRenderTopologyDisplayEdges,
  shouldUseRecordTopologyEdgeTransforms
} from "./topologyDisplayEdgeRuntime.js";
import {
  screenSpaceLineDeviceResolution,
  syncScreenSpaceLineMaterialResolution
} from "./renderEdges.js";
import {
  syncTopologyDisplayEdgeLine
} from "../lib/viewer/topologyDisplayEdgeLine.js";
import {
  applyExplodedViewProgress,
  clearExplodedViewRecords,
  computeExplodedViewLayout,
  explodedViewBounds
} from "../lib/viewer/explodedView.js";
import {
  addFloor as addSharedFloor,
  applyLighting as applySharedLighting,
  boundsCorners as sharedBoundsCorners,
  boundsFromVertices as sharedBoundsFromVertices,
  centerAndRadiusFromBounds as sharedCenterAndRadiusFromBounds,
  colorTextureFromBackground as sharedColorTextureFromBackground,
  configurePngRenderer,
  createSharedRenderOptions,
  drawBurnedInLabel as drawSharedBurnedInLabel,
  fitPerspectiveCamera as fitSharedPerspectiveCamera,
  fitCameraDepthToBounds,
  fitOrthographicCamera,
  frameHalfHeightForView as sharedFrameHalfHeightForView,
  framePadding as sharedFramePadding,
  inferRenderSceneScale,
  normalizeRenderSceneScale as normalizeSharedRenderSceneScale,
  outputSize as sharedOutputSize,
  RENDER_SCENE_SCALE,
  RENDER_VIEW_PRESETS,
  rendererDataUrlWithOptionalLabel as sharedRendererDataUrlWithOptionalLabel,
  resolveRenderView,
  shouldBurnInViewLabels as sharedShouldBurnInViewLabels
} from "./renderOptions.js";
import {
  normalizeCameraSpec
} from "./camera.js";
import {
  resolveDisplayMaterialSettings,
  resolveViewSceneSettings
} from "./sceneSettings.js";
import {
  createEnvironmentResource,
  disposeEnvironmentResource
} from "./environmentMap.js";
import {
  applyPhotographicStudio,
  disposePhotographicStudio
} from "./photographicStudio.js";
import { PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS } from "./photographicStudioRig.js";
import { validateSnapshotRenderJob } from "./snapshotJobValidation.js";

const DEFAULT_RENDER_SCALE = 1;
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
  const explicit = String(job.scale || "").trim().toLowerCase();
  return inferRenderSceneScale({
    explicit,
    kind: job.resolved?.kind || job.kind,
    parts: meshData?.parts
  });
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

function applyLighting(scene, themeSettings, bounds, sceneScale, shadowMapSize) {
  return applySharedLighting(scene, themeSettings, { bounds, sceneScale, shadowMapSize });
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

function addFloor(scene, bounds, themeSettings, sceneScale = RENDER_SCENE_SCALE.CAD, guideSettings = null) {
  return addSharedFloor(scene, bounds, themeSettings, sceneScale, RENDER_SCENE_SCALE_SETTINGS, guideSettings);
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

function fitPerspectiveCamera(camera, cameraSpec, bounds, width, height, {
  framePoints = null,
  padding = 0.12,
  sceneScale = RENDER_SCENE_SCALE.CAD
} = {}) {
  return fitSharedPerspectiveCamera(camera, cameraSpec, bounds, width, height, {
    framePoints,
    padding,
    sceneScale,
    settingsByScale: RENDER_SCENE_SCALE_SETTINGS,
    strict: true
  });
}

function outputSize(output, job) {
  return sharedOutputSize(output, job);
}

function configureRenderer(width, height, job, context) {
  return configurePngRenderer(width, height, job, {
    defaultRenderScale: context.quality?.renderScale ?? DEFAULT_RENDER_SCALE,
    // Render replaces this wholesale in applyPhotographicStudio; only the CAD
    // inspection scene takes its exposure from the theme.
    toneMappingExposure: context.theme?.lighting?.toneMappingExposure ?? 1
  });
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

function rendererDataUrlWithOptionalLabel(renderer, label, job, size) {
  return sharedRendererDataUrlWithOptionalLabel(renderer, label, job, size);
}

export function disposeSnapshotSceneResources(scene, modelRoot = null, extraTextures = []) {
  const disposedGeometries = new Set();
  const disposedMaterials = new Set();
  const disposedTextures = new Set();
  const disposeTexture = (texture) => {
    if (!texture?.isTexture || disposedTextures.has(texture)) return;
    disposedTextures.add(texture);
    texture.dispose?.();
  };
  const disposeMaterial = (material) => {
    if (!material || disposedMaterials.has(material)) return;
    disposedMaterials.add(material);
    for (const value of Object.values(material)) {
      disposeTexture(value);
    }
    material.dispose?.();
  };
  for (const child of [...(scene?.children || [])]) {
    if (child === modelRoot) continue;
    child.traverse?.((object) => {
      if (object.geometry && !disposedGeometries.has(object.geometry)) {
        disposedGeometries.add(object.geometry);
        object.geometry.dispose?.();
      }
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach(disposeMaterial);
    });
    scene.remove?.(child);
  }
  for (const texture of extraTextures) disposeTexture(texture);
  disposeTexture(scene?.background);
  disposeTexture(scene?.environment);
  if (scene?.background?.isTexture) scene.background = null;
  if (scene?.environment?.isTexture) scene.environment = null;
  return {
    geometryCount: disposedGeometries.size,
    materialCount: disposedMaterials.size,
    textureCount: disposedTextures.size
  };
}

function tightFrameEnabled(job = {}) {
  return normalizeBoolean(job.output?.tightFrame, true);
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

function *visibleGeometryWorldPoints(records) {
  const point = new THREE.Vector3();
  for (const record of Array.isArray(records) ? records : []) {
    const mesh = record?.mesh;
    const position = mesh?.geometry?.getAttribute?.("position");
    if (!mesh?.visible || !position || position.count <= 0) {
      continue;
    }
    mesh.updateWorldMatrix?.(true, false);
    for (let index = 0; index < position.count; index += 1) {
      yield point.fromBufferAttribute(position, index).applyMatrix4(mesh.matrixWorld);
    }
  }
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
  const parts = Array.isArray(meshData.parts) ? meshData.parts : [];
  const chunks = parts.length && parts.every((part) => part.sourceMesh)
    ? parts.map((part) => ({ mesh: part.sourceMesh, transform: part.transform }))
    : [{ mesh: meshData, transform: null }];
  const { normal, at, u, v } = resolveSectionPlane(section);
  const point = new THREE.Vector3();
  const tri = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
  const segments = [];
  const signedDistance = (candidate) => normal.dot(new THREE.Vector3().subVectors(candidate, at));
  const project = (candidate) => {
    const relative = new THREE.Vector3().subVectors(candidate, at);
    return [relative.dot(u), relative.dot(v)];
  };
  for (const chunk of chunks) {
    const vertices = chunk.mesh.vertices || new Float32Array(0);
    const indices = chunk.mesh.indices || new Uint32Array(0);
    const transform = Array.isArray(chunk.transform) && chunk.transform.length === 16
      ? new THREE.Matrix4().set(...chunk.transform)
      : null;
    for (let index = 0; index + 2 < indices.length; index += 3) {
      for (let corner = 0; corner < 3; corner += 1) {
        const vertexIndex = Number(indices[index + corner]) * 3;
        tri[corner].set(vertices[vertexIndex], vertices[vertexIndex + 1], vertices[vertexIndex + 2]);
        if (transform) tri[corner].applyMatrix4(transform);
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
  edgeSettings = null,
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
  context.strokeStyle = edgeSettings?.color || "#132232";
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

// Coordinates are millimetres. The mesh pipeline emits full float64 precision
// (-2449.9999046325684 for what is 2450 mm), which is 16 significant figures of noise per
// number, six numbers per part. Three decimals is a nanometre -- far below any tolerance
// this repo models to -- and costs about a fifth of the payload.
const LIST_BOUNDS_DECIMALS = 3;

function roundedBounds(bounds) {
  if (!bounds || typeof bounds !== "object") {
    return null;
  }
  const axis = (values) => (Array.isArray(values)
    ? values.map((value) => {
      const numeric = toFiniteNumber(value, 0);
      return Number(numeric.toFixed(LIST_BOUNDS_DECIMALS));
    })
    : null);
  const min = axis(bounds.min);
  const max = axis(bounds.max);
  return min && max ? { min, max } : null;
}

// The parts inventory: what is in this model and what can be selected.
//
// This is the ONLY output whose size grows with the model -- everything else in the CLI
// surface is constant (a 600-part assembly logs the same ~100 bytes a single part does).
// So it is the one payload where redundancy is measured in tens of thousands of tokens:
// on a 600-part rover the previous shape was 294 KB, of which `id`, `occurrenceId` and
// `ref` were the same string three times over (identical in 600/600 parts), `label`
// duplicated `name` (600/600), and the coordinates carried 16 significant figures.
//
// `ref` survives rather than `id`/`occurrenceId` because it is the form that goes
// straight back into `--focus` / `--hide` / `inspect`; the bare id is one string slice
// away for anyone who needs it.
// A label ref (`#eye_shank`) addresses a part by the `name` already in every row, so this
// payload deliberately does NOT carry a second `labelRef` identifier -- that would undo the
// size work above for a string the row already contains. `inspect refs` reports the exact
// paste spelling, including the numbered form for duplicated labels, where the output is
// small enough for it to be free.
export function listRenderableParts(meshData) {
  return toArray(meshData.parts).map((part, index) => {
    const occurrenceId = String(part?.occurrenceId || part?.id || "");
    return {
      ref: occurrenceId ? `#${occurrenceId}` : "",
      name: String(part?.name || part?.label || part?.id || `Part ${index + 1}`),
      triangleCount: Math.max(0, Math.floor(toFiniteNumber(part?.triangleCount, 0))),
      vertexCount: Math.max(0, Math.floor(toFiniteNumber(part?.vertexCount, 0))),
      bounds: roundedBounds(part?.bounds)
    };
  });
}

export function resolveOutputCameraSpec(context, cameraSpec) {
  const contextCamera = context?.camera || {
    preset: "iso",
    projection: context?.projection || CAMERA_PROJECTION.ORTHOGRAPHIC
  };
  if (cameraSpec == null) {
    return contextCamera;
  }
  if (typeof cameraSpec === "string") {
    return {
      preset: cameraSpec,
      projection: contextCamera.projection,
      ...(contextCamera.focalLength != null ? { focalLength: contextCamera.focalLength } : {})
    };
  }
  return {
    ...(contextCamera.focalLength != null ? { focalLength: contextCamera.focalLength } : {}),
    ...cameraSpec,
    projection: cameraSpec.projection ?? contextCamera.projection
  };
}

// Projection is one field of the canonical per-output camera spec. A named
// output view inherits the job camera's projection unless it explicitly says
// otherwise.
export function resolveOutputCameraProjection(context, cameraSpec) {
  return normalizeCameraSpec(resolveOutputCameraSpec(context, cameraSpec), {
    presets: RENDER_VIEW_PRESETS,
    strict: true,
    defaultProjection: context?.camera?.projection || CAMERA_PROJECTION.ORTHOGRAPHIC
  }).projection;
}

export function renderJobContext(meshData, job = {}) {
  validateSnapshotRenderJob(job);
  const mode = String(job.mode || "view").trim().toLowerCase();
  const sceneScale = resolveRenderSceneScale(job, meshData);
  const sourceKind = String(job.resolved?.kind || job.kind || meshData?.sourceFormat || "").trim().toLowerCase();
  const stepDisplayEnabled = sourceKind === "step" || sourceKind === "stp";
  const sceneSettings = resolveViewSceneSettings({
    appearance: job.appearance || "light",
    camera: job.camera || null,
    display: job.display ?? {},
    // The viewer's rule: only a CAD model has edges to draw, parts to explode or solids to section.
    cadModel: stepDisplayEnabled
  });
  // Neutral CAD lights remain available when only the background/floor is on.
  const theme = sceneSettings.theme;
  const displaySettings = sceneSettings.display;
  const projection = sceneSettings.camera.projection;
  const displayMode = displaySettings.mode;
  const bounds = meshData.bounds || boundsFromVertices(meshData.vertices || []);
  const outputs = toArray(job.outputs).length ? toArray(job.outputs) : [{ path: typeof job.output === "string" ? job.output : job.output?.base || job.output?.path || "" }];
  const warnings = [];
  const sharedRenderOptions = createSharedRenderOptions({
    themeSettings: theme,
    display: displaySettings,
    camera: sceneSettings.camera,
    sceneScale,
    clip: displaySettings.clip,
    selection: job.selection || null,
    floor: theme?.floor || null,
    background: theme?.background || null,
    lighting: theme?.lighting || null,
    renderScale: job.output?.renderScale ?? sceneSettings.quality.renderScale
  });
  const displayEdgeSettings = resolveCadEdgeSettings(
    resolveDisplayEdgeSettings(displaySettings)
  );
  const edgeSettings = {
    ...displayEdgeSettings,
    enabled: sceneSettings.view.edges.enabled,
    depthTest: sceneSettings.view.edges.visibility !== "all"
  };
  const wireframeMode = displayModeIsWireframe(displayMode);
  const edgesVisible = sceneSettings.view.edges.enabled;
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
  return {
    mode,
    theme,
    sceneSettings,
    camera: sceneSettings.camera,
    quality: sceneSettings.quality,
    sceneScale,
    sourceKind,
    stepDisplayEnabled,
    displaySettings,
    projection,
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
  const selection = job.selection || {};
  const keepsAllParts = context.mode === "view";
  const filterSelection = keepsAllParts
    ? {
        hide: selection.hide
      }
    : selection;
  // View/orbit focus keeps every part in the scene so the frame retains
  // assembly context (hide is the removal filter); the focused refs instead
  // ghost the rest of the model through the same focusedPartId path the
  // interactive viewer uses. Section mode still isolates via filterSelection.
  const focusedPartId = keepsAllParts
    ? [
        ...normalizedSelectorValues(selection.focus),
        ...normalizedSelectorValues(selection.refs)
      ]
    : [];
  const renderEnabled = context.sceneSettings.view.lighting.enabled;
  return {
    theme: context.theme ?? undefined,
    // Render's finish is the studio's, not a theme's. CAD takes its material
    // settings from the resolved theme.
    materialSettings: renderEnabled
      ? resolveDisplayMaterialSettings(
          PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS,
          context.displaySettings.partColor
        )
      : undefined,
    appearance: context.sceneSettings.appearance,
    edgeSettings: context.topologyDisplayEdgesVisible
      ? { ...context.edgeSettings, enabled: false }
      : context.edgesVisible
        ? context.edgeSettings
        : { ...context.edgeSettings, enabled: false },
    materialOverrides: context.sceneSettings.materialOverrides,
    receiveShadows: renderEnabled,
    displayMode: context.displayMode,
    surfaceSettings: context.sceneSettings.view.surfaces,
    applyDisplayModeEdgePolicy: false,
    scale: context.sceneScale,
    clip: context.sharedRenderOptions.clip,
    silhouette: context.topologyDisplayEdgesVisible && context.edgeSettings.silhouette === true,
    renderPartsIndividually: true,
    selection: {
      ...selection,
      ...(focusedPartId.length ? { focusedPartId } : {}),
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
      },
      // The choreography half of a still: `{clip, elapsedSec}` rides the channel
      // cadScene's effects pass already reads (the docs hero drives playback
      // through the same key), so the clip's frame merges over the pose exactly
      // as it does in the viewer — one applySceneState, no snapshot-side twin.
      animation: job.stepAnimation || null
    },
    filterSelection
  };
}

// Kinematics is model state in both Inspect and Render. Per-output values take
// precedence so a multi-output capture can pose each frame independently.
export function stepParametersForSnapshotOutput(output = {}, job = {}) {
  return output.stepParameters || job.stepParameters || null;
}

export function renderModel(_THREE, model, viewportOptions = {}) {
  if (!model?.root) {
    throw new Error("renderModel requires a model returned by buildModel");
  }
  const job = viewportOptions.job || {};
  const context = viewportOptions.context || renderJobContext(model.meshData, job);
  const sceneBuildStarted = performance.now();
  const firstSize = outputSize(context.outputs[0] || {}, job);
  const renderer = configureRenderer(firstSize.width, firstSize.height, job, context);
  const scene = new THREE.Scene();
  let disposed = false;
  let environmentResource = null;
  let backgroundTexture = null;
  const photographicConfiguration = context.sceneSettings.render.configuration || null;
  const studioConfiguration = photographicConfiguration && normalizeBoolean(job.output?.transparent, false)
    ? { ...photographicConfiguration, backdrop: { ...photographicConfiguration.backdrop, transparent: true, opacity: 0 } }
    : photographicConfiguration;
  const studioRuntime = studioConfiguration ? { scene, renderer, modelBounds: model.bounds || context.bounds } : null;
  if (studioRuntime) {
    applyPhotographicStudio(THREE, studioRuntime, studioConfiguration, {
      bounds: viewportOptions.floorBounds || studioRuntime.modelBounds,
      sceneScale: context.sceneScale,
      shadowMapSize: context.quality.shadowMapSize
    });
  } else if (normalizeBoolean(job.output?.transparent, false) || context.theme.background?.type === "transparent") {
    scene.background = null;
    renderer.setClearColor(new THREE.Color("#000000"), 0);
  } else {
    backgroundTexture = colorTextureFromBackground(context.theme.background || {}, firstSize.width, firstSize.height);
    scene.background = backgroundTexture;
  }
  // PMREM generation is synchronous, but `ready` stays a promise so a failure
  // reaches the caller after it holds a viewport it can dispose.
  const ready = Promise.resolve().then(() => {
    const resource = context.sceneSettings.view.lighting.enabled
      ? createEnvironmentResource(renderer, studioConfiguration, { size: context.quality.environmentMapSize })
      : hasAuthoredMaterials(model.meshData) ? createInspectEnvironmentResource(THREE) : null;
    if (disposed) {
      disposeEnvironmentResource(resource);
      return null;
    }
    environmentResource = resource;
    scene.environment = resource?.texture || null;
    return resource;
  });
  if (!context.sceneSettings.view.lighting.enabled) applyLighting(
    scene,
    context.theme,
    model.bounds || context.bounds,
    context.sceneScale,
    context.quality.shadowMapSize
  );
  Object.assign(model.runtime, {
    Line2,
    LineGeometry,
    LineSegments2,
    LineSegmentsGeometry,
    LineMaterial
  });
  scene.add(model.root);
  // `floorBounds` is what a locked camera will frame, for a caller that knows
  // more than this pose does. The stage plane and grid are sized and centred on
  // whatever they are handed, and `model.bounds` is the pose the model happens
  // to be in right now — right for a still, which is posed before it gets here,
  // and wrong for a video, whose camera frames the union across its frames and
  // would otherwise show the grid's edge with the moving part walking off it.
  addFloor(
    scene,
    viewportOptions.floorBounds || model.bounds || context.bounds,
    { ...context.theme, floor: { enabled: false }, colorMode: context.sceneSettings.appearance },
    context.sceneScale,
    context.displaySettings.guides
  );
  const orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.001, 10000);
  const perspectiveCamera = new THREE.PerspectiveCamera(48, firstSize.width / Math.max(firstSize.height, 1), 0.1, 50000);
  const viewport = {
    THREE: _THREE || THREE,
    model,
    scene,
    renderer,
    orthographicCamera,
    perspectiveCamera,
    studioRuntime,
    studioConfiguration,
    context,
    sceneBuildStarted,
    ready,
    dispose() {
      if (disposed) return;
      disposed = true;
      model.dispose?.();
      scene.remove?.(model.root);
      if (studioRuntime) disposePhotographicStudio(studioRuntime);
      if (scene.environment === environmentResource?.texture) scene.environment = null;
      if (scene.background === environmentResource?.texture) scene.background = null;
      disposeEnvironmentResource(environmentResource);
      environmentResource = null;
      disposeSnapshotSceneResources(scene, model.root, [backgroundTexture]);
      backgroundTexture = null;
      renderer.dispose?.();
    }
  };
  const cleanDisposedResources = () => {
    if (disposed) {
      disposeSnapshotSceneResources(scene, model.root, [backgroundTexture]);
    }
  };
  // Observe both outcomes without creating a second unhandled rejection. The
  // original ready promise remains the caller's authoritative render failure.
  Promise.resolve(ready).then(cleanDisposedResources, cleanDisposedResources);
  return viewport;
}

function displayRecordPartIds(displayRecords = []) {
  return Array.from(new Set(
    toArray(displayRecords)
      .map((record) => String(record?.partId || "").trim())
      .filter((partId) => partId && partId !== "__model__")
  ));
}

function applyViewportExplodedView(viewport, bounds) {
  const { context, model, THREE: RuntimeTHREE } = viewport;
  const settings = context.displaySettings?.exploded;
  const THREEImpl = RuntimeTHREE || THREE;
  const resetExplodedView = () => {
    clearExplodedViewRecords(model.displayRecords);
    for (const record of model.displayRecords) {
      applyDisplayRecordTransform(THREEImpl, record);
    }
    model.root?.updateMatrixWorld?.(true);
  };
  if (settings?.enabled !== true) {
    resetExplodedView();
    return bounds;
  }
  const layout = computeExplodedViewLayout(model.displayRecords, bounds);
  if (!layout.entries.length) {
    resetExplodedView();
    return bounds;
  }
  const amount = clamp(Number(settings.amount ?? 1), 0, 1);
  applyExplodedViewProgress(THREEImpl, layout, amount);
  for (const record of model.displayRecords) {
    applyDisplayRecordTransform(THREEImpl, record);
  }
  model.root?.updateMatrixWorld?.(true);
  return explodedViewBounds(layout, bounds, amount);
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
    warnings,
    edgeSettings
  } = context;
  const modelBounds = viewport.model?.bounds || meshData.bounds || bounds;

  if (mode === "list") {
    return {
      ok: true,
      mode,
      parts: listRenderableParts(meshData),
      bounds: roundedBounds(modelBounds) || modelBounds,
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
            text: renderSectionSvg(segments, edgeSettings.color)
          };
        }
        return {
            path: String(output.path || ""),
            width,
            height,
            mimeType: "image/png",
            dataUrl: renderSectionPng(segments, width, height, theme, {
              edgeSettings,
              transparent: normalizeBoolean(job.output?.transparent, false),
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

  const stageTimings = captureOptions.stageTimings;
  const readyStarted = performance.now();
  await viewport.ready;
  if (stageTimings) {
    stageTimings.waitViewportMs = Math.round(performance.now() - readyStarted);
    stageTimings.outputs = [];
  }
  const sceneBuildMs = performance.now() - viewport.sceneBuildStarted;
  const padding = framePadding(job);
  const renderedOutputs = [];
  const renderStarted = performance.now();
  for (const output of outputs) {
    const outputTimings = stageTimings ? { path: String(output.path || "") } : null;
    let stageStarted = performance.now();
    const parameters = stepParametersForSnapshotOutput(output, job);
    const { width, height } = outputSize(output, job);
    viewport.renderer.setSize(width, height, false);
    // ONE update per output. `modelState` is a patch a caller needs applied in
    // the same pass -- a video's `callbacks.animation` for this frame -- because
    // applying it separately first means the clip evaluator and the effects pass
    // over every display record run twice for one image.
    const posedBounds = viewport.model.update({
      stepParameters: parameters,
      ...(captureOptions.modelState || null)
    }).bounds;
    // `frameBounds` locks what the camera frames on. A still frames the model
    // it just posed, which is right for one image and wrong for a sequence:
    // every frame of a video would re-fit to that frame's pose and the camera
    // would breathe as the model moves. A video passes the union across its
    // frames, computed once (headlessRenderEntry sequenceFrameBounds).
    const baseOutputBounds = captureOptions.frameBounds || posedBounds;
    const outputBounds = applyViewportExplodedView(viewport, baseOutputBounds);
    syncViewportTopologyDisplayEdges(viewport);
    // Device pixels: renderScale is the renderer's pixel ratio, so a
    // supersampled drawing buffer keeps `thickness` in drawing-buffer units
    // before the final PNG is resampled to this output's requested dimensions.
    const lineResolution = screenSpaceLineDeviceResolution(viewport.renderer, width, height);
    syncScreenSpaceLineMaterialResolution(
      viewport.model.runtime.screenSpaceLineMaterials,
      lineResolution.width,
      lineResolution.height
    );
    if (outputTimings) outputTimings.updateModelMs = Math.round(performance.now() - stageStarted);
    stageStarted = performance.now();
    const cameraSpec = resolveOutputCameraSpec(context, output.camera || null);
    const outputProjection = resolveOutputCameraProjection(context, cameraSpec);
    const usePerspectiveCamera = outputProjection === CAMERA_PROJECTION.PERSPECTIVE;
    const cameraView = usePerspectiveCamera ? null : resolveView(cameraSpec);
    const useTightFrame = !captureOptions.frameBounds && tightFrameEnabled(job);
    if (usePerspectiveCamera && useTightFrame) {
      viewport.scene.updateMatrixWorld(true);
    }
    const resolvedCamera = usePerspectiveCamera
      ? fitPerspectiveCamera(viewport.perspectiveCamera, cameraSpec, outputBounds, width, height, {
          framePoints: useTightFrame ? visibleGeometryWorldPoints(viewport.model.displayRecords) : null,
          padding,
          sceneScale
        })
      : fitCamera(viewport.orthographicCamera, cameraView, outputBounds, width, height, null, padding, sceneScale);
    const renderCamera = usePerspectiveCamera ? viewport.perspectiveCamera : viewport.orthographicCamera;
    // The tight frame is a per-POSE refinement: it re-fits to the vertices the
    // records project right now. Running it on every frame of a sequence is the
    // breathing `frameBounds` exists to stop, and there is no one pose to run it
    // against, so a locked frame keeps the bounds fit and skips it.
    if (!usePerspectiveCamera && useTightFrame) {
      viewport.scene.updateMatrixWorld(true);
      applyTightOrthographicFrame(renderCamera, viewport.model.displayRecords, width, height, padding, cameraView?.zoom);
    }
    if (outputTimings) outputTimings.frameCameraMs = Math.round(performance.now() - stageStarted);
    if (viewport.studioRuntime) {
      stageStarted = performance.now();
      applyPhotographicStudio(THREE, viewport.studioRuntime, viewport.studioConfiguration, {
        bounds: outputBounds,
        sceneScale,
        shadowMapSize: context.quality.shadowMapSize
      });
      fitCameraDepthToBounds(renderCamera, outputBounds, {
        displayRecords: viewport.model.displayRecords,
        modelGroup: viewport.model.runtime.modelGroup,
        groundZ: viewport.studioRuntime.photographicStudio?.ground?.position.z ?? null
      });
      if (outputTimings) outputTimings.prepareStudioMs = Math.round(performance.now() - stageStarted);
    }
    stageStarted = performance.now();
    viewport.renderer.render(viewport.scene, renderCamera);
    if (outputTimings) outputTimings.drawSubmitMs = Math.round(performance.now() - stageStarted);
    // WebGL submission can return before GPU completion. PNG readback may
    // wait for that work, so this is image readback/encoding, not pure CPU PNG.
    stageStarted = performance.now();
    const viewLabel = String(output.viewLabel || output.label || resolvedCamera.name || "").toUpperCase();
    const dataUrl = rendererDataUrlWithOptionalLabel(viewport.renderer, viewLabel, job, { width, height });
    if (outputTimings) {
      outputTimings.encodeImageMs = Math.round(performance.now() - stageStarted);
      stageTimings.outputs.push(outputTimings);
    }
    renderedOutputs.push({
      path: String(output.path || ""),
      camera: resolvedCamera.name,
      // Authoritative per-output echo from the canonical camera specification.
      projection: outputProjection,
      width,
      height,
      mimeType: "image/png",
      dataUrl
    });
  }
  const renderMs = performance.now() - renderStarted;
  return {
    ok: true,
    mode,
    // Echo the display and canonical camera state actually applied.
    displayMode: context.displayMode,
    projection: context.projection,
    quality: context.quality.id,
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
