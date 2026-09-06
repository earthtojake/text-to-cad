import type {
  RuntimeTerminalShellId,
  TerminalShellAvailability,
  TerminalShellFamily,
  TerminalShellId,
} from './shell-ids';

/**
 * A fully resolved shell profile produced on the host that will spawn the PTY.
 * This is the portable value that shell resolution yields; the filesystem/PATH
 * probing that produces it lives in a Node service implementation.
 */
export type ResolvedShellProfile = {
  id: RuntimeTerminalShellId | 'target-default';
  resolvedShellId: RuntimeTerminalShellId;
  resolvedFromSystem: boolean;
  executable: string;
  available: true;
  family: TerminalShellFamily;
  interactiveArgs: string[];
  commandArgs: string[];
  envCaptureArgs?: string[];
  capturedEnv?: Record<string, string>;
  remotePathLookup?: boolean;
};

export type ShellFallbackEvent = {
  shell: TerminalShellId;
  message: string;
};

/**
 * Host-local shell resolution boundary injected into the terminals runtime.
 *
 * Implementations resolve shell intent against the host they run on (its
 * platform, environment, and filesystem), so a remote runtime resolves remote
 * shells and a local runtime resolves local shells. The concrete Node
 * implementation lives in `@emdash/core/services/pty/node`.
 */
export interface TerminalShellResolver {
  resolveWithSystemFallback(input: {
    intent: TerminalShellId;
    onFallback?: (event: ShellFallbackEvent) => void;
  }): Promise<ResolvedShellProfile>;
  getAvailability(): Promise<TerminalShellAvailability[]>;
}
