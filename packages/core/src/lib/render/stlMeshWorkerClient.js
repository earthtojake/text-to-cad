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
      request.resolve(message.meshData);
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

export function loadStlMeshDataInWorker(url, { signal } = {}) {
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
    worker.postMessage({ type: "loadStl", id, url });
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
