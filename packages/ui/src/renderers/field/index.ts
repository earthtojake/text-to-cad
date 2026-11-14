import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import type { LiveViewBinding } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

export interface FieldRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /** Host requests. One to select a reference is consumed and declined in words: a field has none. */
  commands?: ViewerCommandSource;
  /** The mounted view's live command surface. Selection commands are declined, loudly. */
  live?: LiveViewBinding<any>;
}
export interface PreparedFieldDocument extends PreparedWorkspaceEntry {
  services: Omit<FieldRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/** An implicit model: a field, which the engine answers as what to march it with. */
export const FIELD_FILE = /\.gsl$/i;

/** A `.gsl` is shown as its field, marched in the view with no mesh of it. Registers without loading three.js, a viewport or a backend connection. */
export function createFieldRenderer({ client, ...options }: FieldRendererOptions) {
  const services = { ...options, preferences: options.preferences || createCadPreferences() };
  return defineFileRenderer<PreparedFieldDocument>({
    id: 'field',
    priority: 100,
    matches: (file) => FIELD_FILE.test(file.path),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { ...prepared, data: { ...prepared.data, services } };
    },
    load: () => import('./FieldRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedFieldDocument>> }>
  });
}
