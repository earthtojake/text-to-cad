import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import type { LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

/**
 * A board's live state is the base state, its selection the board references a person or a host
 * picked (`blinky.kicad_pcb#R1.2`), plus the board's Display as a snapshot job reads it. It has no
 * camera and no zoom command: `resetCamera` fits the board again; its Display is the person's.
 */
export type BoardLiveState = LiveViewState & {
  boardDisplay?: { mode: string; side: 'top' | 'bottom'; poured: boolean; layers?: string[] };
};
export type BoardLiveController = LiveViewController<BoardLiveState>;

export interface BoardRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /** Host requests. One to select a reference selects it on a board read with its index (`#U3`, `#U3.9`, `#net:VIN`). */
  commands?: ViewerCommandSource;
  /** The mounted view's live command surface. `select` and `clearSelection` are the board's; camera and Display commands are declined, loudly. */
  live?: LiveViewBinding<any>;
}
export interface PreparedBoardDocument extends PreparedWorkspaceEntry {
  services: Omit<BoardRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/** A KiCad board. Never artifact-managed: the backend draws the file as it is. */
export const BOARD_FILE = /\.kicad_pcb$/i;

/**
 * A `.kicad_pcb` is a flat view, as a `.dxf` is: the backend reads the board from its file, layer
 * by layer (`GET /__cad/plot`), and the client paints the layers on a canvas, with Select (its pads,
 * copper and parts), Annotate and Measure, its Board and Layers in the file sidebar, and its Display.
 * Registering loads no three.js, no viewport and no backend connection.
 *
 * It still opens a render session it never draws from, as a DXF does: that session is what
 * registers the file as OPEN with the client, which is how a rewritten board reaches this tab.
 */
export function createBoardRenderer({ client, ...options }: BoardRendererOptions) {
  const services = { ...options, preferences: options.preferences || createCadPreferences() };
  return defineFileRenderer<PreparedBoardDocument>({
    id: 'board',
    priority: 100,
    matches: (file) => BOARD_FILE.test(file.path),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { ...prepared, data: { ...prepared.data, services } };
    },
    load: () => import('./BoardRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedBoardDocument>> }>
  });
}
