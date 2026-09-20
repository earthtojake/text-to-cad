import { createCadPreferences, type CadPreferenceSource } from "./preferences.js";
export { createCadPreferences, CAD_LEGACY_PREFERENCE_KEYS } from "./preferences.js";
export type { CadPreferences, CadPreferenceSource } from "./preferences.js";
import type { CadWorkspaceService, CadEntry, CadRenderSession, CadServerInfo } from '@hardcore/core/client';
import type { PromptContext, PromptReference } from '@hardcore/core/prompt';
import type { ComponentType } from 'react';
import { isCadFile } from '@hardcore/core/lib/fileFormats.js';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { PrepareContext } from '../../file-viewer/types.js';
import { cadPanels } from '../../file-viewer/navigation/panels.js';

export type { CadLiveBinding, CadLiveController, CadLiveState, CadCameraSnapshot } from './live.js';
import type { CadLiveBinding } from './live.js';

export interface CadSelectionSlotProps {
  selection: readonly PromptReference[];
  selectionKey: string;
  disabled: boolean;
  /** Capture belongs to this source/selection. Host delivery still binds its own destination. */
  createContext(options?: { text?: string; capture?: boolean }): PromptContext;
}
export interface CadRendererSlots { selectionExtras?: ComponentType<CadSelectionSlotProps> }
export interface CadCommands {
  selectReference?: { selector: string; key?: string | number } | null;
  captureRequest?: { key: string | number } | null;
}
export interface CadCommandSource {
  subscribe(listener: () => void): () => void;
  getSnapshot(): CadCommands;
  /** Remove only this admitted command; a later nonce must survive an old acknowledgement. */
  acknowledge?(kind: keyof CadCommands, key: string | number): void;
}
export interface CadRendererOptions {
  client: CadWorkspaceService | ((context: PrepareContext) => Promise<CadWorkspaceService>);
  slots?: CadRendererSlots;
  commands?: CadCommandSource;
  live?: CadLiveBinding;
  preferences?: CadPreferenceSource;
}
export interface PreparedCadDocument {
  entry: CadEntry;
  client: CadWorkspaceService;
  serverInfo: CadServerInfo;
  renderSession: CadRenderSession;
  services: Omit<CadRendererOptions, 'client'>;
}

/** Registers CAD without loading Three.js, a viewport, or a backend connection. */
export function createCadRenderer({ client, ...services }: CadRendererOptions) {
  services.preferences ||= createCadPreferences();
  return defineFileRenderer<PreparedCadDocument>({
    id: 'cad',
    priority: 100,
    matches: (file) => file.mediaType === 'cad' || Boolean(isCadFile(file.path)),
    panels: ({ ready, file }) => cadPanels(ready, file),
    async prepare(context) {
      const connection = typeof client === 'function' ? await client(context) : client;
      context.signal.throwIfAborted();
      if (context.refresh) await connection.refresh({ file: context.file.path, signal: context.signal, markRefreshing: false });
      context.signal.throwIfAborted();
      const [entry, serverInfo] = await Promise.all([
        connection.resolveEntry(context.file.path, { signal: context.signal }),
        connection.serverInfo({ signal: context.signal })
      ]);
      context.signal.throwIfAborted();
      const renderSession = connection.createRenderSession({ file: context.file.path });
      return { data: { entry, serverInfo, client: connection, renderSession, services }, dispose: () => renderSession.dispose() };
    },
    load: () => import('./CadRenderer.js')
  });
}
