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
import { createWorkspaceRegistryController } from './api/controller';
import { createRegistryGitContext } from './git-context';

// Composition of the injected git budget with the runtime (spec:
// registry-runtime-carveout, git context): the runtime owns its RegistryGitContext,
// tests inject one, and the schedule's core promise — creation-tier work overflows
// into headroom — holds end-to-end through the wire. Impossible to assert under the
// former process-global singletons.

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

async function eventually(assertion: () => Promise<void>, timeoutMs = 10_000): Promise<void> {
  const started = Date.now();
  for (;;) {
    try {
      await assertion();
      return;
    } catch (error) {
      if (Date.now() - started > timeoutMs) throw error;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
  }
}

describe('workspace registry git context composition', () => {
  let root: string;
  let handle: TempStoreHandle<WorkspaceRegistryDb>;
  let runtime: WorkspaceRegistryRuntime;
  let wire: TestWire<typeof workspaceRegistryContract>;

  beforeEach(async () => {
    root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'ws-gitctx-')));
    handle = await workspaceRegistryStore.openTemp();
  });

  afterEach(async () => {
    wire.dispose();
    runtime.dispose();
    handle.close();
    await fs.rm(root, { recursive: true, force: true });
  });

  it('creation starts immediately under a saturated probe budget', async () => {
    const gitContext = createRegistryGitContext({ capacity: 2, headroom: 2 });
    runtime = new WorkspaceRegistryRuntime({
      handle,
      clock: new ManualClock(10_000),
      gitContext,
    });
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));

    const repoPath = path.join(root, 'repo');
    await fs.mkdir(repoPath);
    git(repoPath, 'init', '--initial-branch=main');
    await fs.writeFile(path.join(repoPath, 'README.md'), '# repo\n');
    git(repoPath, 'add', '.');
    git(repoPath, 'commit', '-m', 'initial');
    const registered = await wire.client.createWorkspace({
      workspaceId: 'ws-repo',
      path: repoPath,
    });
    expect(registered.success).toBe(true);

    // Saturate the probe tier: every plain budget slot is held by blocked work, and a
    // late probe queues behind them for the duration of the test.
    const releases: Array<() => void> = [];
    const blocked = [0, 1].map(() =>
      gitContext.schedule.run(
        { tier: 'probe' },
        () => new Promise<void>((resolve) => releases.push(resolve))
      )
    );
    let lateProbeRan = false;
    const lateProbe = gitContext.schedule.run({ tier: 'probe' }, () => {
      lateProbeRan = true;
    });

    const worktreePath = path.join(root, 'headroom-wt');
    const pending = wire.client.createWorktree({
      workspaceId: 'wt-headroom',
      repositoryId: 'ws-repo',
      branch: 'feature/headroom',
      baseRef: 'main',
      path: worktreePath,
      preservePatterns: [],
    });

    // The creation-tier pipeline overflows into headroom: the worktree materializes on
    // disk while every plain slot is still held (the late probe has not run).
    await eventually(async () => {
      await fs.access(worktreePath);
    });
    expect(lateProbeRan).toBe(false);

    // Release the probes so the finalize observation (probe tier) can land.
    for (const release of releases) release();
    await Promise.all(blocked);
    await lateProbe;

    const created = await pending;
    expect(created.success).toBe(true);
    if (created.success) expect(created.data.observedStatus).toBe('present');
  });
});
