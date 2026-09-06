import { cp, lstat, mkdir, open, rename, rm, rmdir, unlink } from 'node:fs/promises';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import type { PortableRelativePath } from '#primitives/path/api';
import type { FsError } from '#runtimes/files/api';
import { toFsError } from '#runtimes/files/node/api/errors';
import type { RootChange, RootResource } from '#runtimes/files/node/root/root-resource';

export async function createFileInRoot(
  root: RootResource,
  input: { path: PortableRelativePath; content?: string }
): Promise<Result<RootChange[], FsError>> {
  const destination = await root.paths.resolveDestination(input.path);
  if (!destination.success) return destination;
  return root.runFileMutation(destination.data.absolutePath, async () => {
    try {
      const handle = await open(destination.data.absolutePath, 'wx');
      try {
        if (input.content !== undefined) await handle.writeFile(input.content, 'utf8');
      } finally {
        await handle.close();
      }
      return ok<RootChange[]>([{ kind: 'create', path: destination.data.path }]);
    } catch (error) {
      return err(toFsError(error, destination.data.path));
    }
  });
}

export async function createDirectoryInRoot(
  root: RootResource,
  input: { path: PortableRelativePath }
): Promise<Result<RootChange[], FsError>> {
  const destination = await root.paths.resolveDestination(input.path);
  if (!destination.success) return destination;
  return root.runFileMutation(destination.data.absolutePath, async () => {
    try {
      await mkdir(destination.data.absolutePath);
      return ok<RootChange[]>([{ kind: 'create', path: destination.data.path }]);
    } catch (error) {
      return err(toFsError(error, destination.data.path));
    }
  });
}

/** A mutation endpoint addressed as an operational root plus a root-relative path. */
export type RootLocation = {
  root: RootResource;
  path: PortableRelativePath;
};

/**
 * Moves an entry between two (possibly identical) operational roots, returning
 * the change notifications each root should publish. Serves both the classic
 * single-root move and the bare-absolute-path move whose endpoints resolve to
 * two different parent-directory roots.
 */
export async function moveBetweenRoots(
  from: RootLocation,
  to: RootLocation
): Promise<Result<{ source: RootChange[]; target: RootChange[] }, FsError>> {
  const source = await from.root.paths.resolveExistingEntry(from.path);
  if (!source.success) return source;
  if (source.data.path === '') {
    return err({
      type: 'invalid-path',
      path: '',
      message: 'The workspace root cannot be moved',
    });
  }
  const destination = await to.root.paths.resolveDestination(to.path);
  if (!destination.success) return destination;
  const available = await destinationAvailable(
    destination.data.absolutePath,
    destination.data.path
  );
  if (!available.success) return available;
  return from.root.runFileMutation(source.data.absolutePath, async () => {
    try {
      await rename(source.data.absolutePath, destination.data.absolutePath);
      return ok({
        source: [{ kind: 'delete', path: source.data.path } as const],
        target: [{ kind: 'create', path: destination.data.path } as const],
      });
    } catch (error) {
      return err(toFsError(error, source.data.path));
    }
  });
}

/** Copies an entry between two (possibly identical) operational roots. */
export async function copyBetweenRoots(
  from: RootLocation,
  to: RootLocation
): Promise<Result<{ target: RootChange[] }, FsError>> {
  const source = await from.root.paths.resolveExistingEntry(from.path);
  if (!source.success) return source;
  if (source.data.path === '') {
    return err({
      type: 'invalid-path',
      path: '',
      message: 'The workspace root cannot be copied',
    });
  }
  const destination = await to.root.paths.resolveDestination(to.path);
  if (!destination.success) return destination;
  if (destination.data.absolutePath.startsWith(source.data.absolutePath + path.sep)) {
    return err({
      type: 'invalid-path',
      path: destination.data.path,
      message: 'A directory cannot be copied into itself',
    });
  }
  const available = await destinationAvailable(
    destination.data.absolutePath,
    destination.data.path
  );
  if (!available.success) return available;
  return from.root.runFileMutation(source.data.absolutePath, async () => {
    try {
      await cp(source.data.absolutePath, destination.data.absolutePath, {
        recursive: true,
        force: false,
        errorOnExist: true,
        verbatimSymlinks: true,
      });
      return ok({ target: [{ kind: 'create', path: destination.data.path } as const] });
    } catch (error) {
      return err(toFsError(error, source.data.path));
    }
  });
}

export async function deleteInRoot(
  root: RootResource,
  input: { path: PortableRelativePath; recursive?: boolean }
): Promise<Result<RootChange[], FsError>> {
  const target = await root.paths.resolveExistingEntry(input.path);
  if (!target.success) return target;
  if (target.data.path === '') {
    return err({
      type: 'invalid-path',
      path: '',
      message: 'The workspace root cannot be deleted',
    });
  }
  return root.runFileMutation(target.data.absolutePath, async () => {
    try {
      const metadata = await lstat(target.data.absolutePath);
      if (metadata.isDirectory()) {
        if (input.recursive) await rm(target.data.absolutePath, { recursive: true });
        else await rmdir(target.data.absolutePath);
      } else {
        await unlink(target.data.absolutePath);
      }
      return ok<RootChange[]>([{ kind: 'delete', path: target.data.path }]);
    } catch (error) {
      return err(toFsError(error, target.data.path));
    }
  });
}

async function destinationAvailable(
  absolutePath: string,
  relativePath: string
): Promise<Result<void, FsError>> {
  try {
    await lstat(absolutePath);
    return err({ type: 'already-exists', path: relativePath });
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === 'ENOENT'
      ? ok<void>()
      : err(toFsError(error, relativePath));
  }
}
