// Viewer preferences are the workspace module's, shared by every renderer:
// a host reads them from `@hardcore/ui/renderers/workspace`, not through a slice.
import { createCadPreferences, prepareWorkspaceEntry, type CadPreferenceSource, type PreparedWorkspaceEntry, type ViewerCommandSource, type WorkspaceClientOption } from "../workspace/index.js";
import type { PromptContext, PromptReference } from '@hardcore/core/prompt';
import type { ComponentType } from 'react';
import { isCadFile } from '@hardcore/core/lib/fileFormats.js';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import { viewerPanels } from '../../file-viewer/navigation/panels.js';

export type { CadLiveBinding, CadLiveController, CadLiveState, CadCameraSnapshot } from './live.js';
import type { CadLiveBinding } from './live.js';

export interface StepSelectionSlotProps {
  selection: readonly PromptReference[];
  selectionKey: string;
  disabled: boolean;
  /** Capture belongs to this source/selection. Host delivery still binds its own destination. */
  createContext(options?: { text?: string; capture?: boolean }): PromptContext;
}
export interface StepRendererSlots { selectionExtras?: ComponentType<StepSelectionSlotProps> }
export interface StepRendererOptions {
  client: WorkspaceClientOption;
  slots?: StepRendererSlots;
  /** The host's requests every viewer answers (`@hardcore/ui/renderers/workspace`). */
  commands?: ViewerCommandSource;
  live?: CadLiveBinding;
  preferences?: CadPreferenceSource;
}
export interface PreparedStepDocument extends PreparedWorkspaceEntry {
  services: Omit<StepRendererOptions, 'client'>;
}

// A 2D drawing, a native glTF scene, a triangle mesh and a robot description have their own
// renderers (`renderers/dxf`, `renderers/glb`, `renderers/mesh`, `renderers/robot`).
const OTHER_RENDERERS_FILE = /\.(?:dxf|glb|stl|3mf|urdf|srdf|sdf)$/i;

/** Registers STEP without loading Three.js, a viewport, or a backend connection. */
export function createStepRenderer({ client, ...services }: StepRendererOptions) {
  services.preferences ||= createCadPreferences();
  return defineFileRenderer<PreparedStepDocument>({
    id: 'step',
    priority: 100,
    matches: (file) => !OTHER_RENDERERS_FILE.test(file.path) && (file.mediaType === 'cad' || Boolean(isCadFile(file.path))),
    // Its own panel is named for what the file is, with the icon its Features tree draws for it.
    panels: ({ ready }) => viewerPanels(ready, { file: true }),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { data: { ...prepared.data, services }, dispose: prepared.dispose };
    },
    load: () => import('./StepRenderer.js')
  });
}
