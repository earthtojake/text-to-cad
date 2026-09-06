/**
 * Unit tests for mention-pill-helpers.
 * Pure-function tests — no DOM or React required.
 */

import { describe, expect, it } from 'vitest';
import { basename, fileIconClass } from './mention-pill-helpers';

describe('basename', () => {
  it('returns the last path segment', () => {
    expect(basename('src/components/foo.tsx')).toBe('foo.tsx');
  });

  it('returns the filename when there is no directory', () => {
    expect(basename('foo.tsx')).toBe('foo.tsx');
  });

  it('normalizes backslash separators', () => {
    expect(basename('src\\components\\bar.ts')).toBe('bar.ts');
  });

  it('handles deep paths', () => {
    expect(basename('a/b/c/d/e.json')).toBe('e.json');
  });

  it('returns empty string for empty input', () => {
    expect(basename('')).toBe('');
  });

  it('handles trailing slash gracefully', () => {
    // Last segment is empty — returns ''.
    expect(basename('src/components/')).toBe('');
  });
});

describe('fileIconClass', () => {
  it('resolves a TypeScript file icon', () => {
    const cls = fileIconClass('src/utils.ts');
    expect(cls).toBe('devicon-typescript-plain colored');
  });

  it('resolves a TSX file (React icon)', () => {
    const cls = fileIconClass('components/Button.tsx');
    expect(cls).toBe('devicon-react-original colored');
  });

  it('resolves a known config file by full name', () => {
    const cls = fileIconClass('package.json');
    expect(cls).toBe('devicon-npm-original-wordmark colored');
  });

  it('returns null for an unknown extension', () => {
    expect(fileIconClass('file.unknownext')).toBeNull();
  });

  it('resolves a full path by looking at the basename extension', () => {
    expect(fileIconClass('src/lib/utils.py')).toBe('devicon-python-plain colored');
  });
});
