import { withStlBodies } from "./stlBodies.js";

let stlWorker = null;
let nextRequestId = 1;
const pendingRequests = new Map();

function makeAbortError() {
  if (typeof DOMException === "function") {
    return new DOMException("The operation was aborted.", "AbortError");
  }
  const error = new Error("The operation was aborted.");
  error.name = "AbortError";
  return error;
}

function stlWorkerSupported() {
  return typeof Worker === "function" && typeof URL === "function";
}

function rejectPendingRequests(error) {
  for (const request of pendingRequests.values()) {
    request.cleanup();
    request.reject(error);
  }
  pendingRequests.clear();
}

function ensureStlWorker() {
  if (!stlWorkerSupported()) {
    return null;
  }
  if (stlWorker) {
    return stlWorker;
  }
  try {
    stlWorker = new Worker(new URL("./stlMeshWorker.js", import.meta.url), { type: "module" });
  } catch {
    stlWorker = null;
    return null;
  }
  stlWorker.addEventListener("message", (event) => {
    const message = event.data || {};
    const request = pendingRequests.get(message.id);
    if (!request) {
      return;
    }
    pendingRequests.delete(message.id);
    request.cleanup();
    if (message.ok) {
      request.resolve(message.bodies || message.meshData);
      return;
    }
    const error = new Error(message.error?.message || "Failed to load STL mesh in worker.");
    error.name = message.error?.name || "Error";
    request.reject(error);
  });
  stlWorker.addEventListener("error", (event) => {
    const error = new Error(event?.message || "STL mesh worker failed.");
    rejectPendingRequests(error);
    stlWorker?.terminate?.();
    stlWorker = null;
  });
  return stlWorker;
}

export function loadStlMeshDataInWorker(url, { signal, resources } = {}) {
  const resourceSignal = resources?.signal;
  signal = signal && resourceSignal ? AbortSignal.any([signal, resourceSignal]) : signal || resourceSignal;
  const worker = ensureStlWorker();
  if (!worker) {
    return null;
  }
  if (signal?.aborted) {
    return Promise.reject(makeAbortError());
  }

  const id = nextRequestId;
  nextRequestId += 1;

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
      cleanup
    });
    signal?.addEventListener?.("abort", abort, { once: true });
    const post = resource => {
      if (!pendingRequests.has(id)) return;
      try { worker.postMessage({ type: "loadStl", id, url, resource }, resource?.kind === "bytes" ? [resource.bytes] : []); }
      catch (error) { pendingRequests.delete(id); cleanup(); reject(error); }
    };
    if (resources) resources.workerTicket(url, { signal }).then(post, error => {
      if (!pendingRequests.delete(id)) return;
      cleanup(); reject(error);
    });
    else post({ kind: "url", url });
  });
}

// Each decode's bodies, split once: a file reopened finds them here.
const bodiesOf = new WeakMap();

/**
 * An STL's bodies (`stlBodies.js`), split after its model is on screen: in the STL worker, over a copy of its triangles,
 * else here. `meshData` with its triangles in body order and a part a body; the decode itself is never written.
 * @param {object} meshData  `loadRenderStl`'s.
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<object>}
 */
export function loadStlBodies(meshData, { signal } = {}) {
  const known = bodiesOf.get(meshData);
  if (known) return known;
  const worker = ensureStlWorker();
  const split = worker ? new Promise((resolve, reject) => {
    const id = nextRequestId;
    nextRequestId += 1;
    pendingRequests.set(id, { resolve, reject, cleanup: () => {} });
    // Copies: the decode stays the cache's, and the worker sends its own back.
    worker.postMessage({ type: "stlBodies", id, vertices: meshData.vertices, normals: meshData.normals, solids: meshData.stlSolids || [] });
  }) : Promise.resolve().then(() => withStlBodies({ vertices: meshData.vertices, normals: meshData.normals }, meshData.stlSolids || []));
  const result = split.then(({ vertices, normals, parts }) => ({ ...meshData, vertices, normals, parts }));
  bodiesOf.set(meshData, result);
  result.catch(() => bodiesOf.delete(meshData));
  if (!signal) return result;
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(makeAbortError()); return; }
    signal.addEventListener("abort", () => reject(makeAbortError()), { once: true });
    result.then(resolve, reject);
  });
}

// Multiple renderer sessions share worker infrastructure, while each request
// retains its own signal. The last owner releases the worker and pending work.
let ownerCount = 0;
export function retainStlMeshWorker() {
  ownerCount += 1;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    ownerCount -= 1;
    if (!ownerCount) {
      rejectPendingRequests(makeAbortError());
      stlWorker?.terminate?.();
      stlWorker = null;
    }
  };
}
