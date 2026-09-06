import type { Logger } from '@emdash/shared/logger';
import { containsAbsolute, parseAbsolute, type HostAbsolutePath } from '#primitives/path/api';
import type { HostRuntimesClient } from '#services/runtime-broker/api';

export type WorkspaceSessionClients = Pick<HostRuntimesClient, 'acp' | 'terminals' | 'tuiAgents'>;

/** Everything deactivateWorkspace needs from the session plane. */
export type SessionKiller = (workspacePath: string) => Promise<void>;

/**
 * The staleness guards' session probe (pr-workspace-model spec): how many live
 * ACP/TUI/terminal sessions run under the workspace path — exactly the set
 * deactivateWorkspace would kill. "Active" for the update/follow guards means
 * this count is non-zero.
 */
export type SessionCounter = (workspacePath: string) => Promise<number>;

export function createSessionCounter(clients: WorkspaceSessionClients): SessionCounter {
  return async (workspacePath) => {
    const parsed = parseAbsolute(workspacePath);
    if (!parsed.success) return 0;
    const root = parsed.data;

    const [terminalSnapshot, acpSnapshot, tuiSnapshot] = await Promise.all([
      clients.terminals.sessions.state(undefined, 'list').snapshot(),
      clients.acp.sessions.state(undefined, 'list').snapshot(),
      clients.tuiAgents.sessions.state(undefined, 'list').snapshot(),
    ]);

    let count = 0;
    for (const session of Object.values(acpSnapshot.data)) {
      if (cwdUnder(root, session.cwd)) count += 1;
    }
    for (const session of Object.values(tuiSnapshot.data)) {
      if (cwdUnder(root, session.cwd)) count += 1;
    }
    for (const session of Object.values(terminalSnapshot.data)) {
      if (containsAbsolute(root, session.key.workspace.path)) count += 1;
    }
    return count;
  };
}

/**
 * Kills every ACP, TUI, and terminal session whose cwd falls under the workspace path.
 * Best-effort by contract: deactivation must always reach teardown, so individual kill
 * failures are logged, never thrown.
 */
export function createSessionKiller(
  clients: WorkspaceSessionClients,
  logger?: Logger
): SessionKiller {
  return async (workspacePath) => {
    const parsed = parseAbsolute(workspacePath);
    if (!parsed.success) return;
    const root = parsed.data;

    const [terminalSnapshot, acpSnapshot, tuiSnapshot] = await Promise.all([
      clients.terminals.sessions.state(undefined, 'list').snapshot(),
      clients.acp.sessions.state(undefined, 'list').snapshot(),
      clients.tuiAgents.sessions.state(undefined, 'list').snapshot(),
    ]);

    for (const session of Object.values(acpSnapshot.data)) {
      if (!cwdUnder(root, session.cwd)) continue;
      const result = await clients.acp.kill({ conversationId: session.conversationId });
      if (!result.success) {
        logger?.warn?.(`failed to kill ACP session ${session.conversationId}`, {
          error: result.error,
        });
      }
    }

    for (const session of Object.values(tuiSnapshot.data)) {
      if (!cwdUnder(root, session.cwd)) continue;
      const result = await clients.tuiAgents.delete({ conversationId: session.conversationId });
      if (!result.success) {
        logger?.warn?.(`failed to delete TUI session ${session.conversationId}`, {
          error: result.error,
        });
      }
    }

    for (const session of Object.values(terminalSnapshot.data)) {
      if (!containsAbsolute(root, session.key.workspace.path)) continue;
      const result = await clients.terminals.kill({ key: session.key });
      if (!result.success) {
        logger?.warn?.(`failed to kill terminal session ${session.key.id}`, {
          error: result.error,
        });
      }
    }
  };
}

function cwdUnder(root: HostAbsolutePath, cwd: string | null | undefined): boolean {
  if (!cwd) return false;
  const parsed = parseAbsolute(cwd);
  return parsed.success && containsAbsolute(root, parsed.data);
}
