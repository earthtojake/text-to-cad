import { describe, expect, it } from 'vitest';
import type { HostAbsolutePath } from '#primitives/path/api';
import { parseWorktreeList } from './worktrees';

const parsePath = (filePath: string) => filePath as unknown as HostAbsolutePath;

describe('parseWorktreeList', () => {
  it('keeps prunable reasons from porcelain output', () => {
    const worktrees = parseWorktreeList(
      [
        'worktree /repo',
        'HEAD 123',
        'branch refs/heads/main',
        '',
        'worktree /repo/stale',
        'HEAD 456',
        'branch refs/heads/feature/stale',
        'prunable gitdir file points to non-existent location',
        '',
      ].join('\n'),
      parsePath
    );

    expect(worktrees[1]).toMatchObject({
      worktreePath: '/repo/stale',
      prunable: true,
      prunableReason: 'gitdir file points to non-existent location',
    });
  });

  it('keeps bare prunable, locked, and detached summaries', () => {
    const worktrees = parseWorktreeList(
      [
        'worktree /repo',
        'HEAD 123',
        'branch refs/heads/main',
        '',
        'worktree /repo/detached',
        'HEAD 456',
        'detached',
        'locked',
        'prunable',
        '',
      ].join('\n'),
      parsePath
    );

    expect(worktrees[1]).toMatchObject({
      worktreePath: '/repo/detached',
      head: { kind: 'detached' },
      locked: true,
      prunable: true,
    });
    expect(worktrees[1]?.prunableReason).toBeUndefined();
  });
});
