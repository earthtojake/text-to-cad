import type { ManagedFileKind } from '../../../browser/renderers/types';

/** Raster image extensions — rendered with <img>, not Monaco. */
export const RASTER_EXTS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'ico', 'bmp']);

/** HTML extensions — rendered with the HTML preview iframe. */
export const HTML_EXTS = new Set(['html', 'htm']);

/**
 * Known binary / non-text extensions — shown as "unsupported" instead of
 * attempting to load into Monaco.
 */
export const BINARY_EXTS = new Set([
  'exe',
  'dll',
  'so',
  'dylib',
  'wasm',
  'zip',
  'tar',
  'gz',
  'bz2',
  '7z',
  'rar',
  'db',
  'sqlite',
  'sqlite3',
  'class',
  'jar',
  'pyc',
  'o',
  'a',
  'lib',
  'bin',
  'dat',
  'pkg',
  'dmg',
  'iso',
  'ttf',
  'otf',
  'woff',
  'woff2',
  'eot',
  'mp3',
  'mp4',
  'wav',
  'ogg',
  'webm',
  'mov',
  'avi',
]);

/**
 * Determine the kind of a file purely from its extension, with no I/O.
 * Returns everything except `'too-large'`, which is set after reading the file
 * and checking the `truncated` flag from the FS layer.
 */
export function getFileKind(filePath: string): Exclude<ManagedFileKind, 'too-large'> {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? '';
  if (RASTER_EXTS.has(ext)) return 'image';
  if (ext === 'svg') return 'svg';
  if (ext === 'pdf') return 'pdf';
  if (ext === 'csv') return 'csv';
  if (ext === 'md' || ext === 'mdx') return 'markdown';
  if (HTML_EXTS.has(ext)) return 'html';
  if (BINARY_EXTS.has(ext)) return 'binary';
  return 'text';
}

/** True for file kinds that default to rendered/preview mode. */
export function isPreviewableKind(kind: ManagedFileKind): boolean {
  return (
    kind === 'svg' || kind === 'markdown' || kind === 'html' || kind === 'csv' || kind === 'pdf'
  );
}

/** True for files backed by Monaco text models for source editing and saving. */
export function isMonacoBackedKind(kind: ManagedFileKind): boolean {
  return (
    kind === 'text' || kind === 'svg' || kind === 'markdown' || kind === 'html' || kind === 'csv'
  );
}

/** True for files the diff viewer must not load into Monaco. */
export function isBinaryForDiff(filePath: string): boolean {
  const kind = getFileKind(filePath);
  return kind === 'binary' || kind === 'image' || kind === 'svg' || kind === 'pdf';
}

/** True for files the diff viewer renders as an `<img>` preview instead of text. */
export function isImageForDiff(filePath: string): boolean {
  const kind = getFileKind(filePath);
  return kind === 'image' || kind === 'svg';
}
