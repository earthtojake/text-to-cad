import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { DefaultFileSearchExclusions } from '../../exclusions';
import { hostPath as absolute, relativePath as relative } from '../../testing/paths';
import { createRipgrepContentSearchArgs } from './ripgrep-args';

describe('createRipgrepContentSearchArgs', () => {
  const exclusions = new DefaultFileSearchExclusions({ caseSensitive: true });

  it('uses literal case-insensitive JSON search, hard exclusions, and an argument boundary', () => {
    const args = createRipgrepContentSearchArgs(
      {
        root: absolute('/workspace'),
        rootPath: '/workspace',
        searchPath: path.join('/workspace', 'src', 'nested'),
        query: '-needle',
        under: relative('src/nested'),
        limit: 1_000,
      },
      exclusions
    );

    expect(args).toEqual(
      expect.arrayContaining([
        '--json',
        '--hidden',
        '--no-require-git',
        '--no-config',
        '--fixed-strings',
        '--ignore-case',
        '--no-follow',
        '!**/node_modules/**',
      ])
    );
    expect(args.slice(-3)).toEqual(['--', '-needle', path.join('src', 'nested')]);
    expect(args.some((argument) => argument.startsWith('--max-columns'))).toBe(false);

    expect(
      createRipgrepContentSearchArgs(
        {
          root: absolute('/tmp/workspace'),
          rootPath: '/tmp/workspace',
          searchPath: '/tmp/workspace',
          query: 'needle',
          limit: 1_000,
        },
        exclusions
      ).slice(-1)
    ).toEqual(['.']);
    expect(() =>
      createRipgrepContentSearchArgs(
        {
          root: absolute('/workspace'),
          rootPath: '/workspace',
          searchPath: '/outside',
          query: 'needle',
          limit: 1_000,
        },
        exclusions
      )
    ).toThrow('outside');
  });

  it('compiles the supplied domain exclusions instead of maintaining a second list', () => {
    const args = createRipgrepContentSearchArgs(
      {
        root: absolute('/workspace'),
        rootPath: '/workspace',
        searchPath: '/workspace',
        query: 'needle',
        limit: 1_000,
      },
      {
        excludes: () => false,
        ripgrepGlobs: () => ['!**/generated/**'],
        watchIgnoreGlobs: () => [],
      }
    );

    expect(args).toContain('!**/generated/**');
    expect(args).not.toContain('!**/node_modules/**');
  });
});
