import { buildTransformedSelectorRuntime } from "../lib/selectors/runtime.js";
import {
  shouldUseTopologyDisplayEdges
} from "./topologyDisplayEdges.js";

const transformedSelectorRuntimeCache = new WeakMap();
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

// Column-major 4x4 product a * b, as THREE's Matrix4.multiplyMatrices, without THREE.
function multiplyColumnMajor(a, b) {
  const out = new Array(16).fill(0);
  for (let row = 0; row < 4; row += 1) {
    for (let col = 0; col < 4; col += 1) {
      let sum = 0;
      for (let k = 0; k < 4; k += 1) sum += a[k * 4 + row] * b[col * 4 + k];
      out[col * 4 + row] = sum;
    }
  }
  return { elements: out };
}

// `includeExplode` composes each part's exploded-view offset over its effect, in the order
// the mesh does (composeDisplayRecordObjectMatrix): explode after effect.
export function selectorTransformsFromDisplayRecords(displayRecords, { includeExplode = false } = {}) {
  const transforms = new Map();
  for (const record of Array.isArray(displayRecords) ? displayRecords : []) {
    const partId = String(record?.partId || "").trim();
    const effect = record?.effectMatrix && matrixHasTransform(record.effectMatrix) ? record.effectMatrix : null;
    const explode = includeExplode && record?.explodedViewMatrix && matrixHasTransform(record.explodedViewMatrix)
      ? record.explodedViewMatrix
      : null;
    if (!partId || (!effect && !explode)) {
      continue;
    }
    const matrix = explode && effect ? multiplyColumnMajor(explode.elements, effect.elements) : explode || effect;
    const transform = rowMajorArrayFromMatrix4(matrix);
    if (transform) {
      transforms.set(partId, transform);
    }
  }
  return transforms;
}

function runtimeUsesSurfaceOwnedEdges(runtime) {
  return Boolean(runtime?.surfaceEdgeRendering);
}

const explodedPickRuntimeCache = new WeakMap();

/**
 * The selector runtime to PICK against while parts are exploded: its proxies moved to where
 * the parts are drawn. Picking reads only this; highlights keep the runtime at rest and add
 * the explode offset themselves (useStepHighlights). Null when nothing is exploded.
 */
export function explodedPickSelectorRuntime(baseSelectorRuntime, displayRecords) {
  const records = Array.isArray(displayRecords) ? displayRecords : [];
  if (!baseSelectorRuntime || !records.some((record) => record?.explodedViewMatrix && matrixHasTransform(record.explodedViewMatrix))) {
    return null;
  }
  const transforms = selectorTransformsFromDisplayRecords(records, { includeExplode: true });
  return transforms.size
    ? cachedTransformedRuntime(explodedPickRuntimeCache, baseSelectorRuntime, transforms, buildTransformedSelectorRuntime)
    : null;
}

export function resolveTopologyDisplayEdgeRuntimes({
  selectorRuntime = null,
  displayRecords = null
} = {}) {
  const selectorTransforms = selectorTransformsFromDisplayRecords(displayRecords);
  const transformedSelectorRuntime = selectorTransforms.size && selectorRuntime
    ? cachedTransformedRuntime(
        transformedSelectorRuntimeCache,
        selectorRuntime,
        selectorTransforms,
        buildTransformedSelectorRuntime
      )
    : null;
  return {
    selectorTransforms,
    transformCount: selectorTransforms.size,
    transformedSelectorRuntime,
    // What the topology line draws and picking reads: the runtime as the records place it.
    selectorRuntime: transformedSelectorRuntime || selectorRuntime || null
  };
}

export function shouldRenderTopologyDisplayEdges({
  edgesVisible = false,
  wireframeMode = false,
  cadEdgeSource = false,
  selectorRuntime = null,
  edgeSettings = null
} = {}) {
  return Boolean(
    edgesVisible &&
    !wireframeMode &&
    cadEdgeSource &&
    !runtimeUsesSurfaceOwnedEdges(selectorRuntime) &&
    shouldUseTopologyDisplayEdges(selectorRuntime, edgeSettings)
  );
}
