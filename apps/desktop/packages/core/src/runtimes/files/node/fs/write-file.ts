import { constants } from 'node:fs';
import { open } from 'node:fs/promises';
import { err, ok, type Result } from '@emdash/shared';
import type { PortableRelativePath } from '#primitives/path/api';
import type { FsError, WritePrecondition } from '#runtimes/files/api';
import { toFsError } from '#runtimes/files/node/api/errors';
import type { RootResource } from '#runtimes/files/node/root/root-resource';
import { strongEtagForHandle } from './metadata';

export async function writeFileContent(
  root: RootResource,
  entryPath: PortableRelativePath,
  bytes: Uint8Array,
  precondition: WritePrecondition
): Promise<Result<void, FsError>> {
  const target = await root.paths.resolveFollowed(entryPath);
  if (!target.success) return target;

  return root.runFileMutation(target.data.realPath, async () => {
    try {
      const handle = await open(target.data.realPath, constants.O_RDWR | constants.O_NONBLOCK);
      try {
        const metadata = await handle.stat();
        if (metadata.isDirectory()) return err({ type: 'is-a-directory', path: target.data.path });
        if (!metadata.isFile()) return err(notRegularFile(target.data.path));

        if (precondition.kind === 'etag') {
          const actual = await strongEtagForHandle(handle, metadata.size);
          if (actual !== precondition.etag) {
            return err({
              type: 'etag-mismatch',
              path: target.data.path,
              expected: precondition.etag,
              actual,
            });
          }
        }

        await handle.truncate(0);
        await handle.writeFile(bytes);
      } finally {
        await handle.close();
      }
      root.publishKnownChanges([{ kind: 'update', path: target.data.path }]);
      return ok<void>();
    } catch (error) {
      return err(toFsError(error, target.data.path));
    }
  });
}

function notRegularFile(path: PortableRelativePath): FsError {
  return { type: 'invalid-path', path, message: 'Path is not a regular file' };
}
