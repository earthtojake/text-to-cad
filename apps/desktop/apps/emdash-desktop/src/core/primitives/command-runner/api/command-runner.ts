export type CommandRunnerResult = { stdout: string; stderr: string };
export type CommandRunnerOptions = { timeout?: number };

/**
 * Minimal command runner for desktop-local one-shot operations.
 * Inject for testability; production callers use the host-level {@code runLocalCommand}.
 */
export type CommandRunner = (
  command: string,
  args?: string[],
  opts?: CommandRunnerOptions
) => Promise<CommandRunnerResult>;
