import { err, ok, type Result } from '@emdash/shared';
import { hostRefEquals, hostRefKey, type HostRef } from '#primitives/host/api';
import { formatAbsolute, joinAbsolute } from './absolute';
import { type PathError } from './errors';
import {
  formatPortableRelativePath,
  parsePortableRelativePath,
  portableRelativePathParts,
  ROOT_RELATIVE_PATH,
} from './relative';
import { createPathSemantics } from './semantics';
import type {
  HostAbsolutePath,
  HostFileRef,
  HostFileRefComparisonOptions,
  PortableRelativePath,
  ScopedPath,
} from './types';

export function hostFileRef(host: HostRef, path: HostAbsolutePath): HostFileRef {
  return { host, path };
}

export function scopedPath(root: HostFileRef, relative: PortableRelativePath): ScopedPath {
  return { root, relative };
}

export function resolveScopedPath(scoped: ScopedPath): Result<HostFileRef, PathError> {
  const parts = portableRelativePathParts(scoped.relative);
  const path = joinAbsolute(scoped.root.path, ...parts);
  if (!path.success) return path;
  return ok(hostFileRef(scoped.root.host, path.data));
}

export function relativizeHostFileRef(
  root: HostFileRef,
  candidate: HostFileRef,
  options: HostFileRefComparisonOptions = {}
): Result<PortableRelativePath, PathError> {
  if (!hostRefEquals(root.host, candidate.host)) {
    return err({
      type: 'outside-root',
      input: formatHostFileRef(candidate),
      root: formatHostFileRef(root),
      message: 'File refs are on different hosts',
    });
  }
  const semantics = createPathSemantics(options.profile);
  if (!semantics.contains(root.path, candidate.path)) {
    return err({
      type: 'outside-root',
      input: formatHostFileRef(candidate),
      root: formatHostFileRef(root),
      message: 'Path is outside root',
    });
  }
  return parsePortableRelativePath(
    candidate.path.segments.slice(root.path.segments.length).join('/')
  );
}

export function containsHostFileRef(
  root: HostFileRef,
  candidate: HostFileRef,
  options: HostFileRefComparisonOptions = {}
): boolean {
  return (
    hostRefEquals(root.host, candidate.host) &&
    createPathSemantics(options.profile).contains(root.path, candidate.path)
  );
}

export function formatHostFileRef(ref: HostFileRef): string {
  return `${hostRefKey(ref.host)}:${formatAbsolute(ref.path)}`;
}

export function rootScopedPath(root: HostFileRef): ScopedPath {
  return scopedPath(root, ROOT_RELATIVE_PATH);
}

export function formatScopedPath(scoped: ScopedPath): string {
  const relative = formatPortableRelativePath(scoped.relative);
  return relative
    ? `${formatHostFileRef(scoped.root)}#${relative}`
    : formatHostFileRef(scoped.root);
}
