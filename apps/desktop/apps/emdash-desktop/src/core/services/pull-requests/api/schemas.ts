import { z } from 'zod';
import { pullRequestErrorSchema } from './errors';

export const pullRequestStatusSchema = z.enum(['open', 'closed', 'merged']);
export const mergeableStateSchema = z.enum(['MERGEABLE', 'CONFLICTING', 'UNKNOWN']);
export const mergeStateStatusSchema = z.enum([
  'CLEAN',
  'DIRTY',
  'BEHIND',
  'BLOCKED',
  'HAS_HOOKS',
  'UNSTABLE',
  'UNKNOWN',
]);
export const pullRequestMergeStrategySchema = z.enum(['merge', 'squash', 'rebase']);

export const pullRequestUserSchema = z.object({
  userId: z.string(),
  userName: z.string(),
  displayName: z.string().nullable(),
  avatarUrl: z.string().nullable(),
  url: z.string().nullable(),
  userUpdatedAt: z.string().nullable(),
  userCreatedAt: z.string().nullable(),
});

export const pullRequestLabelSchema = z.object({
  name: z.string(),
  color: z.string().nullable(),
});

export const pullRequestCheckSchema = z.object({
  id: z.string(),
  pullRequestUrl: z.string(),
  commitSha: z.string(),
  name: z.string(),
  status: z.string(),
  conclusion: z.string().nullable(),
  detailsUrl: z.string().nullable(),
  startedAt: z.string().nullable(),
  completedAt: z.string().nullable(),
  workflowName: z.string().nullable(),
  appName: z.string().nullable(),
  appLogoUrl: z.string().nullable(),
});

export const pullRequestCommentSchema = z.object({
  id: z.string(),
  pullRequestUrl: z.string(),
  kind: z.enum(['issue', 'review']),
  body: z.string(),
  url: z.string(),
  author: pullRequestUserSchema.nullable(),
  path: z.string().nullable(),
  line: z.number().int().nullable(),
  isResolved: z.boolean(),
  isOutdated: z.boolean(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export const pullRequestSchema = z.object({
  url: z.string(),
  provider: z.string(),
  repositoryUrl: z.string(),
  baseRefName: z.string(),
  baseRefOid: z.string(),
  headRepositoryUrl: z.string(),
  headRefName: z.string(),
  headRefOid: z.string(),
  identifier: z.string().nullable(),
  title: z.string(),
  description: z.string().nullable(),
  status: pullRequestStatusSchema,
  isDraft: z.boolean(),
  additions: z.number().int().nullable(),
  deletions: z.number().int().nullable(),
  changedFiles: z.number().int().nullable(),
  commitCount: z.number().int().nullable(),
  mergeableStatus: mergeableStateSchema.nullable(),
  mergeStateStatus: mergeStateStatusSchema.nullable(),
  reviewDecision: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
  author: pullRequestUserSchema.nullable(),
  labels: z.array(pullRequestLabelSchema),
  assignees: z.array(pullRequestUserSchema),
  checks: z.array(pullRequestCheckSchema),
});

export const pullRequestFileSchema = z.object({
  filename: z.string(),
  status: z.string(),
  additions: z.number().int(),
  deletions: z.number().int(),
  patch: z.string().optional(),
});

export const pullRequestStatusFilterSchema = z.enum([
  'open',
  'closed',
  'merged',
  'all',
  'not-open',
]);

export const pullRequestFiltersSchema = z.object({
  status: pullRequestStatusFilterSchema.optional(),
  authorUserIds: z.array(z.string()).optional(),
  labelNames: z.array(z.string()).optional(),
  assigneeUserIds: z.array(z.string()).optional(),
});

export const pullRequestSortSchema = z.enum(['newest', 'oldest', 'recently-updated']);

export const listPullRequestsInputSchema = z.object({
  repositoryUrls: z.array(z.string()).min(1),
  cursor: z.string().nullable(),
  limit: z.number().int().positive().max(200).default(50),
  searchQuery: z.string().optional(),
  filters: pullRequestFiltersSchema.optional(),
  sort: pullRequestSortSchema.optional(),
});

export const listPullRequestsResultSchema = z.object({
  prs: z.array(pullRequestSchema),
  nextCursor: z.string().nullable(),
});

export const pullRequestFilterOptionsSchema = z.object({
  authors: z.array(pullRequestUserSchema),
  labels: z.array(pullRequestLabelSchema),
  assignees: z.array(pullRequestUserSchema),
});

export const pullRequestMergeOptionsSchema = z.object({
  strategy: pullRequestMergeStrategySchema,
  commitHeadOid: z.string().optional(),
  bypassRequirements: z.boolean().optional(),
});

export const repositoryInputSchema = z.object({
  repositoryUrl: z.string(),
});

export const repositoryListInputSchema = z.object({
  repositoryUrls: z.array(z.string()).min(1),
});

export const branchPullRequestsInputSchema = repositoryInputSchema.extend({
  branch: z.string(),
});

export const pullRequestNumberInputSchema = repositoryInputSchema.extend({
  number: z.number().int().positive(),
});

export const pullRequestUrlInputSchema = repositoryInputSchema.extend({
  url: z.string(),
});

export const syncChecksInputSchema = repositoryInputSchema.extend({
  pullRequestUrl: z.string(),
  headRefOid: z.string(),
});

export const createPullRequestInputSchema = z.object({
  repositoryUrl: z.string(),
  headRepositoryUrl: z.string().optional(),
  head: z.string(),
  base: z.string(),
  title: z.string(),
  body: z.string().optional(),
  draft: z.boolean(),
});

export const mergePullRequestInputSchema = pullRequestNumberInputSchema.extend({
  options: pullRequestMergeOptionsSchema,
});

export const syncStateSchema = z.object({
  phase: z.enum(['idle', 'running', 'error']),
  kind: z.enum(['full', 'incremental', 'single']).nullable(),
  synced: z.number().int().nonnegative().optional(),
  total: z.number().int().nonnegative().optional(),
  error: pullRequestErrorSchema.optional(),
  lastSyncedAt: z.number().int().nonnegative().optional(),
});

export const syncStateKeySchema = repositoryInputSchema;

export type PullRequestStatus = z.infer<typeof pullRequestStatusSchema>;
export type MergeableState = z.infer<typeof mergeableStateSchema>;
export type MergeStateStatus = z.infer<typeof mergeStateStatusSchema>;
export type PullRequestMergeStrategy = z.infer<typeof pullRequestMergeStrategySchema>;
export type PullRequestMergeOptions = z.infer<typeof pullRequestMergeOptionsSchema>;
export type PullRequestUser = z.infer<typeof pullRequestUserSchema>;
export type PullRequestLabel = z.infer<typeof pullRequestLabelSchema>;
export type PullRequestCheck = z.infer<typeof pullRequestCheckSchema>;
export type PullRequestComment = z.infer<typeof pullRequestCommentSchema>;
export type PullRequest = z.infer<typeof pullRequestSchema>;
export type PullRequestFile = z.infer<typeof pullRequestFileSchema>;
export type PullRequestFilters = z.infer<typeof pullRequestFiltersSchema>;
export type PullRequestSort = z.infer<typeof pullRequestSortSchema>;
export type ListPullRequestsInput = z.infer<typeof listPullRequestsInputSchema>;
export type ListPullRequestsResult = z.infer<typeof listPullRequestsResultSchema>;
export type PullRequestFilterOptions = z.infer<typeof pullRequestFilterOptionsSchema>;
export type CreatePullRequestInput = z.infer<typeof createPullRequestInputSchema>;
export type SyncState = z.infer<typeof syncStateSchema>;
