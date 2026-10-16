import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import type { LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

/**
 * A plot's live state is the base state and nothing more. It has no camera and no zoom
 * command: `resetCamera` fits the plot again, and everything else about the view is the
 * pointer's. A board reports its selection, in board references.
 */
export type PlotLiveState = LiveViewState;
export type PlotLiveController = LiveViewController<PlotLiveState>;

export interface PlotRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /**
   * Host requests. One to select a reference selects it on a board read with its index (`#U3`,
   * `#U3.9`, `#net:VIN`), and is consumed without a selection while the board has none.
   */
  commands?: ViewerCommandSource;
  /**
   * The mounted view's live command surface. Camera and Display commands are declined, loudly;
   * `select` and `clearSelection` are the board's (in board references).
   */
  live?: LiveViewBinding<any>;
}
export interface PreparedPlotDocument extends PreparedWorkspaceEntry {
  services: Omit<PlotRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/** The documents shown as a plot: a KiCad board. */
export const PLOT_FILE = /\.kicad_pcb$/i;

/**
 * A KiCad board is a straight 2D render: the backend draws it from its file, layer by layer
 * (`GET /__cad/plot`), and the client draws the layers on a canvas.
 *
 * It declares NO panel: its tools are its own tool stack over the canvas, and its Display settings
 * are among the view's controls in the navbar, as a 3D file's are, so the file tree stays the only
 * panel its tab can open. Registering loads no three.js, no viewport and no backend connection.
 *
 * It still opens a render session it never draws from, as a DXF does: that session is what
 * registers the file as OPEN with the client, which is how a rewritten board reaches this tab.
 */
export function createPlotRenderer({ client, ...options }: PlotRendererOptions) {
  const services = { ...options, preferences: options.preferences || createCadPreferences() };
  return defineFileRenderer<PreparedPlotDocument>({
    id: 'plot',
    priority: 100,
    matches: (file) => PLOT_FILE.test(file.path),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { ...prepared, data: { ...prepared.data, services } };
    },
    load: () => import('./PlotRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedPlotDocument>> }>
  });
}
