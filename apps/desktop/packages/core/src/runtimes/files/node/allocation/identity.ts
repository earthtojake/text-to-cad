import { realpath, stat } from 'node:fs/promises';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import { canonicalExclusionPatterns, DEFAULT_TREE_EXCLUDE } from '#primitives/exclusion-policy/api';
import {
  comparisonKeyForAbsolutePath,
  createPathProfile,
  formatAbsolute,
  parseAbsolute,
  type HostAbsolutePath,
  type PortableRelativePath,
} from '#primitives/path/api';
import type { FsError, TreeKey } from '#runtimes/files/api';
import { toFsError } from '#runtimes/files/node/api/errors';
import { normalizeRelativePath } from '#runtimes/files/node/fs/path-policy';

/**
 * How the root's watch is scoped: 'recursive' for registered workspace roots,
 * 'children' for the synthesized parent-directory root of a bare absolute file
 * path, where only direct children matter (spec §5: per-file watch is served by
 * watching the file's parent directory).
 */
export type RootWatchScope = 'recursive' | 'children';

export type RootIdentity = {
  rootId: string;
  root: HostAbsolutePath;
  rootPath: string;
  watchScope: RootWatchScope;
};

export type TreeIdentity = {
  treeId: string;
  root: RootIdentity;
  sessionId: string;
  exclusions: readonly string[];
};

export type ContentIdentity = {
  contentId: string;
  root: RootIdentity;
  path: PortableRelativePath;
};

/** A file addressed as an operational root plus a root-relative path. */
export type FileLocation = {
  root: RootIdentity;
  relative: PortableRelativePath;
};

export function resolveRootIdentity(
  root: HostAbsolutePath
): Promise<Result<RootIdentity, FsError>> {
  return resolveDirectoryIdentity(root, 'recursive');
}

/**
 * Resolves a bare absolute file path into its operational root (the file's
 * canonical parent directory, watch-scoped to direct children) plus the file
 * name as a root-relative path. Validation here is correctness only — path
 * well-formedness and symlink/realpath normalization; there is deliberately no
 * authorization layer (spec §3: OS permissions are the boundary).
 */
export async function resolveAbsoluteFileLocation(
  file: HostAbsolutePath
): Promise<Result<FileLocation, FsError>> {
  if (file.segments.length === 0) {
    return err({
      type: 'invalid-path',
      path: formatAbsolute(file),
      message: 'An absolute file path must not be the filesystem root',
    });
  }
  const parent: HostAbsolutePath = { root: file.root, segments: file.segments.slice(0, -1) };
  const relative = normalizeRelativePath(file.segments[file.segments.length - 1]);
  if (!relative.success) return relative;
  const root = await resolveDirectoryIdentity(parent, 'children', formatAbsolute(file));
  if (!root.success) return root;
  return ok({ root: root.data, relative: relative.data });
}

export function treeIdentity(root: RootIdentity, key: TreeKey): TreeIdentity {
  const exclusions = canonicalExclusionPatterns(key.exclusions ?? DEFAULT_TREE_EXCLUDE);
  return {
    treeId: JSON.stringify([root.rootId, key.sessionId, exclusions]),
    root,
    sessionId: key.sessionId,
    exclusions,
  };
}

export function contentIdentity(
  root: RootIdentity,
  relative: PortableRelativePath
): ContentIdentity {
  return {
    contentId: JSON.stringify([root.rootId, relative]),
    root,
    path: relative,
  };
}

async function resolveDirectoryIdentity(
  directory: HostAbsolutePath,
  watchScope: RootWatchScope,
  errorPath = ''
): Promise<Result<RootIdentity, FsError>> {
  const compatible =
    path.sep === '\\' ? directory.root.kind !== 'posix' : directory.root.kind === 'posix';
  if (!compatible) {
    return err({
      type: 'invalid-path',
      path: errorPath,
      message: `Path style is not valid on this host: ${formatAbsolute(directory)}`,
    });
  }
  const directoryPath = formatAbsolute(directory, { separator: path.sep as '/' | '\\' });
  if (directoryPath.includes('\0') || !path.isAbsolute(directoryPath)) {
    return err({
      type: 'invalid-path',
      path: errorPath,
      message: 'The root directory must be an absolute path without NUL bytes',
    });
  }
  try {
    const canonical = await realpath(directoryPath);
    const metadata = await stat(canonical);
    if (!metadata.isDirectory()) return err({ type: 'not-a-directory', path: errorPath });
    const parsed = parseAbsolute(canonical, {
      profile: {
        style: path.sep === '\\' ? 'win32' : 'posix',
        unicodeNormalization: 'preserve',
      },
    });
    if (!parsed.success) {
      return err({ type: 'invalid-path', path: errorPath, message: parsed.error.message });
    }
    const profile = createPathProfile({ style: path.sep === '\\' ? 'win32' : 'posix' });
    const comparisonKey = comparisonKeyForAbsolutePath(parsed.data, profile);
    return ok({
      rootId: watchScope === 'children' ? `children:${comparisonKey}` : comparisonKey,
      root: parsed.data,
      rootPath: canonical,
      watchScope,
    });
  } catch (error) {
    return err(toFsError(error, errorPath));
  }
}
