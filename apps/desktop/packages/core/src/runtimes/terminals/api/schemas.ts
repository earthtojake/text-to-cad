import { z } from 'zod';
import { gitCredentialsSessionSpecSchema } from '#primitives/git-credentials/api';
import { hostFileRefSchema } from '#primitives/path/api';
import { terminalShellIdSchema } from '#primitives/terminal-shell/api';

export const terminalSizeSchema = z.object({
  cols: z.number().int().positive(),
  rows: z.number().int().positive(),
});

export type TerminalSize = z.infer<typeof terminalSizeSchema>;

export const terminalExitSchema = z.object({
  exitCode: z.number().int().nullable(),
  signal: z.string().nullable(),
});

export type TerminalExit = z.infer<typeof terminalExitSchema>;

/** Starting the interactive terminal failed (spawn, shell resolution, tmux…). */
export const terminalStartFailedErrorSchema = z.object({
  type: z.literal('terminal-start-failed'),
  message: z.string().min(1),
});

/** Shell availability could not be resolved on this host. */
export const shellAvailabilityFailedErrorSchema = z.object({
  type: z.literal('shell-availability-failed'),
  message: z.string().min(1),
});

/** The addressed terminal session is not running. */
export const terminalNotFoundErrorSchema = z.object({
  type: z.literal('not-found'),
  message: z.string().min(1),
});

/** An unexpected terminals-runtime failure not covered by a more specific variant. */
export const terminalRuntimeErrorSchema = z.object({
  type: z.literal('terminal-runtime-error'),
  message: z.string().min(1),
});

export const terminalErrorSchema = z.discriminatedUnion('type', [
  terminalStartFailedErrorSchema,
  shellAvailabilityFailedErrorSchema,
  terminalNotFoundErrorSchema,
  terminalRuntimeErrorSchema,
]);

export type TerminalError = z.infer<typeof terminalErrorSchema>;
export type TerminalStartFailedError = z.infer<typeof terminalStartFailedErrorSchema>;
export type ShellAvailabilityFailedError = z.infer<typeof shellAvailabilityFailedErrorSchema>;
export type TerminalNotFoundError = z.infer<typeof terminalNotFoundErrorSchema>;
export type TerminalRuntimeError = z.infer<typeof terminalRuntimeErrorSchema>;

export const terminalKeySchema = z.object({
  workspace: hostFileRefSchema,
  id: z.string().min(1),
});

export type TerminalKey = z.infer<typeof terminalKeySchema>;

export const startTerminalSpecSchema = z
  .object({
    cwd: z.string().min(1),
    env: z.record(z.string(), z.string()),
    shellIntent: terminalShellIdSchema.optional(),
    shellSetup: z.string().optional(),
    tmux: z.boolean().optional(),
    /**
     * Per-session git credential behavior, resolved desktop-side from project
     * settings (spec: github-git-settings §4). Absent = native behavior.
     */
    gitCredentials: gitCredentialsSessionSpecSchema.optional(),
  })
  .merge(terminalSizeSchema.partial());

export type StartTerminalSpec = z.infer<typeof startTerminalSpecSchema>;

export const startTerminalInputSchema = z.object({
  key: terminalKeySchema,
  spec: startTerminalSpecSchema,
});

export type StartTerminalInput = z.infer<typeof startTerminalInputSchema>;

export const terminalSessionStateSchema = z.object({
  key: terminalKeySchema,
  status: z.enum(['running', 'exited']),
  startCount: z.number().int().nonnegative(),
  tmux: z.boolean().optional(),
  pid: z.number().int().positive().optional(),
  cols: z.number().int().positive(),
  rows: z.number().int().positive(),
  startedAt: z.number().int(),
  exitedAt: z.number().int().optional(),
  lastInputAt: z.number().int().optional(),
  lastOutputAt: z.number().int().optional(),
  exit: terminalExitSchema.optional(),
});

export type TerminalSessionState = z.infer<typeof terminalSessionStateSchema>;

export const terminalSessionListSchema = z.record(z.string(), terminalSessionStateSchema);

export type TerminalSessionList = z.infer<typeof terminalSessionListSchema>;

export const terminalDataInputSchema = z.object({
  key: terminalKeySchema,
  data: z.string(),
});

export const terminalResizeInputSchema = z
  .object({
    key: terminalKeySchema,
  })
  .merge(terminalSizeSchema);

export const terminalControlInputSchema = z.object({
  key: terminalKeySchema,
});

export const killTmuxSessionsInputSchema = z.object({
  sessionNames: z.array(z.string().min(1)),
});

export type KillTmuxSessionsInput = z.infer<typeof killTmuxSessionsInputSchema>;
