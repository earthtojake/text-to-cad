import path from 'node:path';
import type { FileSearchExclusions } from '../../exclusions';
import type { ResolvedContentSearchInput } from '../content-searcher';

export function createRipgrepContentSearchArgs(
  input: ResolvedContentSearchInput,
  exclusions: FileSearchExclusions
): string[] {
  const args = [
    '--hidden',
    '--no-require-git',
    '--no-config',
    '--json',
    '--fixed-strings',
    '--ignore-case',
    '--no-follow',
  ];
  const globFlag = process.platform === 'win32' ? '--iglob' : '--glob';

  for (const glob of exclusions.ripgrepGlobs()) args.push(globFlag, glob);

  const relativeSearchPath = path.relative(input.rootPath, input.searchPath);
  if (
    relativeSearchPath === '..' ||
    relativeSearchPath.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relativeSearchPath)
  ) {
    throw new Error('Resolved content-search path is outside the registered root');
  }
  args.push('--', input.query, relativeSearchPath || '.');
  return args;
}
