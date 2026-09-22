import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import { viewerPanels } from '../../file-viewer/navigation/panels.js';
import type { CadPreferenceSource } from '../workspace/index.js';
import type { LiveViewBinding } from '../kit/shell/liveBinding.js';

// TEST SCAFFOLDING, registered by the browser-test harness alone and by nothing
// that ships: see `HarnessRenderer.jsx` for why the shell needs a frame of its
// own. It lives beside the renderers rather than under `renderers/harness/`
// because the library build does not compile a `harness` directory, and a
// browser test must drive the COMPILED package — a second copy of the kit
// bundled from source would carry its own React contexts and never see the
// host's.
export interface HarnessRendererOptions { preferences: CadPreferenceSource; live?: LiveViewBinding<any>; }

export function createHarnessRenderer(services: HarnessRendererOptions) {
  return defineFileRenderer<{ services: HarnessRendererOptions }>({
    id: 'shell-harness',
    priority: 100,
    matches: (file) => /\.harness$/i.test(file.path),
    // Fullscreen is the shell's (its controls, its presentation camera), and a renderer only
    // reaches it by declaring it: this frame declares it so the shell's fullscreen is driven here.
    fullscreen: true,
    panels: ({ ready }) => viewerPanels(ready),
    async prepare() { return { data: { services } }; },
    load: () => import('./HarnessRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<{ services: HarnessRendererOptions }>> }>
  });
}
