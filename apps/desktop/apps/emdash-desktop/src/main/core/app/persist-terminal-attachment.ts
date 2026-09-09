import { execFile } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { rmSync } from 'node:fs';
import { mkdtemp, readdir, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { basename, extname, join } from 'node:path';
import { promisify } from 'node:util';
import { app, clipboard, nativeImage } from 'electron';

export const MAX_DROPPED_BLOB_BYTES = 50 * 1024 * 1024;
export const DROPPED_BLOB_FILENAME_PREFIX = 'hardcore-drop-';
export const DROPPED_BLOB_MAX_AGE_MS = 24 * 60 * 60 * 1000;

const execFileAsync = promisify(execFile);
const persistedDroppedBlobPaths = new Set<string>();
let cleanupRegistered = false;

const MIME_TO_EXT: Record<string, string> = {
  'image/png': '.png',
  'image/jpeg': '.jpg',
  'image/jpg': '.jpg',
  'image/gif': '.gif',
  'image/webp': '.webp',
  'image/svg+xml': '.svg',
  'image/bmp': '.bmp',
  'image/tiff': '.tiff',
  'image/heic': '.heic',
  'image/heif': '.heif',
};

export function sanitizeDroppedBlobName(name: string | undefined): string {
  if (!name) return '';
  const base = basename(name).replace(/[^A-Za-z0-9._-]/g, '_');
  return base.slice(0, 64);
}

export function inferDroppedBlobExtension(
  name: string | undefined,
  mimeType: string | undefined
): string {
  const fromName = name ? extname(name).toLowerCase() : '';
  if (fromName) return fromName;
  if (mimeType && MIME_TO_EXT[mimeType.toLowerCase()]) return MIME_TO_EXT[mimeType.toLowerCase()];
  return '.bin';
}

export function isHeicLike(args: { name?: string; mimeType?: string; ext?: string }): boolean {
  const ext = args.ext ?? inferDroppedBlobExtension(args.name, args.mimeType);
  if (ext === '.heic' || ext === '.heif') return true;
  const mime = args.mimeType?.toLowerCase() ?? '';
  return mime.includes('heic') || mime.includes('heif');
}

export async function normalizeDroppedImageBytes(
  bytes: Uint8Array,
  args: { name?: string; mimeType?: string }
): Promise<{ bytes: Uint8Array; ext: string }> {
  const ext = inferDroppedBlobExtension(args.name, args.mimeType);
  if (!isHeicLike({ ...args, ext })) {
    return { bytes, ext };
  }

  const image = nativeImage.createFromBuffer(Buffer.from(bytes));
  if (!image.isEmpty()) {
    const png = image.toPNG();
    if (png.byteLength > 0) return { bytes: new Uint8Array(png), ext: '.png' };
  }

  return { bytes: await convertHeicLikeBytesToPng(bytes, ext), ext: '.png' };
}

async function convertHeicLikeBytesToPng(bytes: Uint8Array, ext: string): Promise<Uint8Array> {
  if (process.platform !== 'darwin') {
    throw new Error('HEIC/HEIF image conversion is only supported on macOS');
  }

  const tempDir = await mkdtemp(join(app.getPath('temp'), 'hardcore-heic-'));
  const inputPath = join(tempDir, `input${ext === '.heif' ? '.heif' : '.heic'}`);
  const outputPath = join(tempDir, 'output.png');

  try {
    await writeFile(inputPath, bytes);
    await execFileAsync('/usr/bin/sips', ['-s', 'format', 'png', inputPath, '--out', outputPath]);
    const png = await readFile(outputPath);
    if (png.byteLength === 0) throw new Error('sips produced an empty PNG');
    return new Uint8Array(png);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Failed to convert HEIC/HEIF image to PNG: ${message}`);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
}

export async function persistDroppedBlobBytes(args: {
  bytes: Uint8Array;
  name?: string;
  mimeType?: string;
}): Promise<string> {
  if (args.bytes.byteLength > MAX_DROPPED_BLOB_BYTES) {
    throw new Error(`Dropped file is too large (${args.bytes.byteLength} bytes)`);
  }

  const normalized = await normalizeDroppedImageBytes(args.bytes, {
    name: args.name,
    mimeType: args.mimeType,
  });
  if (normalized.bytes.byteLength > MAX_DROPPED_BLOB_BYTES) {
    throw new Error(`Dropped file is too large (${normalized.bytes.byteLength} bytes)`);
  }

  const safe = sanitizeDroppedBlobName(args.name?.replace(/\.[^.]+$/, ''));
  const filename = `${DROPPED_BLOB_FILENAME_PREFIX}${randomUUID()}${safe ? `-${safe}` : ''}${normalized.ext}`;
  const fullPath = join(app.getPath('temp'), filename);
  await writeFile(fullPath, normalized.bytes);
  trackPersistedDroppedBlob(fullPath);
  return fullPath;
}

function trackPersistedDroppedBlob(path: string): void {
  persistedDroppedBlobPaths.add(path);
  if (cleanupRegistered) return;
  cleanupRegistered = true;
  app.once('quit', () => {
    cleanupPersistedDroppedBlobsSync();
  });
}

function cleanupPersistedDroppedBlobsSync(): void {
  for (const path of persistedDroppedBlobPaths) {
    rmSync(path, { force: true });
    persistedDroppedBlobPaths.delete(path);
  }
}

export async function cleanupPersistedDroppedBlobs(): Promise<void> {
  const paths = [...persistedDroppedBlobPaths];
  await Promise.all(
    paths.map(async (path) => {
      await rm(path, { force: true });
      persistedDroppedBlobPaths.delete(path);
    })
  );
}

export async function cleanupExpiredDroppedBlobs(now = Date.now()): Promise<void> {
  const tempDir = app.getPath('temp');
  const entries = await readdir(tempDir);
  await Promise.all(
    entries.map(async (entry) => {
      if (!entry.startsWith(DROPPED_BLOB_FILENAME_PREFIX)) return;
      const path = join(tempDir, entry);
      const info = await stat(path).catch(() => null);
      if (!info?.isFile()) return;
      if (now - info.mtimeMs < DROPPED_BLOB_MAX_AGE_MS) return;
      await rm(path, { force: true });
    })
  );
}

export async function persistClipboardImagePath(): Promise<string | null> {
  const image = clipboard.readImage();
  if (image.isEmpty()) return null;
  const png = image.toPNG();
  if (png.byteLength === 0) return null;
  return persistDroppedBlobBytes({
    bytes: new Uint8Array(png),
    name: 'paste.png',
    mimeType: 'image/png',
  });
}
