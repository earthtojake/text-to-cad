import { useLayoutEffect, useState, useSyncExternalStore } from "react";
import { createViewSettingsStore } from "./viewSettingsStore.js";

const NO_SUBSCRIPTION = () => () => {};
const NO_SNAPSHOT = () => null;

/**
 * One file's Display settings: its store and the store's snapshot. `provided` is a caller's own
 * result of this hook (a renderer that needed the settings before the shell could hand them over):
 * it is returned as it is, and no second store is made. A caller passes the same kind every render.
 */
export function useViewSettings(appearance, provided = null) {
  const [store] = useState(() => (provided ? null : createViewSettingsStore({}, { appearance, lightingQuality: "preview" })));
  useLayoutEffect(() => { store?.configure({ appearance, lightingQuality: "preview" }); }, [store, appearance]);
  const snapshot = useSyncExternalStore(store ? store.subscribe : NO_SUBSCRIPTION, store ? store.getSnapshot : NO_SNAPSHOT, store ? store.getSnapshot : NO_SNAPSHOT);
  return provided || { ...snapshot, store };
}
