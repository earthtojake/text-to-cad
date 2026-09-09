import { execFileSync } from 'node:child_process';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ManualClock } from '@emdash/shared/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { TempStoreHandle } from '#primitives/sqlite-store/api';
import {
  workspaceRegistryStore,
  type WorkspaceRegistryDb,
} from '#runtimes/workspace-registry/node/persistence/store';
import { WorkspaceRegistryRuntime } from '#runtimes/workspace-registry/node/runtime';
import { RefFollowScheduler } from './ref-follow';

// The autonomous ref-follow pass (pr-workspace-model spec, Staleness — ref follow):
// follow-flagged, clean, sessionless PR checkouts quietly fast-forward to their
// recorded source ref; every skip (dirty, active, diverged, vanished ref) is a silent
// non-error retried on a later pass. Structural reuse is by construction: the pass is
// a thin caller of `executeUpdateWorktree`, the same guarded fetch + ff-only core the
// manual updateWorktree verb wraps — there is no second guard implementation to test.

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

describe('workspace registry ref-follow pass', () => {
  let root: string;
  let originPath: string;
  let repoPath: string;
  let handle: TempStoreHandle<WorkspaceRegistryDb>;
  let runtime: WorkspaceRegistryRuntime;
  /** The session-count seam — how the registry consults the session plane. */
  let sessionCount: number;

  beforeEach(async () => {
    root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'ws-follow-')));
    // A local "remote": the clone fetches from it over the file protocol.
    originPath = path.join(root, 'origin');
    await fs.mkdir(originPath);
    git(originPath, 'init', '--initial-branch=main');
    const baseOid = await commitFile(originPath, 'README.md', '# origin\n');
    // The PR head the follow-flagged checkouts track.
    git(originPath, 'update-ref', 'refs/pull/7/head', baseOid);

    repoPath = path.join(root, 'clone');
    git(root, 'clone', originPath, repoPath);

    handle = await workspaceRegistryStore.openTemp();
    sessionCount = 0;
    runtime = new WorkspaceRegistryRuntime({
      handle,
      clock: new ManualClock(10_000),
      countSessions: async () => sessionCount,
    });
  });

  afterEach(async () => {
    runtime.dispose();
    handle.close();
    await fs.rm(root, { recursive: true, force: true });
  });

  /** A worktree materialized from the PR-style ref, with the durable follow flag. */
  async function createWorktree(
    name: string,
    options: { followRef?: boolean; sourceRef?: string } = {}
  ): Promise<{ id: string; path: string }> {
    const registered = await runtime.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });
    if (!registered.success) {
      throw new Error(`createWorkspace failed: ${JSON.stringify(registered.error)}`);
    }
    const result = await runtime.createWorktree({
      workspaceId: `wt-${name}`,
      repositoryId: 'ws-repo',
      branch: `branch-${name}`,
      path: path.join(root, name),
      preservePatterns: [],
      gitSetup: {
        fetchBranch: { remote: 'origin', sourceRef: options.sourceRef ?? 'refs/pull/7/head' },
        ...(options.followRef === false ? {} : { followRef: true }),
      },
    });
    if (!result.success) throw new Error(`createWorktree failed: ${JSON.stringify(result.error)}`);
    return { id: result.data.id, path: result.data.path };
  }

  /** Moves the tracked PR head on the remote; returns the new OID. */
  async function advancePrHead(name: string): Promise<string> {
    const movedOid = await commitFile(originPath, name, `${name}\n`);
    git(originPath, 'update-ref', 'refs/pull/7/head', movedOid);
    return movedOid;
  }

  it('fast-forwards a clean, sessionless, follow-flagged checkout within one pass', async () => {
    const worktree = await createWorktree('clean');
    const staleOid = git(worktree.path, 'rev-parse', 'HEAD');
    const movedOid = await advancePrHead('feature.txt');
    expect(movedOid).not.toBe(staleOid);

    const pass = await runtime.runRefFollowPass();
    expect(pass).toEqual({ eligible: 1, updated: 1 });

    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(movedOid);
    // The working tree moved with the ref (a real ff checkout, not a bare ref write).
    await expect(fs.readFile(path.join(worktree.path, 'feature.txt'), 'utf8')).resolves.toBe(
      'feature.txt\n'
    );
    // Executor hygiene holds on the follow path too: no leftover private temp refs.
    expect(git(repoPath, 'for-each-ref', 'refs/emdash')).toBe('');

    // An already-current checkout is a silent no-op on the next pass.
    const again = await runtime.runRefFollowPass();
    expect(again).toEqual({ eligible: 1, updated: 0 });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(movedOid);
  });

  it('skips a dirty worktree silently; a later pass picks it up once clean', async () => {
    const worktree = await createWorktree('dirty');
    const staleOid = git(worktree.path, 'rev-parse', 'HEAD');
    const movedOid = await advancePrHead('feature.txt');
    const scratchPath = path.join(worktree.path, 'scratch.txt');
    await fs.writeFile(scratchPath, 'uncommitted');

    const skipped = await runtime.runRefFollowPass();
    expect(skipped).toEqual({ eligible: 1, updated: 0 });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(staleOid);
    await expect(fs.readFile(scratchPath, 'utf8')).resolves.toBe('uncommitted');

    await fs.rm(scratchPath);
    const retried = await runtime.runRefFollowPass();
    expect(retried).toEqual({ eligible: 1, updated: 1 });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(movedOid);
  });

  it('skips a worktree with live sessions; a later pass picks it up once idle', async () => {
    const worktree = await createWorktree('busy');
    const staleOid = git(worktree.path, 'rev-parse', 'HEAD');
    const movedOid = await advancePrHead('feature.txt');
    sessionCount = 1;

    const skipped = await runtime.runRefFollowPass();
    expect(skipped).toEqual({ eligible: 1, updated: 0 });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(staleOid);

    sessionCount = 0;
    const retried = await runtime.runRefFollowPass();
    expect(retried).toEqual({ eligible: 1, updated: 1 });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(movedOid);
  });

  it('never moves a diverged checkout and surfaces no error', async () => {
    const worktree = await createWorktree('diverged');
    const localOid = await commitFile(worktree.path, 'local.txt', 'local commit\n');
    await advancePrHead('remote.txt');

    const pass = await runtime.runRefFollowPass();
    expect(pass).toEqual({ eligible: 1, updated: 0 });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(localOid);

    // Still diverged on the next pass: silently declined again, never an escalation.
    const again = await runtime.runRefFollowPass();
    expect(again).toEqual({ eligible: 1, updated: 0 });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(localOid);
  });

  it('tolerates a vanished source ref (closed-PR case) as a silent skip', async () => {
    const worktree = await createWorktree('closed-pr');
    const staleOid = git(worktree.path, 'rev-parse', 'HEAD');
    // The forge deleted the PR ref (GitLab does this ~14 days after close/merge).
    git(originPath, 'update-ref', '-d', 'refs/pull/7/head');

    const pass = await runtime.runRefFollowPass();
    expect(pass).toEqual({ eligible: 1, updated: 0 });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(staleOid);

    // The checkout keeps working: local commits land normally after the failed fetch.
    const localOid = await commitFile(worktree.path, 'still-works.txt', 'fine\n');
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(localOid);
  });

  it('never touches non-flagged workspaces; an empty registry pass is a no-op', async () => {
    // Nothing registered at all: no candidates, no git work (the loop body never runs).
    expect(await runtime.runRefFollowPass()).toEqual({ eligible: 0, updated: 0 });

    // A worktree with a fetch instruction but no follow flag is not a candidate.
    const worktree = await createWorktree('unflagged', { followRef: false });
    const staleOid = git(worktree.path, 'rev-parse', 'HEAD');
    await advancePrHead('feature.txt');

    const pass = await runtime.runRefFollowPass();
    expect(pass).toEqual({ eligible: 0, updated: 0 });
    expect(git(worktree.path, 'rev-parse', 'HEAD')).toBe(staleOid);
  });
});

describe('RefFollowScheduler', () => {
  async function eventually(assertion: () => void, timeoutMs = 3_000): Promise<void> {
    const started = Date.now();
    for (;;) {
      try {
        assertion();
        return;
      } catch (error) {
        if (Date.now() - started > timeoutMs) throw error;
        await new Promise((resolve) => setTimeout(resolve, 5));
      }
    }
  }

  it('runs passes on the jittered cadence, one at a time, rescheduling after each', async () => {
    let passes = 0;
    let concurrent = 0;
    let maxConcurrent = 0;
    const scheduler = new RefFollowScheduler({
      runPass: async () => {
        concurrent += 1;
        maxConcurrent = Math.max(maxConcurrent, concurrent);
        await new Promise((resolve) => setTimeout(resolve, 5));
        concurrent -= 1;
        passes += 1;
      },
      intervalMs: 10,
      jitterMs: 10,
      random: () => 0.5,
    });
    scheduler.start();
    try {
      await eventually(() => expect(passes).toBeGreaterThanOrEqual(3));
      expect(maxConcurrent).toBe(1);
    } finally {
      await scheduler.dispose();
    }
  });

  it('a rejected pass never kills the loop', async () => {
    let calls = 0;
    const scheduler = new RefFollowScheduler({
      runPass: async () => {
        calls += 1;
        throw new Error('transient');
      },
      intervalMs: 5,
      jitterMs: 0,
    });
    scheduler.start();
    try {
      await eventually(() => expect(calls).toBeGreaterThanOrEqual(2));
    } finally {
      await scheduler.dispose();
    }
  });

  it('dispose stops the loop cleanly and awaits an in-flight pass', async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let started = 0;
    let finished = 0;
    const scheduler = new RefFollowScheduler({
      runPass: async () => {
        started += 1;
        await gate;
        finished += 1;
      },
      intervalMs: 5,
      jitterMs: 0,
    });
    scheduler.start();
    await eventually(() => expect(started).toBe(1));

    const disposal = scheduler.dispose();
    release();
    await disposal;
    expect(finished).toBe(1);

    // No timer survives disposal: nothing further fires.
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(started).toBe(1);
  });

  it('a never-started scheduler disposes without work', async () => {
    let passes = 0;
    const scheduler = new RefFollowScheduler({
      runPass: async () => {
        passes += 1;
      },
      intervalMs: 1,
      jitterMs: 0,
    });
    await scheduler.dispose();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(passes).toBe(0);
  });
});
