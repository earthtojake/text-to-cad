import { stat } from 'node:fs/promises';
import { ok, type Result } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import {
  containsAbsolute,
  formatAbsolute,
  parseAbsolute,
  type HostAbsolutePath,
} from '#primitives/path/api';
import type { WorkspaceSessionClients } from './session-cleanup';

export interface WorkspaceSessionGcOptions {
  clients: WorkspaceSessionClients;
  intervalMs: number;
  scope?: Scope;
  onError?: (error: unknown) => void;
}

/**
 * Background sweep for sessions whose workspace path vanished outside a registry
 * verb (an `rm -rf` behind the host's back): kills every ACP, TUI, and terminal
 * session under a definitively missing path. Moved from the retired workspace-host
 * runtime (spec §4.1) — deliberate teardown flows through deactivateWorkspace.
 */
export class WorkspaceSessionGc {
  private timer: NodeJS.Timeout | undefined;
  private running: Promise<void> | undefined;

  constructor(private readonly options: WorkspaceSessionGcOptions) {}

  start(): void {
    if (this.timer) return;
    this.timer = setInterval(() => {
      this.poke();
    }, this.options.intervalMs);
    this.timer.unref?.();
    this.options.scope?.add(() => this.dispose());
  }

  poke(): void {
    if (this.running) return;
    this.running = this.runOnce()
      .catch((error) => this.options.onError?.(error))
      .finally(() => {
        this.running = undefined;
      });
  }

  async runOnce(): Promise<void> {
    const paths = await this.missingSessionPaths();
    for (const path of paths) {
      const result = await killSessionsUnderPath(this.options.clients, path);
      if (!result.success) {
        this.options.onError?.(result.error);
      }
    }
  }

  dispose(): void {
    if (!this.timer) return;
    clearInterval(this.timer);
    this.timer = undefined;
  }

  private async missingSessionPaths(): Promise<HostAbsolutePath[]> {
    const candidates = await this.sessionPaths();
    const missing: HostAbsolutePath[] = [];
    for (const path of candidates) {
      if (await isDefinitivelyMissing(path)) {
        missing.push(path);
      }
    }
    return missing;
  }

  private async sessionPaths(): Promise<HostAbsolutePath[]> {
    const [terminalSnapshot, acpSnapshot, tuiSnapshot] = await Promise.all([
      this.options.clients.terminals.sessions.state(undefined, 'list').snapshot(),
      this.options.clients.acp.sessions.state(undefined, 'list').snapshot(),
      this.options.clients.tuiAgents.sessions.state(undefined, 'list').snapshot(),
    ]);

    const byPath = new Map<string, HostAbsolutePath>();
    const add = (path: HostAbsolutePath | null) => {
      if (!path) return;
      byPath.set(formatAbsolute(path), path);
    };

    for (const session of Object.values(terminalSnapshot.data)) {
      add(session.key.workspace.path);
    }
    for (const session of Object.values(acpSnapshot.data)) {
      add(session.cwd ? parsePath(session.cwd) : null);
    }
    for (const session of Object.values(tuiSnapshot.data)) {
      add(session.cwd ? parsePath(session.cwd) : null);
    }
    return [...byPath.values()];
  }
}

export interface SessionCleanupReport {
  acpSessions: number;
  terminalSessions: number;
  tuiSessions: number;
}

export type SessionCleanupError = { type: 'runtime-unavailable'; message: string };

export async function killSessionsUnderPath(
  clients: WorkspaceSessionClients,
  path: HostAbsolutePath
): Promise<Result<SessionCleanupReport, SessionCleanupError>> {
  const targets = await resolveSessionTargets(clients, path);

  for (const conversationId of targets.acpConversationIds) {
    const result = await clients.acp.kill({ conversationId });
    if (!result.success && !isMissingError(result.error)) {
      return sessionError(
        `Failed to kill ACP session ${conversationId}: ${errorMessage(result.error)}`
      );
    }
  }

  for (const conversationId of targets.tuiConversationIds) {
    const result = await clients.tuiAgents.delete({ conversationId });
    if (!result.success && !isMissingError(result.error)) {
      return sessionError(
        `Failed to delete TUI session ${conversationId}: ${errorMessage(result.error)}`
      );
    }
  }

  for (const key of targets.terminalKeys) {
    const result = await clients.terminals.kill({ key });
    if (!result.success && !isMissingError(result.error)) {
      return sessionError(
        `Failed to kill terminal session ${key.id}: ${errorMessage(result.error)}`
      );
    }
  }

  return ok({
    acpSessions: targets.acpConversationIds.length,
    terminalSessions: targets.terminalKeys.length,
    tuiSessions: targets.tuiConversationIds.length,
  });
}

async function resolveSessionTargets(clients: WorkspaceSessionClients, path: HostAbsolutePath) {
  const [terminalSnapshot, acpSnapshot, tuiSnapshot] = await Promise.all([
    clients.terminals.sessions.state(undefined, 'list').snapshot(),
    clients.acp.sessions.state(undefined, 'list').snapshot(),
    clients.tuiAgents.sessions.state(undefined, 'list').snapshot(),
  ]);

  const terminalKeys = Object.values(terminalSnapshot.data)
    .filter((session) => pathContains(path, session.key.workspace.path))
    .map((session) => session.key);

  const acpConversationIds = Object.values(acpSnapshot.data)
    .filter((session) => session.cwd && pathContains(path, parsePath(session.cwd)))
    .map((session) => session.conversationId);

  const tuiConversationIds = Object.values(tuiSnapshot.data)
    .filter((session) => session.cwd && pathContains(path, parsePath(session.cwd)))
    .map((session) => session.conversationId);

  return {
    acpConversationIds,
    terminalKeys,
    tuiConversationIds,
  };
}

function pathContains(root: HostAbsolutePath, candidate: HostAbsolutePath | null): boolean {
  return candidate !== null && containsAbsolute(root, candidate);
}

function parsePath(path: string): HostAbsolutePath | null {
  const parsed = parseAbsolute(path);
  return parsed.success ? parsed.data : null;
}

function sessionError(message: string): Result<never, SessionCleanupError> {
  return {
    success: false,
    error: { type: 'runtime-unavailable', message },
  };
}

function isMissingError(error: unknown): boolean {
  if (typeof error !== 'object' || error === null || !('type' in error)) return false;
  const type = String(error.type);
  return type === 'not-found' || type === 'workspace-not-found' || type === 'missing-workspace';
}

async function isDefinitivelyMissing(path: HostAbsolutePath): Promise<boolean> {
  try {
    await stat(formatAbsolute(path));
    return false;
  } catch (error) {
    return isMissingFsError(error);
  }
}

function isMissingFsError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    String((error as { code?: unknown }).code) === 'ENOENT'
  );
}

function errorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'message' in error) {
    return String(error.message);
  }
  return String(error);
}
