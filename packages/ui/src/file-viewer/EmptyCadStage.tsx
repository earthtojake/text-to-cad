import { useMemo, type ComponentType } from 'react';
import { resolveSceneSettings } from '@hardcore/core/common/sceneSettings.js';
import type { EmptyCadBackdropProps } from './empty.js';
import { useChromeBackdropColor } from '../renderers/kit/look/useChromeBackdropColor.js';
import { sceneBackdropEdgeColor } from '../renderers/kit/look/chromeBackdrop.js';
import ShellViewport from '../renderers/kit/shell/ShellViewport.jsx';

// The kit's viewport with no scene in it: the grid, the axes and the camera, and nothing else.
// It is the HOST's backdrop, so it is built out of the kit — never out of a family slice. It
// used to live in `renderers/step`, which made the host's empty state import the STEP renderer
// to draw a stage with no STEP in it.
const Viewport = ShellViewport as unknown as ComponentType<{
  scene: null;
  modelKey: string;
  projection: string;
  themeSettings: { [key: string]: unknown };
  appearance: 'light' | 'dark';
}>;

export default function EmptyCadStage({ colorScheme = 'light' }: Omit<EmptyCadBackdropProps, 'children'>) {
  const prefersDark = colorScheme === 'dark';
  const chromeBackdropColor = useChromeBackdropColor(prefersDark);
  const scene = useMemo(() => resolveSceneSettings({ appearance: colorScheme, prefersDark }), [colorScheme, prefersDark]);
  const sceneBackdrop = sceneBackdropEdgeColor(scene.theme.background, chromeBackdropColor);
  // Empty and populated CAD stages share the same opinionated Inspect basis.
  return <div className="absolute inset-0" data-cad-scene-backdrop={sceneBackdrop} style={{ backgroundColor: sceneBackdrop }}>
    <Viewport
      scene={null}
      modelKey=""
      projection={scene.camera.projection}
      themeSettings={scene.theme}
      appearance={scene.appearance}
    />
  </div>;
}
