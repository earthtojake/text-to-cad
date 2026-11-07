import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import type { LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

/**
 * A schematic's live state is the base state, its selection the references a person or a host picked
 * (`divider.kicad_sch#R1.2`), plus the sheet shown as a snapshot job reads it (`{ sheet, border }`: a snapshot is
 * drawn light, whatever the viewer's theme).
 * It has no camera: `resetCamera` fits the sheet again.
 */
export type SchematicLiveState = LiveViewState & {
  schematicDisplay?: { sheet: string; border: boolean };
};
export type SchematicLiveController = LiveViewController<SchematicLiveState>;

export interface SchematicRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /** Host requests. One to select a reference selects it, showing the sheet it is on (`#U3`, `#U3.7`, `#net:VIN`, `#sheet:/Power/`). */
  commands?: ViewerCommandSource;
  /** The mounted view's live command surface. `select` and `clearSelection` are the schematic's; camera and Display commands are declined, loudly. */
  live?: LiveViewBinding<any>;
}
export interface PreparedSchematicDocument extends PreparedWorkspaceEntry {
  services: Omit<SchematicRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/** A KiCad schematic. Never artifact-managed: the backend draws the files as they are. */
export const SCHEMATIC_FILE = /\.kicad_sch$/i;

/**
 * A `.kicad_sch` is a flat view, as a board is: the backend reads the hierarchy from its files and
 * answers a sheet at a time (`GET /api/v1/documents/kicad_sch/<id>/plot?sheet=<path>`), and the client
 * paints it on a canvas, with Select, Annotate and Measure, its Hierarchy and Circuit in the view's panel,
 * and its Export. Registering loads no three.js, no viewport and no backend connection.
 *
 * It still opens a render session it never draws from, as a board does: that session is what registers
 * the file as OPEN with the client, which is how a rewritten sheet reaches this tab.
 */
export function createSchematicRenderer({ client, ...options }: SchematicRendererOptions) {
  const services = { ...options, preferences: options.preferences || createCadPreferences() };
  return defineFileRenderer<PreparedSchematicDocument>({
    id: 'schematic',
    priority: 100,
    matches: (file) => SCHEMATIC_FILE.test(file.path),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { ...prepared, data: { ...prepared.data, services } };
    },
    // The renderer, with the file menu's Export of the schematic (`workspace/withFileExport.jsx`).
    load: async () => {
      const [{ default: Schematic }, { withFileExport }] = await Promise.all([import('./SchematicRenderer.jsx'), import('../workspace/withFileExport.jsx')]);
      return { default: withFileExport(Schematic) as ComponentType<FileRendererProps<PreparedSchematicDocument>> };
    }
  });
}
