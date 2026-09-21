import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import { inspectorPanels } from '../../file-viewer/navigation/panels.js';
import type { LiveViewBinding } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

export interface DxfRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /** Host requests. One to select a reference is consumed and declined in words: a DXF has none. */
  commands?: ViewerCommandSource;
  /** The mounted view's live command surface. Selection commands are declined, loudly. */
  live?: LiveViewBinding<any>;
}
export interface PreparedDxfDocument extends PreparedWorkspaceEntry {
  services: Omit<DxfRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/** The 2D drawing format. A DXF is never artifact-managed: the client parses the file itself. */
export const DXF_FILE = /\.dxf$/i;

/** A `.dxf` is shown as a flat pattern, or as its line-work. Registers without loading three.js,
 *  a viewport or a backend connection. */
export function createDxfRenderer({ client, ...options }: DxfRendererOptions) {
  const services = { ...options, preferences: options.preferences || createCadPreferences() };
  return defineFileRenderer<PreparedDxfDocument>({
    id: 'dxf',
    priority: 100,
    matches: (file) => DXF_FILE.test(file.path),
    // A drawing's own settings live in the Inspector (Material, Bends, Layers), so it opens with them.
    panels: ({ ready }) => inspectorPanels(ready, { defaultOpen: true }),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { data: { ...prepared.data, services }, dispose: prepared.dispose };
    },
    load: () => import('./DxfRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedDxfDocument>> }>
  });
}
