import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import type { LiveViewBinding } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

export interface MeshRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /** Host requests. One to select a reference is consumed and declined in words: a mesh has none. */
  commands?: ViewerCommandSource;
  /** The mounted view's live command surface. Selection commands are declined, loudly. */
  live?: LiveViewBinding<any>;
}
export interface PreparedMeshDocument extends PreparedWorkspaceEntry {
  services: Omit<MeshRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/** The triangle-mesh formats: a surface and, in a 3MF, its objects' colours. Nothing else is in the file. */
export const MESH_FILE = /\.(?:stl|3mf)$/i;

/** An `.stl` or `.3mf` is shown as its triangles. Registers without loading three.js, a viewport or a backend connection. */
export function createMeshRenderer({ client, ...options }: MeshRendererOptions) {
  const services = { ...options, preferences: options.preferences || createCadPreferences() };
  return defineFileRenderer<PreparedMeshDocument>({
    id: 'mesh',
    priority: 100,
    matches: (file) => MESH_FILE.test(file.path),
    // A mesh has no settings of its own: only Display, which never opens by itself, so the
    // model gets the room.
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { data: { ...prepared.data, services }, dispose: prepared.dispose };
    },
    load: () => import('./MeshRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedMeshDocument>> }>
  });
}
