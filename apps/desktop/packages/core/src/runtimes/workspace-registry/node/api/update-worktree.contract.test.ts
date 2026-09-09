import { execFileSync } from 'node:child_process';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ManualClock } from '@emdash/shared/testing';
import { createTestWire, type TestWire } from '@emdash/wire/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { TempStoreHandle } from '#primitives/sqlite-store/api';
import { workspaceRegistryContract } from '#runtimes/workspace-registry/api';
import {
  workspaceRegistryStore,
  type WorkspaceRegistryDb,
} from '#runtimes/workspace-registry/node/persistence/store';
import { WorkspaceRegistryRuntime } from '#runtimes/workspace-registry/node/runtime';
import { executeUpdateWorktree } from '#runtimes/workspace-registry/node/update-worktree';
import { createWorkspaceRegistryController } from './controller';

// Contract-seam tests for updateWorktree (pr-workspace-model spec, Staleness — manual
// update): instruction-as-input fetch + ff-only under the per-worktree writer lock,
// with host-side guards that each refuse distinctly and move nothing.

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

async function commitFile(repoPath: string, name: string, contents: string): Promise<string> {
  await fs.writeFile(path.join(repoPath, name), contents);
  git(repoPath, 'add', name);
  git(repoPath, 'commit', '-m', `add ${name}`);
  return git(repoPath, 'rev-parse', 'HEAD');
}

describe('workspace registry updateWorktree', () => {
  let root: string;
  let originPath: string;
  let repoPath: string;
  let handle: TempStoreHandle<WorkspaceRegistryDb>;
  let runtime: WorkspaceRegistryRuntime;
  let wire: TestWire<typeof workspaceRegistryContract>;
  /** The session-count seam — how the registry consults the session plane. */
  let sessionCount: number;

  beforeEach(async () => {
    root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'ws-update-')));
    // A local "remote": the clone fetches from it over the file protocol.
    originPath = path.join(root, 'origin');
    await fs.mkdir(originPath);
    git(originPath, 'init', '--initial-branch=main');
    await commitFile(originPath, 'README.md', '# origin\n');

    repoPath = path.join(root, 'clone');
    git(root, 'clone', originPath, repoPath);

    handle = await workspaceRegistryStore.openTemp();
    sessionCount = 0;
    runtime = new WorkspaceRegistryRuntime({
      handle,
      clock: new ManualClock(10_000),
      countSessions: async () => sessionCount,
    });
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));
  });

  afterEach(async () => {
    wire.dispose();
    runtime.dispose();
    handle.close();
    await fs.rm(root, { recursive: true, force: true });
  });

  /** A plain worktree with NO gitSetup on the record — the pre-model shape. */
  async function createWorktree(name: string): Promise<{ id: string; path: string }> {
    const registered = await wire.client.createWorkspace({
      workspaceId: 'ws-repo',
      path: repoPath,
    });
    if (!registered.success) {
      throw new Error(`createWorkspace failed: ${JSON.stringify(registered.error)}`);
    }
    const result = await wire.client.createWorktree({
      workspaceId: `wt-${name}`,
      repositoryId: 'ws-repo',
      branch: `branch-${name}`,
      baseRef: 'main',
      path: path.join(root, name),
      preservePatterns: [],
    });
    if (!result.success) throw new Error(`createWorktree failed: ${JSON.stringify(result.error)}`);
    expect(result.data.creation?.gitSetup).toBeUndefined();
    return { id: result.data.id, path: result.data.path };
  }

  it('fast-forwards a clean, stale, sessionless checkout to the fetched OID — hygienically', async () => {
    const worktree = await createWorktree('stale');
    const staleOid = git(worktree.path, 'rev-parse', 'HEAD');
    // The "PR head" moves on the remote; expose it through a PR-style ref.
    const movedOid = await commitFile(originPath, 'feature.txt', 'new work\n');
    git(originPath, 'update-ref', 'refs/pull/7/head', movedOid);
    expect(movedOid).not.toBe(staleOid);

    const updated = await wire.client.updateWorktree({
      workspaceId: worktree.id,
      remote: 'origin',
      sourceRef: 'refs/pull/7/head',
    });
    expect(updated).toEqual({ success: true, data: undefined });

    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(movedOid);
    // The working tree moved with the ref (a real ff checkout, not just a ref write).
    await expect(fs.readFile(path.join(worktree.path, 'feature.txt'), 'utf8')).resolves.toBe(
      'new work\n'
    );
    // Hygiene: no FETCH_HEAD write, no private temp refs left behind.
    expect(git(repoPath, 'for-each-ref', 'refs/emdash')).toBe('');
    const gitDir = git(worktree.path, 'rev-parse', '--absolute-git-dir');
    await expect(fs.stat(path.join(gitDir, 'FETCH_HEAD'))).rejects.toThrow();

    // Replay when already at the fetched OID: a no-op success.
    const again = await wire.client.updateWorktree({
      workspaceId: worktree.id,
      remote: 'origin',
      sourceRef: 'refs/pull/7/head',
    });
    expect(again).toEqual({ success: true, data: undefined });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(movedOid);
  });

  it('refuses a dirty worktree distinctly and moves nothing (untracked counts as dirty)', async () => {
    const worktree = await createWorktree('dirty');
    const beforeOid = git(worktree.path, 'rev-parse', 'HEAD');
    await commitFile(originPath, 'feature.txt', 'new work\n');
    await fs.writeFile(path.join(worktree.path, 'scratch.txt'), 'uncommitted');

    const updated = await wire.client.updateWorktree({
      workspaceId: worktree.id,
      remote: 'origin',
      sourceRef: 'refs/heads/main',
    });
    expect(updated).toEqual({
      success: false,
      error: { type: 'worktree-dirty', workspaceId: worktree.id },
    });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(beforeOid);
    await expect(fs.readFile(path.join(worktree.path, 'scratch.txt'), 'utf8')).resolves.toBe(
      'uncommitted'
    );
  });

  it('refuses when the workspace has live sessions and moves nothing', async () => {
    const worktree = await createWorktree('busy');
    const beforeOid = git(worktree.path, 'rev-parse', 'HEAD');
    await commitFile(originPath, 'feature.txt', 'new work\n');
    sessionCount = 1;

    const updated = await wire.client.updateWorktree({
      workspaceId: worktree.id,
      remote: 'origin',
      sourceRef: 'refs/heads/main',
    });
    expect(updated).toEqual({
      success: false,
      error: { type: 'workspace-active', workspaceId: worktree.id },
    });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(beforeOid);

    // The same call succeeds once the sessions are gone — the guard is the only stop.
    sessionCount = 0;
    const retried = await wire.client.updateWorktree({
      workspaceId: worktree.id,
      remote: 'origin',
      sourceRef: 'refs/heads/main',
    });
    expect(retried).toEqual({ success: true, data: undefined });
  });

  it('a diverged branch fails ff-only cleanly ("local commits — resolve manually"); nothing moves', async () => {
    const worktree = await createWorktree('diverged');
    const localOid = await commitFile(worktree.path, 'local.txt', 'local commit\n');
    await commitFile(originPath, 'remote.txt', 'remote commit\n');

    const updated = await wire.client.updateWorktree({
      workspaceId: worktree.id,
      remote: 'origin',
      sourceRef: 'refs/heads/main',
    });
    if (updated.success) throw new Error('expected the diverged update to fail');
    expect(updated.error).toEqual({
      type: 'diverged',
      workspaceId: worktree.id,
      message: expect.stringContaining('resolve manually'),
    });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(localOid);
  });

  it('an ahead-only checkout (fetched head already contained) is a no-op success', async () => {
    const worktree = await createWorktree('ahead');
    const localOid = await commitFile(worktree.path, 'local.txt', 'local commit\n');

    const updated = await wire.client.updateWorktree({
      workspaceId: worktree.id,
      remote: 'origin',
      sourceRef: 'refs/heads/main',
    });
    expect(updated).toEqual({ success: true, data: undefined });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(localOid);
  });

  it('an unfetchable source ref fails at the fetch stage and moves nothing', async () => {
    const worktree = await createWorktree('missing-ref');
    const beforeOid = git(worktree.path, 'rev-parse', 'HEAD');

    const updated = await wire.client.updateWorktree({
      workspaceId: worktree.id,
      remote: 'origin',
      sourceRef: 'refs/pull/404/head',
    });
    if (updated.success) throw new Error('expected the fetch to fail');
    expect(updated.error).toMatchObject({ type: 'stage-failed', stage: 'fetch' });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(beforeOid);
  });

  it('absent, non-worktree, and missing records get their distinct typed errors', async () => {
    expect(
      await wire.client.updateWorktree({
        workspaceId: 'wt-never',
        remote: 'origin',
        sourceRef: 'main',
      })
    ).toEqual({
      success: false,
      error: { type: 'workspace-not-found', workspaceId: 'wt-never' },
    });

    await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });
    expect(
      await wire.client.updateWorktree({
        workspaceId: 'ws-repo',
        remote: 'origin',
        sourceRef: 'main',
      })
    ).toEqual({
      success: false,
      error: { type: 'not-a-worktree', workspaceId: 'ws-repo' },
    });

    const worktree = await createWorktree('vanished');
    git(repoPath, 'worktree', 'remove', '--force', worktree.path);
    await wire.client.refresh({ workspaceId: worktree.id });
    expect(
      await wire.client.updateWorktree({
        workspaceId: worktree.id,
        remote: 'origin',
        sourceRef: 'main',
      })
    ).toEqual({
      success: false,
      error: { type: 'workspace-missing', workspaceId: worktree.id },
    });
  });

  it('holds the per-worktree writer lock for the whole guarded update — scans wait, never a torn checkout', async () => {
    const worktree = await createWorktree('locked');
    // createWorktree returns before its background steps finish. This test exercises
    // only writer-lock behavior, so keep unrelated repository git work out of the ref
    // update window.
    await runtime.gitContext.schedule.whenIdle(repoPath, 5_000);
    await commitFile(originPath, 'feature.txt', 'new work\n');

    // Park the executor inside its guard section; the writer lock must already be held
    // (probes and scans wait on `whenUnlocked`, the existing observe-git seam).
    let releaseGuard!: (active: boolean) => void;
    const guardGate = new Promise<boolean>((resolve) => {
      releaseGuard = resolve;
    });
    const run = executeUpdateWorktree({
      git: runtime.gitContext,
      repositoryPath: repoPath,
      worktreePath: worktree.path,
      remote: 'origin',
      sourceRef: 'refs/heads/main',
      isActive: () => guardGate,
    });

    let unlocked = false;
    void runtime.gitContext.locks.whenUnlocked(worktree.path).then(() => {
      unlocked = true;
    });
    await new Promise((resolve) => setTimeout(resolve, 25));
    expect(unlocked).toBe(false);

    releaseGuard(false);
    const result = await run;
    expect(result.status).toBe('updated');
    await runtime.gitContext.locks.whenUnlocked(worktree.path);
    expect(unlocked).toBe(true);
  });
});
