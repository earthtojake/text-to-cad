import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import { inspectorPanels } from '../../file-viewer/navigation/panels.js';
import type { LiveViewBinding } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

/**
 * Host requests. A snapshot of the view goes to the prompt; a request to select a
 * reference is consumed and declined in words, because a GLB has none.
 */
export interface GlbCommands {
  captureRequest?: { key: string | number } | null;
  selectReference?: { selector: string; key?: string | number } | null;
}
export interface GlbCommandSource {
  subscribe(listener: () => void): () => void;
  getSnapshot(): GlbCommands;
  /** Remove only this admitted command; a later nonce must survive an old acknowledgement. */
  acknowledge?(kind: keyof GlbCommands, key: string | number): void;
}
export interface GlbRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  commands?: GlbCommandSource;
  /** The mounted view's live command surface. Selection commands are declined, loudly. */
  live?: LiveViewBinding<any>;
}
export interface PreparedGlbDocument extends PreparedWorkspaceEntry {
  services: Omit<GlbRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/** A `.glb` is shown as its native glTF scene. Registers without loading three.js, a viewport or a backend connection. */
export function createGlbRenderer({ client, ...options }: GlbRendererOptions) {
  const services = { ...options, preferences: options.preferences || createCadPreferences() };
  return defineFileRenderer<PreparedGlbDocument>({
    id: 'glb',
    priority: 100,
    matches: (file) => /\.glb$/i.test(file.path),
    // The Inspector is the Display tab alone, so it starts shut and the model gets the room.
    panels: ({ ready }) => inspectorPanels(ready, { defaultOpen: false }),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { data: { ...prepared.data, services }, dispose: prepared.dispose };
    },
    load: () => import('./GlbRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedGlbDocument>> }>
  });
}
