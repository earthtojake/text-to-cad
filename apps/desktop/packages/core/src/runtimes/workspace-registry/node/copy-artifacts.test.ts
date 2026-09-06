import { execFileSync } from 'node:child_process';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { executeCopyArtifacts } from './copy-artifacts';
import { createRegistryGitContext } from './git-context';

const gitContext = createRegistryGitContext();

// Unit tests for the copy-artifacts background step (spec: workspace-lifecycle-v2,
// preserved-artifact copy): exactly the gitignored entries named in preservePatterns
// materialize in the new worktree; tracked files are never overwritten; replays after
// a torn copy converge; enumeration scales with the matched set.

function git(cwd: string, ...args: string[]): string {
  return execFileSync('git', args, {
    cwd,
    encoding: 'utf8',
    env: {
      ...process.env,
      GIT_AUTHOR_NAME: 'Test',
      GIT_AUTHOR_EMAIL: 'test@example.com',
      GIT_COMMITTER_NAME: 'Test',
      GIT_COMMITTER_EMAIL: 'test@example.com',
      GIT_TERMINAL_PROMPT: '0',
    },
  }).trim();
}

describe('executeCopyArtifacts', () => {
  let root: string;
  let repoPath: string;
  let worktreePath: string;

  beforeEach(async () => {
    root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'ws-copy-')));
    repoPath = path.join(root, 'repo');
    await fs.mkdir(repoPath, { recursive: true });
    git(repoPath, 'init', '--initial-branch=main');
    await fs.writeFile(path.join(repoPath, 'README.md'), '# repo\n');
    await fs.writeFile(path.join(repoPath, '.gitignore'), 'node_modules/\ndist/\n.env*\n*.log\n');
    git(repoPath, 'add', '.');
    git(repoPath, 'commit', '-m', 'initial');

    // Ignored artifacts at several depths, plus tracked and untracked neighbors.
    await fs.mkdir(path.join(repoPath, 'node_modules', 'dep'), { recursive: true });
    await fs.writeFile(path.join(repoPath, 'node_modules', 'dep', 'index.js'), 'dep\n');
    await fs.mkdir(path.join(repoPath, 'dist'), { recursive: true });
    await fs.writeFile(path.join(repoPath, 'dist', 'out.js'), 'built\n');
    await fs.writeFile(path.join(repoPath, '.env'), 'SECRET=1\n');
    await fs.writeFile(path.join(repoPath, '.env.local'), 'LOCAL=1\n');
    await fs.writeFile(path.join(repoPath, 'debug.log'), 'log\n');
    await fs.writeFile(path.join(repoPath, 'untracked.txt'), 'untracked but not ignored\n');

    worktreePath = path.join(root, 'wt');
    git(repoPath, 'worktree', 'add', '-b', 'copy-test', worktreePath, 'main');
  });

  afterEach(async () => {
    await fs.rm(root, { recursive: true, force: true });
  });

  it('copies exactly the matched gitignored entries and nothing else', async () => {
    const outcome = await executeCopyArtifacts({
      git: gitContext,
      repositoryPath: repoPath,
      worktreePath,
      preservePatterns: ['.env*', 'dist'],
    });

    expect(outcome.status).toBe('succeeded');
    if (outcome.status !== 'succeeded') return;
    // .env, .env.local, and the dist directory (one entry each) = 3 entries.
    expect(outcome.entries).toBe(3);
    expect(await fs.readFile(path.join(worktreePath, '.env'), 'utf8')).toBe('SECRET=1\n');
    expect(await fs.readFile(path.join(worktreePath, '.env.local'), 'utf8')).toBe('LOCAL=1\n');
    await fs.access(path.join(worktreePath, 'dist', 'out.js'));
    // Non-matched ignored artifacts stay behind.
    await expect(fs.access(path.join(worktreePath, 'node_modules'))).rejects.toThrow();
    await expect(fs.access(path.join(worktreePath, 'debug.log'))).rejects.toThrow();
    // Tracked files stay untouched and git status stays clean.
    expect(git(worktreePath, 'status', '--porcelain')).toBe('');
  });

  it('skips with no patterns configured and copies nothing', async () => {
    const outcome = await executeCopyArtifacts({
      git: gitContext,
      repositoryPath: repoPath,
      worktreePath,
      preservePatterns: [],
    });
    expect(outcome).toEqual({ status: 'skipped', reason: 'No preservePatterns configured' });
    await expect(fs.access(path.join(worktreePath, '.env'))).rejects.toThrow();
  });

  it('never copies over tracked or merely-untracked files (check-ignore filter)', async () => {
    await fs.writeFile(path.join(repoPath, 'README.md'), '# diverged in source\n');
    const outcome = await executeCopyArtifacts({
      git: gitContext,
      repositoryPath: repoPath,
      worktreePath,
      // Match a tracked file and an untracked-but-not-ignored file explicitly.
      preservePatterns: ['README.md', 'untracked.txt', '.env'],
    });
    expect(outcome.status).toBe('succeeded');
    if (outcome.status !== 'succeeded') return;
    expect(outcome.entries).toBe(1);
    // The tracked README keeps the checkout's content, not the source's divergence.
    expect(await fs.readFile(path.join(worktreePath, 'README.md'), 'utf8')).toBe('# repo\n');
    await expect(fs.access(path.join(worktreePath, 'untracked.txt'))).rejects.toThrow();
    expect(await fs.readFile(path.join(worktreePath, '.env'), 'utf8')).toBe('SECRET=1\n');
  });

  it('rejects escaping and absolute patterns with warnings instead of copying', async () => {
    const outcome = await executeCopyArtifacts({
      git: gitContext,
      repositoryPath: repoPath,
      worktreePath,
      preservePatterns: ['../outside', '/absolute'],
    });
    expect(outcome).toEqual({
      status: 'succeeded',
      engine: 'none',
      entries: 0,
      warnings: [
        'Skipped unsafe preserve pattern "../outside"',
        'Skipped unsafe preserve pattern "/absolute"',
      ],
    });
  });

  it('replays idempotently: existing entries are trusted, missing ones are redone', async () => {
    const first = await executeCopyArtifacts({
      git: gitContext,
      repositoryPath: repoPath,
      worktreePath,
      preservePatterns: ['.env', 'dist'],
    });
    expect(first.status).toBe('succeeded');

    // A replayed copy must not clobber divergent workspace state...
    await fs.writeFile(path.join(worktreePath, '.env'), 'SECRET=changed\n');
    // ...and must redo entries that are missing (simulated torn copy), including
    // cleaning up an abandoned staging directory.
    await fs.rm(path.join(worktreePath, 'dist'), { recursive: true });
    await fs.mkdir(path.join(worktreePath, 'dist.emdash-clone-tmp'), { recursive: true });
    await fs.writeFile(path.join(worktreePath, 'dist.emdash-clone-tmp', 'torn'), 'partial\n');

    const second = await executeCopyArtifacts({
      git: gitContext,
      repositoryPath: repoPath,
      worktreePath,
      preservePatterns: ['.env', 'dist'],
    });
    expect(second.status).toBe('succeeded');
    if (second.status !== 'succeeded') return;
    expect(second.entries).toBe(2);
    expect(await fs.readFile(path.join(worktreePath, '.env'), 'utf8')).toBe('SECRET=changed\n');
    await fs.access(path.join(worktreePath, 'dist', 'out.js'));
    await expect(fs.access(path.join(worktreePath, 'dist.emdash-clone-tmp'))).rejects.toThrow();
  });

  it('a preserved directory counts as one entry and nested matches ride their parent', async () => {
    const outcome = await executeCopyArtifacts({
      git: gitContext,
      repositoryPath: repoPath,
      worktreePath,
      // Both the directory and a file inside it match; the file rides the directory.
      preservePatterns: ['dist', 'dist/out.js'],
    });
    expect(outcome.status).toBe('succeeded');
    if (outcome.status !== 'succeeded') return;
    expect(outcome.entries).toBe(1);
    await fs.access(path.join(worktreePath, 'dist', 'out.js'));
  });

  it('clones symlinks as symlinks, never following them', async () => {
    await fs.symlink('/etc', path.join(repoPath, 'ignored-link'));
    await fs.appendFile(path.join(repoPath, '.gitignore'), 'ignored-link\n');
    git(repoPath, 'add', '.gitignore');
    git(repoPath, 'commit', '-m', 'ignore link');
    // The worktree's .gitignore lags behind; check-ignore runs in the source repo.
    const outcome = await executeCopyArtifacts({
      git: gitContext,
      repositoryPath: repoPath,
      worktreePath,
      preservePatterns: ['ignored-link'],
    });
    expect(outcome.status).toBe('succeeded');
    const stat = await fs.lstat(path.join(worktreePath, 'ignored-link'));
    expect(stat.isSymbolicLink()).toBe(true);
    expect(await fs.readlink(path.join(worktreePath, 'ignored-link'))).toBe('/etc');
  });
});
