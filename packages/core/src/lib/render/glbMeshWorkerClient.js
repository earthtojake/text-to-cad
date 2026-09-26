import { createHttpCadResourceProvider } from "../../client/resources.js";
let glbWorker = null;
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

function glbWorkerSupported() {
  return typeof Worker === "function" && typeof URL === "function";
}

function rejectPendingRequests(error) {
  for (const request of pendingRequests.values()) {
    request.cleanup();
    request.reject(error);
  }
  pendingRequests.clear();
}

function ensureGlbWorker() {
  if (!glbWorkerSupported()) {
    return null;
  }
  if (glbWorker) {
    return glbWorker;
  }
  try {
    glbWorker = new Worker(new URL("./glbMeshWorker.js", import.meta.url), { type: "module" });
  } catch {
    glbWorker = null;
    return null;
  }
  glbWorker.addEventListener("message", (event) => {
    const message = event.data || {};
    const request = pendingRequests.get(message.id);
    if (!request) {
      return;
    }
    if (message.type === "resource") {
      const provider = request.resources || createHttpCadResourceProvider();
      Promise.resolve().then(() => provider.readBytes(provider.resolveDependency(request.url, message.reference), {
        signal: request.signal, maxBytes: 64 * 1024 * 1024,
      })).then(bytes => {
        if (pendingRequests.has(message.id)) glbWorker?.postMessage({ type: "resource", resourceId: message.resourceId, bytes }, [bytes]);
      }, error => {
        if (pendingRequests.has(message.id)) glbWorker?.postMessage({ type: "resource", resourceId: message.resourceId, error: error.message });
      });
      return;
    }
    pendingRequests.delete(message.id);
    request.cleanup();
    if (message.ok) {
      request.resolve(message.meshData);
      return;
    }
    const error = new Error(message.error?.message || "Failed to load GLB mesh in worker.");
    error.name = message.error?.name || "Error";
    request.reject(error);
  });
  glbWorker.addEventListener("error", (event) => {
    const error = new Error(event?.message || "GLB mesh worker failed.");
    rejectPendingRequests(error);
    glbWorker?.terminate?.();
    glbWorker = null;
  });
  return glbWorker;
}

export function loadGlbMeshDataInWorker(url, { signal, resources } = {}) {
  const resourceSignal = resources?.signal;
  signal = signal && resourceSignal ? AbortSignal.any([signal, resourceSignal]) : signal || resourceSignal;
  const worker = ensureGlbWorker();
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
      resources, url, signal,
      cleanup
    });
    signal?.addEventListener?.("abort", abort, { once: true });
    const post = resource => {
      if (!pendingRequests.has(id)) return;
      try { worker.postMessage({ type: "loadGlb", id, url, resource }, resource?.kind === "bytes" ? [resource.bytes] : []); }
      catch (error) { pendingRequests.delete(id); cleanup(); reject(error); }
    };
    if (resources) resources.workerTicket(url, { signal }).then(post, error => {
      if (!pendingRequests.delete(id)) return;
      cleanup(); reject(error);
    });
    else post({ kind: "url", url });
  });
}

// Multiple renderer sessions share worker infrastructure, while each request
// retains its own signal. The last owner releases the worker and pending work.
let ownerCount = 0;
export function retainGlbMeshWorker() {
  ownerCount += 1;
  let released = false;
  return () => {
    if (released) return;
    released = true;
    ownerCount -= 1;
    if (!ownerCount) {
      rejectPendingRequests(makeAbortError());
      glbWorker?.terminate?.();
      glbWorker = null;
    }
  };
}
