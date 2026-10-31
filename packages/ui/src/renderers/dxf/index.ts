import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import type { LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

/**
 * A drawing's live state is the base state, its selection the references a person picked
 * (`drawing.dxf#h2F`), plus the handles of the entities picked. It has no camera and no zoom
 * command: `resetCamera` fits the drawing again, and everything else about the view is the pointer's.
 */
export type DxfLiveState = LiveViewState & { selectedEntities?: string[] };
export type DxfLiveController = LiveViewController<DxfLiveState>;

export interface DxfRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /** Host requests. One to select a reference is consumed and declined in words: a person picks a DXF's entities. */
  commands?: ViewerCommandSource;
  /** The mounted view's live command surface. Camera, Display and select commands are declined, loudly; clearSelection clears. */
  live?: LiveViewBinding<any>;
}
export interface PreparedDxfDocument extends PreparedWorkspaceEntry {
  services: Omit<DxfRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/** The 2D drawing format. A DXF is never artifact-managed: the backend renders the file as it is. */
export const DXF_FILE = /\.dxf$/i;

/**
 * A `.dxf` is a 2D render: the backend flattens it with ezdxf and the client
 * paints the primitives on a canvas, with Select (its entities, by handle),
 * Annotate and Measure, and a Layers section where the drawing has layers and
 * blocks to read.
 *
 * A drawing has no Display settings, no Material and no Bends. Registering loads
 * no three.js, no viewport and no backend connection.
 *
 * It still opens a render session it never draws from. That session is also
 * what registers the file as OPEN with the client, which is how a rewritten
 * `.dxf` reaches this tab; the worker retains it carries are refcounts, and
 * spawn nothing. Skipping them would mean a second kind of prepared document.
 */
export function createDxfRenderer({ client, ...options }: DxfRendererOptions) {
  const services = { ...options, preferences: options.preferences || createCadPreferences() };
  return defineFileRenderer<PreparedDxfDocument>({
    id: 'dxf',
    priority: 100,
    matches: (file) => DXF_FILE.test(file.path),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { ...prepared, data: { ...prepared.data, services } };
    },
    load: () => import('./DxfRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedDxfDocument>> }>
  });
}
