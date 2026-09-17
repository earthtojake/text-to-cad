import { useMemo, type ComponentType } from 'react';
import { entrySourceFormat } from '@hardcore/core/lib/fileFormats.js';
import { resolveSceneSettings } from '@hardcore/core/common/sceneSettings.js';
import { VIEWER_PICK_MODE } from '@hardcore/core/lib/viewer/constants.js';
import type { EmptyCadBackdropProps } from '../empty.js';
import type { CadStateObject } from '../state.js';
import { useChromeBackdropColor } from '../file-view/cadTheme.js';
import { sceneBackdropEdgeColor } from '../file-view/chromeBackdrop.js';
import CadViewer from './CadViewer.js';

const Viewer = CadViewer as unknown as ComponentType<{
  meshData: null;
  modelKey: string;
  renderFormat: string;
  projection: string;
  themeSettings: CadStateObject;
  appearance: 'light' | 'dark';
  showEdges: boolean;
  recomputeNormals: boolean;
  pickMode: string;
}>;

export default function EmptyCadStage({ colorScheme = 'light' }: Omit<EmptyCadBackdropProps, 'children'>) {
  const prefersDark = colorScheme === 'dark';
  const chromeBackdropColor = useChromeBackdropColor(prefersDark);
  const scene = useMemo(() => resolveSceneSettings({ appearance: colorScheme, prefersDark }), [colorScheme, prefersDark]);
  const sceneBackdrop = sceneBackdropEdgeColor(scene.theme.background, chromeBackdropColor);
  // Empty and populated CAD stages share the same opinionated Inspect basis.
  return <div className="absolute inset-0" data-cad-scene-backdrop={sceneBackdrop} style={{ backgroundColor: sceneBackdrop }}>
    <Viewer
      meshData={null}
      modelKey=""
      renderFormat={entrySourceFormat(null)}
      projection={scene.camera.projection}
      themeSettings={scene.theme}
      appearance={scene.appearance}
      showEdges
      recomputeNormals={false}
      pickMode={VIEWER_PICK_MODE.AUTO}
    />
  </div>;
}
