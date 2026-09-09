import { describe, expect, it } from 'vitest';
import { compileWorktreePayload } from './compile-worktree-payload';

describe('compileWorktreePayload', () => {
  it.each([
    {
      repoPath: '/Users/test/code/emdash',
      worktreeRoot: '/Users/test/emdash/worktrees',
      branchName: 'feature/compiler',
      legacyPath: '/Users/test/emdash/worktrees/emdash-6190d212/feature-compiler',
    },
    {
      repoPath: '/srv/repos/my repo',
      worktreeRoot: '/srv/worktrees',
      branchName: 'feature/über long branch',
      legacyPath: '/srv/worktrees/my repo-f7826658/feature--ber-long-branch',
    },
    {
      repoPath: '/srv/repos/répo',
      worktreeRoot: '/srv/worktrees',
      branchName: 'feature',
      legacyPath: '/srv/worktrees/répo-8c4df4f6/feature',
    },
    {
      repoPath:
        '/Users/test/code/very-long-repository-name-very-long-repository-name-' +
        'very-long-repository-name-very-long-repository-name-',
      worktreeRoot: '/worktrees',
      branchName: 'feature',
      legacyPath:
        '/worktrees/very-long-repository-name-very-long-repository-name-' +
        'very-long-repository-name-very-long-repository-name--dec769ef/feature',
    },
  ])('matches the legacy path compiler for $branchName', (input) => {
    expect(compileWorktreePayload(input)).toEqual({
      worktreePath: input.legacyPath,
      branchName: input.branchName,
      preservePatterns: [],
    });
  });

  it('uses Windows separators for Windows roots', () => {
    const result = compileWorktreePayload({
      repoPath: String.raw`C:\Users\test\code\emdash`,
      worktreeRoot: String.raw`C:\Users\test\emdash\worktrees`,
      branchName: 'fix/windows/path',
    });

    expect(result.worktreePath).toMatch(
      /^C:\\Users\\test\\emdash\\worktrees\\emdash-[a-f0-9]{8}\\fix-windows-path$/u
    );
  });

  it('copies preserve patterns into the payload', () => {
    const preservePatterns = ['.env', 'local/**'];
    const result = compileWorktreePayload({
      repoPath: '/repo/app',
      worktreeRoot: '/worktrees',
      branchName: 'feature',
      preservePatterns,
    });

    expect(result.preservePatterns).toEqual(preservePatterns);
    expect(result.preservePatterns).not.toBe(preservePatterns);
  });

  it.each([
    ['.', 'branch'],
    ['..', 'branch'],
    ['CON', 'CON-branch'],
    ['com1.txt', 'com1.txt-branch'],
  ])('keeps special branch names inside the worktree pool: %s', (branchName, segment) => {
    const result = compileWorktreePayload({
      repoPath: '/repo/app',
      worktreeRoot: '/worktrees',
      branchName,
    });

    expect(result.worktreePath).toMatch(new RegExp(`/${segment.replace('.', '\\.')}$`, 'u'));
  });
});
