import { execFile } from 'node:child_process';
import { mkdtemp, realpath, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { describe, expect, it } from 'vitest';
import type { PortableRelativePath } from '#primitives/path/api';
import type { CheckoutStatusState } from '#runtimes/git/api';
import type { CheckoutIdentity } from '#runtimes/git/node/allocation/identity';
import { gitPath } from '#runtimes/git/node/testing/paths';
import { createBoundExec } from '#services/exec/api';
import { GitCheckout } from './git-checkout';

const execFileAsync = promisify(execFile);

async function makeRepo(): Promise<string> {
  const repo = await mkdtemp(path.join(tmpdir(), 'emdash-git-checkout-'));
  await execFileAsync('git', ['init', '-b', 'main'], { cwd: repo });
  await execFileAsync('git', ['config', 'user.email', 'test@example.com'], { cwd: repo });
  await execFileAsync('git', ['config', 'user.name', 'Test User'], { cwd: repo });
  await writeFile(path.join(repo, 'tracked.txt'), 'before\n', 'utf8');
  await execFileAsync('git', ['add', 'tracked.txt'], { cwd: repo });
  await execFileAsync('git', ['commit', '-m', 'init'], { cwd: repo });
  return realpath(repo);
}

async function makeCheckout() {
  const repo = await makeRepo();
  const gitDir = path.join(repo, '.git');
  const identity = {
    repositoryId: gitDir,
    objectStoreId: path.join(gitDir, 'objects'),
    checkoutId: JSON.stringify([repo, gitDir]),
    checkoutRoot: repo,
    gitDir,
    gitCommonDir: gitDir,
    objectStoreDir: path.join(gitDir, 'objects'),
  } as CheckoutIdentity;
  const checkout = new GitCheckout({
    identity,
    exec: createBoundExec({ file: 'git', cwd: repo }),
  });
  const cleanup = async () => {
    await rm(repo, { recursive: true, force: true });
  };
  return { repo, checkout, cleanup };
}

function okStatus(model: CheckoutStatusState): Extract<CheckoutStatusState, { kind: 'ok' }> {
  expect(model.kind).toBe('ok');
  if (model.kind !== 'ok') throw new Error(`expected ok status, got ${model.kind}`);
  return model;
}

describe('GitCheckout', () => {
  it('keeps the canonical branch name when a tag has the same name', async () => {
    const { repo, checkout, cleanup } = await makeCheckout();
    try {
      await execFileAsync('git', ['tag', 'main'], { cwd: repo });

      await expect(checkout.getHead()).resolves.toMatchObject({
        kind: 'branch',
        ref: 'refs/heads/main',
        upstream: { kind: 'none' },
      });
    } finally {
      await cleanup();
    }
  });

  it('distinguishes remote upstream identity from tracking resolution', async () => {
    const { repo, checkout, cleanup } = await makeCheckout();
    const remote = await mkdtemp(path.join(tmpdir(), 'emdash-git-checkout-remote-'));
    try {
      await execFileAsync('git', ['init', '--bare'], { cwd: remote });
      await execFileAsync('git', ['remote', 'add', 'origin', remote], { cwd: repo });

      await expect(checkout.publish('origin')).resolves.toMatchObject({
        success: true,
      });
      await expect(checkout.getHead()).resolves.toMatchObject({
        kind: 'branch',
        ref: 'refs/heads/main',
        upstream: {
          kind: 'remote',
          remote: 'origin',
          mergeRef: 'refs/heads/main',
          tracking: {
            kind: 'resolved',
            ref: 'refs/remotes/origin/main',
            ahead: 0,
            behind: 0,
          },
        },
      });

      await execFileAsync('git', ['update-ref', '-d', 'refs/remotes/origin/main'], { cwd: repo });
      await execFileAsync('git', ['config', 'branch.main.merge', 'refs/pull/7/head'], {
        cwd: repo,
      });
      await expect(checkout.getHead()).resolves.toMatchObject({
        kind: 'branch',
        upstream: {
          kind: 'remote',
          remote: 'origin',
          mergeRef: 'refs/pull/7/head',
          tracking: { kind: 'unresolved' },
        },
      });
    } finally {
      await cleanup();
      await rm(remote, { recursive: true, force: true });
    }
  });

  it('represents a local branch as a resolved upstream', async () => {
    const { repo, checkout, cleanup } = await makeCheckout();
    try {
      await execFileAsync('git', ['branch', 'other'], { cwd: repo });
      await execFileAsync('git', ['config', 'branch.main.remote', '.'], { cwd: repo });
      await execFileAsync('git', ['config', 'branch.main.merge', 'refs/heads/other'], {
        cwd: repo,
      });

      await expect(checkout.getHead()).resolves.toMatchObject({
        kind: 'branch',
        ref: 'refs/heads/main',
        upstream: {
          kind: 'local',
          mergeRef: 'refs/heads/other',
          tracking: { kind: 'resolved', ref: 'refs/heads/other' },
        },
      });
    } finally {
      await cleanup();
    }
  });

  it('reads status and head and tracks the staging lifecycle', async () => {
    const { repo, checkout, cleanup } = await makeCheckout();
    try {
      const initialStatus = okStatus(await checkout.getStatus());
      expect(initialStatus.entries).toEqual({});
      expect(initialStatus.operation).toBe('none');
      expect(await checkout.getHead()).toMatchObject({ kind: 'branch', ref: 'refs/heads/main' });

      const trackedPath = gitPath('tracked.txt');
      await writeFile(path.join(repo, trackedPath), 'after\n', 'utf8');
      const dirty = okStatus(await checkout.getStatus());
      expect(dirty.entries[trackedPath]?.worktree).toBe('modified');

      const stageResult = await checkout.stage([trackedPath]);
      expect(stageResult.success).toBe(true);
      const staged = okStatus(await checkout.getStatus());
      expect(staged.entries[trackedPath]).toMatchObject({
        index: 'modified',
        worktree: 'unmodified',
      });
      expect(staged.summary).toMatchObject({ staged: 1, unstaged: 0 });

      const previousHead = await checkout.getHead();
      const previousOid = previousHead.kind === 'branch' ? previousHead.oid : '';
      const commitResult = await checkout.commit('update tracked');
      expect(commitResult.success).toBe(true);
      if (!commitResult.success) throw new Error('commit failed');
      expect(commitResult.data.hash).toMatch(/^[0-9a-f]{40}$/);

      const afterCommit = okStatus(await checkout.getStatus());
      expect(afterCommit.entries).toEqual({});
      expect(await checkout.getHead()).toMatchObject({
        kind: 'branch',
        ref: 'refs/heads/main',
        oid: commitResult.data.hash,
      });
      expect(commitResult.data.hash).not.toBe(previousOid);
    } finally {
      await cleanup();
    }
  });

  it('models untracked files and conflict-free summaries', async () => {
    const { repo, checkout, cleanup } = await makeCheckout();
    try {
      await writeFile(path.join(repo, 'fresh.txt'), 'hello\n', 'utf8');
      const model = okStatus(await checkout.getStatus());
      expect(model.entries[gitPath('fresh.txt')]).toMatchObject({
        index: 'untracked',
        worktree: 'untracked',
        isConflicted: false,
      });
      expect(model.summary).toMatchObject({ untracked: 1, staged: 0, unstaged: 0, conflicted: 0 });
    } finally {
      await cleanup();
    }
  });

  it('separates staged and unstaged changes', async () => {
    const { repo, checkout, cleanup } = await makeCheckout();
    try {
      await writeFile(path.join(repo, 'tracked.txt'), 'staged\n', 'utf8');
      await checkout.stage(['tracked.txt']);
      await writeFile(path.join(repo, 'tracked.txt'), 'unstaged\n', 'utf8');

      await expect(checkout.getChangedFiles({ kind: 'staged' })).resolves.toEqual([
        expect.objectContaining({ path: gitPath('tracked.txt'), additions: 1, deletions: 1 }),
      ]);
      await expect(checkout.getChangedFiles({ kind: 'unstaged' })).resolves.toEqual([
        expect.objectContaining({ path: gitPath('tracked.txt'), additions: 1, deletions: 1 }),
      ]);
    } finally {
      await cleanup();
    }
  });

  it('rejects paths outside its checkout root', async () => {
    const { checkout, cleanup } = await makeCheckout();
    try {
      await expect(
        checkout.getFile({
          path: '../secret.txt' as PortableRelativePath,
          source: { kind: 'index' },
        })
      ).rejects.toThrow('outside checkout');
      await expect(checkout.stage(['../secret.txt'])).resolves.toMatchObject({
        success: false,
        error: { type: 'git_error', message: expect.stringContaining('outside checkout') },
      });
    } finally {
      await cleanup();
    }
  });

  it('reads one-shot file content for head, index, and revision sources', async () => {
    const { repo, checkout, cleanup } = await makeCheckout();
    try {
      await writeFile(path.join(repo, 'tracked.txt'), 'staged\n', 'utf8');
      await checkout.stage(['tracked.txt']);

      await expect(
        checkout.getFile({ path: gitPath('tracked.txt'), source: { kind: 'head' } })
      ).resolves.toEqual({ success: true, data: { content: 'before\n' } });
      await expect(
        checkout.getFile({ path: gitPath('tracked.txt'), source: { kind: 'index' } })
      ).resolves.toEqual({ success: true, data: { content: 'staged\n' } });
      await expect(
        checkout.getFile({
          path: gitPath('tracked.txt'),
          source: {
            kind: 'revision',
            revision: { kind: 'branch', branch: { type: 'local', branch: 'main' } },
          },
        })
      ).resolves.toEqual({ success: true, data: { content: 'before\n' } });

      await expect(
        checkout.getFile({ path: gitPath('missing.txt'), source: { kind: 'head' } })
      ).resolves.toEqual({ success: true, data: { content: null } });
      await expect(
        checkout.getFile({ path: gitPath('missing.txt'), source: { kind: 'index' } })
      ).resolves.toEqual({ success: true, data: { content: null } });

      await writeFile(path.join(repo, 'binary.bin'), Buffer.from([0, 1, 2]));
      await checkout.stage(['binary.bin']);
      await expect(
        checkout.getFile({ path: gitPath('binary.bin'), source: { kind: 'index' } })
      ).resolves.toMatchObject({ success: false, error: { type: 'git_error' } });
    } finally {
      await cleanup();
    }
  });

  it('reads log, single commits, commit files, and blame', async () => {
    const { repo, checkout, cleanup } = await makeCheckout();
    try {
      await writeFile(path.join(repo, 'tracked.txt'), 'after\n', 'utf8');
      await checkout.stageAll();
      const commitResult = await checkout.commit('second commit');
      if (!commitResult.success) throw new Error('commit failed');

      const log = await checkout.getLog();
      expect(log.commits).toHaveLength(2);
      expect(log.totalCount).toBe(2);
      expect(log.commits[0]).toMatchObject({ subject: 'second commit', isPushed: false });

      const commit = await checkout.getCommit(commitResult.data.hash);
      expect(commit).toMatchObject({ hash: commitResult.data.hash, subject: 'second commit' });
      await expect(checkout.getCommit('0'.repeat(40))).resolves.toBeNull();

      const files = await checkout.getCommitFiles(commitResult.data.hash);
      expect(files).toEqual([
        expect.objectContaining({
          path: gitPath('tracked.txt'),
          additions: 1,
          deletions: 1,
        }),
      ]);

      const blameResult = await checkout.blame('tracked.txt');
      expect(blameResult.success).toBe(true);
      if (!blameResult.success) throw new Error('blame failed');
      expect(blameResult.data.hunks).toEqual([
        expect.objectContaining({
          oid: commitResult.data.hash,
          author: 'Test User',
          authorEmail: 'test@example.com',
          summary: 'second commit',
          startLine: 1,
          lineCount: 1,
        }),
      ]);
    } finally {
      await cleanup();
    }
  });

  it('classifies live Git file content as text, binary, or missing', async () => {
    const { repo, checkout, cleanup } = await makeCheckout();
    try {
      await expect(
        checkout.getFileContent({ path: gitPath('tracked.txt'), source: { kind: 'head' } })
      ).resolves.toMatchObject({
        kind: 'text',
        content: 'before\n',
        oid: expect.stringMatching(/^[0-9a-f]{40}$/u),
      });
      await expect(
        checkout.getFileContent({ path: gitPath('missing.txt'), source: { kind: 'head' } })
      ).resolves.toEqual({
        kind: 'missing',
        path: 'missing.txt',
        source: { kind: 'head' },
      });

      await writeFile(path.join(repo, 'binary.bin'), Buffer.from([0, 1, 2]));
      await execFileAsync('git', ['add', 'binary.bin'], { cwd: repo });
      await expect(
        checkout.getFileContent({ path: gitPath('binary.bin'), source: { kind: 'index' } })
      ).resolves.toMatchObject({ kind: 'binary', byteSize: 3 });
    } finally {
      await cleanup();
    }
  });

  it('reverts working-tree changes and cleans untracked files', async () => {
    const { repo, checkout, cleanup } = await makeCheckout();
    try {
      await writeFile(path.join(repo, 'tracked.txt'), 'dirty\n', 'utf8');
      await writeFile(path.join(repo, 'junk.txt'), 'junk\n', 'utf8');
      const revertResult = await checkout.revertAll();
      expect(revertResult.success).toBe(true);
      const model = okStatus(await checkout.getStatus());
      expect(model.entries).toEqual({});
    } finally {
      await cleanup();
    }
  });
});
