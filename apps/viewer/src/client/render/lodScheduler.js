// Viewport LOD scheduler (design/unified-tessellation.md Phase 5).
//
// Non-React glue between camera samples and level-keyed re-tessellation. The
// policy math lives in cadgen-js (lodPolicy.js — pure); this module owns TIME:
// debounce after camera movement, one re-tessellation in flight, worst
// projected error first, and cancellation when a newer sample changes the
// plan. It knows nothing about three.js or React: the host feeds camera
// samples and receives level swaps through a callback.

import { LOD_CHORD_LEVELS, planLodWork } from "cadgen-js/lib/surf/lodPolicy.js";

export const LOD_DEBOUNCE_MS = 200;

/**
 * createLodScheduler({
 *   loadLevel(cid, level, { signal }) -> Promise<payload>,
 *   applyLevel(cid, level, payload),
 *   debounceMs?, levels?,
 *   setTimeoutFn?/clearTimeoutFn? (test clocks),
 * })
 *
 * Host contract:
 *  - setComponents([{ cid, diagonal }]) once per model load (resets levels);
 *  - onCameraSample({ camera, viewportHeightPx, distanceFor(cid) }) per
 *    camera change — cheap, just stamps state and re-arms the debounce;
 *  - dispose() on unmount.
 */
export function createLodScheduler({
  loadLevel,
  applyLevel,
  debounceMs = LOD_DEBOUNCE_MS,
  levels = LOD_CHORD_LEVELS,
  setTimeoutFn = (...args) => setTimeout(...args),
  clearTimeoutFn = (handle) => clearTimeout(handle),
} = {}) {
  const components = new Map(); // cid -> { diagonal, level }
  // (cid:level) loads that failed since the last camera sample. Without this
  // memo a persistently failing load busy-loops the drain (fail -> finally ->
  // re-plan -> same item); with it the failure parks until the camera moves.
  const failed = new Set();
  let lastSample = null;
  let timer = null;
  let inFlight = null; // { cid, level, controller }
  let disposed = false;

  function setComponents(list) {
    components.clear();
    for (const { cid, diagonal } of list || []) {
      if (cid && Number.isFinite(diagonal) && diagonal > 0) {
        components.set(cid, { diagonal, level: 0 });
      }
    }
    cancelInFlight();
  }

  function cancelInFlight() {
    if (inFlight) {
      inFlight.controller.abort();
      inFlight = null;
    }
  }

  function onCameraSample(sample) {
    if (disposed) {
      return;
    }
    lastSample = sample;
    failed.clear();
    if (timer !== null) {
      clearTimeoutFn(timer);
    }
    timer = setTimeoutFn(() => {
      timer = null;
      evaluate();
    }, debounceMs);
  }

  function entriesForPlan() {
    const entries = [];
    for (const [cid, state] of components) {
      const cameraDistance = lastSample.distanceFor(cid);
      if (!Number.isFinite(cameraDistance)) {
        continue;
      }
      entries.push({
        cid,
        currentLevel: state.level,
        sample: {
          diagonal: state.diagonal,
          cameraDistance,
          camera: lastSample.camera,
          viewportHeightPx: lastSample.viewportHeightPx,
        },
      });
    }
    return entries;
  }

  function evaluate() {
    if (disposed || !lastSample || inFlight) {
      return;
    }
    const plan = planLodWork(entriesForPlan(), levels)
      .filter((item) => !failed.has(`${item.cid}:${item.level}`));
    if (!plan.length) {
      return;
    }
    const { cid, level } = plan[0];
    const controller = new AbortController();
    inFlight = { cid, level, controller };
    Promise.resolve(loadLevel(cid, level, { signal: controller.signal }))
      .then((payload) => {
        if (disposed || controller.signal.aborted) {
          return;
        }
        const state = components.get(cid);
        if (state) {
          state.level = level;
          applyLevel(cid, level, payload);
        }
      })
      .catch(() => {
        // Aborted or failed: the component stays at its current level and the
        // (cid, level) parks until the next camera sample. A failed level must
        // never break the model that already renders — or spin the drain.
        failed.add(`${cid}:${level}`);
      })
      .finally(() => {
        if (inFlight?.controller === controller) {
          inFlight = null;
        }
        // More work may be queued behind the swap (other components, or the
        // next rung of this one) — keep draining until the plan is empty.
        if (!disposed) {
          evaluate();
        }
      });
  }

  function dispose() {
    disposed = true;
    if (timer !== null) {
      clearTimeoutFn(timer);
      timer = null;
    }
    cancelInFlight();
  }

  return {
    setComponents,
    onCameraSample,
    dispose,
    // Introspection for tests and debugging overlays.
    levelOf: (cid) => components.get(cid)?.level ?? null,
    busy: () => inFlight !== null,
  };
}
