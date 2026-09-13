import { err, ok, type Result } from '@emdash/shared';
import { invalidPath, type PathError } from './errors';
import type { UnicodeNormalization } from './types';

export function normalizeSegment(value: string, normalization: UnicodeNormalization): string {
  return normalization === 'nfc' ? value.normalize('NFC') : value;
}

export function validateSegment(
  segment: string,
  input: string,
  options: { normalization: UnicodeNormalization; allowBackslash: boolean }
): Result<string, PathError> {
  const normalized = normalizeSegment(segment, options.normalization);
  if (!normalized) return err(invalidPath(input, 'Path contains an empty segment'));
  if (normalized === '.' || normalized === '..') {
    return err(invalidPath(input, 'Path contains unresolved relative segments'));
  }
  if (normalized.includes('\0')) return err(invalidPath(input, 'Path contains a null byte'));
  if (normalized.includes('/')) return err(invalidPath(input, 'Path segment contains a slash'));
  if (!options.allowBackslash && normalized.includes('\\')) {
    return err(invalidPath(input, 'Path segment contains a backslash'));
  }
  return ok(normalized);
}

export function normalizeSegmentStack(
  segments: readonly string[],
  input: string,
  options: {
    normalization: UnicodeNormalization;
    allowBackslash: boolean;
    allowRootEscape: boolean;
  }
): Result<string[], PathError> {
  const output: string[] = [];
  for (const rawSegment of segments) {
    if (!rawSegment || rawSegment === '.') continue;
    if (rawSegment === '..') {
      if (output.length === 0) {
        if (options.allowRootEscape) {
          output.push('..');
          continue;
        }
        return err(invalidPath(input, 'Path escapes its root'));
      }
      output.pop();
      continue;
    }
    const segment = validateSegment(rawSegment, input, options);
    if (!segment.success) return segment;
    output.push(segment.data);
  }
  return ok(output);
}

export function splitPortableInput(input: string): string[] {
  return input.replace(/\\/g, '/').split('/');
}

export function splitWindowsInput(input: string): string[] {
  return input.replace(/\\/g, '/').split('/');
}

export function splitPosixInput(input: string): string[] {
  return input.split('/');
}
