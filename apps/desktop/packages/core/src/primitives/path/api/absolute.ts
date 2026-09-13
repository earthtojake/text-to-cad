import { err, ok, type Result } from '@emdash/shared';
import { incompatibleRoot, invalidPath, outsideRoot, type PathError } from './errors';
import { normalizeSegmentStack, splitPosixInput, splitWindowsInput } from './segments';
import { createPathProfile } from './semantics';
import type { HostAbsolutePath, HostPathRoot, PathProfile } from './types';

export type ParseAbsoluteOptions = Readonly<{
  profile?: Partial<PathProfile>;
}>;

export type FormatAbsoluteOptions = Readonly<{
  separator?: '/' | '\\';
  trailingSlash?: 'strip' | 'keep';
}>;

export function parseAbsolute(
  input: string,
  options: ParseAbsoluteOptions = {}
): Result<HostAbsolutePath, PathError> {
  if (input.includes('\0')) return err(invalidPath(input, 'Path contains a null byte'));
  const profile = createPathProfile({
    ...options.profile,
    unicodeNormalization: options.profile?.unicodeNormalization ?? 'preserve',
  });
  return profile.style === 'win32'
    ? parseWindowsAbsolute(input, profile)
    : parsePosixAbsolute(input, profile);
}

export function formatAbsolute(
  path: HostAbsolutePath,
  options: FormatAbsoluteOptions = {}
): string {
  const separator = options.separator ?? '/';
  const trailingSlash = options.trailingSlash ?? 'strip';
  const joinSegments = (segments: readonly string[]) => segments.join(separator);
  const suffix = path.segments.length > 0 ? joinSegments(path.segments) : '';
  const trailing = trailingSlash === 'keep' && path.segments.length === 0 ? separator : '';

  switch (path.root.kind) {
    case 'posix':
      return suffix ? `/${suffix}` : '/';
    case 'drive':
      return suffix
        ? `${path.root.driveLetter}:${separator}${suffix}`
        : `${path.root.driveLetter}:${separator}`;
    case 'unc': {
      const prefix = `${separator}${separator}${path.root.server}${separator}${path.root.share}`;
      return suffix ? `${prefix}${separator}${suffix}` : `${prefix}${trailing}`;
    }
  }
}

export function tryParseAbsolute(
  input: string,
  options: ParseAbsoluteOptions = {}
): HostAbsolutePath | null {
  const parsed = parseAbsolute(input, options);
  return parsed.success ? parsed.data : null;
}

export function absoluteRootEquals(a: HostPathRoot, b: HostPathRoot): boolean {
  if (a.kind !== b.kind) return false;
  switch (a.kind) {
    case 'posix':
      return true;
    case 'drive':
      return b.kind === 'drive' && a.driveLetter === b.driveLetter;
    case 'unc':
      return b.kind === 'unc' && a.server === b.server && a.share === b.share;
  }
}

export function absoluteEquals(a: HostAbsolutePath, b: HostAbsolutePath): boolean {
  return absoluteRootEquals(a.root, b.root) && segmentsEqual(a.segments, b.segments);
}

export function absoluteBasename(path: HostAbsolutePath): string {
  return path.segments.at(-1) ?? '';
}

export function absoluteDirname(path: HostAbsolutePath): HostAbsolutePath | null {
  if (path.segments.length === 0) return null;
  return { root: path.root, segments: path.segments.slice(0, -1) };
}

export function joinAbsolute(
  base: HostAbsolutePath,
  ...segments: string[]
): Result<HostAbsolutePath, PathError> {
  const input = segments.join('/');
  const allowBackslash = base.root.kind === 'posix';
  const normalized = normalizeSegmentStack(
    segments.flatMap((segment) => (allowBackslash ? segment.split('/') : segment.split(/[\\/]/u))),
    input,
    {
      normalization: 'preserve',
      allowBackslash,
      allowRootEscape: false,
    }
  );
  if (!normalized.success) return normalized;
  return ok({ root: base.root, segments: [...base.segments, ...normalized.data] });
}

export function containsAbsolute(root: HostAbsolutePath, candidate: HostAbsolutePath): boolean {
  if (!absoluteRootEquals(root.root, candidate.root)) return false;
  if (root.segments.length > candidate.segments.length) return false;
  return root.segments.every((segment, index) => segment === candidate.segments[index]);
}

export function relativeSegmentsFromAbsolute(
  root: HostAbsolutePath,
  candidate: HostAbsolutePath
): Result<readonly string[], PathError> {
  if (!absoluteRootEquals(root.root, candidate.root)) {
    return err(incompatibleRoot(formatAbsolute(candidate), 'Path roots are not compatible'));
  }
  if (!containsAbsolute(root, candidate)) {
    return err(
      outsideRoot(formatAbsolute(candidate), formatAbsolute(root), 'Path is outside root')
    );
  }
  return ok(candidate.segments.slice(root.segments.length));
}

function parsePosixAbsolute(
  input: string,
  profile: PathProfile
): Result<HostAbsolutePath, PathError> {
  if (!input.startsWith('/')) return err(invalidPath(input, 'Path must be POSIX absolute'));
  const segments = normalizeSegmentStack(splitPosixInput(input).slice(1), input, {
    normalization: profile.unicodeNormalization,
    allowBackslash: true,
    allowRootEscape: false,
  });
  if (!segments.success) return segments;
  return ok({ root: { kind: 'posix' }, segments: segments.data });
}

function parseWindowsAbsolute(
  input: string,
  profile: PathProfile
): Result<HostAbsolutePath, PathError> {
  const windowsInput = input.replace(/\\/g, '/');
  if (windowsInput.startsWith('//')) return parseUncAbsolute(input, windowsInput, profile);

  const driveMatch = /^([A-Za-z]):\//u.exec(windowsInput);
  if (!driveMatch) {
    return err(invalidPath(input, 'Path must be Windows drive or UNC absolute'));
  }
  const driveLetter = driveMatch[1].toUpperCase();
  const segments = normalizeSegmentStack(splitWindowsInput(windowsInput.slice(3)), input, {
    normalization: profile.unicodeNormalization,
    allowBackslash: false,
    allowRootEscape: false,
  });
  if (!segments.success) return segments;
  return ok({ root: { kind: 'drive', driveLetter }, segments: segments.data });
}

function parseUncAbsolute(
  input: string,
  windowsInput: string,
  profile: PathProfile
): Result<HostAbsolutePath, PathError> {
  const parts = splitWindowsInput(windowsInput).filter((part) => part.length > 0);
  if (parts.length < 2) return err(invalidPath(input, 'UNC path must include server and share'));
  const [server, share, ...rawSegments] = parts;
  const normalizedServer = normalizeSegmentStack([server], input, {
    normalization: profile.unicodeNormalization,
    allowBackslash: false,
    allowRootEscape: false,
  });
  if (!normalizedServer.success) return normalizedServer;
  const normalizedShare = normalizeSegmentStack([share], input, {
    normalization: profile.unicodeNormalization,
    allowBackslash: false,
    allowRootEscape: false,
  });
  if (!normalizedShare.success) return normalizedShare;
  const segments = normalizeSegmentStack(rawSegments, input, {
    normalization: profile.unicodeNormalization,
    allowBackslash: false,
    allowRootEscape: false,
  });
  if (!segments.success) return segments;
  return ok({
    root: { kind: 'unc', server: normalizedServer.data[0], share: normalizedShare.data[0] },
    segments: segments.data,
  });
}

function segmentsEqual(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((segment, index) => segment === b[index]);
}
