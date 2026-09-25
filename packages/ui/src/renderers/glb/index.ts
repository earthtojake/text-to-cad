import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import type { LiveViewBinding } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

export interface GlbRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /** Host requests. One to select a reference is consumed and declined in words: a GLB has none. */
  commands?: ViewerCommandSource;
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
    // A GLB has no settings of its own: only Display, which never opens by itself, so the
    // model gets the room.
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { data: { ...prepared.data, services }, dispose: prepared.dispose };
    },
    load: () => import('./GlbRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedGlbDocument>> }>
  });
}
