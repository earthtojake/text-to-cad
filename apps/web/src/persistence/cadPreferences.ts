import { createCadPreferences, type CadPreferences } from '@hardcore/ui/renderers/cad';
import { readPoseTransition, writePoseTransition, POSE_TRANSITION_STORAGE_KEY, readOrbit, writeOrbit, ORBIT_STORAGE_KEY } from '@hardcore/ui/renderers/cad/state';

/** The browser host persists motion preferences; CAD modes own appearance. */
export function createWebCadPreferences() {
  let syncing = false;
  const snapshot = (): CadPreferences => ({ poseTransition: readPoseTransition(localStorage), orbit: readOrbit(localStorage) });
  let baseline = snapshot();
  const source = createCadPreferences({
    initial: baseline,
    onChange(preferences) {
      if (!syncing) {
        if (preferences.poseTransition && JSON.stringify(preferences.poseTransition) !== JSON.stringify(baseline.poseTransition)) writePoseTransition(localStorage, preferences.poseTransition);
        if (preferences.orbit && JSON.stringify(preferences.orbit) !== JSON.stringify(baseline.orbit)) writeOrbit(localStorage, preferences.orbit);
      }
      baseline = preferences;
    },
  });
  return {
    ...source,
    connect() {
      const sync = (event: StorageEvent) => {
        if (event.key === null || event.key === POSE_TRANSITION_STORAGE_KEY || event.key === ORBIT_STORAGE_KEY) {
          syncing = true;
          try { source.update(snapshot()); }
          finally { syncing = false; }
          return;
        }
      };
      window.addEventListener('storage', sync);
      return () => window.removeEventListener('storage', sync);
    },
  };
}
