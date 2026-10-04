import type { CadWorkspaceService, CadEntry, CadRenderSession } from '@text-to-cad/core/client';
import type { PrepareContext, PreparedDocument } from '../../file-viewer/types.js';

/** The backend connection a viewer renderer is registered with: ready, or obtained when a file first needs it. */
export type WorkspaceClientOption = CadWorkspaceService | ((context: PrepareContext) => Promise<CadWorkspaceService>);

/** What every viewer renderer's document starts from: the catalog entry and a render session. */
export interface PreparedWorkspaceEntry {
  entry: CadEntry;
  client: CadWorkspaceService;
  renderSession: CadRenderSession;
}

/**
 * Resolve one file against the workspace backend. Construction of a renderer
 * fetches nothing; this runs when the host selected that renderer for a file.
 * The prepared document owns the render session and releases it. It is opened once:
 * the renderer reads this file's catalog entry as it changes (`useWorkspaceDocument`)
 * and loads a rewritten file's next revision behind the one on screen.
 */
export async function prepareWorkspaceEntry(client: WorkspaceClientOption, context: PrepareContext): Promise<PreparedDocument<PreparedWorkspaceEntry>> {
  const connection = typeof client === 'function' ? await client(context) : client;
  context.signal.throwIfAborted();
  if (context.refresh) await connection.refresh({ file: context.file.path, signal: context.signal, markRefreshing: false });
  context.signal.throwIfAborted();
  const entry = await connection.resolveEntry(context.file.path, { signal: context.signal });
  context.signal.throwIfAborted();
  const renderSession = connection.createRenderSession({ file: context.file.path });
  return { data: { entry, client: connection, renderSession }, dispose: () => renderSession.dispose() };
}
