import { z } from 'zod';
import { workspaceCreateOutcomeSchema, workspaceCreationSchema } from './creation';
import { workspaceGitObservationsSchema } from './git-observation';
import { workspaceLifecycleSchema, workspaceLifecycleStepSchema } from './lifecycle-steps';
import { workspaceRemovalAttemptSchema } from './operations';
import { workspaceConfigSummarySchema } from './project-config';

/** Host-detected at registration, never client-supplied (ADR 0005). */
export const workspaceKindSchema = z.enum(['repository', 'worktree', 'directory']);
export type WorkspaceKind = z.infer<typeof workspaceKindSchema>;

/** Explicit registration vs host-discovered worktree of a registered repository. */
export const workspaceOriginSchema = z.enum(['registered', 'adopted']);
export type WorkspaceOrigin = z.infer<typeof workspaceOriginSchema>;

/**
 * Registered records survive a vanished path as 'missing'; adopted records are deleted
 * instead, so 'missing' is effectively registered-only.
 */
export const workspaceObservedStatusSchema = z.enum(['present', 'missing']);
export type WorkspaceObservedStatus = z.infer<typeof workspaceObservedStatusSchema>;

/**
 * Non-fatal session-plane event (a failed lifecycle script, an unparseable
 * `.emdash.json`), carried on the runtime overlay — informational, never a verb
 * failure.
 */
export const workspaceNoticeSchema = z.union([
  z.object({
    id: z.string().min(1),
    kind: z.literal('script-failed'),
    script: z.enum(['prepare', 'setup', 'run', 'teardown']),
    message: z.string(),
    at: z.number(),
  }),
  z.object({
    id: z.string().min(1),
    kind: z.literal('config-invalid'),
    message: z.string(),
    at: z.number(),
  }),
]);
export type WorkspaceNotice = z.infer<typeof workspaceNoticeSchema>;

/**
 * In-memory host state merged into `records` when publishing; absent after a daemon
 * restart — activation is ephemeral by design. The ONLY progress surface: no job
 * objects on this contract.
 */
export const workspaceRuntimeOverlaySchema = z.object({
  /** Present while a createWorktree run is executing. */
  creation: z.object({ stage: z.string(), startedAt: z.number() }).nullable(),
  notices: z.array(workspaceNoticeSchema),
  /**
   * Lifecycle steps, projected from the durable lifecycle section on every publish
   * (unlike the rest of the overlay, they survive daemon restarts). While the
   * foreground creation pipeline runs, the in-flight stage rides along as a synthetic
   * running step so clients read one step surface.
   */
  lifecycle: z.array(workspaceLifecycleStepSchema).nullable().optional(),
  /**
   * Prepare gates sessions; setup runs after activation concurrent with sessions; run
   * waits on setup success. Script failures surface as notices, never fail activation.
   */
  activation: z
    .object({
      phase: z.enum(['preparing', 'active']),
      scripts: z.object({
        prepare: z.enum(['running', 'succeeded', 'failed', 'skipped']),
        setup: z.enum(['pending', 'running', 'succeeded', 'failed', 'skipped']),
        run: z.enum(['pending', 'running', 'exited', 'failed', 'skipped']),
      }),
      activatedAt: z.number().nullable(),
    })
    .nullable(),
});
export type WorkspaceRuntimeOverlay = z.infer<typeof workspaceRuntimeOverlaySchema>;

/** One host workspace record. All timestamps are epoch-ms. */
export const workspaceRecordSchema = z.object({
  /** UUID; desktop-minted on create verbs, host-minted on adoption. Never changes. */
  id: z.string().min(1),
  kind: workspaceKindSchema,
  /** Mutable, unique among live records per host; moves relink by git admin name. */
  path: z.string().min(1),
  /** Worktree → its repository's record id. Null for repository/directory. */
  parentId: z.string().nullable(),
  origin: workspaceOriginSchema,
  /** Git worktree admin name; the relink anchor for moved worktrees. */
  gitAdminName: z.string().nullable(),
  observedStatus: workspaceObservedStatusSchema,
  creation: workspaceCreationSchema.nullable(),
  /** Null unless this record was born from createWorktree. */
  lastCreateOutcome: workspaceCreateOutcomeSchema.nullable(),
  /** Durable lifecycle steps; null until creation or activation first writes one. */
  lifecycle: workspaceLifecycleSchema.nullable(),
  /** Null until a delete verb fails; removed with the record on success. */
  lastRemovalAttempt: workspaceRemovalAttemptSchema.nullable(),
  /** Null for plain directories (and until first observed). */
  git: workspaceGitObservationsSchema.nullable(),
  /** Observation only — never a durable "active" flag. */
  lastActivatedAt: z.number().nullable(),
  createdAt: z.number(),
  updatedAt: z.number(),
  /** Staleness is displayed, not hidden. */
  lastObservedAt: z.number(),
  /** The config live model's summary; null until the first read lands. */
  config: workspaceConfigSummarySchema.nullable(),
  /** In-memory overlay; null when nothing is running (or after a daemon restart). */
  runtime: workspaceRuntimeOverlaySchema.nullable(),
});
export type WorkspaceRecord = z.infer<typeof workspaceRecordSchema>;

export const workspaceRecordsSchema = z.record(z.string(), workspaceRecordSchema);
export type WorkspaceRecords = z.infer<typeof workspaceRecordsSchema>;
