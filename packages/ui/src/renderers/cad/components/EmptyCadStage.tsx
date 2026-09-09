import { useMemo, useSyncExternalStore, type ComponentType } from 'react';
import { entrySourceFormat } from '@hardcore/core/lib/fileFormats.js';
import { normalizeCameraProjection } from '@hardcore/core/lib/displaySettings.js';
import { VIEWER_PICK_MODE } from '@hardcore/core/lib/viewer/constants.js';
import type { EmptyCadBackdropProps } from '../empty.js';
import type { CadPreferences } from '../preferences.js';
import { createThemeState, type CadStateObject } from '../state.js';
import { resolveCadThemeSettings, useChromeBackdropColor } from '../file-view/cadTheme.js';
import { sceneBackdropEdgeColor } from '../file-view/chromeBackdrop.js';
import CadViewer from './CadViewer.js';

const emptyPreferences: CadPreferences = Object.freeze({});
const getEmptyPreferences = () => emptyPreferences;
const subscribeEmpty = () => () => {};
const Viewer = CadViewer as unknown as ComponentType<{
  meshData: null;
  modelKey: string;
  renderFormat: string;
  projection: string;
  themeSettings: CadStateObject;
  showEdges: boolean;
  recomputeNormals: boolean;
  pickMode: string;
}>;

export default function EmptyCadStage({ preferences, colorScheme = 'light' }: Omit<EmptyCadBackdropProps, 'children'>) {
  const snapshot = useSyncExternalStore(
    preferences?.subscribe || subscribeEmpty,
    preferences?.getSnapshot || getEmptyPreferences,
    preferences?.getSnapshot || getEmptyPreferences,
  );
  const prefersDark = colorScheme === 'dark';
  const chromeBackdropColor = useChromeBackdropColor(prefersDark);
  const themeSettings = useMemo(() => {
    const theme = createThemeState(snapshot.theme?.themeId, snapshot.theme?.custom, { prefersDark });
    return resolveCadThemeSettings(theme.settings, theme.themeId, { prefersDark, chromeBackdropColor });
  }, [snapshot.theme, prefersDark, chromeBackdropColor]);
  const sceneBackdrop = sceneBackdropEdgeColor(themeSettings.background, chromeBackdropColor);
  // A missing entry historically resolves to STEP, including the theme's
  // projection, even when the requested path ends in .stl.
  return <div className="absolute inset-0" data-cad-scene-backdrop={sceneBackdrop} style={{ backgroundColor: sceneBackdrop }}>
    <Viewer
      meshData={null}
      modelKey=""
      renderFormat={entrySourceFormat(null)}
      projection={normalizeCameraProjection(themeSettings.projection)}
      themeSettings={themeSettings}
      showEdges
      recomputeNormals={false}
      pickMode={VIEWER_PICK_MODE.AUTO}
    />
  </div>;
}
