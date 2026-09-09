import { defineContract, fallible } from '@emdash/wire/rpc';
import { z } from 'zod';

export const githubAuthErrorSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('auth_required'),
    host: z.string(),
    message: z.string(),
    hint: z.string().optional(),
  }),
  z.object({
    type: z.literal('account_not_found'),
    host: z.string(),
    accountId: z.string(),
    message: z.string(),
    hint: z.string().optional(),
  }),
  z.object({
    type: z.literal('account_host_mismatch'),
    host: z.string(),
    accountId: z.string(),
    accountHost: z.string(),
    message: z.string(),
    hint: z.string().optional(),
  }),
  z.object({
    type: z.literal('token_missing'),
    host: z.string(),
    accountId: z.string(),
    message: z.string(),
    hint: z.string().optional(),
  }),
  /**
   * Fail-closed identity resolution failure (spec: github-git-settings §8): the
   * effective account for the repository cannot be produced — a broken pin, a
   * resolution error, or no open project referencing the repository. The sync
   * is skipped; never run as a fallback identity.
   */
  z.object({
    type: z.literal('account_unresolvable'),
    host: z.string(),
    message: z.string(),
    hint: z.string().optional(),
  }),
  /** The project explicitly disabled GitHub (`githubAccount: { kind: 'none' }`). */
  z.object({
    type: z.literal('github_disabled'),
    host: z.string(),
    message: z.string(),
    hint: z.string().optional(),
  }),
]);

/**
 * The worker's per-sync identity request (spec: github-git-settings §8): the
 * worker names only *what* it is about to sync; the desktop answers *as whom*
 * through the blessed resolver and returns the matching token. Account changes
 * apply on the next request — no persisted binding, no refresh events.
 */
export const githubAuthContract = defineContract({
  resolveAuth: fallible({
    input: z.object({
      repositoryUrl: z.string(),
    }),
    data: z.object({
      token: z.string(),
      host: z.string(),
      apiBaseUrl: z.string(),
      /** Resolved account row id; used by the worker to key per-identity request lanes. */
      accountId: z.string().optional(),
    }),
    error: githubAuthErrorSchema,
  }),
});

export type GitHubAuthContract = typeof githubAuthContract;
export type GitHubAuthError = z.infer<typeof githubAuthErrorSchema>;
