// Camera-only LOD exclusion. This never changes display visibility or ownership.
// Dynamic scenes deliberately keep the conservative all-occurrence policy until
// pose changes have their own scheduler resampling boundary.
import { lodSampleNumberEqual } from "./lodSamplePrecision.js";

const cameraIntents = new WeakMap();

function stableCameraKey(camera, values) {
  const previous = cameraIntents.get(camera);
  if (previous?.values.length === values.length
    && values.every((value, index) => lodSampleNumberEqual(value, previous.values[index]))) return previous.key;
  const key = JSON.stringify(values);
  cameraIntents.set(camera, { values, key });
  return key;
}

export function lodSceneMayMove({ kinematics = null,
  kinematicsLoading = false, animation = null, exploded = false } = {}) {
  return Boolean(kinematics || kinematicsLoading || animation || exploded);
}

export function resampleLodAfterViewportResize(runtime, { syncFraming, syncZoom, emitPerspective, resample }) {
  if (syncFraming(runtime)) {
    syncZoom(runtime);
    emitPerspective(runtime);
  }
  // Aspect/viewport changes can expose a part without changing persisted
  // position/target/zoom, so perspective deduplication cannot own this signal.
  resample?.();
}

function validBounds(bounds) {
  return bounds?.min?.length === 3 && bounds?.max?.length === 3
    && bounds.min.every(Number.isFinite) && bounds.max.every(Number.isFinite)
    && bounds.min.every((value, axis) => value <= bounds.max[axis]);
}

function recordMayMove(record) {
  return Boolean(record?.effectMatrix || record?.explodedViewMatrix || record?.effectDeformation
    || record?.tubeDeformationState?.active || record?.tubeGpuState?.active);
}

function invalidMatrix(matrix) {
  return matrix && (!matrix.isMatrix4 || !matrix.elements.every(Number.isFinite));
}

function verticalViewScale(camera) {
  const view = camera?.view;
  if (!view?.enabled) return 1;
  const fullHeight = Number(view.fullHeight), height = Number(view.height);
  return fullHeight > 0 && height > 0 ? height / fullHeight : 1;
}

function perspectiveFovYDeg(camera) {
  const fovY = Number(camera?.fov) * Math.PI / 180;
  const zoom = Number(camera?.zoom);
  const effectiveZoom = Number.isFinite(zoom) && zoom > 0 ? zoom : 1;
  return 2 * Math.atan(Math.tan(fovY / 2) * verticalViewScale(camera) / effectiveZoom) * 180 / Math.PI;
}

function selectedPartId(partId, selected) {
  if (!selected.size) return false;
  if (selected.has("__model__")) return true;
  const normalized = String(partId || "").trim().replace(/^#\s*/, "");
  if (!normalized) return false;
  for (const candidate of selected) {
    const value = String(candidate || "").trim().replace(/^#\s*/, "");
    if (value && (normalized === value || normalized.startsWith(`${value}.`))) return true;
  }
  return false;
}

export function sampleLodCamera(THREE, runtime, { components = new Map(), dynamicScene = false,
  selectedPartIds = [] } = {}) {
  const camera = runtime?.camera, canvas = runtime?.renderer?.domElement;
  if (!camera || !canvas) return null;
  const records = runtime.displayRecords || [];
  const failOpen = dynamicScene || records.some(recordMayMove);
  const group = runtime.modelGroup;
  group?.updateWorldMatrix?.(true, false);
  camera.updateWorldMatrix?.(true, false);
  const projection = new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
  const frustum = new THREE.Frustum().setFromProjectionMatrix(projection, camera.coordinateSystem, camera.reversedDepth);
  const cameraPosition = new THREE.Vector3().setFromMatrixPosition(camera.matrixWorld);
  const box = new THREE.Box3(), point = new THREE.Vector3(), matrix = new THREE.Matrix4();
  const selected = new Set((Array.isArray(selectedPartIds) ? selectedPartIds : [selectedPartIds])
    .map(value => String(value || "").trim()).filter(Boolean));
  const byCid = new Map(), distances = new Map(), visibility = new Map(), selectedComponents = new Map();
  const telemetry = { components: components.size, occurrences: 0, visibleOccurrences: 0,
    excludedOccurrences: 0, fallbackOccurrences: 0, visibleComponents: 0,
    excludedComponents: 0, fallbackComponents: 0, selectedComponents: 0,
    pendingOccurrences: 0, dynamicFailOpen: Number(failOpen) };
  for (const record of records) {
    const cid = record?.sourcePart?.componentId;
    if (!components.has(cid)) continue;
    let state = byCid.get(cid);
    if (!state) { state = { count: 0, nearest: Infinity, nearestAll: Infinity, fallback: false, selected: false }; byCid.set(cid, state); }
    state.count++; telemetry.occurrences++;
    if (selectedPartId(record?.partId, selected)) state.selected = true;
    // partBounds already contains the occurrence's base transform. Reapplying
    // that transform would move it twice. Post-pose and floor/group transforms
    // are applied in the same order as the displayed mesh.
    if (!validBounds(record.partBounds) || invalidMatrix(record.effectMatrix)
      || invalidMatrix(record.explodedViewMatrix) || invalidMatrix(group?.matrixWorld)) {
      state.fallback = true; telemetry.fallbackOccurrences++; continue;
    }
    matrix.identity();
    if (record.effectMatrix) matrix.premultiply(record.effectMatrix);
    if (record.explodedViewMatrix) matrix.premultiply(record.explodedViewMatrix);
    if (group) matrix.premultiply(group.matrixWorld);
    if (!matrix.elements.every(Number.isFinite)) {
      state.fallback = true; telemetry.fallbackOccurrences++; continue;
    }
    box.min.fromArray(record.partBounds.min); box.max.fromArray(record.partBounds.max);
    box.applyMatrix4(matrix);
    box.getCenter(point);
    const distance = cameraPosition.distanceTo(point);
    state.nearestAll = Math.min(state.nearestAll, distance);
    // The full AABB, including near/far crossings, is conservative under
    // rotations, mirrors and nonuniform scale. A center-only test is unsafe.
    const visible = failOpen || frustum.intersectsBox(box);
    if (visible) {
      telemetry.visibleOccurrences++;
      state.nearest = Math.min(state.nearest, distance);
    } else telemetry.excludedOccurrences++;
  }
  for (const [cid, component] of components) {
    const state = byCid.get(cid);
    const pending = !state || state.count !== component.centers?.length;
    if (pending || state.fallback) {
      telemetry.pendingOccurrences += Math.max(0, (component.centers?.length || 0) - (state?.count || 0));
      // The summary can arrive before React adopts its occurrences. Never
      // exclude missing/new records using a partially adopted scene.
      let nearest = state?.nearest ?? Infinity;
      for (const center of component.centers || []) {
        if (center?.length !== 3 || !center.every(Number.isFinite)) continue;
        point.fromArray(center);
        if (group) point.applyMatrix4(group.matrixWorld);
        nearest = Math.min(nearest, cameraPosition.distanceTo(point));
      }
      distances.set(cid, Number.isFinite(nearest) ? nearest : 0);
      visibility.set(cid, true);
      telemetry.fallbackComponents++;
    } else {
      const visible = Number.isFinite(state.nearest);
      distances.set(cid, visible ? state.nearest : state.nearestAll);
      visibility.set(cid, visible);
      if (visible) telemetry.visibleComponents++;
      else telemetry.excludedComponents++;
    }
    selectedComponents.set(cid, state?.selected === true);
    if (state?.selected) telemetry.selectedComponents++;
  }
  const viewportWidthPx = canvas.clientWidth || canvas.width || 0;
  const viewportHeightPx = canvas.clientHeight || canvas.height || 0;
  const projectionIntent = camera.isOrthographicCamera
    ? [0, camera.left, camera.right, camera.top, camera.bottom, camera.zoom]
    : [1, camera.fov, camera.aspect, camera.zoom, camera.filmGauge, camera.filmOffset];
  const view = camera.view;
  const viewIntent = view?.enabled
    ? [1, view.fullWidth, view.fullHeight, view.offsetX, view.offsetY, view.width, view.height] : [0];
  return {
    // Retry identity includes only the actual camera and viewport. A changed
    // tessellated bound or model-group placement may resample distances, but
    // must not erase a pressure ceiling and restart accepted L3/L2 oscillation.
    // Clip near/far come from mesh bounds. Use projection intent fields rather
    // than matrix coefficients: rebuilding a perspective matrix with another
    // near distance can even round its x/y coefficients differently.
    cameraKey: stableCameraKey(camera, [...camera.matrixWorld.elements, ...projectionIntent, ...viewIntent,
      viewportWidthPx, viewportHeightPx]),
    camera: camera.isOrthographicCamera
      ? { kind: "orthographic", visibleWorldHeight: (camera.top - camera.bottom) * verticalViewScale(camera) / (camera.zoom || 1) }
      : { kind: "perspective", fovYDeg: perspectiveFovYDeg(camera) },
    viewportWidthPx,
    viewportHeightPx,
    distanceFor: cid => distances.get(cid) ?? NaN,
    visibleFor: cid => visibility.get(cid) !== false,
    selectedFor: cid => selectedComponents.get(cid) === true,
    visibility: telemetry,
  };
}
