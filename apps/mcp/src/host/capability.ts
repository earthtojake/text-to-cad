import type { HostContext, ToolResult } from './bridge';

/** Where CAD's server puts the page's capability (`cad_server/mcp/server.py`'s `_APP_TOKEN_META`). */
export const CAPABILITY_META = 'dev.texttocad/httpToken';

const tokenIn = (meta: unknown): string | null => {
  const token = meta && typeof meta === 'object' ? (meta as Record<string, unknown>)[CAPABILITY_META] : undefined;
  return typeof token === 'string' && token ? token : null;
};

/**
 * The capability every one of this page's calls carries (`host/server.ts`), as its host handed it over,
 * and never anything the model reads:
 *
 * - the launch's own result metadata (`_meta`), which Codex and Claude Desktop hand the page whole;
 * - else the tool that launched the page, as the host describes it at `ui/initialize`
 *   (`hostContext.toolInfo.tool`, MCP Apps), in its metadata: Cursor hands the page a result rebuilt
 *   from its transcript, content and structured content alone, and the tool whole, its metadata as
 *   `meta`. The server puts the capability there for Cursor alone (`host.carries_capability`).
 *
 * Null where neither carries one: the page then says it cannot connect (`Connection.tsx`).
 */
export function appCapability(result: Pick<ToolResult, '_meta'> | undefined, context: HostContext | undefined): string | null {
  const launched = tokenIn(result?._meta);
  if (launched) return launched;
  const info = context?.toolInfo as { tool?: { _meta?: unknown; meta?: unknown } } | undefined;
  return tokenIn(info?.tool?._meta) ?? tokenIn(info?.tool?.meta);
}
