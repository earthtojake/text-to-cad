import type { CadWorkspaceService, CadEntry, CadRenderSession, CadServerInfo } from '@hardcore/core/client';
import type { PrepareContext, PreparedDocument } from '../../file-viewer/types.js';

/** The backend connection a viewer renderer is registered with: ready, or obtained when a file first needs it. */
export type WorkspaceClientOption = CadWorkspaceService | ((context: PrepareContext) => Promise<CadWorkspaceService>);

/** What every viewer renderer's document starts from: the catalog entry, its server and a render session. */
export interface PreparedWorkspaceEntry {
  entry: CadEntry;
  client: CadWorkspaceService;
  serverInfo: CadServerInfo;
  renderSession: CadRenderSession;
}

/**
 * Resolve one file against the workspace backend. Construction of a renderer
 * fetches nothing; this runs when the host selected that renderer for a file.
 * The prepared document owns the render session and releases it.
 */
export async function prepareWorkspaceEntry(client: WorkspaceClientOption, context: PrepareContext): Promise<PreparedDocument<PreparedWorkspaceEntry>> {
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
  return { data: { entry, serverInfo, client: connection, renderSession }, dispose: () => renderSession.dispose() };
}
