import { useLayoutEffect, useState, useSyncExternalStore } from "react";
import { createViewSettingsStore } from "./viewSettingsStore.js";

export function useViewSettings(appearance) {
  const [store] = useState(() => createViewSettingsStore({}, { appearance, lightingQuality: "preview" }));
  useLayoutEffect(() => { store.configure({ appearance, lightingQuality: "preview" }); }, [store, appearance]);
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  return { ...snapshot, store };
}
