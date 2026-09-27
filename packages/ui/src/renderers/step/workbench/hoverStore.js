import { useSyncExternalStore } from "react";

/**
 * What the pointer is over, held OUTSIDE React state: the reference or part under it in the
 * viewport (`modelReferenceId`, `modelPartId`) and the Features row under it (`listPartId`).
 *
 * Hover changes at pointer rate. As state of the surface, every change re-rendered the whole
 * STEP surface, the tool stack and the Features tree under it — about a second a hover on a
 * large assembly — although nothing there draws hover: the viewport's layers do. So the
 * surface writes hover here, and only what draws it subscribes (`scene/StepSceneLayers.jsx`).
 *
 * The setters are React's contract, so the surface's hover paths read the same as they did as
 * `useState`: a value or an updater of the current value, a no-op when nothing changes, and
 * stable identities. One snapshot object per change, so a subscriber compares by identity.
 */
export const EMPTY_HOVER = Object.freeze({ modelReferenceId: "", modelPartId: "", listPartId: "" });

export function createHoverStore() {
  let snapshot = EMPTY_HOVER;
  const listeners = new Set();
  const getSnapshot = () => snapshot;
  const subscribe = (listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  };
  /** Several fields in one change: one snapshot, one notification. */
  const update = (patch) => {
    let next = snapshot;
    for (const key of Object.keys(patch)) {
      if (!Object.prototype.hasOwnProperty.call(EMPTY_HOVER, key)) throw new Error(`Unknown hover field: ${key}`);
      const value = typeof patch[key] === "function" ? patch[key](next[key]) : patch[key];
      if (!Object.is(value, next[key])) next = { ...next, [key]: value };
    }
    if (next === snapshot) return;
    snapshot = Object.freeze(next);
    for (const listener of [...listeners]) listener();
  };
  const setter = (key) => (value) => update({ [key]: value });
  return {
    getSnapshot,
    subscribe,
    update,
    clear: () => update(EMPTY_HOVER),
    setModelReferenceId: setter("modelReferenceId"),
    setModelPartId: setter("modelPartId"),
    setListPartId: setter("listPartId"),
  };
}

/** The current hover, re-rendering the caller only when it changes. */
export function useHover(store) {
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}
