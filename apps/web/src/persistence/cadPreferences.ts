import { createCadPreferences, type CadPreferences } from '@hardcore/ui/renderers/cad';
import { readFileSheetTabLayoutStore, writeFileSheetTabLayoutStore, readPoseTransition, writePoseTransition, POSE_TRANSITION_STORAGE_KEY } from '@hardcore/ui/renderers/cad/state';
import { readSeenTutorialTipIds, markTutorialTipSeen } from '../client/workbench/persistence.js';

/** The browser host persists layout, motion and tips; CAD modes own appearance. */
export function createWebCadPreferences() {
  let syncing = false;
  const source = createCadPreferences({
    initial: { poseTransition: readPoseTransition(localStorage), seenTips: readSeenTutorialTipIds(), fileSheetTabs: readFileSheetTabLayoutStore(localStorage) } as CadPreferences,
    onChange(preferences) {
      if (syncing) return;
      if (preferences.poseTransition) writePoseTransition(localStorage, preferences.poseTransition);
      if (preferences.fileSheetTabs) writeFileSheetTabLayoutStore(localStorage, preferences.fileSheetTabs);
      preferences.seenTips?.forEach(id => markTutorialTipSeen(id));
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
