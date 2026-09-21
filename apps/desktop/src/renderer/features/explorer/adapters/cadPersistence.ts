import { createCadPreferences } from "@hardcore/ui/renderers/workspace";
import type { CadPreferences, CadPreferenceSource } from "@hardcore/ui/renderers/workspace";
import { readOrbit, writeOrbit, ORBIT_STORAGE_KEY } from "@hardcore/ui/renderers/step/state";

/** Global motion preferences apply to every desktop root. */
export function migrateCadPreferences(storage: Storage): CadPreferences {
  return {
    orbit: readOrbit(storage),
  };
}

let sharedPreferences: CadPreferenceSource | undefined;
/** CAD motion preferences are shared by every root in this desktop window. */
export function desktopCadPreferences(): CadPreferenceSource {
  if (!sharedPreferences) {
    let syncing = false;
    const snapshot = () => migrateCadPreferences(localStorage);
    let baseline = snapshot();
    const source = createCadPreferences({ initial: baseline, onChange: (preferences) => {
      if (!syncing) {
        if (preferences.orbit && JSON.stringify(preferences.orbit) !== JSON.stringify(baseline.orbit)) writeOrbit(localStorage, preferences.orbit);
      }
      baseline = preferences;
    } });
    // Browser storage events carry updates from another Hardcore window. This
    // host-owned store has the lifetime of the window, independent of its roots.
    window.addEventListener("storage", event => {
      if (event.key !== null && event.key !== ORBIT_STORAGE_KEY) return;
      syncing = true;
      try { source.update(snapshot()); } finally { syncing = false; }
    });
    sharedPreferences = source;
  }
  return sharedPreferences;
}
