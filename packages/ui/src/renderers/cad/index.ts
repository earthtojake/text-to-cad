import { createCadPreferences, type CadPreferenceSource } from "./preferences.js";
export { createCadPreferences, CAD_LEGACY_PREFERENCE_KEYS } from "./preferences.js";
export type { CadPreferences, CadPreferenceSource } from "./preferences.js";
import type { CadClient, CadEntry, CadRenderSession, CadServerInfo } from '@hardcore/core/client';
import { isCadFile } from '@hardcore/core/lib/fileFormats.js';
import { defineFileRenderer } from '../../file-viewer/registry.js';
import type { PrepareContext } from '../../file-viewer/types.js';
import { cadPanels } from '../../file-viewer/navigation/panels.js';

export interface CadReference { file: string; selector: string; label?: string; text?: string }
export interface CadCapture { blob: Blob; file: string; references?: CadReference[] }
export interface CadPromptContext { text: string; references: CadReference[] }
export interface CadCommands {
  selectReference?: { selector: string; key?: string | number } | null;
  captureRequest?: { key: string | number } | null;
}
export interface CadCommandSource {
  subscribe(listener: () => void): () => void;
  getSnapshot(): CadCommands;
}
export interface CadRendererOptions {
  client: CadClient | ((context: PrepareContext) => Promise<CadClient>);
  onReference?: (reference: CadReference) => void;
  onPromptContext?: (context: CadPromptContext) => void;
  onCapture?: (capture: CadCapture) => void;
  commands?: CadCommandSource;
  preferences?: CadPreferenceSource;
}
export interface PreparedCadDocument {
  entry: CadEntry;
  client: CadClient;
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
    panels: ({ ready }) => cadPanels(ready),
    async prepare(context) {
      const connection = typeof client === 'function' ? await client(context) : client;
      context.signal.throwIfAborted();
      const [entry, serverInfo] = await Promise.all([
        connection.resolveEntry(context.file.path, { signal: context.signal }),
        connection.serverInfo({ signal: context.signal })
      ]);
      context.signal.throwIfAborted();
      const renderSession = connection.createRenderSession();
      return { data: { entry, serverInfo, client: connection, renderSession, services }, dispose: () => renderSession.dispose() };
    },
    load: () => import('./CadRenderer.js')
  });
}
