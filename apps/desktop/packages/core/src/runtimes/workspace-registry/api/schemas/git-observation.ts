import { z } from 'zod';

/**
 * The observed upstream identity, verbatim from `branch.<branch>.remote` and
 * `branch.<branch>.merge` config; `remoteUrl` from `git remote get-url`, null when the
 * remote does not resolve. Raw git facts — provider recognition is desktop-side.
 */
export const workspaceGitUpstreamSchema = z.object({
  remote: z.string(),
  mergeRef: z.string(),
  remoteUrl: z.string().nullable(),
});
export type WorkspaceGitUpstream = z.infer<typeof workspaceGitUpstreamSchema>;

/**
 * Host-computed git observations. `diffStats` includes untracked files' lines as
 * additions (respecting .gitignore); null = stats unavailable — a pathological worktree
 * degrades its own record, never the scan. The head OID, upstream identity, and PR
 * breadcrumb fields default to null so records from hosts predating them still parse
 * (wire-additive); each degrades to null independently on probe failure.
 */
export const workspaceGitObservationsSchema = z.object({
  branch: z.string().nullable(),
  dirty: z.boolean(),
  diffStats: z.object({ added: z.number(), deleted: z.number() }).nullable(),
  ahead: z.number().nullable(),
  behind: z.number().nullable(),
  locked: z.boolean(),
  prunable: z.boolean(),
  /** Full OID of HEAD; null on unborn HEAD or probe failure. */
  headOid: z.string().nullable().default(null),
  /** Null when detached, untracked, or the config probe failed. */
  upstream: workspaceGitUpstreamSchema.nullable().default(null),
  /** Raw value of `branch.<branch>.emdash-pr-url` config; never interpreted here. */
  prBreadcrumb: z.string().nullable().default(null),
});
export type WorkspaceGitObservations = z.infer<typeof workspaceGitObservationsSchema>;
