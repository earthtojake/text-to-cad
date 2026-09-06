/**
 * Git wire error vocabulary: shared variant schemas composed into a closed
 * `type`-discriminated union per verb (convention 2), plus the `gitErr`
 * constructors the runtime uses to produce declared failures.
 */

import { err, type Err } from '@emdash/shared';
import { z } from 'zod';
import {
  hostAbsolutePathSchema,
  portableRelativePathSchema,
  type HostAbsolutePath,
  type PortableRelativePath,
} from '#primitives/path/api';

const messageError = <Type extends string>(type: Type) =>
  z.object({ type: z.literal(type), message: z.string() });

export const gitExecErrorCodeSchema = z.enum(['stale_ref_update']);
export type GitExecErrorCode = z.infer<typeof gitExecErrorCodeSchema>;

export const gitExecErrorSchema = z.object({
  type: z.literal('git_error'),
  code: gitExecErrorCodeSchema.optional(),
  message: z.string(),
  stderr: z.string().optional(),
});
export type GitExecError = z.infer<typeof gitExecErrorSchema>;

export const gitResolutionErrorSchema = z.object({
  type: z.literal('resolution_failed'),
  path: hostAbsolutePathSchema,
  message: z.string(),
});
export type GitResolutionError = z.infer<typeof gitResolutionErrorSchema>;

export const gitCommandErrorSchema = z.discriminatedUnion('type', [
  gitExecErrorSchema,
  gitResolutionErrorSchema,
]);
export type GitCommandError = z.infer<typeof gitCommandErrorSchema>;

export const authRequiredErrorSchema = messageError('auth_required');
export const authFailedErrorSchema = messageError('auth_failed');
export const networkErrorSchema = messageError('network_error');
export const noRemoteErrorSchema = z.object({
  type: z.literal('no_remote'),
  message: z.string().optional(),
});
export const noUpstreamErrorSchema = messageError('no_upstream');
export const remoteNotFoundErrorSchema = z.object({
  type: z.literal('remote_not_found'),
  remote: z.string().optional(),
  message: z.string(),
});
export const conflictErrorSchema = z.object({
  type: z.literal('conflict'),
  message: z.string(),
  conflictedFiles: z.array(portableRelativePathSchema).optional(),
});
export const targetExistsErrorSchema = z.object({
  type: z.literal('target_exists'),
  path: hostAbsolutePathSchema,
  message: z.string(),
});
export const notRepositoryErrorSchema = z.object({
  type: z.literal('not-repository'),
  path: hostAbsolutePathSchema,
});
export const inspectFailedErrorSchema = z.object({
  type: z.literal('inspect-failed'),
  path: hostAbsolutePathSchema,
  message: z.string(),
});
export const initFailedErrorSchema = z.object({
  type: z.literal('init-failed'),
  path: hostAbsolutePathSchema,
  message: z.string(),
});

export const inspectPathErrorSchema = inspectFailedErrorSchema;
export type InspectPathError = z.infer<typeof inspectPathErrorSchema>;

export const cloneRepositoryErrorSchema = z.discriminatedUnion('type', [
  targetExistsErrorSchema,
  authRequiredErrorSchema,
  authFailedErrorSchema,
  networkErrorSchema,
  remoteNotFoundErrorSchema,
  gitExecErrorSchema,
  gitResolutionErrorSchema,
]);
export type CloneRepositoryError = z.infer<typeof cloneRepositoryErrorSchema>;

export const ensureRepositoryErrorSchema = z.discriminatedUnion('type', [
  notRepositoryErrorSchema,
  inspectFailedErrorSchema,
  initFailedErrorSchema,
]);
export type EnsureRepositoryError = z.infer<typeof ensureRepositoryErrorSchema>;

export const fetchErrorSchema = z.discriminatedUnion('type', [
  noRemoteErrorSchema,
  remoteNotFoundErrorSchema,
  authRequiredErrorSchema,
  authFailedErrorSchema,
  networkErrorSchema,
  gitExecErrorSchema,
  gitResolutionErrorSchema,
]);
export type FetchError = z.infer<typeof fetchErrorSchema>;

export const commitErrorSchema = z.discriminatedUnion('type', [
  messageError('nothing_to_commit'),
  messageError('empty_message'),
  messageError('hook_failed'),
  gitExecErrorSchema,
  gitResolutionErrorSchema,
]);
export type CommitError = z.infer<typeof commitErrorSchema>;

export const pushErrorSchema = z.discriminatedUnion('type', [
  noRemoteErrorSchema,
  noUpstreamErrorSchema,
  messageError('rejected'),
  authRequiredErrorSchema,
  authFailedErrorSchema,
  networkErrorSchema,
  remoteNotFoundErrorSchema,
  messageError('hook_rejected'),
  gitExecErrorSchema,
  gitResolutionErrorSchema,
]);
export type PushError = z.infer<typeof pushErrorSchema>;

export const pullErrorSchema = z.discriminatedUnion('type', [
  conflictErrorSchema,
  noUpstreamErrorSchema,
  messageError('diverged'),
  authRequiredErrorSchema,
  authFailedErrorSchema,
  networkErrorSchema,
  gitExecErrorSchema,
  gitResolutionErrorSchema,
]);
export type PullError = z.infer<typeof pullErrorSchema>;

export const downloadErrorSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('missing') }),
  z.object({ type: z.literal('too-large'), maxBytes: z.number().int() }),
  z.object({ type: z.literal('lfs-pointer') }),
  gitExecErrorSchema,
  gitResolutionErrorSchema,
]);
export type DownloadError = z.infer<typeof downloadErrorSchema>;

export const fetchPrForReviewErrorSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('not_found'), prNumber: z.number().int(), message: z.string() }),
  authRequiredErrorSchema,
  gitExecErrorSchema,
  gitResolutionErrorSchema,
]);
export type FetchPrForReviewError = z.infer<typeof fetchPrForReviewErrorSchema>;

export type GitOperationError =
  | CloneRepositoryError
  | EnsureRepositoryError
  | FetchError
  | CommitError
  | PushError
  | PullError
  | FetchPrForReviewError;

type TaggedError<Type extends GitOperationError['type']> = Extract<
  GitOperationError,
  { type: Type }
>;

const failure = <E>(error: E): Err<E> => err(error);

/** Constructors for declared Git domain failures. */
export const gitErr = {
  commandFailed(message: string, stderr?: string): Err<GitExecError> {
    return failure({ type: 'git_error', message, ...(stderr ? { stderr } : {}) });
  },
  staleRefUpdate(message: string, stderr?: string): Err<GitExecError> {
    return failure({
      type: 'git_error',
      code: 'stale_ref_update',
      message,
      ...(stderr ? { stderr } : {}),
    });
  },
  resolutionFailed(path: HostAbsolutePath, message: string): Err<GitResolutionError> {
    return failure({ type: 'resolution_failed', path, message });
  },
  targetExists(path: HostAbsolutePath, message: string): Err<TaggedError<'target_exists'>> {
    return failure({ type: 'target_exists', path, message });
  },
  authRequired(message: string): Err<TaggedError<'auth_required'>> {
    return failure({ type: 'auth_required', message });
  },
  authFailed(message: string): Err<TaggedError<'auth_failed'>> {
    return failure({ type: 'auth_failed', message });
  },
  remoteNotFound(message: string, remote?: string): Err<TaggedError<'remote_not_found'>> {
    return failure({ type: 'remote_not_found', message, ...(remote ? { remote } : {}) });
  },
  noRemote(message?: string): Err<TaggedError<'no_remote'>> {
    return failure({ type: 'no_remote', ...(message ? { message } : {}) });
  },
  networkError(message: string): Err<TaggedError<'network_error'>> {
    return failure({ type: 'network_error', message });
  },
  nothingToCommit(message: string): Err<TaggedError<'nothing_to_commit'>> {
    return failure({ type: 'nothing_to_commit', message });
  },
  emptyMessage(message: string): Err<TaggedError<'empty_message'>> {
    return failure({ type: 'empty_message', message });
  },
  hookFailed(message: string): Err<TaggedError<'hook_failed'>> {
    return failure({ type: 'hook_failed', message });
  },
  noUpstream(message: string): Err<TaggedError<'no_upstream'>> {
    return failure({ type: 'no_upstream', message });
  },
  rejected(message: string): Err<TaggedError<'rejected'>> {
    return failure({ type: 'rejected', message });
  },
  hookRejected(message: string): Err<TaggedError<'hook_rejected'>> {
    return failure({ type: 'hook_rejected', message });
  },
  conflict(
    message: string,
    conflictedFiles?: PortableRelativePath[]
  ): Err<TaggedError<'conflict'>> {
    return failure({ type: 'conflict', message, conflictedFiles });
  },
  diverged(message: string): Err<TaggedError<'diverged'>> {
    return failure({ type: 'diverged', message });
  },
  prNotFound(
    prNumber: number,
    message: string
  ): Err<Extract<FetchPrForReviewError, { type: 'not_found' }>> {
    return failure({ type: 'not_found', prNumber, message });
  },
  notRepository(path: HostAbsolutePath): Err<TaggedError<'not-repository'>> {
    return failure({ type: 'not-repository', path });
  },
  inspectFailed(path: HostAbsolutePath, message: string): Err<TaggedError<'inspect-failed'>> {
    return failure({ type: 'inspect-failed', path, message });
  },
  initFailed(path: HostAbsolutePath, message: string): Err<TaggedError<'init-failed'>> {
    return failure({ type: 'init-failed', path, message });
  },
} as const;
