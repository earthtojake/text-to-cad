import { describe, expect, it, vi } from 'vitest';
import type { BoundExec } from '#services/exec/api';
import { validateWorktreePath } from './worktree-path-safety';

describe('validateWorktreePath', () => {
  it('allows missing external targets for creation', async () => {
    await expect(
      validateWorktreePath({
        repoPath: '/repo',
        targetPath: '/worktrees/task',
        mutation: 'create',
        pathExists: async () => false,
      })
    ).resolves.toEqual({ success: true, data: undefined });
  });

  it('rejects creating a nested worktree inside the repository', async () => {
    await expect(
      validateWorktreePath({
        repoPath: '/repo',
        targetPath: '/repo/.worktrees/task',
        mutation: 'create',
        pathExists: async () => false,
      })
    ).resolves.toMatchObject({
      success: false,
      error: { code: 'unsafe-worktree-path' },
    });
  });

  it('rejects a missing target whose existing ancestor resolves inside the repository', async () => {
    await expect(
      validateWorktreePath({
        repoPath: '/real/repo',
        targetPath: '/pool/task',
        mutation: 'create',
        pathExists: async () => false,
        canonicalPath: async (value) => value,
        canonicalPotentialPath: async (value) =>
          value === '/pool/task' ? '/real/repo/worktrees/task' : value,
      })
    ).resolves.toMatchObject({
      success: false,
      error: { code: 'unsafe-worktree-path' },
    });
  });

  it('allows an existing worktree owned by the repository regardless of placement', async () => {
    await expect(
      validateWorktreePath({
        repoPath: '/repo',
        targetPath: '/legacy-pool/task',
        mutation: 'remove',
        pathExists: async () => true,
        createGitExec: gitFactory({
          '/repo': '/repo/.git',
          '/legacy-pool/task': '/repo/.git',
        }),
        canonicalPath: async (value) => value,
      })
    ).resolves.toEqual({ success: true, data: undefined });
  });

  it('rejects worktrees owned by another repository', async () => {
    await expect(
      validateWorktreePath({
        repoPath: '/repo',
        targetPath: '/worktrees/foreign',
        mutation: 'remove',
        pathExists: async () => true,
        createGitExec: gitFactory({
          '/repo': '/repo/.git',
          '/worktrees/foreign': '/other/.git',
        }),
        canonicalPath: async (value) => value,
      })
    ).resolves.toMatchObject({
      success: false,
      error: { code: 'foreign-worktree' },
    });
  });

  it('rejects existing non-worktree targets', async () => {
    await expect(
      validateWorktreePath({
        repoPath: '/repo',
        targetPath: '/worktrees/plain-directory',
        mutation: 'remove',
        pathExists: async () => true,
        createGitExec: gitFactory({
          '/repo': '/repo/.git',
          '/worktrees/plain-directory': null,
        }),
        canonicalPath: async (value) => value,
      })
    ).resolves.toMatchObject({
      success: false,
      error: { code: 'unsafe-worktree-path' },
    });
  });

  it('compares canonical common directories', async () => {
    await expect(
      validateWorktreePath({
        repoPath: '/repo-link',
        targetPath: '/worktrees/task',
        mutation: 'remove',
        pathExists: async () => true,
        createGitExec: gitFactory({
          '/repo-link': '/repo-link/.git',
          '/worktrees/task': '/real/repo/.git',
        }),
        canonicalPath: async (value) => (value === '/repo-link/.git' ? '/real/repo/.git' : value),
      })
    ).resolves.toEqual({ success: true, data: undefined });
  });
});

function gitFactory(commonDirs: Record<string, string | null>) {
  return (cwd: string): BoundExec => ({
    file: 'git',
    cwd,
    exec: vi.fn(async () => {
      const commonDir = commonDirs[cwd];
      if (!commonDir) throw new Error('not a git repository');
      return { stdout: `${commonDir}\n`, stderr: '' };
    }),
    execStreaming: vi.fn(),
    execBuffer: vi.fn(),
    spawn: vi.fn(),
    withCwd: vi.fn(),
  });
}
