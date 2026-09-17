import { useSyncExternalStore, type ComponentType } from 'react';
import type { FileActivity, FileRendererProps, JsonValue } from '../../file-viewer/types.js';
import type { CadWorkspaceService, CadEntry, CadRenderSession, CadServerInfo } from '@hardcore/core/client';
import type { CadCommands, CadCommandSource, CadRendererSlots, PreparedCadDocument } from './index.js';
import type { ResourceRef } from '@hardcore/core/prompt';
import type { CadPreferences } from './preferences.js';
import CadFileView from './file-view/CadFileView.js';

const emptyCommands: CadCommands = Object.freeze({});
const emptySubscribe = () => () => {};
const getEmptyCommands = () => emptyCommands;
interface CadSurfaceProps {
  preferences: CadPreferences;
  onPreferenceChange(patch: Partial<CadPreferences>): void;
  client: CadWorkspaceService;
  entry: CadEntry;
  serverInfo: CadServerInfo;
  renderSession: CadRenderSession;
  onOpenFile(path: string): void;
  panelSlot: HTMLElement | null;
  colorScheme: 'light' | 'dark';
  openPanel: string;
  onPanelOpen(id: string): void;
  onChromeVisibilityChange(visible: boolean): void;
  onActivityChange(activity: FileActivity | null): void;
  onReload(): void;
  state: JsonValue | undefined;
  onStateChange(state: JsonValue): void;
  selectReference?: CadCommands['selectReference'];
  captureRequest?: CadCommands['captureRequest'];
  acknowledgeCommand?: CadCommandSource['acknowledge'];
  documentResource: ResourceRef;
  slots?: CadRendererSlots;
}
const Surface = CadFileView as ComponentType<CadSurfaceProps>;

export default function CadRenderer(props: FileRendererProps<PreparedCadDocument>) {
  const { data } = props;
  const commands = useSyncExternalStore(
    data.services.commands?.subscribe || emptySubscribe,
    data.services.commands?.getSnapshot || getEmptyCommands,
    getEmptyCommands
  );
  const preferences = useSyncExternalStore(data.services.preferences!.subscribe, data.services.preferences!.getSnapshot, data.services.preferences!.getSnapshot);
  return <Surface
    key={JSON.stringify([props.source.id, props.file.path])}
    preferences={preferences}
    onPreferenceChange={data.services.preferences!.update}
    client={data.client}
    entry={data.entry}
    serverInfo={data.serverInfo}
    renderSession={data.renderSession}
    onOpenFile={props.onOpenFile}
    panelSlot={props.panelSlot}
    colorScheme={props.appearance.colorScheme}
    openPanel={props.openPanel}
    onPanelOpen={props.onPanelOpen}
    onChromeVisibilityChange={props.onChromeVisibilityChange}
    onActivityChange={props.onActivityChange}
    onReload={props.reload}
    state={props.state}
    onStateChange={props.onStateChange}
    documentResource={{ kind: 'workspace-file', workspaceId: props.source.id, path: props.file.path, revision: String(data.entry.hash || props.file.revision || '') }}
    slots={data.services.slots}
    selectReference={commands.selectReference}
    captureRequest={commands.captureRequest}
    acknowledgeCommand={data.services.commands?.acknowledge}
  />;
}
