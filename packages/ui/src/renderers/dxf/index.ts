import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import type { LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

/** The live state of a mounted drawing: the base state, plus how far it is zoomed. */
export interface DxfLiveState extends LiveViewState {
  /**
   * The current scale as a percentage of the FITTED one, so 100 is the whole
   * drawing as it opens. Relative because an absolute scale means nothing: the
   * same drawing in metres and in millimetres would read a thousand apart.
   */
  zoomPercent: number;
}
export interface DxfLiveController extends LiveViewController<DxfLiveState> {
  /** Zoom to a percentage of the fitted view, about the pane's centre. */
  setZoom(percent: number): Promise<DxfLiveState>;
}

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
      return { data: { ...prepared.data, services }, dispose: prepared.dispose };
    },
    load: () => import('./DxfRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedDxfDocument>> }>
  });
}
