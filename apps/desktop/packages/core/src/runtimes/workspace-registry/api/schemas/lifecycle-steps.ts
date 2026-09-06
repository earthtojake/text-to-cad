import { z } from 'zod';

/**
 * Identity of one workspace lifecycle step. Creation-class steps (adopt-worktree |
 * fetch-branch | fetch-remote-base | create-worktree | configure-branch) settle in the
 * foreground pipeline; background-class steps (copy-artifacts | push-branch |
 * fetch-refs) run after the verb returns; script-class steps (prepare | setup | run |
 * teardown) track the current activation cycle.
 */
export const workspaceLifecycleStepIdSchema = z.enum([
  'adopt-worktree',
  'fetch-branch',
  'fetch-remote-base',
  'create-worktree',
  'configure-branch',
  'copy-artifacts',
  'push-branch',
  'fetch-refs',
  'prepare',
  'setup',
  'run',
  'teardown',
]);
export type WorkspaceLifecycleStepId = z.infer<typeof workspaceLifecycleStepIdSchema>;

/**
 * 'pending' and 'running' read as incomplete: background-class steps replay them
 * idempotently on host restart or the next activation; 'failed' is terminal and only
 * re-runs through the explicit retryStep verb — never automatically. 'skipped' marks
 * a step that was planned but became inapplicable at runtime; steps that never
 * applied to a record are absent, not skipped. 'cancelled' marks a run somebody
 * stopped (deactivation, the drawer's stop button) or a restart interrupted —
 * distinct from failed and from never-started.
 */
export const workspaceLifecycleStepStatusSchema = z.enum([
  'pending',
  'running',
  'succeeded',
  'failed',
  'skipped',
  'cancelled',
]);
export type WorkspaceLifecycleStepStatus = z.infer<typeof workspaceLifecycleStepStatusSchema>;

/** Typed step params (branch, path, base, fileCount…); display copy is derived at render. */
export const workspaceLifecycleStepParamsSchema = z.record(
  z.string(),
  z.union([z.string(), z.number(), z.boolean()])
);
export type WorkspaceLifecycleStepParams = z.infer<typeof workspaceLifecycleStepParamsSchema>;

/**
 * One durable lifecycle step: machine facts only — titles, descriptions, and relative
 * dates are derived at render time, never persisted.
 */
export const workspaceLifecycleStepSchema = z.object({
  id: workspaceLifecycleStepIdSchema,
  status: workspaceLifecycleStepStatusSchema,
  /** Null until the step first runs (pending steps have not started). */
  startedAt: z.number().nullable(),
  /** Null until the step settles; long-lived run scripts may never settle. */
  finishedAt: z.number().nullable(),
  /** Present for failed steps (and skip reasons). */
  message: z.string().optional(),
  params: workspaceLifecycleStepParamsSchema,
});
export type WorkspaceLifecycleStep = z.infer<typeof workspaceLifecycleStepSchema>;

/**
 * The ordered durable lifecycle section: the single source of truth for what happened
 * to a workspace — it drives replay, gating, retry, AND the Activity timeline. Steps
 * appear in lifecycle order; conditional steps that never applied are absent.
 */
export const workspaceLifecycleSchema = z.object({
  steps: z.array(workspaceLifecycleStepSchema),
  /** Replay input for the copy-artifacts step; not part of the creation identity. */
  preservePatterns: z.array(z.string()),
});
export type WorkspaceLifecycle = z.infer<typeof workspaceLifecycleSchema>;

export const activateWorkspaceInputSchema = z.object({
  workspaceId: z.string().min(1),
});
export type ActivateWorkspaceInput = z.infer<typeof activateWorkspaceInputSchema>;

export const deactivateWorkspaceInputSchema = z.object({
  workspaceId: z.string().min(1),
});
export type DeactivateWorkspaceInput = z.infer<typeof deactivateWorkspaceInputSchema>;

/** The lifecycle steps a user may retry after a durable failure. */
export const retryableLifecycleStepSchema = z.enum(['copy-artifacts', 'push-branch']);
export type RetryableLifecycleStep = z.infer<typeof retryableLifecycleStepSchema>;

/**
 * Manual retry of a durably failed lifecycle step. Only failed retryable steps
 * re-run; anything else (succeeded, skipped, in-flight) is a no-op returning the
 * current record.
 */
export const retryStepInputSchema = z.object({
  workspaceId: z.string().min(1),
  step: retryableLifecycleStepSchema,
});
export type RetryStepInput = z.infer<typeof retryStepInputSchema>;

/**
 * Manual/retry script run, brokered by the registry: the registry builds the
 * request (facts, timeout) from its record and starts the run on the scripts
 * runtime — clients never resolve env or settings themselves (spec:
 * activation-scripts-via-terminals, the manual path). The run itself lands in
 * the same scripts-runtime scope as activation runs and mirrors into the
 * timeline through observation like every other run.
 */
export const runScriptInputSchema = z.object({
  workspaceId: z.string().min(1),
  script: z.enum(['prepare', 'setup', 'run', 'teardown']),
  provenance: z.enum(['manual', 'retry']),
});
export type RunScriptInput = z.infer<typeof runScriptInputSchema>;
