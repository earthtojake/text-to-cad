import type { ComponentType } from 'react';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { FileRendererProps } from '../../file-viewer/types.js';
import { inspectorPanels } from '../../file-viewer/navigation/panels.js';
import type { LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';
import { createCadPreferences, prepareWorkspaceEntry } from '../workspace/index.js';
import type { CadPreferenceSource, PreparedWorkspaceEntry, ViewerCommandSource, WorkspaceClientOption } from '../workspace/index.js';

export type { LiveCameraSnapshot, LiveViewBinding, LiveViewController, LiveViewState } from '../kit/shell/liveBinding.js';

/** The live state of a mounted robot: the base state, plus what is selected in it. */
export interface RobotLiveState extends LiveViewState {
  /** The selected link, as the description names it. */
  selectedLinks: readonly string[];
  /** The selected mesh parts: a link's parts, or the named objects picked. */
  selectedPartIds: readonly string[];
}
export interface RobotLiveController extends LiveViewController<RobotLiveState> {
  clearSelection(): Promise<RobotLiveState>;
}
export interface RobotRendererOptions {
  client: WorkspaceClientOption;
  preferences?: CadPreferenceSource;
  /** Host requests. One to select a reference is consumed and declined in words: a robot description has none. */
  commands?: ViewerCommandSource;
  /** The mounted view's live command surface. `select` is declined, loudly; `clearSelection` clears the link selection. */
  live?: LiveViewBinding<any>;
}
export interface PreparedRobotDocument extends PreparedWorkspaceEntry {
  services: Omit<RobotRendererOptions, 'client'> & { preferences: CadPreferenceSource };
}

/** The robot descriptions: links joined by joints. An SRDF is shown on the URDF it is about; an SDF is read as one model. */
export const ROBOT_FILE = /\.(?:urdf|srdf|sdf)$/i;

/** A `.urdf`, `.srdf` or `.sdf` is shown as its kinematic tree. Registers without loading three.js, a viewport or a backend connection. */
export function createRobotRenderer({ client, ...options }: RobotRendererOptions) {
  const services = { ...options, preferences: options.preferences || createCadPreferences() };
  return defineFileRenderer<PreparedRobotDocument>({
    id: 'robot',
    priority: 100,
    matches: (file) => ROBOT_FILE.test(file.path),
    // A robot opens onto its joints: the Inspector starts open, on Kinematics.
    panels: ({ ready }) => inspectorPanels(ready, { defaultOpen: true }),
    async prepare(context) {
      const prepared = await prepareWorkspaceEntry(client, context);
      return { data: { ...prepared.data, services }, dispose: prepared.dispose };
    },
    load: () => import('./RobotRenderer.jsx') as Promise<{ default: ComponentType<FileRendererProps<PreparedRobotDocument>> }>
  });
}
