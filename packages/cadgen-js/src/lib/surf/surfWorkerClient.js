// Pooled client for surfWorker.js.
//
// Unlike the single-worker GLB client this is a POOL: a large assembly has
// hundreds of independent components and tessellation is pure CPU, so the
// wall-clock win scales with cores. Requests round-robin across workers;
// each resolves to { meshData, bundle } for one component URL. Returns null
// from loadSurfComponentInWorker when Workers are unavailable (node, old
// browsers) so callers can fall back to inline tessellation.

import {
  getCachedEntryBytes,
  tessellationCacheProviderRegistered,
  tessellationOptionsCacheable,
  writeBackEntryBytes,
} from "./tessellationCache.js";
import { PERF_MEASURE_NAMES, perfMeasure, perfStart } from "../viewer/perfMarks.js";

let pool = null;
let nextWorkerIndex = 0;
let nextRequestId = 1;
const pendingRequests = new Map();

// A component surf under a package's components/ dir is CONTENT-ADDRESSED —
// its stem is the cid the shared tessellation cache keys on. Anything else
// (arbitrary .surf paths) has no stable identity and must not be cached.
//
// Two URL shapes carry component surfs: the PATH form the snapshot host and
// package-relative routes serve (…/components/<cid>.surf) and the QUERY form
// the viewer's asset route serves (/__cad/asset?file=<abs path ending in
// components/<cid>.surf>&v=…). The first release of this function parsed only
// the path form, which silently disabled the entire shared-cache integration
// in the real viewer client — every component URL there is query-form, so
// `cacheable` was always false and no cache read or write-back ever ran.
function cidFromComponentPath(pathLike, { decode = false } = {}) {
  const segments = String(pathLike || "").split("/").filter(Boolean);
  if (segments.length < 2 || segments[segments.length - 2] !== "components") {
    return "";
  }
  let name = segments[segments.length - 1];
  if (decode) {
    try {
      name = decodeURIComponent(name);
    } catch {
      // keep the raw name; a malformed escape must not throw picking offline
    }
  }
  return name.toLowerCase().endsWith(".surf") ? name.slice(0, -5) : "";
}

export function cidFromSurfUrl(url) {
  const withoutFragment = String(url || "").split("#", 1)[0];
  const queryIndex = withoutFragment.indexOf("?");
  const pathnamePart = queryIndex === -1 ? withoutFragment : withoutFragment.slice(0, queryIndex);
  const fromPath = cidFromComponentPath(pathnamePart, { decode: true });
  if (fromPath) {
    return fromPath;
  }
  if (queryIndex === -1) {
    return "";
  }
  // URLSearchParams decodes the `file` value, so its segments are plain.
  const file = new URLSearchParams(withoutFragment.slice(queryIndex + 1)).get("file");
  return file ? cidFromComponentPath(file) : "";
}

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

function ensurePool() {
  if (!workersSupported()) {
    return null;
  }
  if (pool) {
    return pool;
  }
  try {
    pool = Array.from({ length: poolSize() }, () => {
      const worker = new Worker(new URL("./surfWorker.js", import.meta.url), { type: "module" });
      worker.addEventListener("message", (event) => {
        const message = event.data || {};
        const request = pendingRequests.get(message.id);
        if (!request) {
          return;
        }
        pendingRequests.delete(message.id);
        request.cleanup();
        if (message.ok) {
          perfMeasure(PERF_MEASURE_NAMES.tessellate, request.startedAt, { cid: request.cid, cacheHit: request.cacheHit });
          if (message.entryBytes && request.writeBack) {
            request.writeBack(message.entryBytes); // fire-and-forget
          }
          request.resolve({ meshData: message.meshData, bundle: message.bundle });
          return;
        }
        const error = new Error(message.error?.message || "Failed to load surf component in worker.");
        error.name = message.error?.name || "Error";
        request.reject(error);
      });
      worker.addEventListener("error", (event) => {
        // One broken worker poisons in-flight requests; tear the pool down
        // so the next load falls back (or rebuilds a fresh pool).
        rejectAllPending(new Error(event?.message || "surf worker failed."));
        for (const w of pool || []) w.terminate?.();
        pool = null;
      });
      return worker;
    });
  } catch {
    pool = null;
    return null;
  }
  return pool;
}

export function loadSurfComponentInWorker(url, { signal, tessellation } = {}) {
  const workers = ensurePool();
  if (!workers) {
    return null;
  }
  if (signal?.aborted) {
    return Promise.reject(makeAbortError());
  }
  const id = nextRequestId;
  nextRequestId += 1;
  const startedAt = perfStart();
  const worker = workers[nextWorkerIndex % workers.length];
  nextWorkerIndex += 1;
  // The shared tessellation cache lives on THIS thread's provider (a fetch
  // against the host's /__tess_cache/ routes); the worker cannot reach it, so
  // the entry bytes ride the request in (transferred, hit = tessellation
  // skipped) and a miss rides back out as freshly encoded bytes to write
  // back. Everything is best-effort: no provider, no cid (a non-package
  // surf), or debug options mean the message carries nothing extra.
  const cid = cidFromSurfUrl(url);
  const cacheable = Boolean(cid)
    && tessellationCacheProviderRegistered()
    && tessellationOptionsCacheable(tessellation || {});
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      signal?.removeEventListener?.("abort", abort);
    };
    const abort = () => {
      pendingRequests.delete(id);
      cleanup();
      worker.postMessage({ type: "cancel", id });
      reject(makeAbortError());
    };
    pendingRequests.set(id, {
      resolve,
      reject,
      cleanup,
      startedAt,
      cid,
      cacheHit: false,
      writeBack: cacheable
        ? (entryBytes) => { writeBackEntryBytes(cid, tessellation || {}, entryBytes); }
        : null,
    });
    signal?.addEventListener?.("abort", abort, { once: true });
    const post = (cachedEntry) => {
      const request = pendingRequests.get(id);
      if (!request) {
        return; // aborted while the cache lookup was in flight
      }
      request.cacheHit = Boolean(cachedEntry);
      worker.postMessage(
        {
          type: "loadSurf",
          id,
          url,
          ...(tessellation ? { tessellation } : {}),
          ...(cachedEntry ? { cachedEntry } : {}),
          ...(cacheable ? { wantEntry: !cachedEntry } : {}),
        },
        cachedEntry && cachedEntry.buffer.byteLength === cachedEntry.byteLength ? [cachedEntry.buffer] : [],
      );
    };
    if (cacheable) {
      getCachedEntryBytes(cid, tessellation || {}).then(post, () => post(null));
    } else {
      post(null);
    }
  });
}
