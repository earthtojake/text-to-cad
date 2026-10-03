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
 * pointer's.
 */
export type PlotLiveState = LiveViewState;
export type PlotLiveController = LiveViewController<PlotLiveState>;

export interface PlotRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /** Host requests. One to select a reference is consumed and declined in words: a plot has none. */
  commands?: ViewerCommandSource;
  /** The mounted view's live command surface. Camera, Display and selection commands are declined, loudly. */
  live?: LiveViewBinding<any>;
}
export interface PreparedPlotDocument extends PreparedWorkspaceEntry {
  services: Omit<PlotRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/**
 * The documents shown as their own tool's plot: a KiCad board, a KiCad schematic, and a WireViz
 * wiring harness (`<name>.harness.yml`; a plain `.yml` is no CAD file).
 */
export const PLOT_FILE = /(?:\.kicad_(?:pcb|sch)|[^/\\]\.harness\.yml)$/i;

/**
 * A KiCad board or schematic, or a wiring harness, is a straight 2D render: the backend has its
 * own tool (KiCad, WireViz) plot it to SVG (`GET /__cad/plot`) and the client draws the sheets
 * on a canvas.
 *
 * It declares NO panel. A plot has nothing to configure — no Display settings, no layers — so
 * the navbar shows no toggle for one, and the file tree stays the only panel its tab can open.
 * Registering loads no three.js, no viewport and no backend connection.
 *
 * It still opens a render session it never draws from, as a DXF does: that session is what
 * registers the file as OPEN with the client, which is how a rewritten document reaches this tab.
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
