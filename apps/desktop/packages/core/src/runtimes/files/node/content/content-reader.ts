import { constants } from 'node:fs';
import { access, open } from 'node:fs/promises';
import type { PortableRelativePath } from '#primitives/path/api';
import { contentUnavailableCode, type FileContentModel, type FsError } from '#runtimes/files/api';
import { toFsError } from '#runtimes/files/node/api/errors';
import {
  etagForStat,
  mimeTypeForPath,
  normalizeMaxBytes,
  readStrongSnapshot,
} from '#runtimes/files/node/fs/metadata';
import type { RootPathPolicy } from '#runtimes/files/node/fs/path-policy';

const BINARY_SAMPLE_BYTES = 8 * 1024;

export class ContentReader {
  constructor(
    private readonly paths: RootPathPolicy,
    private readonly maxBytes?: number
  ) {}

  async read(entryPath: PortableRelativePath): Promise<FileContentModel> {
    const resolved = await this.paths.resolveFollowed(entryPath);
    if (!resolved.success) return unavailable(entryPath, resolved.error);

    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const handle = await open(
          resolved.data.realPath,
          constants.O_RDONLY | constants.O_NONBLOCK
        );
        try {
          const before = await handle.stat();
          if (before.isDirectory()) {
            return unavailable(entryPath, { type: 'is-a-directory', path: entryPath });
          }
          if (!before.isFile()) {
            return unavailable(entryPath, {
              type: 'invalid-path',
              path: entryPath,
              message: 'Path is not a regular file',
            });
          }
          const limit = normalizeMaxBytes(this.maxBytes);
          if (before.size > limit) {
            // Never truncate silently: over-limit content is a classification,
            // mirroring the binary classification below (spec §3).
            return { kind: 'too-large', path: entryPath, byteSize: before.size, limit };
          }
          const snapshot = await readStrongSnapshot(handle, before.size, before.size);
          const bytes = snapshot.bytes;
          const after = await handle.stat();
          if (etagForStat(before) !== etagForStat(after) || before.ctimeMs !== after.ctimeMs) {
            if (attempt === 0) continue;
            return unavailable(entryPath, {
              type: 'io',
              path: entryPath,
              message: 'File changed repeatedly while it was being read',
            });
          }

          const base = {
            path: entryPath,
            etag: snapshot.etag,
            byteSize: after.size,
            readonly: !(await isWritable(resolved.data.realPath)),
          };
          const content = decodeUtf8(bytes);
          if (isBinary(bytes.subarray(0, BINARY_SAMPLE_BYTES)) || content === null) {
            return {
              ...base,
              kind: 'binary',
              ...(mimeTypeForPath(entryPath) ? { mimeType: mimeTypeForPath(entryPath) } : {}),
            };
          }
          return {
            ...base,
            kind: 'text',
            content,
            eol: content.includes('\r\n') ? 'crlf' : 'lf',
          };
        } finally {
          await handle.close();
        }
      } catch (error) {
        return unavailable(entryPath, toFsError(error, entryPath));
      }
    }
    throw new Error('ContentReader exhausted its read attempts');
  }
}

function isBinary(sample: Uint8Array): boolean {
  if (sample.length >= 3 && sample[0] === 0xef && sample[1] === 0xbb && sample[2] === 0xbf) {
    return false;
  }
  return sample.includes(0);
}

function decodeUtf8(bytes: Uint8Array): string | null {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
}

async function isWritable(filePath: string): Promise<boolean> {
  try {
    await access(filePath, constants.W_OK);
    return true;
  } catch {
    return false;
  }
}

function unavailable(path: PortableRelativePath, error: FsError): FileContentModel {
  return { kind: 'unavailable', path, code: contentUnavailableCode(error) };
}
