// Performance measures for the render path, recorded ONLY when a profiler
// asks for them.
//
// A profiling harness sets `globalThis.__cadgenPerf`
// and reads the User Timing entries back with `performance.getEntriesByName`;
// without that flag every call here is one property read, and the timeline
// buffer — which is unbounded for measures — never grows under a long-lived
// window. Framework-free, DOM-free: usable from a worker or Node too, where
// `performance` is global.
//
// Names are a closed set so a reader can ask for them by name:
//   cad:tessellate   one component surf → triangles, in a worker; the detail
//                    carries `{ cid, cacheHit }` (hit = the shared cache
//                    answered, and the worker skipped the tessellator)
//   cad:hover-pick   one hover raycast over the model, from whichever pointer
//                    pick the renderer mounts (`renderers/step/scene/useStepPicking.js`)
//   cad:frame        one render-on-demand frame (useViewerRuntime)
//   cad:topology-batch   one batch of an assembly's selector topology, from its start to its
//                    publication; the detail carries `{ parts, added, requested, composeMs }`
//                    (useCadAssets' loadReferencesForEntry)
//   cad:topology-settled a topology request, from the loader's start to publishing exactly
//                    the parts requested; the detail carries `{ parts, batches }`

export const PERF_MEASURE_NAMES = Object.freeze({
  tessellate: "cad:tessellate",
  hoverPick: "cad:hover-pick",
  frame: "cad:frame",
  topologyBatch: "cad:topology-batch",
  topologySettled: "cad:topology-settled",
});

function performanceAvailable() {
  return typeof performance !== "undefined"
    && typeof performance.now === "function"
    && typeof performance.measure === "function";
}

export function perfEnabled() {
  return globalThis.__cadgenPerf === true && performanceAvailable();
}

/** `performance.now()` when profiling, else 0 — a start token for `perfMeasure`. */
export function perfStart() {
  return perfEnabled() ? performance.now() : 0;
}

/** Record `name` from `start` (a `perfStart` token) to now. No-op unless profiling. */
export function perfMeasure(name, start, detail = undefined) {
  if (!perfEnabled()) {
    return;
  }
  try {
    performance.measure(name, { start, end: performance.now(), ...(detail ? { detail } : {}) });
  } catch {
    // An older User Timing API without the options form: nothing to record.
  }
}
