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
  /** An app's own layers over the model, drawn in this order (`XbfLayer`). */
  layers?: readonly XbfLayer[];
}
/**
 * What an app's layer over an engine document's view is handed: the file and its scene (null
 * while it loads), the viewport (its runtime, the element its pointer events arrive on, the
 * element the canvas is mounted in, a tick that changes when the runtime is replaced, and
 * `commitScene()`), the faces and edges selected by their ids, `requestFrame()` to draw again
 * after the layer changed the scene, and `claimPicks(handler)`: each click on the model is
 * offered to `handler(hit, modifiers)` first, until the function it returns is called. `hit` is
 * what the click found (a part, or a face or an edge by its `id` and `kind`), null over empty
 * space; a handler that returns true takes the click, and the view's selection stays as it was.
 */
export interface XbfLayerProps {
  file: string;
  scene: unknown;
  viewport: { runtimeRef: object; hostRef: object; mountRef: object; viewerReadyTick: number; commitScene: () => boolean };
  selected: readonly string[];
  requestFrame(): void;
  claimPicks(handler: (hit: { id: string; kind?: string } | null, modifiers: { multiSelect: boolean }) => boolean): () => void;
}
/** One layer: drawn over the model's canvas beside the view's own overlays, keyed by `id`. */
export interface XbfLayer {
  id: string;
  Layer: ComponentType<XbfLayerProps>;
}
export interface PreparedXbfDocument extends PreparedWorkspaceEntry {
  services: Omit<XbfRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}
/** What the engine reads and serves as a document: its own, and a STEP. */
export const ENGINE_DOCUMENT_FILE = /\.(?:xbf|step|stp)$/i;

/**
 * An `.xbf` or a STEP is drawn from what the engine serves of it (its structure and one
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
