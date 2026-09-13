import { z } from 'zod';
import { hostAbsolutePathSchema } from '#primitives/path/api';
import { localBranchRefSchema } from '#runtimes/git/api/repository/states/refs';

export const worktreeHeadSummarySchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('branch'), ref: localBranchRefSchema }),
  z.object({ kind: z.literal('detached') }),
  z.object({ kind: z.literal('unborn'), ref: localBranchRefSchema }),
]);
export type WorktreeHeadSummary = z.infer<typeof worktreeHeadSummarySchema>;

export const worktreeSummarySchema = z.object({
  worktreePath: hostAbsolutePathSchema,
  isMain: z.boolean(),
  head: worktreeHeadSummarySchema,
  locked: z.boolean().optional(),
  prunable: z.boolean().optional(),
  prunableReason: z.string().optional(),
});
export type WorktreeSummary = z.infer<typeof worktreeSummarySchema>;

export const gitWorktreesStateSchema = z.array(worktreeSummarySchema);
export type GitWorktreesState = z.infer<typeof gitWorktreesStateSchema>;
