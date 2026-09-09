import { z } from 'zod';

export const pullRequestErrorSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('invalid_repository'), input: z.string() }),
  z.object({ type: z.literal('remote_not_ready'), status: z.string() }),
  z.object({ type: z.literal('cross_host_pr'), baseHost: z.string(), headHost: z.string() }),
  z.object({ type: z.literal('host_unreachable'), host: z.string(), reason: z.string() }),
  z.object({ type: z.literal('github_auth_required'), host: z.string(), hint: z.string() }),
  z.object({ type: z.literal('ghes_auth_required'), host: z.string(), hint: z.string() }),
  z.object({
    type: z.literal('github_account_not_found'),
    message: z.string(),
    accountId: z.string().optional(),
    host: z.string().optional(),
  }),
  z.object({
    type: z.literal('github_account_host_mismatch'),
    message: z.string(),
    accountId: z.string(),
    accountHost: z.string(),
    host: z.string(),
  }),
  z.object({
    type: z.literal('github_token_missing'),
    message: z.string(),
    accountId: z.string(),
    host: z.string(),
  }),
  z.object({
    type: z.literal('github_not_found_or_no_access'),
    host: z.string(),
    message: z.string(),
  }),
  z.object({
    type: z.literal('github_sso_required'),
    host: z.string(),
    message: z.string(),
    ssoUrl: z.string().optional(),
  }),
  z.object({
    type: z.literal('github_rate_limited'),
    host: z.string(),
    message: z.string(),
    resetAt: z.string().optional(),
  }),
  z.object({ type: z.literal('github_forbidden'), host: z.string(), message: z.string() }),
  z.object({ type: z.literal('list_failed'), message: z.string() }),
  z.object({ type: z.literal('filter_options_failed'), message: z.string() }),
  z.object({ type: z.literal('task_pull_requests_failed'), message: z.string() }),
  z.object({ type: z.literal('sync_failed'), message: z.string() }),
  z.object({ type: z.literal('refresh_failed'), message: z.string() }),
  z.object({ type: z.literal('checks_failed'), message: z.string() }),
  z.object({ type: z.literal('comments_failed'), message: z.string() }),
  z.object({ type: z.literal('create_failed'), message: z.string() }),
  z.object({ type: z.literal('merge_failed'), message: z.string() }),
  z.object({ type: z.literal('mark_ready_failed'), message: z.string() }),
  z.object({ type: z.literal('files_failed'), message: z.string() }),
  z.object({ type: z.literal('repository_not_registered'), repositoryUrl: z.string() }),
]);

export type PullRequestError = z.infer<typeof pullRequestErrorSchema>;

export function pullRequestErrorMessage(error: PullRequestError): string {
  if ('message' in error) return error.message;
  if ('reason' in error) return error.reason;
  if ('hint' in error) return error.hint;
  return error.type;
}
