// Progressive publish of a component package (design/viewer-memory.md §6,
// lever C), split out of useCadAssets so it unit-tests in Node (the hook's
// other imports are Vite-resolved; same pattern as packageReferenceComposition.js).
//
// The hook used to fetch every component, compose once and publish once, so a
// 866-component model painted nothing until the last component landed and a
// cancel mid-way freed nothing it had not yet published. This module loads the
// components with bounded concurrency and, as they arrive, re-composes the ones
// loaded so far through the SAME reference-based composition a viewport-LOD
// level swap uses (buildComposedPackageMeshData shares component buffers, it
// copies nothing), publishing each batch. The last publish is the full model.
import { buildComposedPackageMeshData } from "cadgen-js/lib/assembly/meshData.js";
import { estimateMeshRenderCost } from "cadgen-js/lib/render/meshCost.js";

// A batch publishes as soon as EITHER ceiling is crossed by the components
// that arrived since the previous publish — whichever comes first.
//
// Component ceiling: never more than this many unpublished components. Bounds
// the wait for the first paint on models of many small parts (fasteners), where
// the byte budget alone would hold hundreds of them back. ~866/32 ≈ 27
// recompositions for the tendon hand; each is a reference-based walk of the
// occurrence list (see the timing test), not a geometry copy.
export const PROGRESSIVE_PUBLISH_MAX_COMPONENTS = 32;
// Byte ceiling on the mesh typed arrays (estimateMeshRenderCost) held back
// since the previous publish. Large components upload their GPU buffers as
// soon as they are published instead of piling up unpainted on the main thread;
// 64 MB is roughly the cost of a scene rebuild the viewer already absorbs on a
// LOD swap, so a publish this size does not stall interaction noticeably.
export const PROGRESSIVE_PUBLISH_MAX_BYTES = 64 * 1024 * 1024;

// Load-time admission (the peak that killed the tab): a component decodes in a
// surf worker whose intermediates count against the renderer process, and a
// hand component reaches ~90 MB of meshData. A count cap alone (8 wide) admits
// 8 of those at once. Admission is therefore ALSO byte-aware: the estimated
// decoded bytes of everything in flight stay under this budget (a single
// component larger than the budget runs alone).
export const PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES = 256 * 1024 * 1024;
// Estimated decoded size of a component before anything is known about the
// model — a quarter of the budget, so at most four unmeasured components are
// in flight until the first decode calibrates the estimate (below).
export const PROGRESSIVE_LOAD_UNMEASURED_SHARE = 4;

// Decoded-bytes estimator. A .surf is an exact surface and tessellation expands
// it many-fold, so its fetched byte length (the HEAD content-length the hook
// supplies as a hint) is scaled by the decoded/fetched ratio measured on the
// components already decoded; without a hint, the running mean decoded size;
// before any decode, the unmeasured share of the budget.
export function createDecodeSizeEstimator({ maxInFlightBytes = PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES } = {}) {
  let ratioSum = 0;
  let ratioCount = 0;
  let decodedSum = 0;
  let decodedCount = 0;
  return {
    estimate(hintBytes) {
      const hint = Number(hintBytes);
      if (Number.isFinite(hint) && hint > 0 && ratioCount > 0) {
        return hint * (ratioSum / ratioCount);
      }
      if (decodedCount > 0) {
        return decodedSum / decodedCount;
      }
      return maxInFlightBytes / PROGRESSIVE_LOAD_UNMEASURED_SHARE;
    },
    observe(hintBytes, decodedBytes) {
      const decoded = Number(decodedBytes) || 0;
      decodedSum += decoded;
      decodedCount += 1;
      const hint = Number(hintBytes);
      if (Number.isFinite(hint) && hint > 0) {
        ratioSum += decoded / hint;
        ratioCount += 1;
      }
    }
  };
}

export function progressiveLoadStage(loaded, total) {
  return `loading components ${loaded}/${total}`;
}

// Whether a published mesh state is the COMPLETE model: the final publish
// (assemblyInteractionReady true, every component composed). The render module
// attaches on the first publish and stays live across publishes; what waits for
// the complete state is the clip VALIDATION (validateRenderModuleClips), which
// reports every label the composition lacks — noise against a partial one.
export function meshStateIsComplete(meshState) {
  if (!meshState?.meshData) {
    return false;
  }
  if (meshState.assemblyInteractionReady === false) {
    return false;
  }
  const missing = meshState.meshData.missingComponentIds;
  return !(Array.isArray(missing) && missing.length > 0);
}

// A clip's model handle for a PARTIAL composition. The runtime's m.get() throws
// on a label no part carries (a typo must never silently animate nothing) —
// right for the complete model, wrong while occurrences are still arriving.
// While partial, an absent label resolves to a chainable no-op handle so the
// clip keeps driving the occurrences that ARE present; on the next publish that
// carries the occurrence, the same lookup binds to it. The complete model uses
// the strict clip again, so validation still catches real typos.
const NOOP_ANIMATION_HANDLE = Object.freeze({
  deformTube() { return this; },
  rotate() { return this; },
  translate() { return this; },
  opacity() { return this; },
  visible() { return this; }
});

export function partialAnimationModel(model) {
  return {
    ...model,
    get(target) {
      try {
        return model.get(target);
      } catch {
        return NOOP_ANIMATION_HANDLE;
      }
    }
  };
}

export function tolerantAnimationClip(clip) {
  if (!clip || typeof clip.update !== "function") {
    return clip;
  }
  return { ...clip, update: (t, model) => clip.update(t, partialAnimationModel(model)) };
}

// Readable memory accounting for the headless harness (design/viewer-memory.md
// §7), following the window.__cadModelPlacement / __CAD_VIEWER_LOD__ precedent:
// written on EVERY progressive publish, nulled on cancel, never React state.
// Harmless without a window (Node tests).
export function meshCostAccounting({ meshData, componentMeshDataByCid, loaded, total, publishCount, final }) {
  let componentTotalBytes = 0;
  let componentTotalTriangles = 0;
  const components = Object.values(componentMeshDataByCid || {});
  for (const component of components) {
    const cost = estimateMeshRenderCost(component);
    componentTotalBytes += cost.typedArrayBytes;
    componentTotalTriangles += cost.triangleCount;
  }
  return {
    composed: estimateMeshRenderCost(meshData),
    componentTotalBytes,
    componentTotalTriangles,
    componentCount: components.length,
    totalComponents: total,
    loadedComponents: loaded,
    publishCount,
    final: !!final,
    at: typeof performance !== "undefined" ? performance.now() : Date.now()
  };
}

export function publishMeshCostAccounting(publish) {
  if (typeof window === "undefined") {
    return null;
  }
  window.__cadMeshCost = publish ? meshCostAccounting(publish) : null;
  return window.__cadMeshCost;
}

function abortError() {
  if (typeof DOMException === "function") {
    return new DOMException("The operation was aborted.", "AbortError");
  }
  const error = new Error("The operation was aborted.");
  error.name = "AbortError";
  return error;
}

export function progressivePublishDue(
  { pendingComponents, pendingBytes },
  { maxComponents = PROGRESSIVE_PUBLISH_MAX_COMPONENTS, maxBytes = PROGRESSIVE_PUBLISH_MAX_BYTES } = {}
) {
  return pendingComponents >= maxComponents || pendingBytes >= maxBytes;
}

function occurrenceTranslation(transform) {
  // Row-major 4x4 (or 3x4): translation is the last column.
  if (Array.isArray(transform) && transform.length >= 12) {
    return [Number(transform[3]) || 0, Number(transform[7]) || 0, Number(transform[11]) || 0];
  }
  return [0, 0, 0];
}

// Load order: the components placed at the model's extreme positions (per-axis
// min and max occurrence translation, up to six cids) come first, then the rest
// in descriptor order. The viewer frames the camera ONCE per model, on the
// first publish (CadViewer's framedModelKeyRef gate), so the first batch must
// span the model: without this the first 32 components of a hand could all be
// one fingertip and the rest of the model would arrive outside the frame. The
// descriptor carries no component bounds, so the placement is the proxy.
export function orderComponentsForProgressiveLoad(descriptor) {
  const entries = Object.entries(descriptor?.components || {});
  const occurrences = Array.isArray(descriptor?.occurrences) ? descriptor.occurrences : [];
  const extremes = [
    { axis: 0, sign: -1, value: Infinity, cid: "" },
    { axis: 0, sign: 1, value: -Infinity, cid: "" },
    { axis: 1, sign: -1, value: Infinity, cid: "" },
    { axis: 1, sign: 1, value: -Infinity, cid: "" },
    { axis: 2, sign: -1, value: Infinity, cid: "" },
    { axis: 2, sign: 1, value: -Infinity, cid: "" }
  ];
  for (const occurrence of occurrences) {
    const cid = String(occurrence?.component || "").trim();
    if (!cid) {
      continue;
    }
    const translation = occurrenceTranslation(occurrence?.transform);
    for (const extreme of extremes) {
      const value = translation[extreme.axis];
      if (extreme.sign < 0 ? value < extreme.value : value > extreme.value) {
        extreme.value = value;
        extreme.cid = cid;
      }
    }
  }
  const byCid = new Map(entries);
  const firstCids = [...new Set(extremes.map((extreme) => extreme.cid).filter((cid) => byCid.has(cid)))];
  return [
    ...firstCids.map((cid) => [cid, byCid.get(cid)]),
    ...entries.filter(([cid]) => !firstCids.includes(cid))
  ];
}

/**
 * createProgressivePackageLoader({
 *   descriptor,                        // the assembly.json package descriptor
 *   loadComponent(cid, component),     // -> Promise<meshData> (loadRenderSurf)
 *   concurrency,
 *   isCurrent(),                       // false once the request is superseded or aborted
 *   sizeHint?(cid, component),         // -> Promise<fetched byte length | null> before admission
 *   maxInFlightBytes?,                 // estimated decoded bytes in flight (PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES)
 *   swappedComponents?(),              // the live LOD working set (cid -> meshData) or null
 *   onPublish({ meshData, componentMeshDataByCid, loaded, total, final, composeMs, publishCount }),
 *   maxComponents?, maxBytes?
 * }).run() -> Promise<{ loaded, total, publishes }>
 *
 * Admission is count- AND byte-capped: a component starts decoding only when
 * fewer than `concurrency` are in flight and the estimated decoded bytes in
 * flight (createDecodeSizeEstimator over the sizeHint) fit `maxInFlightBytes`,
 * or nothing else is in flight. Every publish re-checks isCurrent() first; a superseded or aborted load
 * publishes nothing further, drops its references to every component it
 * loaded (retainedComponentCount() -> 0) and rejects with an AbortError.
 * Composition is `{ ...loadedSoFar, ...swappedComponents() }`, so a viewport
 * LOD swap that lands mid-load is kept by the next batch rather than reverted
 * to level 0. The final publish (`final: true`) carries every component and is
 * the same composition the single post-load publish produced.
 */
export function createProgressivePackageLoader({
  descriptor,
  loadComponent,
  concurrency = 8,
  isCurrent = () => true,
  sizeHint = null,
  maxInFlightBytes = PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
  swappedComponents = () => null,
  onPublish,
  maxComponents = PROGRESSIVE_PUBLISH_MAX_COMPONENTS,
  maxBytes = PROGRESSIVE_PUBLISH_MAX_BYTES
}) {
  const componentEntries = orderComponentsForProgressiveLoad(descriptor);
  const total = componentEntries.length;
  const loadedByCid = {};
  let loaded = 0;
  let pendingComponents = 0;
  let pendingBytes = 0;
  let publishes = 0;
  let publishedFinal = false;

  function release() {
    for (const cid of Object.keys(loadedByCid)) {
      delete loadedByCid[cid];
    }
  }

  function stop() {
    release();
    throw abortError();
  }

  function publish(final) {
    if (!isCurrent()) {
      stop();
    }
    const swapped = swappedComponents?.();
    const componentMeshDataByCid = swapped && typeof swapped === "object"
      ? { ...loadedByCid, ...swapped }
      : { ...loadedByCid };
    const startedAt = typeof performance !== "undefined" ? performance.now() : Date.now();
    const meshData = buildComposedPackageMeshData(descriptor, componentMeshDataByCid);
    const composeMs = (typeof performance !== "undefined" ? performance.now() : Date.now()) - startedAt;
    pendingComponents = 0;
    pendingBytes = 0;
    publishes += 1;
    publishedFinal = publishedFinal || final;
    onPublish?.({ meshData, componentMeshDataByCid, loaded, total, final, composeMs, publishCount: publishes });
  }

  const estimator = createDecodeSizeEstimator({ maxInFlightBytes });
  let inFlight = 0;
  let inFlightBytes = 0;
  let cancelled = false;
  let waiters = [];
  let peakInFlight = 0;

  function wakeWaiters() {
    const pending = waiters;
    waiters = [];
    for (const wake of pending) {
      wake();
    }
  }

  function canAdmit(estimate) {
    return inFlight < concurrency && (inFlight === 0 || inFlightBytes + estimate <= maxInFlightBytes);
  }

  // Re-estimates on every wake: a decode finishing while this one waited has
  // calibrated the estimator, and the size it should be admitted at is the
  // current one, not the one it computed before waiting.
  async function admit(hint) {
    let estimate = estimator.estimate(hint);
    while (!canAdmit(estimate)) {
      if (cancelled) {
        throw abortError();
      }
      await new Promise((resolve) => waiters.push(resolve));
      estimate = estimator.estimate(hint);
    }
    inFlight += 1;
    inFlightBytes += estimate;
    peakInFlight = Math.max(peakInFlight, inFlight);
    return estimate;
  }

  function releaseSlot(estimate) {
    inFlight -= 1;
    inFlightBytes -= estimate;
    wakeWaiters();
  }

  async function loadOne([cid, component]) {
    if (!isCurrent()) {
      stop();
    }
    let hint = null;
    if (typeof sizeHint === "function") {
      try {
        hint = await sizeHint(cid, component);
      } catch {
        hint = null;
      }
    }
    if (!isCurrent()) {
      stop();
    }
    const estimate = await admit(hint);
    let meshData;
    try {
      if (!isCurrent()) {
        stop();
      }
      meshData = await loadComponent(cid, component);
    } finally {
      releaseSlot(estimate);
    }
    if (!isCurrent()) {
      stop();
    }
    const decodedBytes = estimateMeshRenderCost(meshData).typedArrayBytes;
    estimator.observe(hint, decodedBytes);
    loadedByCid[cid] = meshData;
    loaded += 1;
    pendingComponents += 1;
    pendingBytes += decodedBytes;
    const final = loaded === total;
    if (final || progressivePublishDue({ pendingComponents, pendingBytes }, { maxComponents, maxBytes })) {
      publish(final);
    }
  }

  async function run() {
    const queue = componentEntries.slice();
    const workerCount = Math.max(1, Math.min(queue.length || 1, Math.floor(Number(concurrency) || 1)));
    try {
      await Promise.all(Array.from({ length: workerCount }, async () => {
        while (queue.length) {
          await loadOne(queue.shift());
        }
      }));
      if (!isCurrent()) {
        stop();
      }
      if (!publishedFinal) {
        // No components at all: compose anyway so the descriptor's own error
        // ("matched no renderable component GLBs") surfaces exactly as before.
        publish(true);
      }
    } catch (error) {
      // An aborted fetch rejects out of loadComponent before any isCurrent()
      // check runs, and a failed component fails the load: neither may keep
      // the components already loaded alive, nor leave a worker parked in
      // admit() forever.
      cancelled = true;
      wakeWaiters();
      release();
      throw error;
    }
    return { loaded, total, publishes };
  }

  return {
    run,
    total,
    // Diagnostics: how many loaded components this loader still references,
    // and the most decodes it ever had in flight at once.
    retainedComponentCount: () => Object.keys(loadedByCid).length,
    peakInFlight: () => peakInFlight
  };
}
