import { z } from 'zod';

/**
 * Durable trace of the last failed removal attempt (ADR 0006): written by the delete
 * verbs before they return a failure; removed with the record on success — no explicit
 * clear. `stage` names the removal step that failed ('teardown' | 'remove' |
 * 'unregister'); `class` is host-decided — 'transient' failures ride silent sweep
 * retries, 'terminal' ones stop auto-retry and need user attention. The client never
 * classifies.
 */
export const workspaceRemovalAttemptSchema = z.object({
  stage: z.string(),
  class: z.enum(['transient', 'terminal']),
  message: z.string(),
  at: z.number(),
});
export type WorkspaceRemovalAttempt = z.infer<typeof workspaceRemovalAttemptSchema>;

export const deleteWorkspaceInputSchema = z.object({
  workspaceId: z.string().min(1),
});
export type DeleteWorkspaceInput = z.infer<typeof deleteWorkspaceInputSchema>;

export const deleteWorktreeInputSchema = z.object({
  workspaceId: z.string().min(1),
  /** The branch is deletable independently of its worktree. */
  deleteBranch: z.boolean().default(false),
});
export type DeleteWorktreeInput = z.infer<typeof deleteWorktreeInputSchema>;

/**
 * Fast-forward one worktree's checkout to `sourceRef` fetched from `remote` (spec:
 * pr-workspace-model staleness, manual update). Instruction-as-input: the host never
 * reads the durable record's `gitSetup` for this verb, which is what makes workspaces
 * created before the model shipped updatable with the exact same call.
 */
export const updateWorktreeInputSchema = z.object({
  workspaceId: z.string().min(1),
  remote: z.string().min(1),
  sourceRef: z.string().min(1),
});
export type UpdateWorktreeInput = z.infer<typeof updateWorktreeInputSchema>;

/**
 * Explicit "refresh now": rescans one workspace, or the whole host when workspaceId is
 * omitted.
 */
export const refreshWorkspacesInputSchema = z.object({
  workspaceId: z.string().min(1).optional(),
});
export type RefreshWorkspacesInput = z.infer<typeof refreshWorkspacesInputSchema>;
