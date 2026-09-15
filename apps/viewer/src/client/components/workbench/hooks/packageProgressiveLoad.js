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
import { ViewerMemoryLimitError } from "../../../render/viewerMemoryPolicy.js";

// A batch publishes as soon as EITHER ceiling is crossed by the components
// that arrived since the previous publish — whichever comes first — and both
// ceilings DOUBLE after each publish, from the first pair to the last.
//
// A publish costs a recomposition plus a walk of every occurrence already on
// screen, so its cost grows with the model while a fixed batch size keeps the
// publish COUNT growing with it too: the hand recomposed 28 times and spent
// longer republishing what was already drawn than decoding what was not.
// Doubling makes the count logarithmic (the hand publishes 8 times) without
// making the first paint wait: the first batch is SMALLER than the old fixed
// one, so first geometry arrives sooner than it did.
//
// First ceilings. The load order puts the model's six extreme components first,
// so eight components already span it for the one camera framing.
export const PROGRESSIVE_PUBLISH_FIRST_COMPONENTS = 8;
export const PROGRESSIVE_PUBLISH_FIRST_BYTES = 8 * 1024 * 1024;
// Last ceilings, once doubling reaches them. A batch this size is roughly the
// cost of a scene rebuild the viewer already absorbs on an LOD swap, so it does
// not stall interaction noticeably; the byte ceiling also bounds how much
// decoded geometry sits on the main thread unpainted, waiting to be uploaded.
export const PROGRESSIVE_PUBLISH_MAX_COMPONENTS = 256;
export const PROGRESSIVE_PUBLISH_MAX_BYTES = 128 * 1024 * 1024;

// Load-time admission (the peak that killed the tab): a component decodes in a
// surf worker whose intermediates count against the renderer process, and a
// hand component reaches ~90 MB of meshData. A count cap alone (8 wide) admits
// 8 of those at once. Admission is therefore ALSO byte-aware: the estimated
// decoded bytes of ordinary concurrent work stay under this budget. The
// Viewer may opt one larger component into serial admission only after its
// global owned-memory ledger reserves the complete estimate.
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
export function createDecodeSizeEstimator({
  maxInFlightBytes = PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
  sourceExpansionRatio = 0,
} = {}) {
  let ratioSum = 0;
  let ratioCount = 0;
  let decodedSum = 0;
  let decodedCount = 0;
  return {
    estimate(hintBytes, expansionRatio = sourceExpansionRatio) {
      const hint = Number(hintBytes);
      const unmeasuredFloor = maxInFlightBytes / PROGRESSIVE_LOAD_UNMEASURED_SHARE;
      const ratio = Number(expansionRatio) || 0;
      const sourceFloor = Number.isFinite(hint) && hint > 0 && ratio > 0
        ? hint * ratio
        : 0;
      if (Number.isFinite(hint) && hint > 0 && ratioCount > 0) {
        return Math.max(unmeasuredFloor, sourceFloor, hint * (ratioSum / ratioCount));
      }
      if (decodedCount > 0) {
        return Math.max(unmeasuredFloor, sourceFloor, decodedSum / decodedCount);
      }
      return Math.max(unmeasuredFloor, sourceFloor);
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
  return progressiveLoadProgress(loaded, total).label;
}

export function progressiveLoadProgress(loaded, total, detail = undefined) {
  const normalizedTotal = Math.max(0, Math.floor(Number(total) || 0));
  const normalizedLoaded = Math.max(0, Math.min(
    normalizedTotal,
    Math.floor(Number(loaded) || 0),
  ));
  return {
    phase: "geometry",
    label: "Loading geometry",
    done: normalizedLoaded,
    total: normalizedTotal,
    determinate: true,
    ...(detail === undefined ? {} : { detail }),
  };
}

// Whether a published mesh state is the COMPLETE model: the final publish
// (assemblyInteractionReady true, every component composed). Embedded animation
// attaches on the first publish and stays live across publishes; what waits for
// the complete state is clip validation, which
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

export function shouldRetainCompleteSameFileMesh(current, entry, targetMeshHash) {
  return String(entry?.kind || "") === "assembly" &&
    String(current?.file || "") === String(entry?.file || "") &&
    String(current?.meshHash || "") !== String(targetMeshHash || "") &&
    meshStateIsComplete(current);
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
export function meshCostAccounting({ meshData, componentMeshDataByCid, loaded, total, publishCount, final, meshRevision = "" }) {
  let componentTotalBytes = 0;
  let componentTotalTriangles = 0;
  const components = Object.values(componentMeshDataByCid || {});
  for (const component of components) {
    const cost = estimateMeshRenderCost(component);
    componentTotalBytes += cost.typedArrayBytes;
    componentTotalTriangles += cost.triangleCount;
  }
  return {
    meshRevision,
    composed: estimateMeshRenderCost(meshData),
    componentTotalBytes,
    componentTotalTriangles,
    componentCount: components.length,
    occurrenceCount: Array.isArray(meshData?.parts) ? meshData.parts.length : 0,
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

// The ceilings this batch publishes at, `publishCount` publishes into the load.
// A caller that pins the last ceilings below the first ones (small fixtures,
// tests) gets that size flat, never a batch above what it asked for.
export function progressivePublishCeilings(
  publishCount,
  {
    firstComponents = PROGRESSIVE_PUBLISH_FIRST_COMPONENTS,
    firstBytes = PROGRESSIVE_PUBLISH_FIRST_BYTES,
    maxComponents = PROGRESSIVE_PUBLISH_MAX_COMPONENTS,
    maxBytes = PROGRESSIVE_PUBLISH_MAX_BYTES
  } = {}
) {
  const growth = 2 ** Math.max(0, Math.min(30, Number(publishCount) || 0));
  return {
    components: Math.max(1, Math.min(maxComponents, firstComponents * growth)),
    bytes: Math.max(1, Math.min(maxBytes, firstBytes * growth))
  };
}

export function progressivePublishDue({ pendingComponents, pendingBytes, publishCount = 0 }, options = {}) {
  const ceilings = progressivePublishCeilings(publishCount, options);
  return pendingComponents >= ceilings.components || pendingBytes >= ceilings.bytes;
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
 *   loadComponent(cid, component, { estimatedBytes, cacheProbe }), // -> Promise<meshData>
 *   concurrency,
 *   isCurrent(),                       // false once the request is superseded or aborted
 *   sizeHint?(cid, component),         // -> Promise<number|{sourceBytes,cacheProbe}> before admission
 *   retryCacheProbeMiss?(error, probe),// true re-enters metadata + admission after a stale body
 *   maxInFlightBytes?,                 // estimated decoded bytes in flight (PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES)
 *   allowOversizedSingle?,             // one > maxInFlightBytes decode after reserveLoad accepts it
 *   sourceExpansionRatio?,             // conservative decoded/source estimate floor for this concrete tier
 *   retainedComponent?(cid, component),// already-owned exact meshData, bypassing decode admission
 *   initialComposition?,               // immediately preceding same-file composition
 *   reserveLoad?({ cid, estimatedBytes }) -> { ok, token?, detail? },
 *   releaseLoad?(token), onMemoryLimitation?(detail),
 *   recoverMemoryPressure?(detail),    // one bounded reclaim attempt after admitted work drains
 *   onRetainedChange?({ loaded, total, retainedBytes }), // every unique component completion
 *   swappedComponents?(),              // the live LOD working set (cid -> meshData) or null
 *   onPublish({ meshData, componentMeshDataByCid, loaded, total, final, composeMs, publishCount }),
 *   maxComponents?, maxBytes?
 * }).run() -> Promise<{ loaded, total, publishes }>
 *
 * Admission is count- AND byte-capped: a component starts decoding only when
 * fewer than `concurrency` are in flight and the estimated decoded bytes in
 * flight (createDecodeSizeEstimator over the sizeHint) fit `maxInFlightBytes`.
 * With `allowOversizedSingle`, one larger estimate may run alone after
 * `reserveLoad` accepts it. Every publish re-checks isCurrent() first; a superseded or aborted load
 * publishes nothing further, drops its references to every component it
 * loaded (retainedComponentCount() -> 0) and rejects with an AbortError.
 * Composition is `{ ...loadedSoFar, ...swappedComponents() }`, so a viewport
 * LOD swap that lands mid-load is kept by the next batch rather than reverted
 * to its initially requested level. The final publish (`final: true`) carries every component and is
 * the same composition the single post-load publish produced.
 */
export function createProgressivePackageLoader({
  descriptor,
  loadComponent,
  concurrency = 8,
  isCurrent = () => true,
  sizeHint = null,
  retryCacheProbeMiss = null,
  maxInFlightBytes = PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
  allowOversizedSingle = false,
  sourceExpansionRatio = 0,
  retainedComponent = null,
  initialComposition = null,
  reserveLoad = null,
  releaseLoad = null,
  recoverMemoryPressure = null,
  onMemoryLimitation = null,
  onRetainedChange = null,
  swappedComponents = () => null,
  onPublish,
  publishIntermediate = true,
  firstComponents = PROGRESSIVE_PUBLISH_FIRST_COMPONENTS,
  firstBytes = PROGRESSIVE_PUBLISH_FIRST_BYTES,
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
  let retainedBytes = 0;
  let previousComposition = initialComposition;

  function notifyRetained() {
    onRetainedChange?.({ loaded, total, retainedBytes });
  }

  function release() {
    previousComposition = null;
    for (const cid of Object.keys(loadedByCid)) {
      delete loadedByCid[cid];
    }
    retainedBytes = 0;
    notifyRetained();
  }

  function stop() {
    throw abortError();
  }

  function active() {
    return !cancelled && isCurrent();
  }

  function publish(final) {
    if (!active()) {
      stop();
    }
    const swapped = swappedComponents?.();
    const componentMeshDataByCid = swapped && typeof swapped === "object"
      ? { ...loadedByCid, ...swapped }
      : { ...loadedByCid };
    const startedAt = typeof performance !== "undefined" ? performance.now() : Date.now();
    const meshData = buildComposedPackageMeshData(descriptor, componentMeshDataByCid, { previous: previousComposition });
    previousComposition = meshData;
    const composeMs = (typeof performance !== "undefined" ? performance.now() : Date.now()) - startedAt;
    pendingComponents = 0;
    pendingBytes = 0;
    publishes += 1;
    publishedFinal = publishedFinal || final;
    onPublish?.({ meshData, componentMeshDataByCid, loaded, total, final, composeMs, publishCount: publishes });
  }

  // Coarse and canonical tessellations have different expansion curves. Keep
  // their observations separate so a dense L1 leaf cannot make a valid L0
  // estimate appear unfit (or vice versa) in a mixed small assembly.
  const estimatorsByExpansionRatio = new Map();
  function estimatorFor(expansionRatio) {
    const numeric = Number(expansionRatio) || 0;
    if (!estimatorsByExpansionRatio.has(numeric)) {
      estimatorsByExpansionRatio.set(numeric, createDecodeSizeEstimator({
        maxInFlightBytes,
        sourceExpansionRatio: numeric,
      }));
    }
    return estimatorsByExpansionRatio.get(numeric);
  }
  let inFlight = 0;
  let inFlightBytes = 0;
  let cancelled = false;
  let firstFailure = null;
  let waiters = [];
  let peakInFlight = 0;
  let releaseProgressEpoch = 0;

  function wakeWaiters() {
    const pending = waiters;
    waiters = [];
    for (const wake of pending) {
      wake();
    }
  }

  function markFailed(error) {
    if (!firstFailure) firstFailure = error;
    cancelled = true;
    wakeWaiters();
  }

  function canAdmit(estimate) {
    if (inFlight >= concurrency) return false;
    if (inFlightBytes + estimate <= maxInFlightBytes) return true;
    // The fixed byte cap bounds aggregate concurrency, not a second global
    // memory envelope. A larger single component can proceed only through a
    // real external reservation; once admitted, its own occupancy keeps every
    // sibling waiting until it releases.
    return allowOversizedSingle === true && typeof reserveLoad === "function"
      && inFlight === 0 && estimate > maxInFlightBytes;
  }

  // Re-estimates on every wake: a decode finishing while this one waited has
  // calibrated the estimator, and the size it should be admitted at is the
  // current one, not the one it computed before waiting.
  async function admit(hint, cid, component) {
    let lastRecoveryEpoch = -1;
    while (true) {
      if (!active()) throw abortError();
      const sourceBytes = hint && typeof hint === "object" ? hint.sourceBytes : hint;
      const cacheProbe = hint && typeof hint === "object" ? hint.cacheProbe : null;
      const configuredRatio = typeof sourceExpansionRatio === "function"
        ? sourceExpansionRatio(cid, component, sourceBytes)
        : sourceExpansionRatio;
      const estimator = estimatorFor(configuredRatio);
      const cachedBytes = Number(cacheProbe?.byteLength) + Number(cacheProbe?.decodedBytes);
      const estimate = cacheProbe && Number.isSafeInteger(cachedBytes) && cachedBytes > 0
        ? cachedBytes
        : estimator.estimate(sourceBytes);
      if (!canAdmit(estimate)) {
        if (cancelled) throw abortError();
        if (inFlight === 0) {
          const detail = {
            cid,
            requestedBytes: estimate,
            decodedEstimateBytes: estimate,
            availableBytes: maxInFlightBytes,
            category: "workerInFlight",
            preservingCurrentView: true,
          };
          onMemoryLimitation?.(detail);
          throw new ViewerMemoryLimitError(
            `Component ${cid} needs an estimated ${Math.ceil(estimate / (1024 * 1024))} MiB decode, above the viewer's ${Math.floor(maxInFlightBytes / (1024 * 1024))} MiB in-flight limit. The current view was kept.`,
            detail
          );
        }
        await new Promise((resolve) => waiters.push(resolve));
        continue;
      }
      let reservation = { ok: true, token: null };
      if (typeof reserveLoad === "function") {
        reservation = reserveLoad({ cid, estimatedBytes: estimate, cacheProbe }) || { ok: false };
      }
      if (reservation.ok !== false) {
        inFlight += 1;
        inFlightBytes += estimate;
        peakInFlight = Math.max(peakInFlight, inFlight);
        return { estimate, estimator, reservation: reservation.token, sourceBytes, cacheProbe,
          oversized: estimate > maxInFlightBytes };
      }
      if (inFlight > 0) {
        await new Promise((resolve) => waiters.push(resolve));
        continue;
      }
      const reservationDetail = reservation.detail || {};
      if (lastRecoveryEpoch !== releaseProgressEpoch && typeof recoverMemoryPressure === "function") {
        const attemptedAtEpoch = releaseProgressEpoch;
        lastRecoveryEpoch = attemptedAtEpoch;
        const recovered = await recoverMemoryPressure({
          cid,
          decodedEstimateBytes: estimate,
          reservationDetail,
        });
        // A sibling can finish while recovery itself awaits worker retirement.
        // Retry against that new state even when the callback could not reclaim
        // anything. With no intervening release, one unsuccessful retry remains
        // the bound and an impossible request fails predictably.
        if (recovered || releaseProgressEpoch !== attemptedAtEpoch) continue;
      }
      const detail = {
        ...reservationDetail,
        cid,
        decodedEstimateBytes: estimate,
        requestedBytes: Number(reservationDetail.requestedBytes) || estimate,
        preservingCurrentView: true,
      };
      onMemoryLimitation?.(detail);
      throw new ViewerMemoryLimitError(
        `Loading component ${cid} would exceed the viewer memory envelope. The current view was kept.`,
        detail
      );
    }
  }

  function releaseSlot({ estimate, reservation }) {
    inFlight -= 1;
    inFlightBytes -= estimate;
    releaseLoad?.(reservation, { estimatedBytes: estimate });
    releaseProgressEpoch += 1;
    wakeWaiters();
  }

  async function loadOne([cid, component]) {
    if (!active()) {
      stop();
    }
    const retainedMeshData = retainedComponent?.(cid, component) || null;
    if (retainedMeshData) {
      loadedByCid[cid] = retainedMeshData;
      loaded += 1;
      notifyRetained();
      pendingComponents += 1;
      const final = loaded === total;
      if (final || (publishIntermediate && progressivePublishDue(
        { pendingComponents, pendingBytes, publishCount: publishes },
        { firstComponents, firstBytes, maxComponents, maxBytes }
      ))) {
        publish(final);
      }
      return;
    }
    const rejectedCacheObjects = new Set();
    let cacheProbeMisses = 0;
    let meshData;
    let admission;
    while (true) {
      let hint = null;
      if (typeof sizeHint === "function") {
        // Optional metadata probes handle ordinary misses themselves. A thrown
        // error is cancellation, an invalid immutable binding, or failed surface
        // derivation and must fence sibling lanes like a decode failure.
        try {
          hint = await sizeHint(cid, component, {
            rejectedCacheObjects,
            // L1 and L0 are the only initial tiers. If both probed objects
            // disappear, force the next pass through cold resolution instead
            // of following a rapidly changing cache index forever.
            skipCacheProbes: cacheProbeMisses >= 2,
          });
        } catch (error) {
          markFailed(error);
          throw error;
        }
      }
      if (!active()) stop();
      admission = await admit(hint, cid, component);
      try {
        if (!active()) stop();
        meshData = await loadComponent(cid, component, {
          estimatedBytes: admission.estimate,
          cacheProbe: admission.cacheProbe,
        });
        if (!active()) stop();
        const decodedBytes = estimateMeshRenderCost(meshData).typedArrayBytes;
        const decodedLimit = admission.oversized ? admission.estimate : maxInFlightBytes;
        if (decodedBytes > decodedLimit) {
          const detail = {
            cid,
            requestedBytes: decodedBytes,
            availableBytes: decodedLimit,
            category: "workerInFlight",
            preservingCurrentView: true,
            actualDecodedBytes: decodedBytes,
            decodedEstimateBytes: admission.estimate,
          };
          onMemoryLimitation?.(detail);
          throw new ViewerMemoryLimitError(
            `Component ${cid} decoded to ${Math.ceil(decodedBytes / (1024 * 1024))} MiB, above its admitted ${Math.floor(decodedLimit / (1024 * 1024))} MiB component estimate. The current view was kept.`,
            detail,
          );
        }
        admission.decodedBytes = decodedBytes;
        releaseSlot(admission);
        break;
      } catch (error) {
        const retry = cacheProbeMisses < 2 && admission.cacheProbe
          && retryCacheProbeMiss?.(error, admission.cacheProbe) === true;
        if (!retry) markFailed(error);
        releaseSlot(admission);
        if (retry) {
          rejectedCacheObjects.add(admission.cacheProbe.object);
          cacheProbeMisses += 1;
          continue;
        }
        // The retryable probed-body case above is the only failure that may
        // admit again; every other failure fences waiters before release.
        throw error;
      }
    }
    const decodedBytes = admission.decodedBytes;
    if (!admission.cacheProbe) admission.estimator.observe(admission.sourceBytes, decodedBytes);
    loadedByCid[cid] = meshData;
    loaded += 1;
    retainedBytes += decodedBytes;
    notifyRetained();
    pendingComponents += 1;
    pendingBytes += decodedBytes;
    const final = loaded === total;
    if (final || (publishIntermediate && progressivePublishDue(
      { pendingComponents, pendingBytes, publishCount: publishes },
      { firstComponents, firstBytes, maxComponents, maxBytes }
    ))) {
      publish(final);
    }
  }

  async function run() {
    const queue = componentEntries.slice();
    const workerCount = Math.max(1, Math.min(queue.length || 1, Math.floor(Number(concurrency) || 1)));
    try {
      await Promise.all(Array.from({ length: workerCount }, async () => {
        try {
          while (!cancelled && queue.length) {
            await loadOne(queue.shift());
          }
        } catch (error) {
          // Promise.all rejects as soon as one lane fails, but its sibling
          // lanes keep running. Returning to the hook at that point lets a
          // late sibling publish after the hook has attached its terminal
          // error, erasing the failure and starting the package again. Fence
          // every lane immediately, wake queued admissions, then let already
          // admitted work settle so each reservation releases exactly once.
          markFailed(error);
        }
      }));
      if (firstFailure) {
        throw firstFailure;
      }
      if (!active()) {
        stop();
      }
      if (!publishedFinal) {
        // No components at all: compose anyway so the descriptor's own error
        // ("matched no renderable component GLBs") surfaces exactly as before.
        publish(true);
      }
    } catch (error) {
      // All consumer lanes are settled here. No sibling can publish after
      // this cleanup or mutate the hook after it handles the original error.
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
