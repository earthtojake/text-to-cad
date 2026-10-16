// Viewer preferences are the workspace module's, shared by every renderer:
// a host reads them from `@text-to-cad/ui/renderers/workspace`, not through a slice.
import { createCadPreferences, prepareWorkspaceEntry, type CadPreferenceSource, type PreparedWorkspaceEntry, type ViewerCommandSource, type WorkspaceClientOption } from "../workspace/index.js";
import { isCadFile } from '@text-to-cad/core/lib/fileFormats.js';
import { defineFileRenderer } from '../../file-viewer/registry.js';

export type { CadLiveBinding, CadLiveController, CadLiveState, CadCameraSnapshot } from './live.js';
import type { CadLiveBinding } from './live.js';

export interface StepRendererOptions {
  client: WorkspaceClientOption;
  /** The host's requests every viewer answers (`@text-to-cad/ui/renderers/workspace`). */
  commands?: ViewerCommandSource;
  live?: CadLiveBinding;
  preferences?: CadPreferenceSource;
}
export interface PreparedStepDocument extends PreparedWorkspaceEntry {
  services: Omit<StepRendererOptions, 'client'>;
}

// A 2D drawing, a KiCad board or schematic, a wiring harness, a native glTF scene, a triangle mesh
// and a robot description have their own renderers (`renderers/dxf`, `renderers/plot`,
// `renderers/glb`, `renderers/mesh`, `renderers/robot`).
const OTHER_RENDERERS_FILE = /\.(?:dxf|kicad_pcb|kicad_sch|harness\.yml|glb|stl|3mf|urdf|srdf|sdf)$/i;

/** Registers STEP without loading Three.js, a viewport, or a backend connection. */
export function createStepRenderer({ client, ...services }: StepRendererOptions) {
  services.preferences ||= createCadPreferences();
  return defineFileRenderer<PreparedStepDocument>({
    id: 'step',
    priority: 100,
    matches: (file) => !OTHER_RENDERERS_FILE.test(file.path) && (file.mediaType === 'cad' || Boolean(isCadFile(file.path))),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { ...prepared, data: { ...prepared.data, services } };
    },
    load: () => import('./StepRenderer.js')
  });
}
