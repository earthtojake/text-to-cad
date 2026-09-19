import {
  buildTransformedDisplayEdgeRuntime,
  buildTransformedSelectorRuntime
} from "../lib/selectors/runtime.js";
import {
  shouldUseTopologyDisplayEdges
} from "./topologyDisplayEdges.js";

const displayEdgeVisibilityClassRuntimeCache = new WeakMap();
const transformedSelectorRuntimeCache = new WeakMap();
const transformedDisplayEdgeRuntimeCache = new WeakMap();
const MAX_TRANSFORMED_RUNTIME_CACHE_ENTRIES = 32;

export function topologyDisplayEdgeSurfaceOffsetForSettings(edgeSettings = {}) {
  return 0;
}

export function applyTopologyDisplayEdgeSurfaceOffset(records, edgeSettings = {}) {
  // Topology display edges must depth-test against the true solid surface.
  // Pushing the whole mesh away makes close-but-hidden edges bleed through at distance.
  for (const record of Array.isArray(records) ? records : []) {
    const material = record?.material;
    if (!material) {
      continue;
    }
    material.polygonOffset = false;
    material.polygonOffsetFactor = 0;
    material.polygonOffsetUnits = 0;
    material.needsUpdate = true;
  }
}

export function disposeTopologyDisplayEdgeObject(object) {
  if (!object) {
    return;
  }
  while (object.children?.length) {
    disposeTopologyDisplayEdgeObject(object.children[0]);
  }
  object.parent?.remove?.(object);
  if (typeof object.userData?.beforeDispose === "function") {
    object.userData.beforeDispose(object);
    delete object.userData.beforeDispose;
  }
  if (object.userData?.disposeGeometry !== false) {
    object.geometry?.dispose?.();
  }
  if (object.userData?.disposeMaterial !== false) {
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of materials) {
      material?.dispose?.();
    }
  }
}

export function matrixHasTransform(matrix, epsilon = 1e-6) {
  if (!matrix?.elements || matrix.elements.length !== 16) {
    return false;
  }
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  return matrix.elements.some((value, index) => Math.abs(Number(value) - identity[index]) > epsilon);
}

export function rowMajorArrayFromMatrix4(matrix) {
  if (!matrix?.elements || matrix.elements.length !== 16) {
    return null;
  }
  const elements = matrix.elements;
  return [
    elements[0], elements[4], elements[8], elements[12],
    elements[1], elements[5], elements[9], elements[13],
    elements[2], elements[6], elements[10], elements[14],
    elements[3], elements[7], elements[11], elements[15],
  ];
}

function transformSignatureValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? String(number) : "0";
}

function transformEntriesSignature(transforms) {
  if (!transforms?.size) {
    return "";
  }
  return [...transforms.entries()]
    .map(([partId, transform]) => {
      const transformValues = Array.isArray(transform) || ArrayBuffer.isView(transform)
        ? Array.from(transform, transformSignatureValue)
        : [];
      return `${String(partId || "").trim()}:${transformValues.join(",")}`;
    })
    .sort()
    .join("|");
}

function cachedTransformedRuntime(cache, baseRuntime, transforms, buildRuntime) {
  if (!baseRuntime || !transforms?.size) {
    return null;
  }
  const signature = transformEntriesSignature(transforms);
  if (!signature) {
    return null;
  }
  let runtimeBySignature = cache.get(baseRuntime);
  if (!runtimeBySignature) {
    runtimeBySignature = new Map();
    cache.set(baseRuntime, runtimeBySignature);
  }
  if (runtimeBySignature.has(signature)) {
    return runtimeBySignature.get(signature);
  }
  const runtime = buildRuntime(baseRuntime, transforms);
  runtimeBySignature.set(signature, runtime);
  if (runtimeBySignature.size > MAX_TRANSFORMED_RUNTIME_CACHE_ENTRIES) {
    runtimeBySignature.delete(runtimeBySignature.keys().next().value);
  }
  return runtime;
}

export function selectorTransformsFromDisplayRecords(displayRecords) {
  const transforms = new Map();
  for (const record of Array.isArray(displayRecords) ? displayRecords : []) {
    const partId = String(record?.partId || "").trim();
    if (!partId || !record?.effectMatrix || !matrixHasTransform(record.effectMatrix)) {
      continue;
    }
    const transform = rowMajorArrayFromMatrix4(record.effectMatrix);
    if (transform) {
      transforms.set(partId, transform);
    }
  }
  return transforms;
}

function runtimeHasVisibilityClassRows(runtime) {
  return Array.isArray(runtime?.edges) &&
    runtime.edges.some((row) => String(row?.visibilityClass || "").trim());
}

function displayEdgeRowsCanUseSelectorClasses(displayEdgeRuntime, selectorRuntime) {
  const displayRows = Array.isArray(displayEdgeRuntime?.edges) ? displayEdgeRuntime.edges : [];
  const selectorRows = Array.isArray(selectorRuntime?.edges) ? selectorRuntime.edges : [];
  const alignedRows = displayRows.every((row, rowIndex) => {
    const selectorRow = selectorRows[rowIndex] || {};
    const displayStart = Number(row?.segmentStart);
    const selectorStart = Number(selectorRow?.segmentStart);
    const displayCount = Number(row?.segmentCount);
    const selectorCount = Number(selectorRow?.segmentCount);
    return (
      (!Number.isFinite(displayStart) || !Number.isFinite(selectorStart) || displayStart === selectorStart) &&
      (!Number.isFinite(displayCount) || !Number.isFinite(selectorCount) || displayCount === selectorCount)
    );
  });
  return Boolean(
    displayRows.length &&
    displayRows.length === selectorRows.length &&
    alignedRows &&
    !runtimeHasVisibilityClassRows(displayEdgeRuntime) &&
    runtimeHasVisibilityClassRows(selectorRuntime)
  );
}

function runtimeUsesSurfaceOwnedEdges(runtime) {
  return Boolean(runtime?.surfaceEdgeRendering);
}

export function displayEdgeRuntimeWithSelectorVisibilityClasses(displayEdgeRuntime, selectorRuntime) {
  if (!displayEdgeRowsCanUseSelectorClasses(displayEdgeRuntime, selectorRuntime)) {
    return displayEdgeRuntime || null;
  }
  const cached = displayEdgeVisibilityClassRuntimeCache.get(displayEdgeRuntime);
  if (cached?.selectorRuntime === selectorRuntime) {
    return cached.runtime;
  }
  const runtime = {
    ...displayEdgeRuntime,
    edges: displayEdgeRuntime.edges.map((row, rowIndex) => ({
      ...row,
      visibilityClass: selectorRuntime.edges[rowIndex]?.visibilityClass || "feature"
    }))
  };
  displayEdgeVisibilityClassRuntimeCache.set(displayEdgeRuntime, { selectorRuntime, runtime });
  return runtime;
}

export function resolveTopologyDisplayEdgeRuntimes({
  selectorRuntime = null,
  displayEdgeRuntime = null,
  displayRecords = null,
  transformDisplayEdges = true
} = {}) {
  const selectorTransforms = selectorTransformsFromDisplayRecords(displayRecords);
  const baseDisplayEdgeRuntime = displayEdgeRuntimeWithSelectorVisibilityClasses(displayEdgeRuntime, selectorRuntime);
  const transformedSelectorRuntime = selectorTransforms.size && selectorRuntime
    ? cachedTransformedRuntime(
        transformedSelectorRuntimeCache,
        selectorRuntime,
        selectorTransforms,
        buildTransformedSelectorRuntime
      )
    : null;
  const transformedDisplayEdgeRuntime = transformDisplayEdges && selectorTransforms.size && baseDisplayEdgeRuntime
    ? cachedTransformedRuntime(
        transformedDisplayEdgeRuntimeCache,
        baseDisplayEdgeRuntime,
        selectorTransforms,
        buildTransformedDisplayEdgeRuntime
      )
    : null;
  const activeSelectorRuntime = transformedSelectorRuntime || selectorRuntime || null;
  const activeDisplayEdgeRuntime = transformedDisplayEdgeRuntime || baseDisplayEdgeRuntime || null;
  return {
    selectorTransforms,
    transformCount: selectorTransforms.size,
    transformedSelectorRuntime,
    transformedDisplayEdgeRuntime,
    selectorRuntime: activeSelectorRuntime,
    displayEdgeRuntime: activeDisplayEdgeRuntime,
    topologyRuntime: activeDisplayEdgeRuntime || activeSelectorRuntime
  };
}

export function shouldRenderTopologyDisplayEdges({
  edgesVisible = false,
  wireframeMode = false,
  cadEdgeSource = false,
  displayEdgeRuntime = null,
  selectorRuntime = null,
  edgeSettings = null
} = {}) {
  return Boolean(
    edgesVisible &&
    !wireframeMode &&
    cadEdgeSource &&
    !runtimeUsesSurfaceOwnedEdges(displayEdgeRuntime || selectorRuntime) &&
    shouldUseTopologyDisplayEdges(displayEdgeRuntime || selectorRuntime, edgeSettings)
  );
}

export function shouldUseRecordTopologyEdgeTransforms({
  transformDetected = false,
  topologyDisplayEdgesVisible = false,
  displayEdgeRuntime = null,
  displayRecords = []
} = {}) {
  return Boolean(
    transformDetected &&
    topologyDisplayEdgesVisible &&
    displayEdgeRuntime &&
    Array.isArray(displayRecords) &&
    displayRecords.length > 1
  );
}
