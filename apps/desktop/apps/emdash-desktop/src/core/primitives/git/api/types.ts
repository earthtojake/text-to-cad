import type { HostAbsolutePath } from '@emdash/core/primitives/path/api';

export type GitRemote = {
  name: string;
  url: string;
};

export type GitLocalBranchRef = {
  type: 'local';
  branch: string;
  remote?: GitRemote;
};

export type GitRemoteBranchRef = {
  type: 'remote';
  branch: string;
  remote: GitRemote;
};

export type GitBranchRef = GitLocalBranchRef | GitRemoteBranchRef;

export type DiffMode = { kind: 'head' } | { kind: 'staged' } | { kind: 'unstaged' };

export type GitObjectRef =
  | { kind: 'branch'; branch: GitBranchRef }
  | { kind: 'commit'; sha: string }
  | { kind: 'tag'; name: string };

export type MergeBaseRange = {
  base: GitObjectRef;
  head: GitObjectRef;
};

export type GitExecErrorCode = 'stale_ref_update';

type MessageError<Type extends string> = { type: Type; message: string };

export type GitExecError = {
  type: 'git_error';
  code?: GitExecErrorCode;
  message: string;
  stderr?: string;
};

export type GitResolutionError = {
  type: 'resolution_failed';
  path: HostAbsolutePath;
  message: string;
};

export type GitCommandError = GitExecError | GitResolutionError;
export type FetchError =
  | { type: 'no_remote'; message?: string }
  | { type: 'remote_not_found'; remote?: string; message: string }
  | MessageError<'auth_required'>
  | MessageError<'auth_failed'>
  | MessageError<'network_error'>
  | GitCommandError;

export type CreateBranchError =
  | { type: 'already_exists'; branch: string; message: string }
  | { type: 'invalid_name'; branch: string; message: string }
  | { type: 'invalid_base'; branch: string; from: string; message: string }
  | { type: 'fetch_failed'; remote: string; branch: string; error: FetchError }
  | GitCommandError;

export type FetchPrForReviewError =
  | { type: 'not_found'; prNumber: number; message: string }
  | MessageError<'auth_required'>
  | GitCommandError;

export type PushError =
  | { type: 'no_remote'; message?: string }
  | MessageError<'no_upstream'>
  | MessageError<'rejected'>
  | MessageError<'auth_required'>
  | MessageError<'auth_failed'>
  | MessageError<'network_error'>
  | MessageError<'remote_not_found'>
  | MessageError<'hook_rejected'>
  | GitCommandError;

/** The conventional name for a repository's first remote — a naming default, not resolution. */
export const DEFAULT_REMOTE_NAME = 'origin';

export const HEAD_REF: DiffMode = { kind: 'head' };
export const STAGED_REF: DiffMode = { kind: 'staged' };

export type GitRef = DiffMode | GitObjectRef;
