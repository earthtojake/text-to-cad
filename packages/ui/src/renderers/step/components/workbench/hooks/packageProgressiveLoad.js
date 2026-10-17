// Progressive publish of a component package (packages/ui/docs/loading.md,
// section 2), split out of useCadAssets so it unit-tests in Node (the hook's
// other imports are Vite-resolved; same pattern as packageReferenceComposition.js).
//
// The hook used to fetch every component, compose once and publish once, so a
// 866-component model painted nothing until the last component landed and a
// cancel mid-way freed nothing it had not yet published. This module loads the
// components with bounded concurrency and, as they arrive, re-composes the ones
// loaded so far through one reference-based composition
// (buildComposedPackageMeshData shares component buffers, it copies nothing),
// publishing each batch. The last publish is the full model.
import { buildComposedPackageMeshData } from "@text-to-cad/core/lib/assembly/meshData.js";
import { estimateMeshRenderCost } from "@text-to-cad/core/lib/render/meshCost.js";
import { displayMeshBytes } from "../../../render/initialDisplay.js";
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
// First ceilings. The camera frames the box the descriptor declares (`bbox`)
// from the first publish, so what that publish holds decides only what is drawn
// first; the load order puts the model's six extreme components first, so eight
// components already span the model on screen, and span the frame of a
// descriptor that declares no box.
export const PROGRESSIVE_PUBLISH_FIRST_COMPONENTS = 8;
export const PROGRESSIVE_PUBLISH_FIRST_BYTES = 8 * 1024 * 1024;
// Last ceilings, once doubling reaches them. A batch this size is roughly the
// cost of one scene rebuild, so it does not stall interaction noticeably; the byte ceiling also bounds how much
// decoded geometry sits on the main thread unpainted, waiting to be uploaded.
export const PROGRESSIVE_PUBLISH_MAX_COMPONENTS = 256;
export const PROGRESSIVE_PUBLISH_MAX_BYTES = 128 * 1024 * 1024;

// Load-time admission (the peak that killed the tab): a component decodes in a
// part worker whose intermediates count against the renderer process, and a
// hand component reaches ~90 MB of meshData. A count cap alone (8 wide) admits
// 8 of those at once. Admission is therefore ALSO byte-aware: the bytes the
// parts' rows charge for the decodes in flight (`displayMeshBytes`) stay under
// this budget. The Viewer may opt one larger component into serial admission
// only after its global owned-memory ledger reserves the complete charge.
export const PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES = 256 * 1024 * 1024;

// `meshing`: cadgen is deriving parts the store did not hold (a cold open), which the
// screen names as meshing; otherwise the parts are only being read.
export function progressiveLoadProgress(loaded, total, detail = undefined, { meshing = false } = {}) {
  const normalizedTotal = Math.max(0, Math.floor(Number(total) || 0));
  const normalizedLoaded = Math.max(0, Math.min(
    normalizedTotal,
    Math.floor(Number(loaded) || 0),
  ));
  return {
    phase: meshing ? "meshing" : "geometry",
    label: meshing ? "Meshing parts" : "Loading geometry",
    done: normalizedLoaded,
    total: normalizedTotal,
    determinate: true,
    ...(detail === undefined ? {} : { detail }),
  };
}

// Whether a published mesh state is the COMPLETE model: the final publish
// (assemblyInteractionReady true, every component composed). Animation attaches
// on the first publish and stays live across publishes: its tracks name
// occurrence ids, so they drive whatever has arrived.
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

// A load that has ended without the components cadgen could not mesh: short of their parts for good,
// not still arriving. The viewport warns of them (buildViewerMeshAlert) instead of reading
// "Updating model…" over a model that will not change.
export function meshStateSettledShort(meshState) {
  return meshState?.assemblyInteractionReady === true && !meshStateIsComplete(meshState)
    && (meshState?.assemblyFailedParts?.length || 0) > 0;
}

// A rewritten file whose next revision is not built yet: the entry has no mesh while its render
// artifact (re)builds, and the complete model of this same file is the one on screen. It stays
// there, reported as an update, until the new revision replaces it atomically
// (`shouldRetainCompleteSameFileMesh`): once a model has been shown, a rebuild never takes it down.
export function awaitingSameFileRevision(current, entry) {
  return Boolean(entry?.file) &&
    String(current?.file || "") === String(entry.file) &&
    meshStateIsComplete(current);
}

// What the viewer SHOWS while a same-file revision loads, whatever the entry's kind: the complete
// model on screen until the new one is published. (`shouldRetainCompleteSameFileMesh` is the
// loader's own, narrower question: whether to stage an assembly's replacement atomically.)
export function replacingSameFileMesh(current, entry, targetMeshHash) {
  return String(current?.file || "") === String(entry?.file || "") &&
    String(current?.meshHash || "") !== String(targetMeshHash || "") &&
    meshStateIsComplete(current);
}

// Whether the model on screen stays while `entry`'s revision loads: through the rebuild, while the
// entry has no mesh yet, and through the load of its new mesh. Whatever the model is -- a part, an
// assembly, one with motion -- an edit is an update, never the loading screen again.
export function retainsPreviousStepMesh(current, entry, { entryHasMesh, meshHash }) {
  return entryHasMesh
    ? Boolean(meshHash) && replacingSameFileMesh(current, entry, meshHash)
    : awaitingSameFileRevision(current, entry);
}

// What stays on screen when a load is cancelled part-way (a newer revision, or another file):
// the partial composition that load published for its file goes, a complete model -- a part's as
// much as an assembly's -- stays, and another file's state is not the cancelled load's to touch.
export function meshStateAfterCancelledLoad(current, cancelledFile) {
  return current && current.file === cancelledFile && !meshStateIsComplete(current) ? null : current;
}

export function shouldRetainCompleteSameFileMesh(current, entry, targetMeshHash) {
  return String(entry?.kind || "") === "assembly" &&
    String(current?.file || "") === String(entry?.file || "") &&
    String(current?.meshHash || "") !== String(targetMeshHash || "") &&
    meshStateIsComplete(current);
}

// Readable memory accounting for the headless harness, following the
// window.__cadModelPlacement precedent:
// written on EVERY progressive publish, nulled on cancel, never React state.
// Harmless without a window (Node tests).
function meshCostAccounting({ meshData, componentMeshDataByCid, loaded, total, publishCount, final, meshRevision = "" }) {
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
// in descriptor order, so the first paint already spans the model rather than
// showing 32 components of one fingertip of a hand. The viewer frames the
// camera ONCE per model, on the first publish, on the box the descriptor
// declares (`bbox`), which this order does not change. A descriptor without
// one is framed on its first batch and again when the last component lands,
// and this order keeps that first frame close to the final one. The
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
 *   loadComponent(cid, component, { estimatedBytes, row }), // -> Promise<meshData>
 *   concurrency,
 *   isCurrent(),                       // false once the request is superseded or aborted
 *   partRow(cid, component, { rejectedCacheObjects, skipCacheProbes }), // -> Promise<row>: the
 *                                      // component's part row (core's `partRow`), before admission
 *   retryCacheProbeMiss?(error, row),  // true asks for the row again, and admits again, after a stale body
 *   componentFailed?(error, cid),      // true: partRow's error is that component's alone (cadgen could
 *                                      // not derive or mesh it); the rest load on without it
 *   maxInFlightBytes?,                 // bytes the decodes in flight charge (PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES)
 *   allowOversizedSingle?,             // one > maxInFlightBytes decode after reserveLoad accepts it
 *   retainedComponent?(cid, component),// already-owned exact meshData, bypassing decode admission
 *   initialComposition?,               // immediately preceding same-file composition
 *   reserveLoad?({ cid, estimatedBytes, row }) -> { ok, token?, detail? },
 *   releaseLoad?(token), onMemoryLimitation?(detail),
 *   recoverMemoryPressure?(detail),    // one bounded reclaim attempt after admitted work drains
 *   onRetainedChange?({ loaded, failed, total, retainedBytes }), // every unique component completion
 *   onPublish({ meshData, componentMeshDataByCid, loaded, total, final, composeMs, publishCount, failures }),
 *   maxComponents?, maxBytes?
 * }).run() -> Promise<{ loaded, total, publishes, failures }>
 *
 * Admission is count- AND byte-capped: a component starts decoding only when
 * fewer than `concurrency` are in flight and what its part's row charges, its
 * stored mesh and the cost of decoding it (`displayMeshBytes`), fits
 * `maxInFlightBytes` beside the decodes in flight. A row that states no size is
 * the load's error. With `allowOversizedSingle`, one larger part may run alone
 * after `reserveLoad` accepts it, and its decode is held to its own charge.
 * Every publish re-checks isCurrent() first; a superseded or aborted load
 * publishes nothing further, drops its references to every component it
 * loaded (retainedComponentCount() -> 0) and rejects with an AbortError.
 * The final publish (`final: true`) carries every component and is
 * the same composition the single post-load publish produced.
 *
 * A component whose own failure `componentFailed` recognizes settles alone: every other component
 * still loads, and the final publish carries the rest with `failures` ([{ cid, error }]) naming
 * what is missing. Every other failure fences every lane, and only when every component failed on
 * its own is the first failure the load's.
 */
export function createProgressivePackageLoader({
  descriptor,
  loadComponent,
  concurrency = 8,
  isCurrent = () => true,
  partRow,
  retryCacheProbeMiss = null,
  componentFailed = null,
  maxInFlightBytes = PROGRESSIVE_LOAD_MAX_INFLIGHT_BYTES,
  allowOversizedSingle = false,
  retainedComponent = null,
  initialComposition = null,
  reserveLoad = null,
  releaseLoad = null,
  recoverMemoryPressure = null,
  onMemoryLimitation = null,
  onRetainedChange = null,
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
  // The components that failed on their own ({ cid, error }): settled, and left out.
  const failures = [];
  let pendingComponents = 0;
  let pendingBytes = 0;
  let publishes = 0;
  let publishedFinal = false;
  let retainedBytes = 0;
  let previousComposition = initialComposition;

  function notifyRetained() {
    onRetainedChange?.({ loaded, failed: failures.length, total, retainedBytes });
  }

  // Every component has loaded or failed on its own.
  function settled() {
    return loaded + failures.length === total;
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
    const componentMeshDataByCid = { ...loadedByCid };
    const startedAt = typeof performance !== "undefined" ? performance.now() : Date.now();
    const meshData = buildComposedPackageMeshData(descriptor, componentMeshDataByCid, { previous: previousComposition });
    previousComposition = meshData;
    const composeMs = (typeof performance !== "undefined" ? performance.now() : Date.now()) - startedAt;
    pendingComponents = 0;
    pendingBytes = 0;
    publishes += 1;
    publishedFinal = publishedFinal || final;
    onPublish?.({ meshData, componentMeshDataByCid, loaded, total, final, composeMs, publishCount: publishes,
      failures: [...failures] });
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

  // Admits one decode at what its part's row charges (`estimate`), waiting while the decodes in
  // flight leave it no room.
  async function admit(cid, row, estimate) {
    let lastRecoveryEpoch = -1;
    while (true) {
      if (!active()) throw abortError();
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
        reservation = reserveLoad({ cid, estimatedBytes: estimate, row }) || { ok: false };
      }
      if (reservation.ok !== false) {
        inFlight += 1;
        inFlightBytes += estimate;
        peakInFlight = Math.max(peakInFlight, inFlight);
        return { estimate, reservation: reservation.token, oversized: estimate > maxInFlightBytes };
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
      const final = settled();
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
      let row;
      // The ask handles an ordinary miss itself (a part the store lacks is derived). A thrown
      // error is cancellation, an invalid immutable binding, or failed part derivation and
      // must fence sibling lanes like a decode failure.
      try {
        row = await partRow(cid, component, {
          rejectedCacheObjects,
          // Two stored bodies gone missing force the next ask through cold resolution instead
          // of following a rapidly changing cache index forever.
          skipCacheProbes: cacheProbeMisses >= 2,
        });
      } catch (error) {
        // One component cadgen could not derive or mesh is that component's failure: it settles
        // alone, and every other component goes on loading (`run` publishes the final
        // composition when a failure settles last).
        if (componentFailed?.(error, cid) === true && active()) {
          failures.push({ cid, error });
          notifyRetained();
          return;
        }
        markFailed(error);
        throw error;
      }
      if (!active()) stop();
      const estimate = displayMeshBytes(row);
      if (estimate === null) throw new Error(`Component ${cid} has no part row to size its decode by`);
      admission = await admit(cid, row, estimate);
      try {
        if (!active()) stop();
        meshData = await loadComponent(cid, component, { estimatedBytes: admission.estimate, row });
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
        const retry = cacheProbeMisses < 2 && retryCacheProbeMiss?.(error, row) === true;
        if (!retry) markFailed(error);
        releaseSlot(admission);
        if (retry) {
          // The next ask passes over this body: the store no longer holds it.
          rejectedCacheObjects.add(row.glb.object);
          cacheProbeMisses += 1;
          continue;
        }
        // The retryable stale-body case above is the only failure that may
        // admit again; every other failure fences waiters before release.
        throw error;
      }
    }
    const decodedBytes = admission.decodedBytes;
    loadedByCid[cid] = meshData;
    loaded += 1;
    retainedBytes += decodedBytes;
    notifyRetained();
    pendingComponents += 1;
    pendingBytes += decodedBytes;
    const final = settled();
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
      // Every component failed on its own: there is nothing to draw, and the first one's error
      // is the load's.
      if (!loaded && failures.length) {
        throw failures[0].error;
      }
      if (!publishedFinal) {
        // The last component to settle failed on its own: the rest are the final composition.
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
    return { loaded, total, publishes, failures: [...failures] };
  }

  // Draws what has loaded while a lane waits on something outside the load (a preview's part the
  // build is still deriving, `useCadAssets`): one publish of the components pending, once nothing
  // is in flight to join them -- so a load that publishes whole still shows what it has while it
  // waits. Nothing while a decode is in flight, after the final publish, or with nothing pending.
  function publishPending() {
    if (!active() || publishedFinal || inFlight > 0 || pendingComponents === 0) return false;
    publish(false);
    return true;
  }

  return {
    run,
    total,
    publishPending,
    // Diagnostics: how many loaded components this loader still references,
    // and the most decodes it ever had in flight at once.
    retainedComponentCount: () => Object.keys(loadedByCid).length,
    peakInFlight: () => peakInFlight
  };
}
