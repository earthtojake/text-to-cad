import path from 'node:path';
import { describe, expect, it } from 'vitest';
import type { FileSearchExclusions } from '../../exclusions';
import { affectedSubtrees } from './affected-subtrees';

const exclusions: FileSearchExclusions = {
  excludes: (relativePath) => relativePath === 'excluded' || relativePath.startsWith('excluded/'),
  ripgrepGlobs: () => [],
  watchIgnoreGlobs: () => [],
};

describe('affectedSubtrees', () => {
  const rootPath = path.resolve('workspace');

  it('ignores relative, outside-root, and excluded event paths', () => {
    expect(
      affectedSubtrees(
        [
          { kind: 'create', path: 'relative.ts' },
          { kind: 'create', path: path.resolve('outside.ts') },
          { kind: 'create', path: path.join(rootPath, 'excluded', 'generated.ts') },
          { kind: 'create', path: path.join(rootPath, 'src', 'index.ts') },
        ],
        rootPath,
        exclusions
      )
    ).toEqual(['src/index.ts']);
  });

  it('deduplicates paths and removes descendants of affected ancestors', () => {
    expect(
      affectedSubtrees(
        [
          { kind: 'update', path: path.join(rootPath, 'src', 'nested', 'deep.ts') },
          { kind: 'update', path: path.join(rootPath, 'src') },
          { kind: 'update', path: path.join(rootPath, 'src', 'other.ts') },
          { kind: 'update', path: path.join(rootPath, 'README.md') },
          { kind: 'update', path: path.join(rootPath, 'README.md') },
        ],
        rootPath,
        exclusions
      )
    ).toEqual(['src', 'README.md']);
  });

  it('short-circuits all descendants when the root itself is affected', () => {
    expect(
      affectedSubtrees(
        [
          { kind: 'update', path: path.join(rootPath, 'src', 'index.ts') },
          { kind: 'update', path: rootPath },
        ],
        rootPath,
        exclusions
      )
    ).toEqual(['']);
  });
});
