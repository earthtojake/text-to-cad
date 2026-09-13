import { lstat, readdir, realpath, stat } from 'node:fs/promises';
import path from 'node:path';
import { throwIfAborted } from '@emdash/shared/scheduling';
import {
  joinPortableRelativePath,
  portableRelativePathParts,
  type PortableRelativePath,
} from '#primitives/path/api';
import type { FileSearchExclusions } from '../../exclusions';
import { containsNativePath, sameNativePath } from '../../native-paths';
import type { PathIndexEntry } from './path-index-store';

export type PathScanOptions = Readonly<{
  signal: AbortSignal;
  exclusions: FileSearchExclusions;
}>;

/** Traversal port for full-root and subtree scans. */
export interface PathScanner {
  scan(
    rootPath: string,
    relativeRoot: PortableRelativePath,
    options: PathScanOptions
  ): AsyncIterable<PathIndexEntry>;
}

/** Filesystem scanner that never follows directory symlinks or leaves the canonical root. */
export class NodePathScanner implements PathScanner {
  async *scan(
    rootPath: string,
    relativeRoot: PortableRelativePath,
    options: PathScanOptions
  ): AsyncIterable<PathIndexEntry> {
    throwIfAborted(options.signal, 'Path scan cancelled');
    if (relativeRoot !== '' && (await hasSymlinkAncestor(rootPath, relativeRoot))) return;

    const absoluteRoot = path.join(rootPath, ...portableRelativePathParts(relativeRoot));
    if (relativeRoot === '') {
      yield* this.scanDirectoryChildren(rootPath, relativeRoot, absoluteRoot, options, true);
      return;
    }
    yield* this.scanEntry(rootPath, relativeRoot, absoluteRoot, options);
  }

  private async *scanEntry(
    rootPath: string,
    relativePath: PortableRelativePath,
    absolutePath: string,
    options: PathScanOptions
  ): AsyncIterable<PathIndexEntry> {
    throwIfAborted(options.signal, 'Path scan cancelled');
    let metadata;
    try {
      metadata = await lstat(absolutePath);
    } catch (error) {
      if (isSkippableEntryError(error)) return;
      throw error;
    }

    if (metadata.isSymbolicLink()) {
      const kind = await classifySafeSymlink(rootPath, absolutePath);
      if (!kind || options.exclusions.excludes(relativePath)) return;
      yield { path: relativePath, kind };
      return;
    }

    if (metadata.isFile()) {
      if (!options.exclusions.excludes(relativePath)) {
        yield { path: relativePath, kind: 'file' };
      }
      return;
    }
    if (!metadata.isDirectory() || options.exclusions.excludes(relativePath)) return;

    yield { path: relativePath, kind: 'directory' };
    yield* this.scanDirectoryChildren(rootPath, relativePath, absolutePath, options, false);
  }

  private async *scanDirectoryChildren(
    rootPath: string,
    relativePath: PortableRelativePath,
    absolutePath: string,
    options: PathScanOptions,
    isRoot: boolean
  ): AsyncIterable<PathIndexEntry> {
    throwIfAborted(options.signal, 'Path scan cancelled');
    let canonicalDirectory: string;
    let entries;
    try {
      canonicalDirectory = await realpath(absolutePath);
      if (!sameNativePath(absolutePath, canonicalDirectory)) return;
      entries = await readdir(canonicalDirectory, { withFileTypes: true });
    } catch (error) {
      if (!isRoot && isSkippableEntryError(error)) return;
      throw error;
    }
    entries.sort((left, right) => left.name.localeCompare(right.name));

    for (const entry of entries) {
      throwIfAborted(options.signal, 'Path scan cancelled');
      const childPath = joinPortableRelativePath(relativePath, entry.name);
      if (!childPath.success) continue;
      yield* this.scanEntry(
        rootPath,
        childPath.data,
        path.join(canonicalDirectory, entry.name),
        options
      );
    }
  }
}

async function classifySafeSymlink(
  rootPath: string,
  absolutePath: string
): Promise<'file' | 'directory' | null> {
  try {
    const canonical = await realpath(absolutePath);
    if (!containsNativePath(rootPath, canonical)) return null;
    const metadata = await stat(absolutePath);
    if (metadata.isFile()) return 'file';
    if (metadata.isDirectory()) return 'directory';
    return null;
  } catch (error) {
    if (isSkippableEntryError(error)) return null;
    throw error;
  }
}

async function hasSymlinkAncestor(
  rootPath: string,
  relativePath: PortableRelativePath
): Promise<boolean> {
  const parts = portableRelativePathParts(relativePath);
  let current = rootPath;
  for (const part of parts.slice(0, -1)) {
    current = path.join(current, part);
    try {
      if ((await lstat(current)).isSymbolicLink()) return true;
    } catch (error) {
      if (isSkippableEntryError(error)) return true;
      throw error;
    }
  }
  return false;
}

function isSkippableEntryError(error: unknown): boolean {
  const code = (error as NodeJS.ErrnoException).code;
  return (
    code === 'ENOENT' ||
    code === 'ENOTDIR' ||
    code === 'EACCES' ||
    code === 'EPERM' ||
    code === 'ELOOP'
  );
}
