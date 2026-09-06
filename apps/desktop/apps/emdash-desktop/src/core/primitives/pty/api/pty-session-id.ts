/**
 * Deterministic PTY session ID.
 *
 * Format: `<projectId>:<scopeId>:<leafId>` where leafId is either a
 * conversationId (agent sessions) or a terminalId (shell sessions).
 *
 * There is at most one active terminal-like runtime session per leaf entity.
 * Using a deterministic ID lets the renderer and runtime agree on xterm/log
 * keys before the backing process is started or reattached.
 */
export function makePtySessionId(projectId: string, scopeId: string, leafId: string): string {
  return `${projectId}:${scopeId}:${leafId}`;
}

export interface ParsedPtySessionId {
  projectId: string;
  scopeId: string;
  leafId: string;
}

export function parsePtySessionId(id: string): ParsedPtySessionId | null {
  const parts = id.split(':');
  if (parts.length !== 3 || !parts[0] || !parts[1] || !parts[2]) return null;
  return { projectId: parts[0], scopeId: parts[1], leafId: parts[2] };
}
