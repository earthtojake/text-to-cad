import { createHash } from 'node:crypto';
import type { FileHandle } from 'node:fs/promises';
import path from 'node:path';

export const DEFAULT_MAX_BYTES = 200 * 1024;
export const MAX_READ_BYTES = 100 * 1024 * 1024;

export function normalizeMaxBytes(maxBytes: number | undefined): number {
  if (maxBytes === undefined) return DEFAULT_MAX_BYTES;
  return Math.min(Math.max(0, Math.floor(maxBytes)), MAX_READ_BYTES);
}

export function etagForStat(stat: { mtimeMs: number; size: number }): string {
  return `${Math.floor(stat.mtimeMs).toString(29)}-${stat.size.toString(31)}`;
}

export async function strongEtagForHandle(handle: FileHandle, totalBytes: number): Promise<string> {
  return (await readStrongSnapshot(handle, totalBytes, 0)).etag;
}

export async function readStrongSnapshot(
  handle: FileHandle,
  totalBytes: number,
  captureBytes: number
): Promise<{ etag: string; bytes: Buffer }> {
  const hash = createHash('sha256');
  const buffer = Buffer.alloc(64 * 1024);
  const captured = Buffer.alloc(Math.min(totalBytes, captureBytes));
  let position = 0;
  while (position < totalBytes) {
    const length = Math.min(buffer.byteLength, totalBytes - position);
    const { bytesRead } = await handle.read(buffer, 0, length, position);
    if (bytesRead === 0) throw new Error('File ended while its ETag was being computed');
    hash.update(buffer.subarray(0, bytesRead));
    if (position < captured.length) {
      const captureLength = Math.min(bytesRead, captured.length - position);
      buffer.copy(captured, position, 0, captureLength);
    }
    position += bytesRead;
  }
  return { etag: `sha256:${hash.digest('base64url')}`, bytes: captured };
}

export function mimeTypeForPath(filePath: string): string | undefined {
  switch (path.extname(filePath).toLowerCase()) {
    case '.avif':
      return 'image/avif';
    case '.gif':
      return 'image/gif';
    case '.jpeg':
    case '.jpg':
      return 'image/jpeg';
    case '.json':
      return 'application/json';
    case '.pdf':
      return 'application/pdf';
    case '.png':
      return 'image/png';
    case '.svg':
      return 'image/svg+xml';
    case '.webp':
      return 'image/webp';
    default:
      return undefined;
  }
}
