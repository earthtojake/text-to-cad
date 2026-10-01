import type { Bridge, ToolResult } from './bridge';
import { readLaunch, type Launch } from './server';

const textOf = (result: ToolResult) => result.content?.find(part => part.type === 'text')?.text || 'CAD could not open.';

/**
 * The same view, launched again in today's terms: a tab the host restores from an older build
 * replays the launch it was first opened with, which this page no longer reads. The sidebar's home,
 * a thread's tab, a file's tab or an agent's model, as that launch was.
 */
export async function relaunch(bridge: Pick<Bridge, 'callTool'>, stale: Launch): Promise<Launch> {
  const call = async (name: string, args: Record<string, unknown>) => {
    const result = await bridge.callTool(name, args);
    const fresh = readLaunch(result);
    if (!fresh) throw new Error(textOf(result));
    return fresh;
  };
  if (stale.page === 'home') return call('cad_home', {});
  if (!stale.model) return call('cad_tab', {});
  if (stale.surface === 'file') return call('cad_file', { file: { name: stale.model.split(/[\\/]/).pop(), resourceUri: new URL(`file://${stale.model}`).href } });
  return { ...(await call('cad_launch', { model: stale.model })), surface: stale.surface };
}
