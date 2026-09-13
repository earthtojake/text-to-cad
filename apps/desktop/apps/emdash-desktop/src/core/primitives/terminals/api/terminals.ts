import type { TerminalShellId } from '@emdash/core/primitives/terminal-shell/api';

export type Terminal = {
  id: string;
  projectId: string;
  taskId: string;
  ssh?: boolean;
  shellId: TerminalShellId;
  name: string;
};

export type CreateTerminalParams = {
  id: string;
  projectId: string;
  taskId: string;
  name: string;
  shell?: TerminalShellId;
  initialSize?: { cols: number; rows: number };
};

/** Prefix for the synthetic terminal ids of workspace lifecycle scripts. */
export const LIFECYCLE_SCRIPT_TERMINAL_ID_PREFIX = 'script-lifecycle-';

export function createLifecycleScriptTerminalId(type: 'prepare' | 'setup' | 'run' | 'teardown') {
  return `${LIFECYCLE_SCRIPT_TERMINAL_ID_PREFIX}${type}`;
}

export function lifecycleScriptNodeIdFromTerminalId(leafId: string): string | null {
  if (!leafId.startsWith(LIFECYCLE_SCRIPT_TERMINAL_ID_PREFIX)) return null;
  return leafId.slice(LIFECYCLE_SCRIPT_TERMINAL_ID_PREFIX.length);
}
