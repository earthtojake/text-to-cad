import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import type { LiveViewBinding } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

export interface XbfRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /** Host requests. One to select a reference is consumed and declined in words. */
  commands?: ViewerCommandSource;
  /** The mounted view's live command surface. */
  live?: LiveViewBinding<any>;
}
export interface PreparedXbfDocument extends PreparedWorkspaceEntry {
  services: Omit<XbfRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/** A cadgen engine document: B-rep parts placed by instances, every face, edge and vertex named. */
export const XBF_FILE = /\.xbf$/i;
/** What the cadgen engine reads and serves as a document: its own, and a STEP. */
export const ENGINE_DOCUMENT_FILE = /\.(?:xbf|step|stp)$/i;

/**
 * An `.xbf` or a STEP is drawn from what the cadgen engine serves of it (its structure and one
 * buffer per part), read by the page through the viewer (`client.engineDocument`). Registers
 * without loading three.js, a viewport or a backend connection.
 */
export function createXbfRenderer({ client, ...options }: XbfRendererOptions) {
  const services = { ...options, preferences: options.preferences || createCadPreferences() };
  return defineFileRenderer<PreparedXbfDocument>({
    id: 'xbf',
    // An .xbf and a STEP are this one's, above any renderer that takes whatever the viewer calls CAD,
    // and so is a document the engine holds by its id alone (a model's: `cad-document`).
    priority: 110,
    matches: (file) => ENGINE_DOCUMENT_FILE.test(file.path) || file.mediaType === 'cad-document',
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { ...prepared, data: { ...prepared.data, services } };
    },
    load: () => import('./XbfRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedXbfDocument>> }>
  });
}
