import { CAD_LEGACY_PREFERENCE_KEYS, createCadPreferences, type CadPreferences } from '@hardcore/ui/renderers/cad';
import { readFileSheetTabLayoutStore, writeFileSheetTabLayoutStore, readPoseTransition, writePoseTransition, POSE_TRANSITION_STORAGE_KEY } from '@hardcore/ui/renderers/cad/state';
import { mergeChangedRecords } from './statePatch';

/** The browser host persists layout and motion; CAD modes own appearance. */
export function createWebCadPreferences() {
  let syncing = false;
  let baseline: CadPreferences = { poseTransition: readPoseTransition(localStorage), fileSheetTabs: readFileSheetTabLayoutStore(localStorage) };
  const source = createCadPreferences({
    initial: baseline,
    onChange(preferences) {
      if (!syncing) {
        if (preferences.poseTransition && JSON.stringify(preferences.poseTransition) !== JSON.stringify(baseline.poseTransition)) writePoseTransition(localStorage, preferences.poseTransition);
        if (JSON.stringify(preferences.fileSheetTabs) !== JSON.stringify(baseline.fileSheetTabs)) writeFileSheetTabLayoutStore(localStorage, mergeChangedRecords(readFileSheetTabLayoutStore(localStorage), baseline.fileSheetTabs ?? {}, preferences.fileSheetTabs ?? {}));
      }
      baseline = preferences;
    },
  });
  return {
    ...source,
    connect() {
      const sync = (event: StorageEvent) => {
        if (event.key === POSE_TRANSITION_STORAGE_KEY || event.key === CAD_LEGACY_PREFERENCE_KEYS.fileSheetTabs) {
          syncing = true;
          try { source.update({ poseTransition: readPoseTransition(localStorage), fileSheetTabs: readFileSheetTabLayoutStore(localStorage) }); }
          finally { syncing = false; }
          return;
        }
      };
      window.addEventListener('storage', sync);
      return () => window.removeEventListener('storage', sync);
    },
  };
}
