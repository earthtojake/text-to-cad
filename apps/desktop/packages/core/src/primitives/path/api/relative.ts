import { err, ok, type Result } from '@emdash/shared';
import { invalidPath, type PathError } from './errors';
import { normalizeSegmentStack, splitPosixInput } from './segments';
import type { PortableRelativePath, UnicodeNormalization } from './types';

export const ROOT_RELATIVE_PATH = '' as PortableRelativePath;

export type ParseRelativeOptions = Readonly<{
  unicodeNormalization?: UnicodeNormalization;
}>;

export function parsePortableRelativePath(
  input: string,
  options: ParseRelativeOptions = {}
): Result<PortableRelativePath, PathError> {
  if (input.includes('\0')) return err(invalidPath(input, 'Path contains a null byte'));
  if (input.startsWith('/')) return err(invalidPath(input, 'Path must be relative'));
  if (/^[A-Za-z]:[/\\]/u.test(input)) return err(invalidPath(input, 'Path must be relative'));
  if (input.startsWith('//') || input.startsWith('\\\\')) {
    return err(invalidPath(input, 'Path must be relative'));
  }

  const normalization = options.unicodeNormalization ?? 'preserve';
  const segments = normalizeSegmentStack(splitPosixInput(input), input, {
    normalization,
    allowBackslash: true,
    allowRootEscape: false,
  });
  if (!segments.success) return segments;
  return ok(segments.data.join('/') as PortableRelativePath);
}

export function tryParsePortableRelativePath(
  input: string,
  options: ParseRelativeOptions = {}
): PortableRelativePath | null {
  const parsed = parsePortableRelativePath(input, options);
  return parsed.success ? parsed.data : null;
}

export function formatPortableRelativePath(path: PortableRelativePath): string {
  return path;
}

export function joinPortableRelativePath(
  base: PortableRelativePath,
  ...segments: string[]
): Result<PortableRelativePath, PathError> {
  const suffix = segments.filter(Boolean).join('/');
  const joined = base && suffix ? `${base}/${suffix}` : base || suffix;
  return parsePortableRelativePath(joined);
}

export function portableRelativePathParts(path: PortableRelativePath): readonly string[] {
  return path ? path.split('/') : [];
}

export function portableRelativePathBasename(path: PortableRelativePath): string {
  return portableRelativePathParts(path).at(-1) ?? '';
}

export function portableRelativePathDirname(
  path: PortableRelativePath
): PortableRelativePath | null {
  const parts = portableRelativePathParts(path);
  if (parts.length === 0) return null;
  if (parts.length === 1) return ROOT_RELATIVE_PATH;
  return parts.slice(0, -1).join('/') as PortableRelativePath;
}

export function portableRelativePathParent(
  path: PortableRelativePath
): PortableRelativePath | null {
  return portableRelativePathDirname(path);
}

export function portableRelativePathEquals(
  a: PortableRelativePath,
  b: PortableRelativePath
): boolean {
  return a === b;
}
