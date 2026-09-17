import { createCadPreferences, type CadPreferences } from '@hardcore/ui/renderers/cad';
import { readFileSheetTabLayoutStore, writeFileSheetTabLayoutStore, readPoseTransition, writePoseTransition, POSE_TRANSITION_STORAGE_KEY } from '@hardcore/ui/renderers/cad/state';
import { readDirectoryThemeSettingsState, readThemeSettingsState, readSeenTutorialTipIds, writeCadDirectorySessionState,
  readCadDirectorySessionState, createDirectorySessionThemeSlice, markTutorialTipSeen,
  THEME_STORAGE_KEY, THEME_STORAGE_VERSION } from '../client/workbench/persistence.js';

/** The browser host retains the existing global theme and session override semantics. */
export function createWebCadPreferences() {
  const theme = readDirectoryThemeSettingsState();
  let syncing = false;
  const source = createCadPreferences({
    initial: { poseTransition: readPoseTransition(localStorage), theme: { themeId: theme.themeId, custom: theme.custom }, seenTips: readSeenTutorialTipIds(), fileSheetTabs: readFileSheetTabLayoutStore(localStorage) } as CadPreferences,
    onChange(preferences) {
      if (syncing) return;
      if (preferences.poseTransition) writePoseTransition(localStorage, preferences.poseTransition);
      if (preferences.fileSheetTabs) writeFileSheetTabLayoutStore(localStorage, preferences.fileSheetTabs);
      if (preferences.theme) {
        try {
          localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify({ version: THEME_STORAGE_VERSION, ...preferences.theme }));
          writeCadDirectorySessionState({ ...readCadDirectorySessionState(), theme: createDirectorySessionThemeSlice(preferences.theme) });
        } catch { /* The view remains usable when browser storage is blocked. */ }
      }
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
        if (event.key !== THEME_STORAGE_KEY) return;
        const next = readThemeSettingsState();
        syncing = true;
        try { source.update({ theme: { themeId: next.themeId, custom: next.custom } as CadPreferences['theme'] }); }
        finally { syncing = false; }
      };
      window.addEventListener('storage', sync);
      return () => window.removeEventListener('storage', sync);
    },
  };
}
