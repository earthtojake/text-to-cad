import { describe, expect, it } from 'vitest';
import type { PortableRelativePath } from '#primitives/path/api';
import {
  canonicalExclusionPatterns,
  ExclusionPolicy,
  normalizeExclusionPatterns,
} from './exclusion-policy';

const relative = (path: string) => path as PortableRelativePath;

describe('ExclusionPolicy', () => {
  it('excludes bare segment names anywhere in the path', () => {
    const policy = new ExclusionPolicy(['node_modules', '.git'], { caseSensitive: true });

    expect(policy.excludes(relative('node_modules/pkg/index.js'))).toBe(true);
    expect(policy.excludes(relative('packages/app/.git/config'))).toBe(true);
    expect(policy.excludes(relative('src/node_modules.ts'))).toBe(false);
  });

  it('matches glob patterns against paths and ancestor directories', () => {
    const policy = new ExclusionPolicy(['src/generated', '**/*.snap'], { caseSensitive: true });

    expect(policy.excludes(relative('src/generated/client.ts'))).toBe(true);
    expect(policy.excludes(relative('src/components/button.snap'))).toBe(true);
    expect(policy.excludes(relative('src/components/button.ts'))).toBe(false);
  });

  it('can match case-insensitively', () => {
    const policy = new ExclusionPolicy(['Thumbs.db'], { caseSensitive: false });

    expect(policy.excludes(relative('assets/thumbs.DB'))).toBe(true);
  });

  it('generates ripgrep and watcher globs for segment and glob patterns', () => {
    const policy = new ExclusionPolicy(['node_modules', 'src/generated'], {
      caseSensitive: true,
    });

    expect(policy.ripgrepGlobs()).toEqual([
      '!**/node_modules',
      '!**/node_modules/**',
      '!src/generated',
      '!src/generated/**',
    ]);
    expect(policy.watchIgnoreGlobs()).toEqual([
      'node_modules',
      'node_modules/**',
      '**/node_modules',
      '**/node_modules/**',
      'src/generated',
      'src/generated/**',
    ]);
  });

  it('normalizes user-entered patterns', () => {
    expect(
      normalizeExclusionPatterns([' ./src//generated/ ', 'src/generated', '', 'dist\\out'])
    ).toEqual(['src/generated', 'dist/out']);
  });
});

describe('canonicalExclusionPatterns', () => {
  it('returns a sorted, deduped, normalized list', () => {
    expect(canonicalExclusionPatterns(['dist', '.git', 'dist', 'build'])).toEqual([
      '.git',
      'build',
      'dist',
    ]);
  });

  it('treats different orderings as identical', () => {
    const a = canonicalExclusionPatterns(['dist', 'build', 'node_modules']);
    const b = canonicalExclusionPatterns(['node_modules', 'dist', 'build']);
    expect(a).toEqual(b);
  });

  it('handles normalization before sorting', () => {
    expect(canonicalExclusionPatterns([' dist/ ', './build', 'node_modules'])).toEqual([
      'build',
      'dist',
      'node_modules',
    ]);
  });
});
