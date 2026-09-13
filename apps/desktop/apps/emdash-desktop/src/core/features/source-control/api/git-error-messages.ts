import { formatAbsolute } from '@emdash/core/primitives/path/api';
import type {
  CloneRepositoryError,
  FetchError,
  PullError,
  PushError,
} from '@emdash/core/runtimes/git/api';

type GitErrorMessageOptions = { isSshProject?: boolean };
type GitLikeError = { type: string; message?: string };
type FetchLikeError = FetchError | GitLikeError;
type PullLikeError = PullError | GitLikeError;
type PushLikeError = PushError | GitLikeError;
type CloneTargetExistsError = Extract<CloneRepositoryError, { type: 'target_exists' }>;
type GitRemoteAccessError = {
  type: 'auth_required' | 'auth_failed' | 'network_error' | 'remote_not_found';
};

export function formatCloneErrorDetail(
  error: CloneRepositoryError,
  opts?: GitErrorMessageOptions
): string {
  switch (error.type) {
    case 'auth_required':
    case 'auth_failed':
    case 'network_error':
    case 'remote_not_found':
      return formatRemoteAccessError(error, opts);
    case 'target_exists':
      return `Clone destination is not empty: ${formatHostPath(error.path)}`;
    case 'git_error':
    case 'resolution_failed':
      return error.message;
  }
}

export function formatFetchErrorDetail(
  error: FetchLikeError,
  opts?: GitErrorMessageOptions
): string {
  const message = error.message ?? error.type;
  if (isRemoteAccessError(error)) return formatRemoteAccessError(error, opts);

  switch (error.type) {
    case 'no_remote':
      return 'No Git remote is configured.';
    case 'git_error':
      return 'Git fetch failed.';
    default:
      return message;
  }
}

export function formatPushErrorDetail(error: PushLikeError, opts?: GitErrorMessageOptions): string {
  const message = 'message' in error ? (error.message ?? error.type) : error.type;
  if (isRemoteAccessError(error)) return formatRemoteAccessError(error, opts);

  switch (error.type) {
    case 'no_remote':
      return 'No Git remote is configured.';
    case 'no_upstream':
      return 'No upstream branch is configured.';
    default:
      return message;
  }
}

export function formatPullErrorDetail(error: PullLikeError, opts?: GitErrorMessageOptions): string {
  const message = error.message ?? error.type;
  if (isRemoteAccessError(error)) return formatRemoteAccessError(error, opts);

  switch (error.type) {
    case 'no_upstream':
      return 'No upstream branch is configured.';
    case 'conflict':
      return 'Pull has merge conflicts.';
    case 'diverged':
      return 'Local and remote branches have diverged.';
    default:
      return message;
  }
}

function formatRemoteAccessError(
  error: GitRemoteAccessError,
  opts?: GitErrorMessageOptions
): string {
  switch (error.type) {
    case 'auth_required':
      return `Git is not authenticated${hostSuffix(opts)}.`;
    case 'auth_failed':
      return `Git authentication failed${hostSuffix(opts)}.`;
    case 'network_error':
      return opts?.isSshProject
        ? 'Cannot reach the repository from the remote.'
        : 'Cannot reach the repository.';
    case 'remote_not_found':
      return 'Repository not found or inaccessible.';
  }
}

function isRemoteAccessError(error: { type: string }): error is GitRemoteAccessError {
  return (
    error.type === 'auth_required' ||
    error.type === 'auth_failed' ||
    error.type === 'network_error' ||
    error.type === 'remote_not_found'
  );
}

function hostSuffix(opts?: GitErrorMessageOptions): string {
  return opts?.isSshProject ? ' on the remote' : '';
}

function formatHostPath(path: CloneTargetExistsError['path']): string {
  return formatAbsolute(path, { separator: path.root.kind === 'posix' ? '/' : '\\' });
}
