import { constants } from 'node:fs';
import { lstat, open, stat } from 'node:fs/promises';
import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import type { LiveJobContext } from '@emdash/wire/live';
import type { BlobSource, WireFile } from '@emdash/wire/rpc';
import {
  absoluteDirname,
  formatAbsolute,
  parseAbsolute,
  ROOT_RELATIVE_PATH,
  type HostAbsolutePath,
  type PortableRelativePath,
} from '#primitives/path/api';
import type {
  AbsolutePathKey,
  CreateDirectoryInput,
  CreateFileInput,
  DeleteInput,
  FileStat,
  FromToKey,
  FsError,
  PathBatch,
  PathList,
  ReadBytesMeta,
  ReadFileKey,
  ReadTextResult,
  UploadFileInput,
  UploadFileResult,
  WriteFileInput,
} from '#runtimes/files/api';
import type { FilesAllocationGraph } from '#runtimes/files/node/allocation/allocation-graph';
import { expectedFsError, toFsError } from '#runtimes/files/node/api/errors';
import type {
  AbsoluteChange,
  RootChange,
  RootResource,
} from '#runtimes/files/node/root/root-resource';
import { enumerateFiles } from './enumerate';
import { mimeTypeForPath, normalizeMaxBytes, readStrongSnapshot } from './metadata';
import {
  copyBetweenRoots,
  createDirectoryInRoot,
  createFileInRoot,
  deleteInRoot,
  moveBetweenRoots,
  type RootLocation,
} from './mutation-ops';
import { writeFileContent } from './write-file';

const STREAM_CHUNK_SIZE = 64 * 1024;

/**
 * The stateless fs plane, keyed by bare host-absolute paths (spec §3.4). Every
 * successful mutation is reflected into affected live tree sessions before it
 * resolves (ack-time republish); the fs watcher covers external changes only.
 */
export class FileSystemRuntime {
  constructor(private readonly allocations: FilesAllocationGraph) {}

  stat(input: AbsolutePathKey): Promise<Result<FileStat, FsError>> {
    return this.runAt(input, async (root, relative) => {
      const resolved = await root.paths.resolveFollowed(relative);
      if (!resolved.success) return resolved;
      try {
        const metadata = await stat(resolved.data.realPath);
        if (!metadata.isDirectory() && !metadata.isFile()) {
          return err(notRegularFile(resolved.data.path));
        }
        return ok({
          path: resolved.data.path,
          type: metadata.isDirectory() ? 'directory' : 'file',
          size: metadata.size,
          mtimeMs: metadata.mtimeMs,
          ctimeMs: metadata.ctimeMs,
          mode: metadata.mode,
        });
      } catch (error) {
        return err(toFsError(error, resolved.data.path));
      }
    });
  }

  async exists(input: AbsolutePathKey): Promise<Result<{ exists: boolean }, FsError>> {
    const result = await this.runAt(input, async (root, relative) => {
      const resolved = await root.paths.resolveFollowed(relative);
      if (resolved.success) return ok({ exists: true });
      return resolved.error.type === 'not-found' ? ok({ exists: false }) : resolved;
    });
    // A missing parent directory means the file does not exist rather than an
    // addressing failure.
    if (!result.success && result.error.type === 'not-found') return ok({ exists: false });
    return result;
  }

  realPath(input: AbsolutePathKey): Promise<Result<{ path: HostAbsolutePath }, FsError>> {
    return this.runAt(input, async (root, relative) => {
      const resolved = await root.paths.resolveFollowed(relative);
      if (!resolved.success) return resolved;
      const parsed = parseAbsolute(resolved.data.realPath, {
        profile: {
          style: path.sep === '\\' ? 'win32' : 'posix',
          unicodeNormalization: 'preserve',
        },
      });
      return parsed.success
        ? ok({ path: parsed.data })
        : err({ type: 'invalid-path', path: relative, message: parsed.error.message });
    });
  }

  readText(input: ReadFileKey): Promise<Result<ReadTextResult, FsError>> {
    return this.runAt(input, async (root, relative) => {
      const resolved = await root.paths.resolveFollowed(relative);
      if (!resolved.success) return resolved;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          const handle = await open(
            resolved.data.realPath,
            constants.O_RDONLY | constants.O_NONBLOCK
          );
          try {
            const before = await handle.stat();
            if (before.isDirectory()) return err({ type: 'is-a-directory', path: relative });
            if (!before.isFile()) return err(notRegularFile(relative));
            const readSize = Math.min(before.size, normalizeMaxBytes(input.options?.maxBytes));
            const snapshot = await readStrongSnapshot(handle, before.size, readSize);
            const after = await handle.stat();
            if (!sameFileVersion(before, after)) {
              if (attempt === 0) continue;
              return err(changedWhileReading(relative));
            }
            return ok({
              content: snapshot.bytes.toString('utf8'),
              truncated: after.size > snapshot.bytes.length,
              totalSize: after.size,
              etag: snapshot.etag,
            });
          } finally {
            await handle.close();
          }
        } catch (error) {
          return err(toFsError(error, relative));
        }
      }
      throw new Error('readText exhausted its read attempts');
    });
  }

  readBytes(
    input: ReadFileKey
  ): Promise<Result<{ meta: ReadBytesMeta; source: BlobSource }, FsError>> {
    return this.runAt(input, async (root, relative) => {
      const resolved = await root.paths.resolveFollowed(relative);
      if (!resolved.success) return resolved;
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          const handle = await open(
            resolved.data.realPath,
            constants.O_RDONLY | constants.O_NONBLOCK
          );
          let result: { meta: ReadBytesMeta; source: BlobSource } | undefined;
          try {
            const before = await handle.stat();
            if (before.isDirectory()) {
              return err({ type: 'is-a-directory', path: relative });
            }
            if (!before.isFile()) return err(notRegularFile(relative));
            const readSize = Math.min(before.size, normalizeMaxBytes(input.options?.maxBytes));
            const snapshot = await readStrongSnapshot(handle, before.size, readSize);
            const after = await handle.stat();
            if (!sameFileVersion(before, after)) {
              if (attempt === 0) continue;
              return err(changedWhileReading(relative));
            }
            result = {
              meta: {
                name: path.basename(relative) || path.basename(resolved.data.realPath),
                mimeType: mimeTypeForPath(relative) ?? 'application/octet-stream',
                size: snapshot.bytes.length,
                lastModified: after.mtimeMs,
                truncated: after.size > snapshot.bytes.length,
                totalSize: after.size,
                etag: snapshot.etag,
              },
              source: bufferBlobSource(snapshot.bytes),
            };
          } finally {
            await handle.close();
          }
          if (result) return ok(result);
        } catch (error) {
          return err(toFsError(error, relative));
        }
      }
      throw new Error('readBytes exhausted its read attempts');
    });
  }

  async upload(input: UploadFileInput, file: WireFile): Promise<Result<UploadFileResult, FsError>> {
    let bytes: Uint8Array;
    try {
      bytes = await file.bytes();
    } catch (error) {
      return err(toFsError(error, formatAbsolute(input.path)));
    }

    return this.runAt({ path: input.path }, async (root, relative) => {
      const destination = await root.paths.resolveDestination(relative);
      if (!destination.success) return destination;

      const written = await root.runFileMutation(
        destination.data.absolutePath,
        async (): Promise<Result<{ bytesWritten: number; change: RootChange }, FsError>> => {
          try {
            const metadata = await lstat(destination.data.absolutePath).catch((error: unknown) => {
              if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null;
              throw error;
            });
            const existed = metadata !== null;
            if (metadata?.isDirectory()) {
              return err({ type: 'is-a-directory', path: destination.data.path });
            }
            if (metadata?.isSymbolicLink()) {
              return err({
                type: 'invalid-path',
                path: destination.data.path,
                message: 'Upload destination must not be a symbolic link',
              });
            }
            if (existed && !input.overwrite) {
              return err({ type: 'already-exists', path: destination.data.path });
            }

            const flags = input.overwrite
              ? constants.O_WRONLY | constants.O_CREAT | constants.O_TRUNC | constants.O_NOFOLLOW
              : constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL;
            const handle = await open(destination.data.absolutePath, flags, 0o666);
            try {
              await handle.writeFile(bytes);
            } finally {
              await handle.close();
            }
            return ok({
              bytesWritten: bytes.byteLength,
              change: { kind: existed ? 'update' : 'create', path: destination.data.path },
            });
          } catch (error) {
            return err(toFsError(error, destination.data.path));
          }
        }
      );
      if (!written.success) return written;
      this.allocations.notifyActiveRoot(root, [written.data.change]);
      await this.allocations.reflectMutation(
        [root],
        toAbsoluteChanges(root, [written.data.change])
      );
      return ok({ bytesWritten: written.data.bytesWritten });
    });
  }

  enumerate(
    input: AbsolutePathKey & { options?: { includeSymlinkFiles?: boolean } },
    context: LiveJobContext<PathBatch>
  ): Promise<Result<PathList, FsError>> {
    return this.run(input.path, (root) =>
      enumerateFiles(root, ROOT_RELATIVE_PATH, input.options ?? {}, context)
    );
  }

  createFile(input: CreateFileInput): Promise<Result<void, FsError>> {
    return this.mutateAt(input, (root, relative) => createFileInRoot(root, { path: relative }));
  }

  createDirectory(input: CreateDirectoryInput): Promise<Result<void, FsError>> {
    return this.mutateAt(input, (root, relative) =>
      createDirectoryInRoot(root, { path: relative })
    );
  }

  delete(input: DeleteInput): Promise<Result<void, FsError>> {
    return this.mutateAt(input, (root, relative) =>
      deleteInRoot(root, { path: relative, recursive: input.recursive })
    );
  }

  writeFile(input: WriteFileInput): Promise<Result<void, FsError>> {
    return this.runAt({ path: input.path }, async (root, relative) => {
      const written = await writeFileContent(
        root,
        relative,
        Buffer.from(input.content, input.encoding ?? 'utf8'),
        input.precondition
      );
      if (!written.success) return written;
      await this.allocations.reflectMutation(
        [root],
        toAbsoluteChanges(root, [{ kind: 'update', path: relative }])
      );
      return ok<void>();
    });
  }

  rename(input: FromToKey): Promise<Result<void, FsError>> {
    const fromParent = absoluteDirname(input.from);
    const toParent = absoluteDirname(input.to);
    if (!fromParent || !toParent || formatAbsolute(fromParent) !== formatAbsolute(toParent)) {
      return Promise.resolve(
        err({
          type: 'invalid-path',
          path: formatAbsolute(input.to),
          message: 'Rename requires the same parent',
        })
      );
    }
    return this.move(input);
  }

  move(input: FromToKey): Promise<Result<void, FsError>> {
    return this.runAtPair(input, async (from, to) => {
      const moved = await moveBetweenRoots(from, to);
      if (!moved.success) return moved;
      this.allocations.notifyActiveRoot(from.root, moved.data.source);
      this.allocations.notifyActiveRoot(to.root, moved.data.target);
      await this.allocations.reflectMutation(
        [from.root, to.root],
        [
          ...toAbsoluteChanges(from.root, moved.data.source),
          ...toAbsoluteChanges(to.root, moved.data.target),
        ]
      );
      return ok<void>();
    });
  }

  copy(input: FromToKey): Promise<Result<void, FsError>> {
    return this.runAtPair(input, async (from, to) => {
      const copied = await copyBetweenRoots(from, to);
      if (!copied.success) return copied;
      this.allocations.notifyActiveRoot(to.root, copied.data.target);
      await this.allocations.reflectMutation(
        [to.root],
        toAbsoluteChanges(to.root, copied.data.target)
      );
      return ok<void>();
    });
  }

  private run<T>(
    root: HostAbsolutePath,
    operation: (root: RootResource) => Promise<Result<T, FsError>>
  ): Promise<Result<T, FsError>> {
    return this.withExpectedErrors(() => this.allocations.useRoot({ root }, operation));
  }

  private runAt<T>(
    key: AbsolutePathKey,
    operation: (root: RootResource, relative: PortableRelativePath) => Promise<Result<T, FsError>>
  ): Promise<Result<T, FsError>> {
    return this.withExpectedErrors(() => this.allocations.useFileLocation(key, operation));
  }

  private runAtPair<T>(
    key: FromToKey,
    operation: (from: RootLocation, to: RootLocation) => Promise<Result<T, FsError>>
  ): Promise<Result<T, FsError>> {
    return this.withExpectedErrors(() =>
      this.allocations.useFileLocation({ path: key.from }, (fromRoot, fromRelative) =>
        this.allocations.useFileLocation({ path: key.to }, (toRoot, toRelative) =>
          operation({ root: fromRoot, path: fromRelative }, { root: toRoot, path: toRelative })
        )
      )
    );
  }

  /**
   * Runs a single-target mutation in the operational root the target resolves
   * to (the entry's parent directory), publishes the resulting changes to it,
   * and reflects them into affected live tree sessions before resolving.
   */
  private mutateAt(
    key: AbsolutePathKey,
    operation: (
      root: RootResource,
      relative: PortableRelativePath
    ) => Promise<Result<RootChange[], FsError>>
  ): Promise<Result<void, FsError>> {
    return this.runAt(key, async (root, relative) => {
      const result = await operation(root, relative);
      if (!result.success) return result;
      this.allocations.notifyActiveRoot(root, result.data);
      await this.allocations.reflectMutation([root], toAbsoluteChanges(root, result.data));
      return ok<void>();
    });
  }

  private async withExpectedErrors<T>(
    operation: () => Promise<Result<T, FsError>>
  ): Promise<Result<T, FsError>> {
    try {
      return await operation();
    } catch (error) {
      const expected = expectedFsError(error);
      if (expected) return err(expected);
      throw error;
    }
  }
}

function toAbsoluteChanges(root: RootResource, changes: RootChange[]): AbsoluteChange[] {
  return changes.flatMap((change): AbsoluteChange[] => {
    if (change.kind === 'resync') return [];
    return [
      {
        kind: change.kind,
        absolutePath: path.resolve(
          root.identity.rootPath,
          ...change.path.split('/').filter(Boolean)
        ),
      },
    ];
  });
}

function bufferBlobSource(bytes: Buffer): AsyncIterable<Uint8Array> {
  let position = 0;
  return {
    [Symbol.asyncIterator]() {
      return {
        async next(): Promise<IteratorResult<Uint8Array>> {
          if (position >= bytes.length) return { done: true, value: undefined };
          const end = Math.min(position + STREAM_CHUNK_SIZE, bytes.length);
          const value = bytes.subarray(position, end);
          position = end;
          return { done: false, value };
        },
      };
    },
  };
}

function sameFileVersion(
  before: { size: number; mtimeMs: number; ctimeMs: number },
  after: { size: number; mtimeMs: number; ctimeMs: number }
): boolean {
  return (
    before.size === after.size &&
    before.mtimeMs === after.mtimeMs &&
    before.ctimeMs === after.ctimeMs
  );
}

function changedWhileReading(entryPath: PortableRelativePath): FsError {
  return {
    type: 'io',
    path: entryPath,
    message: 'File changed repeatedly while it was being read',
  };
}

function notRegularFile(entryPath: string): FsError {
  return {
    type: 'invalid-path',
    path: entryPath,
    message: 'Path is not a regular file or directory',
  };
}
