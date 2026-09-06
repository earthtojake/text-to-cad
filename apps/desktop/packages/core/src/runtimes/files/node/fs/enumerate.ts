import { lstat, readdir, realpath, stat } from 'node:fs/promises';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import type { LiveJobContext } from '@emdash/wire/live';
import { joinPortableRelativePath, type PortableRelativePath } from '#primitives/path/api';
import type { FileEnumerationOptions, FsError, PathBatch, PathList } from '#runtimes/files/api';
import { toFsError } from '#runtimes/files/node/api/errors';
import type { RootResource } from '#runtimes/files/node/root/root-resource';
import { containsPath } from './path-policy';

const PROGRESS_BATCH_SIZE = 100;

export async function enumerateFiles(
  root: RootResource,
  entryPath: PortableRelativePath,
  options: FileEnumerationOptions,
  context: LiveJobContext<PathBatch>
): Promise<Result<PathList, FsError>> {
  const entry = await root.paths.resolveExistingEntry(entryPath);
  if (!entry.success) return entry;

  try {
    const metadata = await lstat(entry.data.absolutePath);
    if (!metadata.isDirectory() || metadata.isSymbolicLink()) {
      return err({ type: 'not-a-directory', path: entry.data.path });
    }
    const followed = await root.paths.resolveFollowed(entry.data.path);
    if (!followed.success) return followed;

    const paths: PortableRelativePath[] = [];
    const pending: PortableRelativePath[] = [];
    const emit = (filePath: PortableRelativePath) => {
      paths.push(filePath);
      pending.push(filePath);
      if (pending.length >= PROGRESS_BATCH_SIZE) context.progress({ paths: pending.splice(0) });
    };

    await visitDirectory(
      followed.data.realPath,
      entry.data.path,
      async (absolute, relative, kind) => {
        if (context.signal.aborted) return false;
        if (kind === 'file') emit(relative);
        if (kind !== 'symlink' || options.includeSymlinkFiles === false) return true;
        try {
          const canonical = await realpath(absolute);
          if (!containsPath(root.identity.rootPath, canonical)) return true;
          if ((await stat(absolute)).isFile()) emit(relative);
        } catch {
          // Broken and unreadable symlinks are not enumeration results.
        }
        return true;
      }
    );
    if (pending.length > 0) context.progress({ paths: pending });
    return ok({ paths });
  } catch (error) {
    return err(toFsError(error, entry.data.path));
  }
}

async function visitDirectory(
  absoluteDirectory: string,
  relativeDirectory: PortableRelativePath,
  visit: (
    absolutePath: string,
    relativePath: PortableRelativePath,
    kind: 'file' | 'directory' | 'symlink'
  ) => Promise<boolean>
): Promise<boolean> {
  const entries = await readdir(absoluteDirectory, { withFileTypes: true });
  entries.sort((left, right) => left.name.localeCompare(right.name));
  for (const entry of entries) {
    const absolute = path.join(absoluteDirectory, entry.name);
    const joined = joinPortableRelativePath(relativeDirectory, entry.name);
    if (!joined.success) continue;
    const relative = joined.data;
    if (entry.isDirectory()) {
      if (!(await visit(absolute, relative, 'directory'))) return false;
      if (!(await visitDirectory(absolute, relative, visit))) return false;
    } else if (entry.isFile()) {
      if (!(await visit(absolute, relative, 'file'))) return false;
    } else if (entry.isSymbolicLink() && !(await visit(absolute, relative, 'symlink'))) {
      return false;
    }
  }
  return true;
}
