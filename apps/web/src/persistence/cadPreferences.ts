import { createCadPreferences, type CadPreferences } from '@hardcore/ui/renderers/cad';
import { readPoseTransition, writePoseTransition, POSE_TRANSITION_STORAGE_KEY } from '@hardcore/ui/renderers/cad/state';

/** The browser host persists motion preferences; CAD modes own appearance. */
export function createWebCadPreferences() {
  let syncing = false;
  let baseline: CadPreferences = { poseTransition: readPoseTransition(localStorage) };
  const source = createCadPreferences({
    initial: baseline,
    onChange(preferences) {
      if (!syncing) {
        if (preferences.poseTransition && JSON.stringify(preferences.poseTransition) !== JSON.stringify(baseline.poseTransition)) writePoseTransition(localStorage, preferences.poseTransition);
      }
      baseline = preferences;
    },
  });
  return {
    ...source,
    connect() {
      const sync = (event: StorageEvent) => {
        if (event.key === POSE_TRANSITION_STORAGE_KEY) {
          syncing = true;
          try { source.update({ poseTransition: readPoseTransition(localStorage) }); }
          finally { syncing = false; }
          return;
        }
      };
      window.addEventListener('storage', sync);
      return () => window.removeEventListener('storage', sync);
    },
  };
}
