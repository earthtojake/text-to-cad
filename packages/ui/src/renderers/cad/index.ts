import { createCadPreferences, prepareWorkspaceEntry, type CadPreferenceSource, type PreparedWorkspaceEntry, type WorkspaceClientOption } from "../workspace/index.js";
export { createCadPreferences, CAD_LEGACY_PREFERENCE_KEYS } from "../workspace/index.js";
export type { CadPreferences, CadPreferenceSource } from "../workspace/index.js";
import type { PromptContext, PromptReference } from '@hardcore/core/prompt';
import type { ComponentType } from 'react';
import { isCadFile } from '@hardcore/core/lib/fileFormats.js';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import { inspectorPanels } from '../../file-viewer/navigation/panels.js';

export type { CadLiveBinding, CadLiveController, CadLiveState, CadCameraSnapshot } from './live.js';
import type { CadLiveBinding } from './live.js';

export interface CadSelectionSlotProps {
  selection: readonly PromptReference[];
  selectionKey: string;
  disabled: boolean;
  /** Capture belongs to this source/selection. Host delivery still binds its own destination. */
  createContext(options?: { text?: string; capture?: boolean }): PromptContext;
}
export interface CadRendererSlots { selectionExtras?: ComponentType<CadSelectionSlotProps> }
export interface CadCommands {
  selectReference?: { selector: string; key?: string | number } | null;
  captureRequest?: { key: string | number } | null;
}
export interface CadCommandSource {
  subscribe(listener: () => void): () => void;
  getSnapshot(): CadCommands;
  /** Remove only this admitted command; a later nonce must survive an old acknowledgement. */
  acknowledge?(kind: keyof CadCommands, key: string | number): void;
}
export interface CadRendererOptions {
  client: WorkspaceClientOption;
  slots?: CadRendererSlots;
  commands?: CadCommandSource;
  live?: CadLiveBinding;
  preferences?: CadPreferenceSource;
}
export interface PreparedCadDocument extends PreparedWorkspaceEntry {
  services: Omit<CadRendererOptions, 'client'>;
}

// A native glTF scene, a triangle mesh and a robot description have their own renderers
// (`renderers/glb`, `renderers/mesh`, `renderers/robot`).
const OTHER_RENDERERS_FILE = /\.(?:glb|stl|3mf|urdf|srdf|sdf)$/i;

/** Registers CAD without loading Three.js, a viewport, or a backend connection. */
export function createCadRenderer({ client, ...services }: CadRendererOptions) {
  services.preferences ||= createCadPreferences();
  return defineFileRenderer<PreparedCadDocument>({
    id: 'cad',
    priority: 100,
    matches: (file) => !OTHER_RENDERERS_FILE.test(file.path) && (file.mediaType === 'cad' || Boolean(isCadFile(file.path))),
    panels: ({ ready }) => inspectorPanels(ready),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { data: { ...prepared.data, services }, dispose: prepared.dispose };
    },
    load: () => import('./CadRenderer.js')
  });
}
