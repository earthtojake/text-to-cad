import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import type { LiveViewBinding } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

export interface DxfRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /** Host requests. One to select a reference is consumed and declined in words: a DXF has none. */
  commands?: ViewerCommandSource;
  /** The mounted view's live command surface. Camera, Display and selection commands are declined, loudly. */
  live?: LiveViewBinding<any>;
}
export interface PreparedDxfDocument extends PreparedWorkspaceEntry {
  services: Omit<DxfRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/** The 2D drawing format. A DXF is never artifact-managed: the backend renders the file as it is. */
export const DXF_FILE = /\.dxf$/i;

/**
 * A `.dxf` is a straight 2D render: the backend flattens it with ezdxf and the
 * client paints the primitives on a canvas.
 *
 * It declares NO panel. There is no Inspector for a drawing — no Display
 * settings, no Material, no Bends, no Layers — so the navbar shows no toggle for
 * one, and the file tree stays the only panel a DXF tab can open. Registering
 * loads no three.js, no viewport and no backend connection.
 */
export function createDxfRenderer({ client, ...options }: DxfRendererOptions) {
  const services = { ...options, preferences: options.preferences || createCadPreferences() };
  return defineFileRenderer<PreparedDxfDocument>({
    id: 'dxf',
    priority: 100,
    matches: (file) => DXF_FILE.test(file.path),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { data: { ...prepared.data, services }, dispose: prepared.dispose };
    },
    load: () => import('./DxfRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedDxfDocument>> }>
  });
}
