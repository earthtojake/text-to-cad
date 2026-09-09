import { z } from 'zod';

/**
 * Durable outcome of the last createWorktree attempt (precedent: conversations'
 * lastResumeOutcome). 'started' + no runtime overlay = interrupted; resolved only by a
 * client replay, never host-initiated — outcomes are facts, not desired state.
 */
export const workspaceCreateOutcomeSchema = z.union([
  z.object({ status: z.literal('started'), at: z.number() }),
  z.object({ status: z.literal('succeeded'), at: z.number() }),
  z.object({
    status: z.literal('failed'),
    at: z.number(),
    stage: z.string(),
    message: z.string(),
  }),
]);
export type WorkspaceCreateOutcome = z.infer<typeof workspaceCreateOutcomeSchema>;

/**
 * Structured, host-validated git setup executed inside the foreground creation
 * pipeline (spec: pr-workspace-model provisioning). No raw refspecs or config keys
 * cross the contract: the host constructs the fetch destination from the verb's own
 * `branch` (a plain, never-force refspec guarded by a branch-exists check) and owns
 * the exact config keys the upstream and breadcrumb become.
 */
export const workspaceGitSetupSchema = z.object({
  /** Materialize the branch: fetch sourceRef from remote into refs/heads/<branch>. */
  fetchBranch: z.object({ remote: z.string().min(1), sourceRef: z.string().min(1) }).optional(),
  /** Upstream tracking, written as `branch.<branch>.remote` / `branch.<branch>.merge`. */
  upstream: z.object({ remote: z.string().min(1), mergeRef: z.string().min(1) }).optional(),
  /** PR breadcrumb, written as `branch.<branch>.emdash-pr-url`. */
  breadcrumb: z.object({ prUrl: z.string().min(1) }).optional(),
  /** Host-local ref-follow policy, recorded durably (consumed by the follow loop). */
  followRef: z.boolean().optional(),
});
export type WorkspaceGitSetup = z.infer<typeof workspaceGitSetupSchema>;

/** Explicit publication destination for a newly created branch. */
export const workspacePublishTargetSchema = z.object({
  remote: z.string().min(1),
});
export type WorkspacePublishTarget = z.infer<typeof workspacePublishTargetSchema>;

/**
 * Minimal immutable creation fields — what replay identity is enforced against and what
 * failure diagnosis needs. NOT rich provenance (that stays a desktop annotation). Null
 * for registered-existing and adopted records.
 */
export const workspaceCreationSchema = z.object({
  branch: z.string(),
  /** Null when gitSetup.fetchBranch materialized the branch instead of a base ref. */
  baseRef: z.string().nullable(),
  requestedPath: z.string(),
  /** The verb's gitSetup block, verbatim; the host's ref-follow loop reads it later. */
  gitSetup: workspaceGitSetupSchema.optional(),
});
export type WorkspaceCreation = z.infer<typeof workspaceCreationSchema>;

export const createWorkspaceInputSchema = z.object({
  workspaceId: z.string().min(1),
  path: z.string().min(1),
});
export type CreateWorkspaceInput = z.infer<typeof createWorkspaceInputSchema>;

export const createWorktreeInputSchema = z
  .object({
    /** Desktop-minted UUID for the new worktree record. */
    workspaceId: z.string().min(1),
    /** The registered repository record to create from. */
    repositoryId: z.string().min(1),
    branch: z.string().min(1),
    /** Optional when gitSetup.fetchBranch materializes the branch instead. */
    baseRef: z.string().min(1).optional(),
    path: z.string().min(1),
    preservePatterns: z.array(z.string()).default([]),
    publish: workspacePublishTargetSchema.optional(),
    gitSetup: workspaceGitSetupSchema.optional(),
  })
  .superRefine((input, ctx) => {
    if (input.baseRef === undefined && input.gitSetup?.fetchBranch === undefined) {
      ctx.addIssue({
        code: 'custom',
        path: ['baseRef'],
        message: 'baseRef is required unless gitSetup.fetchBranch materializes the branch',
      });
    }
  });
export type CreateWorktreeInput = z.infer<typeof createWorktreeInputSchema>;
