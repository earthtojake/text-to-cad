import { describe, expect, it } from 'vitest';
import {
  absoluteRuntimePath,
  hostFileRefFromNativePath,
  hostPathFromNative,
  nativePathFromHost,
} from './paths';

describe('hostFileRefFromNativePath', () => {
  it('uses the local host by default', () => {
    expect(hostFileRefFromNativePath('/repo')).toMatchObject({
      host: { type: 'local', id: 'local' },
      path: { root: { kind: 'posix' }, segments: ['repo'] },
    });
  });

  it('uses the supplied remote host identity', () => {
    expect(hostFileRefFromNativePath('/repo', 'ssh-1')).toMatchObject({
      host: { type: 'remote', id: 'ssh-1' },
      path: { root: { kind: 'posix' }, segments: ['repo'] },
    });
  });
});

describe('absoluteRuntimePath', () => {
  it.each([
    ['/repo/worktree', '../shared/types.ts', '/repo/shared/types.ts'],
    ['C:\\repo\\worktree', '..\\shared\\types.ts', 'C:\\repo\\shared\\types.ts'],
    [
      '\\\\server\\share\\repo\\worktree',
      '../shared/types.ts',
      '\\\\server\\share\\repo\\shared\\types.ts',
    ],
  ])('resolves parent-relative paths using the host path style', (root, input, expected) => {
    expect(nativePathFromHost(absoluteRuntimePath(hostPathFromNative(root), input))).toBe(expected);
  });

  it('rejects parent traversal above the host filesystem root', () => {
    expect(() =>
      absoluteRuntimePath(hostPathFromNative('/repo/worktree'), '../../../etc/passwd')
    ).toThrow('Path escapes its root');
  });
});
