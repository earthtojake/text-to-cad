import path from 'node:path';
import { err, ok, type Result } from '@emdash/shared';
import type { PortableRelativePath } from '#primitives/path/api';
import type { DownloadError, DownloadMeta, GitFileSource } from '#runtimes/git/api';
import { commandFailed, gitFailure } from '#runtimes/git/node/exec/errors';
import type { BoundExec } from '#services/exec/api';
import { isMissingGitContent, sourceSpec } from './content';

const MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024;
const LFS_POINTER_PREFIX = Buffer.from('version https://git-lfs.github.com/spec/');
const MIME_BY_EXT: Record<string, string> = {
  '.avif': 'image/avif',
  '.bmp': 'image/bmp',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.jpeg': 'image/jpeg',
  '.jpg': 'image/jpeg',
  '.json': 'application/json',
  '.pdf': 'application/pdf',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
};

/**
 * One-shot binary read of a blob at head/index/revision, resolved through the
 * same spec vocabulary as the content live model. Returns the raw (filtered)
 * bytes plus download metadata; LFS pointers are surfaced as an error because
 * the pointer bytes are never the content the caller wants.
 */
export async function readGitBlobDownload(
  exec: BoundExec,
  filePath: PortableRelativePath,
  source: GitFileSource
): Promise<Result<{ meta: DownloadMeta; bytes: Buffer }, DownloadError>> {
  let bytes: Buffer;
  try {
    const spec = sourceSpec(source, filePath);
    const { stdout: oidOutput } = await exec.exec([
      'rev-parse',
      '--verify',
      '--end-of-options',
      spec,
    ]);
    const oid = oidOutput.trim();
    const { stdout } = await exec.execBuffer(['cat-file', '--filters', `--path=${filePath}`, oid], {
      maxBuffer: MAX_DOWNLOAD_BYTES,
    });
    bytes = stdout;
  } catch (error) {
    const failure = gitFailure(error);
    if (failure.stderr.includes('maxBuffer')) {
      return err({ type: 'too-large', maxBytes: MAX_DOWNLOAD_BYTES });
    }
    if (isMissingGitContent(error, source)) return err({ type: 'missing' });
    return commandFailed(error);
  }
  if (looksLikeLfsPointer(bytes)) return err({ type: 'lfs-pointer' });
  return ok({
    meta: {
      name: path.posix.basename(filePath),
      mimeType:
        MIME_BY_EXT[path.posix.extname(filePath).toLowerCase()] ?? 'application/octet-stream',
      size: bytes.length,
    },
    bytes,
  });
}

function looksLikeLfsPointer(buffer: Buffer): boolean {
  if (buffer.length > 1024) return false;
  return buffer.subarray(0, LFS_POINTER_PREFIX.length).equals(LFS_POINTER_PREFIX);
}
