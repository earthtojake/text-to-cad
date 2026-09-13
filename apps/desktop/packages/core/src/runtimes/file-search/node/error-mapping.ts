import type { HostAbsolutePath } from '#primitives/path/api';
import type {
  ContentSearchError,
  FileSearchRegisterRootError,
  FileSearchRootUnavailableReason,
  FileSearchUnregisterRootError,
  PathSearchError,
} from '#runtimes/file-search/api';
import {
  errorMessage,
  isExpectedContentScopeNodeError,
  isExpectedPathIndexNodeError,
  isExpectedRootNodeError,
  nodeErrorCode,
} from './node-errors';
import { RootWatchError } from './path/index/errors';
import { isOperationalSqliteError } from './storage/errors';

type RootUnavailableError = Extract<FileSearchRegisterRootError, { type: 'root-unavailable' }>;
type RootOrIoError = FileSearchRegisterRootError;

export function rootUnavailable(
  root: HostAbsolutePath,
  reason: FileSearchRootUnavailableReason,
  message: string
): RootUnavailableError {
  return { type: 'root-unavailable', root, reason, message };
}

export function rootNotRegistered(
  root: HostAbsolutePath
): Extract<PathSearchError | ContentSearchError, { type: 'root-not-registered' }> {
  return {
    type: 'root-not-registered',
    root,
    message: 'Root is not registered for file search',
  };
}

export function indexNotReady(
  root: HostAbsolutePath
): Extract<PathSearchError, { type: 'index-not-ready' }> {
  return {
    type: 'index-not-ready',
    root,
    message: 'The file-search index is still being built',
  };
}

export function toExpectedRootAccessError(
  root: HostAbsolutePath,
  error: unknown,
  subject = 'File-search root'
): RootUnavailableError | undefined {
  switch (nodeErrorCode(error)) {
    case 'ENOENT':
      return rootUnavailable(root, 'not-found', `${subject} does not exist`);
    case 'ENOTDIR':
      return rootUnavailable(root, 'not-a-directory', `${subject} is not a directory`);
    case 'EACCES':
    case 'EPERM':
      return rootUnavailable(root, 'permission-denied', `${subject} cannot be accessed`);
    case 'ELOOP':
      return rootUnavailable(root, 'invalid-path', `${subject} contains a symbolic-link loop`);
    case 'EINVAL':
    case 'ENAMETOOLONG':
      return rootUnavailable(root, 'invalid-path', `${subject} is not a valid filesystem path`);
    default:
      return undefined;
  }
}

export function toExpectedStoreError(
  root: HostAbsolutePath,
  error: unknown,
  fallback: string
): FileSearchUnregisterRootError | undefined {
  if (!isOperationalSqliteError(error)) return undefined;
  return ioError(root, error, fallback);
}

export function toExpectedRootOrIndexError(
  root: HostAbsolutePath,
  error: unknown,
  fallback: string,
  boundary: 'root' | 'path-index'
): RootOrIoError | undefined {
  if (error instanceof RootWatchError) {
    return (
      toExpectedRootAccessError(root, error.cause) ?? ioError(root, error.cause, error.message)
    );
  }
  const access = toExpectedRootAccessError(root, error);
  if (access) return access;
  const expectedNodeError =
    boundary === 'root' ? isExpectedRootNodeError(error) : isExpectedPathIndexNodeError(error);
  if (!expectedNodeError && !isOperationalSqliteError(error)) return undefined;
  return ioError(root, error, fallback);
}

export function toExpectedContentScopeError(
  root: HostAbsolutePath,
  error: unknown,
  fallback: string
): ContentSearchError | undefined {
  return (
    toExpectedRootAccessError(root, error, 'Content-search root or scope') ??
    (isExpectedContentScopeNodeError(error) ? ioError(root, error, fallback) : undefined)
  );
}

function ioError(
  root: HostAbsolutePath,
  error: unknown,
  fallback: string
): FileSearchUnregisterRootError {
  return { type: 'io', root, message: errorMessage(error, fallback) };
}
