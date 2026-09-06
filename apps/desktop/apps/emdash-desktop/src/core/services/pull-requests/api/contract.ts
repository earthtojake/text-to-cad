import { defineContract, fallible, liveModel, liveState } from '@emdash/wire/rpc';
import { z } from 'zod';
import { pullRequestErrorSchema } from './errors';
import {
  branchPullRequestsInputSchema,
  createPullRequestInputSchema,
  listPullRequestsInputSchema,
  listPullRequestsResultSchema,
  mergePullRequestInputSchema,
  pullRequestCommentSchema,
  pullRequestFileSchema,
  pullRequestFilterOptionsSchema,
  pullRequestNumberInputSchema,
  pullRequestSchema,
  pullRequestUrlInputSchema,
  repositoryInputSchema,
  repositoryListInputSchema,
  syncChecksInputSchema,
  syncStateKeySchema,
  syncStateSchema,
} from './schemas';

export const pullRequestsDomain = 'pullRequests' as const;

export const pullRequestsContract = defineContract({
  listPullRequests: fallible({
    input: listPullRequestsInputSchema,
    data: listPullRequestsResultSchema,
    error: pullRequestErrorSchema,
  }),
  getFilterOptions: fallible({
    input: repositoryListInputSchema,
    data: pullRequestFilterOptionsSchema,
    error: pullRequestErrorSchema,
  }),
  getPullRequestsForBranch: fallible({
    input: branchPullRequestsInputSchema,
    data: z.object({ prs: z.array(pullRequestSchema) }),
    error: pullRequestErrorSchema,
  }),
  /**
   * Breadcrumb validation read (pr-workspace-model spec, Association): the cache's
   * PR for a canonical PR URL, scoped to one registered repository. `pr` is null
   * when the URL is unknown to the cache — never an error, so a stale breadcrumb
   * degrades silently to the caller's fallback.
   */
  getPullRequestByUrl: fallible({
    input: pullRequestUrlInputSchema,
    data: z.object({ pr: pullRequestSchema.nullable() }),
    error: pullRequestErrorSchema,
  }),
  registerRepository: fallible({
    input: repositoryInputSchema,
    data: z.void(),
    error: pullRequestErrorSchema,
  }),
  unregisterRepository: fallible({
    input: repositoryInputSchema,
    data: z.void(),
    error: pullRequestErrorSchema,
  }),
  sync: fallible({
    input: repositoryInputSchema,
    data: z.void(),
    error: pullRequestErrorSchema,
  }),
  forceFullSync: fallible({
    input: repositoryInputSchema,
    data: z.void(),
    error: pullRequestErrorSchema,
  }),
  syncSingle: fallible({
    input: pullRequestNumberInputSchema,
    data: z.object({ pr: pullRequestSchema }),
    error: pullRequestErrorSchema,
  }),
  syncChecks: fallible({
    input: syncChecksInputSchema,
    data: z.object({ hasRunning: z.boolean() }),
    error: pullRequestErrorSchema,
  }),
  cancelSync: fallible({
    input: repositoryInputSchema,
    data: z.void(),
    error: pullRequestErrorSchema,
  }),
  createPullRequest: fallible({
    input: createPullRequestInputSchema,
    data: z.object({ url: z.string(), number: z.number().int().positive() }),
    error: pullRequestErrorSchema,
  }),
  mergePullRequest: fallible({
    input: mergePullRequestInputSchema,
    data: z.object({ sha: z.string().nullable(), merged: z.boolean() }),
    error: pullRequestErrorSchema,
  }),
  markReadyForReview: fallible({
    input: pullRequestNumberInputSchema,
    data: z.void(),
    error: pullRequestErrorSchema,
  }),
  getPullRequestFiles: fallible({
    input: pullRequestNumberInputSchema,
    data: z.object({ files: z.array(pullRequestFileSchema) }),
    error: pullRequestErrorSchema,
  }),
  getPullRequestComments: fallible({
    input: pullRequestNumberInputSchema,
    data: z.object({ comments: z.array(pullRequestCommentSchema) }),
    error: pullRequestErrorSchema,
  }),
  syncState: liveModel({
    key: syncStateKeySchema,
    states: {
      state: liveState({ data: syncStateSchema }),
    },
  }),
});

export type PullRequestsContract = typeof pullRequestsContract;
