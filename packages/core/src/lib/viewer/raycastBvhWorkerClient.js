function defaultWorker() {
  return new Worker(new URL("./raycastBvhWorker.js", import.meta.url), { type: "module" });
}

function abortError() {
  const error = new Error("BVH build released");
  error.name = "AbortError";
  return error;
}

// One admitted build at a time across scenes. Queued requests hold no copies
// or worker. Each isolate ends with its reservation, including its allocation
// high-water mark; a later small request cannot inherit uncharged large scratch.
export function createRaycastBvhWorkerClient({ createWorker = defaultWorker } = {}) {
  const queue = [];
  let active = null;
  const pump = () => {
    if (active || !queue.length) return;
    const request = queue.shift();
    active = request;
    const finish = (error, value = null) => {
      if (request.done) return;
      request.done = true;
      if (request.worker) {
        request.worker.onmessage = request.worker.onerror = request.worker.onmessageerror = null;
        request.worker.terminate();
        request.worker = null;
      }
      active = null;
      if (error) request.reject(error);
      else request.resolve(value);
      queueMicrotask(pump);
    };
    request.finish = finish;
    try {
      const prepared = request.prepare();
      if (!prepared || request.done) {
        finish(null);
        return;
      }
      const worker = request.worker = createWorker();
      worker.onmessage = ({ data }) => {
        if (data?.error) finish(new Error(String(data.error)));
        else if (!data?.serialized) finish(new Error("Invalid BVH worker response"));
        else finish(null, data.serialized);
      };
      worker.onerror = (event) => finish(new Error(event?.message || "BVH worker failed"));
      worker.onmessageerror = () => finish(new Error("Unreadable BVH worker response"));
      worker.postMessage(prepared.payload, prepared.transfer);
    } catch (error) {
      finish(error);
    }
  };
  return {
    enqueue(prepare) {
      let resolve, reject;
      const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
      const request = { prepare, resolve, reject, done: false, worker: null, finish: null };
      queue.push(request);
      // The caller can register cancellation before admission/copy callbacks run.
      queueMicrotask(pump);
      return {
        promise,
        cancel() {
          if (request.done) return;
          if (active === request) request.finish(abortError());
          else {
            const index = queue.indexOf(request);
            if (index !== -1) queue.splice(index, 1);
            request.done = true;
            reject(abortError());
          }
        },
      };
    },
  };
}

let defaultClient = null;
export function defaultRaycastBvhWorkerClient() {
  if (typeof Worker !== "function") return null;
  return defaultClient ||= createRaycastBvhWorkerClient();
}
