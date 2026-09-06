import path from 'node:path';
import { ROOT_RELATIVE_PATH, type PortableRelativePath } from '#primitives/path/api';
import type { WatchEvent } from '#services/fs-watch/api';
import type { FileSearchExclusions } from '../../exclusions';
import { containsNativePath, portableRelativePathFromNative } from '../../native-paths';

/** Reduces watcher events to the smallest set of root-relative subtrees that need rescanning. */
export function affectedSubtrees(
  events: readonly WatchEvent[],
  rootPath: string,
  exclusions: FileSearchExclusions
): PortableRelativePath[] {
  const paths = new Set<PortableRelativePath>();
  for (const event of events) {
    if (!path.isAbsolute(event.path)) continue;
    const absolutePath = path.resolve(event.path);
    if (!containsNativePath(rootPath, absolutePath)) continue;
    const relativePath = portableRelativePathFromNative(rootPath, absolutePath);
    if (relativePath !== null && !exclusions.excludes(relativePath)) paths.add(relativePath);
  }

  if (paths.has(ROOT_RELATIVE_PATH)) return [ROOT_RELATIVE_PATH];
  const ordered = [...paths].sort((left, right) => depth(left) - depth(right));
  return ordered.filter((candidate) => !hasAffectedAncestor(candidate, paths));
}

function hasAffectedAncestor(
  candidate: PortableRelativePath,
  affected: ReadonlySet<PortableRelativePath>
): boolean {
  const segments = candidate.split('/');
  let ancestor = '';
  for (const segment of segments.slice(0, -1)) {
    ancestor = ancestor ? `${ancestor}/${segment}` : segment;
    if (affected.has(ancestor as PortableRelativePath)) return true;
  }
  return false;
}

function depth(path: PortableRelativePath): number {
  return path === '' ? 0 : path.split('/').length;
}
