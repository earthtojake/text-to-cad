// Pooled client for surfWorker.js.
//
// Unlike the single-worker GLB client this is a POOL: a large assembly has
// hundreds of independent components and tessellation is pure CPU, so the
// wall-clock win scales with cores. Requests round-robin across workers and
// name the render/selectors capabilities they require. Returns null from
// loadSurfComponentInWorker when Workers are unavailable (node, old browsers)
// so callers can fall back to inline tessellation.

import {
  TessellationCacheProbeMissError,
  tessellationOptionsCacheable,
} from "./tessellationCache.js";

import { PERF_MEASURE_NAMES, perfMeasure, perfStart } from "../viewer/perfMarks.js";

let pool = null;
let poolGeneration = 0;
let nextWorkerIndex = 0;
let poolGrowthLimit = 0;
let nextRequestId = 1;
const pendingRequests = new Map();
const idleReleaseWaiters = new Map();
let dispatching = false;
let dispatchRequested = false;
const UNKNOWN_WORKER_MEMORY_ESTIMATE_BYTES = 128 * 1024 * 1024;

function makeAbortError() {
  if (typeof DOMException === "function") {
    return new DOMException("The operation was aborted.", "AbortError");
  }
  const error = new Error("The operation was aborted.");
  error.name = "AbortError";
  return error;
}

function workersSupported() {
  return typeof Worker === "function" && typeof URL === "function";
}

function normalizedMemoryEstimateBytes(value) {
  const bytes = Number(value);
  return Number.isFinite(bytes) && bytes > 0
    ? Math.ceil(bytes)
    : UNKNOWN_WORKER_MEMORY_ESTIMATE_BYTES;
}

function normalizeCapabilities(value) {
  if (value === undefined) {
    return { render: true, selectors: true };
  }
  if (!value || typeof value !== "object") {
    throw new TypeError("Surf worker capabilities must be an object");
  }
  const capabilities = {
    render: value.render === true,
    selectors: value.selectors === true,
  };
  if (!capabilities.render && !capabilities.selectors) {
    throw new TypeError("Surf worker request must require render or selectors capability");
  }
  return capabilities;
}

function poolSize() {
  const cores = typeof navigator !== "undefined" ? navigator.hardwareConcurrency || 4 : 4;
  return Math.max(2, Math.min(cores - 1, 8));
}

function rejectAllPending(error) {
  for (const request of pendingRequests.values()) {
    request.cleanup();
    request.reject(error);
  }
  pendingRequests.clear();
}

function resolveIdleReleaseWaiters(generation, released) {
  const waiters = idleReleaseWaiters.get(generation);
  if (!waiters) return;
  for (const resolve of waiters) resolve(released);
  idleReleaseWaiters.delete(generation);
}

function releaseIdlePool(generation = poolGeneration) {
  if (generation !== poolGeneration) {
    resolveIdleReleaseWaiters(generation, false);
    return false;
  }
  if (pendingRequests.size > 0) return false;
  if (pool) {
    for (const slot of pool) {
      slot?.worker.terminate?.();
    }
    pool = null;
    nextWorkerIndex = 0;
  }
  resolveIdleReleaseWaiters(generation, true);
  return true;
}

function releaseDeferredPoolIfIdle(generation = poolGeneration) {
  if (idleReleaseWaiters.has(generation)) releaseIdlePool(generation);
}

function nextReadyRequest(generation) {
  for (const [id, request] of pendingRequests) {
    if (request.poolGeneration === generation && request.ready && !request.slot) {
      return [id, request];
    }
  }
  return null;
}

function dispatchQueuedRequests() {
  if (dispatching) {
    dispatchRequested = true;
    return;
  }
  dispatching = true;
  try {
    do {
      dispatchRequested = false;
      const currentPool = pool;
      const generation = poolGeneration;
      if (!currentPool) break;
      const startIndex = nextWorkerIndex;
      for (let offset = 0; offset < currentPool.length; offset += 1) {
        if (pool !== currentPool || poolGeneration !== generation) break;
        const index = (startIndex + offset) % currentPool.length;
        const slot = currentPool[index];
        if (!slot || slot.requestId != null) continue;
        const queued = nextReadyRequest(generation);
        if (!queued) break;
        const [id, request] = queued;
        slot.requestId = id;
        request.slot = slot;
        nextWorkerIndex = (index + 1) % currentPool.length;
        try {
          slot.worker.postMessage(request.message, request.transfer);
        } catch (error) {
          handleWorkerError(slot, error);
        }
      }
      // Sequential refinement needs one isolate. Grow only for ready work
      // that existing slots cannot start, never merely for a cache waiter.
      if (pool === currentPool && poolGeneration === generation && nextReadyRequest(generation) && currentPool.length < poolGrowthLimit) {
        try {
          currentPool.push(createWorkerSlot(currentPool.length, generation));
          dispatchRequested = true;
        } catch {
          // Existing workers still own their requests and can drain the queue.
          // Stop growth for this generation if another isolate cannot start.
          poolGrowthLimit = currentPool.length;
        }
      }
    } while (dispatchRequested);
  } finally {
    dispatching = false;
    // A callback can request another pass as the final loop condition is
    // checked. Drain it iteratively from a fresh call after unwinding.
    if (dispatchRequested) {
      dispatchRequested = false;
      queueMicrotask(dispatchQueuedRequests);
    }
  }
}

function finishRequest(slot, id) {
  const request = pendingRequests.get(id);
  if (!request || request.slot !== slot) return null;
  pendingRequests.delete(id);
  request.slot = null;
  slot.requestId = null;
  request.cleanup();
  return request;
}

function replaceWorkerSlot(slot) {
  if (!pool || slot.poolGeneration !== poolGeneration || pool[slot.index] !== slot) return;
  slot.worker.terminate?.();
  pool[slot.index] = null;
  releaseDeferredPoolIfIdle(slot.poolGeneration);
  if (!pool || slot.poolGeneration !== poolGeneration) return;
  try {
    pool[slot.index] = createWorkerSlot(slot.index, slot.poolGeneration);
  } catch (error) {
    // Losing one replacement slot does not invalidate work already owned by
    // the remaining isolates. They keep draining the queue; only a pool with
    // no surviving slot is terminal.
    pool[slot.index] = null;
    if (!pool.some(Boolean)) {
      pool = null;
      rejectAllPending(error instanceof Error ? error : new Error(String(error)));
      resolveIdleReleaseWaiters(slot.poolGeneration, true);
    }
  }
}

function handleWorkerMessage(slot, event) {
  const message = event.data || {};
  const request = finishRequest(slot, message.id);
  if (!request) return;
  // An ok:false reply can arrive after tessellation grew the isolate's heap.
  // The worker remains reusable, so it owns that high-water estimate until its
  // exact slot is terminated. A stale reply has no request and cannot charge a
  // replacement slot.
  slot.residentEstimateBytes = Math.max(
    slot.residentEstimateBytes,
    request.memoryEstimateBytes,
  );
  dispatchQueuedRequests();
  releaseDeferredPoolIfIdle(request.poolGeneration);
  if (message.ok) {
    perfMeasure(PERF_MEASURE_NAMES.tessellate, request.startedAt, { cid: request.cid, cacheHit: request.cacheHit });
    if (message.entryBytes && request.writeBack) {
      request.writeBack(message.entryBytes); // fire-and-forget
    }
    request.resolve({
      ...(message.meshData ? { meshData: message.meshData } : {}),
      ...(message.bundle ? { bundle: message.bundle } : {}),
    });
    return;
  }
  const error = new Error(message.error?.message || "Failed to load surf component in worker.");
  error.name = message.error?.name || "Error";
  request.reject(error);
}

function handleWorkerError(slot, event) {
  if (!pool || slot.poolGeneration !== poolGeneration || pool[slot.index] !== slot) return;
  const request = slot.requestId == null ? null : finishRequest(slot, slot.requestId);
  if (request) {
    request.reject(new Error(event?.message || "surf worker failed."));
  }
  replaceWorkerSlot(slot);
  dispatchQueuedRequests();
}

function createWorkerSlot(index, generation) {
  const worker = new Worker(new URL("./surfWorker.js", import.meta.url), { type: "module" });
  const slot = {
    worker,
    index,
    poolGeneration: generation,
    requestId: null,
    residentEstimateBytes: 0,
  };
  worker.addEventListener("message", (event) => handleWorkerMessage(slot, event));
  worker.addEventListener("error", (event) => handleWorkerError(slot, event));
  return slot;
}

function ensurePool() {
  if (!workersSupported()) {
    return null;
  }
  if (pool) {
    return pool;
  }
  const slots = [];
  try {
    poolGeneration += 1;
    const generation = poolGeneration;
    poolGrowthLimit = poolSize();
    slots.push(createWorkerSlot(0, generation));
    pool = slots;
  } catch {
    for (const slot of slots) slot.worker.terminate?.();
    pool = null;
    return null;
  }
  return pool;
}

// Shed only isolates that own no request. Memory admission can fail while a
// progressive package load is still alive because completed tessellations
// leave their workers' high-water heaps resident. The caller may retry the
// same allocation after this synchronous reclamation without canceling work:
// active slots remain, requests waiting for a cache read remain queued, and at
// least one idle slot remains when queued work has no active slot to inherit.
// The counts describe live isolates after the call, so the viewer can reduce
// its conservative worker-resident estimate by exactly the capacity returned.
export function reclaimIdleSurfWorkers() {
  const currentPool = pool;
  const generation = poolGeneration;
  if (!currentPool) {
    return { reclaimedSlots: 0, residentSlots: 0, fullyReleased: true };
  }

  const before = currentPool.filter(Boolean).length;
  // A pressure reclamation constrains this generation; a later cache-ready
  // request must inherit a surviving slot rather than recreate one just shed.
  poolGrowthLimit = currentPool.length;
  if (pendingRequests.size === 0) {
    const fullyReleased = releaseIdlePool(generation);
    return {
      reclaimedSlots: fullyReleased ? before : 0,
      residentSlots: fullyReleased ? 0 : before,
      fullyReleased,
    };
  }

  const activeSlots = currentPool.filter((slot) => slot?.requestId != null).length;
  const idleSlots = currentPool.filter((slot) => slot && slot.requestId == null);
  const keepIdle = activeSlots === 0 ? 1 : 0;
  for (const slot of idleSlots.slice(keepIdle)) {
    slot.worker.terminate?.();
    if (pool === currentPool && poolGeneration === generation && currentPool[slot.index] === slot) {
      currentPool[slot.index] = null;
    }
  }
  const residentSlots = currentPool.filter(Boolean).length;
  return {
    reclaimedSlots: before - residentSlots,
    residentSlots,
    fullyReleased: residentSlots === 0,
  };
}

// Process-local ownership only. Estimates describe the live worker slots that
// actually completed a request in this generation; they are not geometry or
// cache identity and never cross the worker protocol boundary.
export function surfWorkerMemoryStats() {
  const slots = pool ? pool.filter(Boolean) : [];
  return Object.freeze({
    generation: poolGeneration,
    residentSlots: slots.length,
    usedSlots: slots.filter((slot) => slot.residentEstimateBytes > 0).length,
    residentEstimateBytes: slots.reduce(
      (total, slot) => total + slot.residentEstimateBytes,
      0,
    ),
  });
}

// Hand the pool's isolates back once they are idle. A worker keeps the heap it
// grew for the largest component it tessellated, and eight of those, on a model
// whose biggest component decodes to tens of megabytes, is memory the renderer
// process never returns while the pool lives — measured as the bulk of the gap
// between what the scene retains and the renderer's RSS on the tendon hand.
// Only the load and later LOD refinement use the pool, so a caller that has
// finished loading releases it; the next request builds a fresh pool at the
// cost of one module load per worker.
//
// A package load and a viewport refinement can briefly overlap, so in-flight
// work is left alone — terminating then would reject work the caller is still
// waiting on — while its caller still needs to know when the isolates are
// actually gone so retained-memory accounting can be cleared. Resolve once the
// last pending request completes or aborts; no pool is also a successfully
// released state.
export function releaseSurfWorkerPoolWhenIdle() {
  const generation = poolGeneration;
  if (!pool) {
    return Promise.resolve(true);
  }
  if (pendingRequests.size === 0) {
    return Promise.resolve(releaseIdlePool(generation));
  }
  return new Promise((resolve) => {
    const waiters = idleReleaseWaiters.get(generation) || new Set();
    waiters.add(resolve);
    idleReleaseWaiters.set(generation, waiters);
  });
}

export function loadSurfComponentInWorker(url, {
  signal,
  tessellation,
  identity,
  capabilities: rawCapabilities,
  memoryEstimateBytes,
  tessellationCache,
} = {}) {
  const capabilities = normalizeCapabilities(rawCapabilities);
  const workers = ensurePool();
  if (!workers) {
    return null;
  }
  if (signal?.aborted) {
    return Promise.reject(makeAbortError());
  }
  const id = nextRequestId;
  nextRequestId += 1;
  // The shared tessellation cache lives on THIS thread's provider (a fetch
  // against the host's /__tess_cache/ routes); the worker cannot reach it, so
  // the entry bytes ride the request in (transferred, hit = tessellation
  // skipped) and a miss rides back out as freshly encoded bytes to write
  // back. Everything is best-effort: no provider, no exact surface identity,
  // or debug options mean the message carries nothing extra.
  const surfaceInput = String(identity?.surfaceInput || "");
  const surfaceObject = String(identity?.surfaceObject || "");
  const strictProbe = Boolean(identity?.tessellationProbe);
  const cacheable = Boolean(surfaceInput && surfaceObject)
    && tessellationCache?.tessellationCacheProviderRegistered()
    && tessellationOptionsCacheable(tessellation || {});
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      signal?.removeEventListener?.("abort", abort);
    };
    const abort = () => {
      const request = pendingRequests.get(id);
      if (!request) return;
      pendingRequests.delete(id);
      cleanup();
      const slot = request.slot;
      request.slot = null;
      if (slot) {
        slot.requestId = null;
        replaceWorkerSlot(slot);
      }
      dispatchQueuedRequests();
      releaseDeferredPoolIfIdle(request?.poolGeneration);
      reject(makeAbortError());
    };
    pendingRequests.set(id, {
      resolve,
      reject,
      cleanup,
      poolGeneration,
      memoryEstimateBytes: normalizedMemoryEstimateBytes(memoryEstimateBytes),
      startedAt: perfStart(),
      cid: surfaceInput,
      cacheHit: false,
      ready: false,
      slot: null,
      message: null,
      transfer: null,
      writeBack: cacheable
        ? (entryBytes) => { tessellationCache.writeBackEntryBytes(surfaceInput, tessellation || {}, entryBytes); }
        : null,
    });
    signal?.addEventListener?.("abort", abort, { once: true });
    const post = (cachedEntry) => {
      const request = pendingRequests.get(id);
      if (!request) {
        return; // aborted while the cache lookup was in flight
      }
      request.cacheHit = Boolean(cachedEntry);
      request.message = {
        type: "loadSurf",
        id,
        url,
        capabilities,
        ...(tessellation ? { tessellation } : {}),
        ...(cacheable ? { cacheIdentity: { surfaceInput, surfaceObject } } : {}),
        ...(cachedEntry ? { cachedEntry } : {}),
        ...(cacheable ? { wantEntry: !cachedEntry } : {}),
      };
      request.transfer = cachedEntry && cachedEntry.buffer.byteLength === cachedEntry.byteLength
        ? [cachedEntry.buffer]
        : [];
      request.ready = true;
      dispatchQueuedRequests();
    };
    if (cacheable) {
      tessellationCache.getCachedEntryBytes(surfaceInput, tessellation || {}, {
        signal,
        probe: identity?.tessellationProbe || null,
        strictProbe,
      }).then(post, (error) => {
        const request = pendingRequests.get(id);
        if (!request) return;
        pendingRequests.delete(id);
        request.cleanup();
        request.reject(error);
        dispatchQueuedRequests();
        releaseDeferredPoolIfIdle(request.poolGeneration);
      });
    } else if (strictProbe) {
      const request = pendingRequests.get(id);
      pendingRequests.delete(id);
      request?.cleanup();
      request?.reject(new TessellationCacheProbeMissError(identity.tessellationProbe));
      dispatchQueuedRequests();
      releaseDeferredPoolIfIdle(request?.poolGeneration);
    } else {
      post(null);
    }
  });
}

// A render session leases the shared scheduler. Dropping one session never
// interrupts another owner's work; the last release retires remaining requests.
let ownerCount = 0;
export function retainSurfWorkerPool() {
  ownerCount += 1;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    ownerCount -= 1;
    if (!ownerCount) {
      rejectAllPending(makeAbortError());
      releaseIdlePool();
    }
  };
}
