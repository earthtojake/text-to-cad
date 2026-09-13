import { lstat, readdir, readlink, realpath, stat } from 'node:fs/promises';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import type { ExclusionMatcher } from '#primitives/exclusion-policy/api';
import {
  joinPortableRelativePath,
  portableRelativePathParent,
  type PortableRelativePath,
} from '#primitives/path/api';
import {
  isExpandableFileEntry,
  type FileEntry,
  type FsError,
  type SymlinkTargetKind,
} from '#runtimes/files/api';
import { toFsError } from '#runtimes/files/node/api/errors';
import { etagForStat } from '#runtimes/files/node/fs/metadata';
import { containsPath, type RootPathPolicy } from '#runtimes/files/node/fs/path-policy';

export class TreeDirectoryReader {
  constructor(
    private readonly paths: RootPathPolicy,
    private readonly exclusions?: ExclusionMatcher
  ) {}

  async readChildren(directoryPath: PortableRelativePath): Promise<Result<FileEntry[], FsError>> {
    const resolved = await this.paths.resolveFollowed(directoryPath);
    if (!resolved.success) return resolved;

    let dirents;
    try {
      dirents = await readdir(resolved.data.realPath, { withFileTypes: true });
    } catch (error) {
      return err(toFsError(error, directoryPath));
    }

    const entries: FileEntry[] = [];
    for (const dirent of dirents) {
      const childPath = joinPortableRelativePath(directoryPath, dirent.name);
      if (!childPath.success) continue;
      if (this.exclusions?.excludes(childPath.data)) continue;
      const classified = await this.readEntry(
        childPath.data,
        path.join(resolved.data.realPath, dirent.name)
      );
      if (classified.success) entries.push(classified.data);
      else if (classified.error.type !== 'not-found') return classified;
    }
    entries.sort(compareFileEntries);
    return ok(entries);
  }

  async readEntry(
    entryPath: PortableRelativePath,
    canonicalPath?: string
  ): Promise<Result<FileEntry, FsError>> {
    const resolved = this.paths.resolveEntry(entryPath);
    if (!resolved.success) return resolved;

    try {
      const absolutePath = canonicalPath ?? resolved.data.absolutePath;
      const metadata = await lstat(absolutePath);
      const base = {
        path: resolved.data.path,
        name: path.basename(resolved.data.absolutePath),
        parentPath: portableRelativePathParent(resolved.data.path),
        childrenLoaded: false,
        children: [] as PortableRelativePath[],
        size: metadata.size,
        mtimeMs: metadata.mtimeMs,
      };

      if (metadata.isSymbolicLink()) {
        const target = await classifySymlink(absolutePath, this.paths.rootPath);
        return ok({
          ...base,
          kind: 'symlink',
          symlinkTarget: target.target,
          symlinkTargetKind: target.kind,
          ...(target.stat && target.kind === 'file' ? { etag: etagForStat(target.stat) } : {}),
        });
      }
      if (metadata.isDirectory()) return ok({ ...base, kind: 'directory' });
      if (metadata.isFile()) return ok({ ...base, kind: 'file', etag: etagForStat(metadata) });
      return err({ type: 'not-found', path: resolved.data.path });
    } catch (error) {
      return err(toFsError(error, resolved.data.path));
    }
  }
}

async function classifySymlink(
  absolutePath: string,
  rootPath: string
): Promise<{
  target: string | null;
  kind: SymlinkTargetKind;
  stat?: { mtimeMs: number; size: number };
}> {
  let target: string | null = null;
  try {
    target = await readlink(absolutePath);
  } catch {
    // The entry remains useful even when its raw target cannot be read.
  }

  try {
    const canonical = await realpath(absolutePath);
    if (!containsPath(rootPath, canonical)) return { target, kind: 'outside-root' };
    const metadata = await stat(absolutePath);
    const statMetadata = { mtimeMs: Number(metadata.mtimeMs), size: Number(metadata.size) };
    if (metadata.isDirectory()) return { target, kind: 'directory', stat: statMetadata };
    if (metadata.isFile()) return { target, kind: 'file', stat: statMetadata };
    return { target, kind: 'other', stat: statMetadata };
  } catch (error) {
    return {
      target,
      kind: (error as NodeJS.ErrnoException).code === 'ENOENT' ? 'missing' : 'other',
    };
  }
}

function compareFileEntries(left: FileEntry, right: FileEntry): number {
  const rank = Number(isExpandableFileEntry(right)) - Number(isExpandableFileEntry(left));
  if (rank !== 0) return rank;
  const folded = left.name.toLowerCase().localeCompare(right.name.toLowerCase());
  return folded || left.name.localeCompare(right.name);
}
