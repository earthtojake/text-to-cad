import { execFileSync } from 'node:child_process';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createScope } from '@emdash/shared/concurrency';
import { ManualClock } from '@emdash/shared/testing';
import { pin, remote, snapshot } from '@emdash/wire/state';
import { createTestWire, type TestWire } from '@emdash/wire/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { TempStoreHandle } from '#primitives/sqlite-store/api';
import { workspaceRegistryContract } from '#runtimes/workspace-registry/api';
import { WorkspaceRecordStore } from '#runtimes/workspace-registry/node/persistence/record-store';
import {
  workspaceRegistryStore,
  type WorkspaceRegistryDb,
} from '#runtimes/workspace-registry/node/persistence/store';
import { WorkspaceRegistryRuntime } from '#runtimes/workspace-registry/node/runtime';
import { WorkspaceScanScheduler } from '#runtimes/workspace-registry/node/scan/scheduler';
import { nativeWatchBackend } from '#services/fs-watch/impl/native-backend';
import { createWatchService } from '#services/fs-watch/impl/watch-service';
import { createWorkspaceRegistryController } from './controller';

async function eventually(assertion: () => Promise<void>, timeoutMs = 10_000): Promise<void> {
  const started = Date.now();
  for (;;) {
    try {
      await assertion();
      return;
    } catch (error) {
      if (Date.now() - started > timeoutMs) throw error;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
}

// Contract-seam tests for the host workspace registry (ADR 0005), against real SQLite
// and real git repositories in a temp dir. Property statements under test:
//
// - Sole writer: every mutation goes through the wire contract — the only client-facing
//   write path; the `records` live model is the sole read path.
// - Kind is host-detected, never client-supplied.
// - Identity: ids are minted by the caller on create verbs and never reused; path is a
//   mutable unique attribute, not the identity.
// - Deletes are idempotent facts, not desired state.

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

async function makeRepo(root: string, name: string): Promise<string> {
  const repoPath = path.join(root, name);
  await fs.mkdir(repoPath, { recursive: true });
  git(repoPath, 'init', '--initial-branch=main');
  await fs.writeFile(path.join(repoPath, 'README.md'), `# ${name}\n`);
  git(repoPath, 'add', '.');
  git(repoPath, 'commit', '-m', 'initial');
  return repoPath;
}

async function makeWorktree(repoPath: string, root: string, name: string): Promise<string> {
  const worktreePath = path.join(root, name);
  git(repoPath, 'worktree', 'add', worktreePath, '-b', `branch-${name}`);
  return await fs.realpath(worktreePath);
}

/** One lifecycle step from a wire record's runtime projection, by id. */
function lifecycleStep(
  record: { runtime: { lifecycle?: Array<{ id: string }> | null } | null } | undefined,
  id: string
) {
  return record?.runtime?.lifecycle?.find((step) => step.id === id);
}

describe('workspace registry contract', () => {
  let root: string;
  let handle: TempStoreHandle<WorkspaceRegistryDb>;
  let clock: ManualClock;
  let runtime: WorkspaceRegistryRuntime;
  let wire: TestWire<typeof workspaceRegistryContract>;

  beforeEach(async () => {
    root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'ws-registry-')));
    handle = await workspaceRegistryStore.openTemp();
    clock = new ManualClock(10_000);
    runtime = new WorkspaceRegistryRuntime({ handle, clock });
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));
  });

  afterEach(async () => {
    wire.dispose();
    runtime.dispose();
    handle.close();
    await fs.rm(root, { recursive: true, force: true });
  });

  async function listRecords() {
    const records = remote(workspaceRegistryContract.records, wire.client.records);
    const model = records(undefined);
    try {
      await model.states.list.refresh();
      return snapshot(model.states.list).value ?? {};
    } finally {
      await records.dispose();
    }
  }

  it('createWorkspace detects a repository and the records model lists it', async () => {
    const repoPath = await makeRepo(root, 'repo');

    const created = await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });
    expect(created).toEqual({
      success: true,
      data: {
        id: 'ws-repo',
        kind: 'repository',
        path: repoPath,
        parentId: null,
        origin: 'registered',
        gitAdminName: null,
        observedStatus: 'present',
        creation: null,
        lastCreateOutcome: null,
        lifecycle: null,
        lastRemovalAttempt: null,
        git: null,
        lastActivatedAt: null,
        createdAt: 10_000,
        updatedAt: 10_000,
        lastObservedAt: 10_000,
        config: {
          scripts: { prepare: false, setup: false, run: false, teardown: false },
          preservePatterns: [],
          parseError: false,
        },
        runtime: null,
      },
    });

    const records = await listRecords();
    expect(Object.keys(records)).toEqual(['ws-repo']);
  });

  it('createWorkspace detects a plain directory (including subdirectories of a repo)', async () => {
    const plain = path.join(root, 'plain');
    await fs.mkdir(plain);
    const created = await wire.client.createWorkspace({ workspaceId: 'ws-dir', path: plain });
    expect(created).toMatchObject({ success: true, data: { kind: 'directory' } });

    const repoPath = await makeRepo(root, 'repo-with-sub');
    const sub = path.join(repoPath, 'packages');
    await fs.mkdir(sub);
    const subCreated = await wire.client.createWorkspace({ workspaceId: 'ws-sub', path: sub });
    expect(subCreated).toMatchObject({ success: true, data: { kind: 'directory' } });
  });

  it('persists personal config and legacy imports for directory project roots', async () => {
    const directoryPath = path.join(root, 'plain-directory-config');
    await fs.mkdir(directoryPath);
    await wire.client.createWorkspace({ workspaceId: 'ws-directory-config', path: directoryPath });

    const patched = await wire.client.patchPersonalProjectConfig({
      workspaceId: 'ws-directory-config',
      patch: { scripts: { setup: 'personal setup' } },
    });
    expect(patched).toMatchObject({
      success: true,
      data: {
        repositoryId: 'ws-directory-config',
        personalConfig: { scripts: { setup: 'personal setup' } },
      },
    });

    const imported = await wire.client.importLegacyLifecycleSettings({
      workspaceId: 'ws-directory-config',
      settings: { scripts: { setup: 'legacy setup', run: 'legacy run' } },
    });
    expect(imported).toMatchObject({
      success: true,
      data: {
        personalConfig: { scripts: { setup: 'personal setup', run: 'legacy run' } },
        legacyDesktopSettingsMigrated: true,
      },
    });
  });

  it('createWorkspace on a worktree auto-registers the parent repository as adopted', async () => {
    const repoPath = await makeRepo(root, 'repo');
    const worktreePath = await makeWorktree(repoPath, root, 'wt-1');

    const created = await wire.client.createWorkspace({ workspaceId: 'ws-wt', path: worktreePath });
    expect(created).toMatchObject({
      success: true,
      data: {
        kind: 'worktree',
        path: worktreePath,
        origin: 'registered',
        gitAdminName: 'wt-1',
      },
    });
    if (!created.success) throw new Error('expected success');
    const parentId = created.data.parentId;
    expect(parentId).not.toBeNull();

    const records = await listRecords();
    expect(records[parentId!]).toMatchObject({
      kind: 'repository',
      path: repoPath,
      origin: 'adopted',
      parentId: null,
    });
  });

  it('createWorkspace replays idempotently and rejects a divergent path', async () => {
    const repoPath = await makeRepo(root, 'repo');
    const first = await wire.client.createWorkspace({ workspaceId: 'ws-1', path: repoPath });
    const replay = await wire.client.createWorkspace({ workspaceId: 'ws-1', path: repoPath });
    if (!first.success || !replay.success) throw new Error('createWorkspace failed');
    // The config summary is a live-model projection and may fill in between the two
    // calls; replay idempotency is a property of the durable record.
    const { config: _firstConfig, ...firstRest } = first.data;
    const { config: _replayConfig, ...replayRest } = replay.data;
    expect(replayRest).toEqual(firstRest);

    const other = path.join(root, 'other');
    await fs.mkdir(other);
    const divergent = await wire.client.createWorkspace({ workspaceId: 'ws-1', path: other });
    expect(divergent).toMatchObject({
      success: false,
      error: { type: 'immutable-field-mismatch', workspaceId: 'ws-1' },
    });
  });

  it('resolves each worktree team config and preserves personal config on record writes', async () => {
    const repoPath = await makeRepo(root, 'config-repo');
    await fs.writeFile(
      path.join(repoPath, '.emdash.json'),
      JSON.stringify({
        preservePatterns: ['repo/**'],
        scripts: { setup: 'repo setup', run: 'repo run' },
      })
    );
    expect(
      (await wire.client.createWorkspace({ workspaceId: 'ws-config-repo', path: repoPath })).success
    ).toBe(true);

    const worktreePath = await makeWorktree(repoPath, root, 'config-wt');
    await fs.writeFile(
      path.join(worktreePath, '.emdash.json'),
      JSON.stringify({
        preservePatterns: ['worktree/**'],
        scripts: { setup: 'worktree setup', run: 'worktree run' },
      })
    );
    expect(
      (
        await wire.client.createWorkspace({
          workspaceId: 'ws-config-wt',
          path: worktreePath,
        })
      ).success
    ).toBe(true);

    const patched = await wire.client.patchPersonalProjectConfig({
      workspaceId: 'ws-config-wt',
      patch: { scripts: { setup: 'personal setup' } },
    });
    expect(patched).toMatchObject({
      success: true,
      data: {
        repositoryId: 'ws-config-repo',
        resolved: {
          preservePatterns: { value: ['worktree/**'], from: 'team' },
          setup: { value: 'personal setup', from: 'personal' },
          run: { value: 'worktree run', from: 'team' },
        },
      },
    });

    // Observation writes intentionally exclude personalConfig, so scans cannot erase
    // personal settings while updating the durable workspace record.
    const store = new WorkspaceRecordStore(handle);
    const repository = store.get('ws-config-repo');
    if (!repository) throw new Error('repository record missing');
    store.update({ ...repository, updatedAt: 11_000 });

    wire.dispose();
    runtime.dispose();
    runtime = new WorkspaceRegistryRuntime({ handle, clock });
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));

    const repositoryConfig = await wire.client.getProjectConfig({
      workspaceId: 'ws-config-repo',
    });
    const worktreeConfig = await wire.client.getProjectConfig({ workspaceId: 'ws-config-wt' });
    expect(repositoryConfig).toMatchObject({
      success: true,
      data: {
        resolved: {
          setup: { value: 'personal setup', from: 'personal' },
          run: { value: 'repo run', from: 'team' },
        },
      },
    });
    expect(worktreeConfig).toMatchObject({
      success: true,
      data: {
        resolved: {
          setup: { value: 'personal setup', from: 'personal' },
          run: { value: 'worktree run', from: 'team' },
        },
        personalConfig: { scripts: { setup: 'personal setup' } },
        sources: {
          preservePatterns: expect.arrayContaining([
            expect.objectContaining({
              workspaceId: 'ws-config-repo',
              value: ['repo/**'],
            }),
            expect.objectContaining({
              workspaceId: 'ws-config-wt',
              value: ['worktree/**'],
            }),
          ]),
          run: expect.arrayContaining([
            expect.objectContaining({ workspaceId: 'ws-config-repo', value: 'repo run' }),
            expect.objectContaining({ workspaceId: 'ws-config-wt', value: 'worktree run' }),
          ]),
        },
      },
    });
  });

  it('publishes the initial project config snapshot for a workspace key', async () => {
    const workspacePath = path.join(root, 'live-config');
    await fs.mkdir(workspacePath);
    await fs.writeFile(
      path.join(workspacePath, '.emdash.json'),
      JSON.stringify({ scripts: { setup: 'team setup' } })
    );
    await wire.client.createWorkspace({ workspaceId: 'ws-live-config', path: workspacePath });

    const configs = remote(workspaceRegistryContract.projectConfig, wire.client.projectConfig);
    const current = configs({ workspaceId: 'ws-live-config' }).states.current;
    try {
      await current.refresh();
      expect(snapshot(current).value).toMatchObject({
        workspaceId: 'ws-live-config',
        repositoryId: 'ws-live-config',
        resolved: {
          setup: { value: 'team setup', from: 'team' },
          autoRunSetup: { value: true, from: 'built-in' },
        },
      });
    } finally {
      await configs.dispose();
    }
  });

  it('updates the project config model after personal config patches and imports', async () => {
    const workspacePath = path.join(root, 'live-personal');
    await fs.mkdir(workspacePath);
    await wire.client.createWorkspace({ workspaceId: 'ws-live-personal', path: workspacePath });

    const scope = createScope({ label: 'project-config-personal-test' });
    const configs = remote(workspaceRegistryContract.projectConfig, wire.client.projectConfig, {
      scope,
    });
    const current = configs({ workspaceId: 'ws-live-personal' }).states.current;
    pin(scope, [current]);
    await current.refresh();

    await wire.client.patchPersonalProjectConfig({
      workspaceId: 'ws-live-personal',
      patch: { scripts: { setup: 'personal setup' } },
    });

    try {
      await eventually(async () => {
        expect(snapshot(current).value?.resolved.setup).toEqual({
          value: 'personal setup',
          from: 'personal',
        });
      });
      await wire.client.importLegacyLifecycleSettings({
        workspaceId: 'ws-live-personal',
        settings: { scripts: { teardown: 'imported teardown' } },
      });
      await eventually(async () => {
        expect(snapshot(current).value?.resolved.teardown).toEqual({
          value: 'imported teardown',
          from: 'personal',
        });
      });
    } finally {
      await scope.dispose();
    }
  });

  it('updates the project config model after the team file changes', async () => {
    const workspacePath = path.join(root, 'live-team');
    await fs.mkdir(workspacePath);
    await fs.writeFile(
      path.join(workspacePath, '.emdash.json'),
      JSON.stringify({ scripts: { setup: 'first setup' } })
    );
    await wire.client.createWorkspace({ workspaceId: 'ws-live-team', path: workspacePath });

    const scope = createScope({ label: 'project-config-team-test' });
    const configs = remote(workspaceRegistryContract.projectConfig, wire.client.projectConfig, {
      scope,
    });
    const current = configs({ workspaceId: 'ws-live-team' }).states.current;
    pin(scope, [current]);
    await current.refresh();

    await fs.writeFile(
      path.join(workspacePath, '.emdash.json'),
      JSON.stringify({ scripts: { setup: 'second setup' } })
    );
    await wire.client.refresh({ workspaceId: 'ws-live-team' });

    try {
      await eventually(async () => {
        expect(snapshot(current).value?.resolved.setup).toEqual({
          value: 'second setup',
          from: 'team',
        });
      });
    } finally {
      await scope.dispose();
    }
  });

  it('updates the project config model after host settings change', async () => {
    wire.dispose();
    runtime.dispose();
    let shellSetup = 'first host setup';
    runtime = new WorkspaceRegistryRuntime({
      handle,
      clock,
      getHostSettings: async () => ({ shellSetup }),
    });
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));

    const workspacePath = path.join(root, 'live-host');
    await fs.mkdir(workspacePath);
    await wire.client.createWorkspace({ workspaceId: 'ws-live-host', path: workspacePath });

    const scope = createScope({ label: 'project-config-host-test' });
    const configs = remote(workspaceRegistryContract.projectConfig, wire.client.projectConfig, {
      scope,
    });
    const current = configs({ workspaceId: 'ws-live-host' }).states.current;
    pin(scope, [current]);
    await current.refresh();
    expect(snapshot(current).value?.resolved.shellSetup).toEqual({
      value: 'first host setup',
      from: 'host-default',
    });

    shellSetup = 'second host setup';
    runtime.hostSettingsChanged();

    try {
      await eventually(async () => {
        expect(snapshot(current).value?.resolved.shellSetup).toEqual({
          value: 'second host setup',
          from: 'host-default',
        });
      });
    } finally {
      await scope.dispose();
    }
  });

  it('updates project config sources when project membership changes', async () => {
    const repoPath = await makeRepo(root, 'live-membership');
    await fs.writeFile(
      path.join(repoPath, '.emdash.json'),
      JSON.stringify({ scripts: { setup: 'shared setup' } })
    );
    git(repoPath, 'add', '.emdash.json');
    git(repoPath, 'commit', '-m', 'add config');
    await wire.client.createWorkspace({ workspaceId: 'ws-live-membership', path: repoPath });

    const scope = createScope({ label: 'project-config-membership-test' });
    const configs = remote(workspaceRegistryContract.projectConfig, wire.client.projectConfig, {
      scope,
    });
    const current = configs({ workspaceId: 'ws-live-membership' }).states.current;
    pin(scope, [current]);
    await current.refresh();
    expect(snapshot(current).value?.sources.setup).toHaveLength(1);

    const created = await wire.client.createWorktree({
      workspaceId: 'wt-live-membership',
      repositoryId: 'ws-live-membership',
      path: path.join(root, 'live-membership-worktree'),
      branch: 'live-membership-worktree',
      baseRef: 'main',
      preservePatterns: [],
    });
    expect(created.success).toBe(true);

    try {
      await eventually(async () => {
        expect(snapshot(current).value?.sources.setup).toEqual(
          expect.arrayContaining([
            expect.objectContaining({ workspaceId: 'ws-live-membership' }),
            expect.objectContaining({ workspaceId: 'wt-live-membership' }),
          ])
        );
      });
      await wire.client.deleteWorkspace({ workspaceId: 'wt-live-membership' });
      await eventually(async () => {
        expect(snapshot(current).value?.sources.setup).toEqual([
          expect.objectContaining({ workspaceId: 'ws-live-membership' }),
        ]);
      });
    } finally {
      await scope.dispose();
    }
  });

  it('imports legacy lifecycle settings only once and persists the marker separately', async () => {
    const repoPath = await makeRepo(root, 'legacy-config-repo');
    await wire.client.createWorkspace({ workspaceId: 'ws-legacy-config', path: repoPath });
    await wire.client.patchPersonalProjectConfig({
      workspaceId: 'ws-legacy-config',
      patch: { scripts: { setup: 'personal setup' }, autoRunRun: true },
    });

    const imported = await wire.client.importLegacyLifecycleSettings({
      workspaceId: 'ws-legacy-config',
      settings: {
        scripts: { setup: 'legacy setup', teardown: 'legacy teardown' },
        autoRunSetup: false,
        autoRunRun: false,
      },
    });
    expect(imported).toMatchObject({
      success: true,
      data: {
        personalConfig: {
          scripts: { setup: 'personal setup', teardown: 'legacy teardown' },
          autoRunSetup: false,
          autoRunRun: true,
        },
        legacyDesktopSettingsMigrated: true,
      },
    });

    await wire.client.importLegacyLifecycleSettings({
      workspaceId: 'ws-legacy-config',
      settings: { scripts: { run: 'late legacy run' } },
    });
    wire.dispose();
    runtime.dispose();
    runtime = new WorkspaceRegistryRuntime({ handle, clock });
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));

    const restarted = await wire.client.getProjectConfig({ workspaceId: 'ws-legacy-config' });
    expect(restarted).toMatchObject({
      success: true,
      data: {
        personalConfig: {
          scripts: { setup: 'personal setup', teardown: 'legacy teardown' },
        },
        legacyDesktopSettingsMigrated: true,
      },
    });
    expect(restarted).not.toMatchObject({
      data: { personalConfig: { scripts: { run: 'late legacy run' } } },
    });
  });

  it('createWorkspace returns the canonical record to a second registrant of the same path', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await wire.client.createWorkspace({ workspaceId: 'ws-a', path: repoPath });

    const second = await wire.client.createWorkspace({ workspaceId: 'ws-b', path: repoPath });
    expect(second).toMatchObject({
      success: true,
      data: { id: 'ws-a', path: repoPath },
    });
  });

  it('createWorkspace errors on a nonexistent path', async () => {
    const missing = path.join(root, 'does-not-exist');
    const created = await wire.client.createWorkspace({ workspaceId: 'ws-x', path: missing });
    expect(created).toEqual({
      success: false,
      error: { type: 'path-not-found', path: missing },
    });
  });

  it('deleteWorkspace unregisters without touching disk and is idempotent', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await wire.client.createWorkspace({ workspaceId: 'ws-1', path: repoPath });

    const deleted = await wire.client.deleteWorkspace({ workspaceId: 'ws-1' });
    expect(deleted).toEqual({ success: true, data: undefined });
    expect(await listRecords()).toEqual({});
    // The artifact is untouched.
    await fs.access(path.join(repoPath, 'README.md'));

    const again = await wire.client.deleteWorkspace({ workspaceId: 'ws-1' });
    expect(again).toEqual({ success: true, data: undefined });
    const absent = await wire.client.deleteWorkspace({ workspaceId: 'never-existed' });
    expect(absent).toEqual({ success: true, data: undefined });
  });

  it('refresh observes git state with untracked lines counted as additions', async () => {
    const repoPath = await makeRepo(root, 'repo');
    const worktreePath = await makeWorktree(repoPath, root, 'wt-1');
    const created = await wire.client.createWorkspace({ workspaceId: 'ws-wt', path: worktreePath });
    expect(created).toMatchObject({ success: true });

    // Only untracked changes: a new 3-line file plus an ignored file that must not count.
    await fs.writeFile(path.join(worktreePath, 'new-file.txt'), 'one\ntwo\nthree\n');
    await fs.writeFile(path.join(worktreePath, '.gitignore'), 'ignored.txt\n');
    await fs.writeFile(path.join(worktreePath, 'ignored.txt'), 'x\n'.repeat(100));

    const refreshed = await wire.client.refresh({ workspaceId: 'ws-wt' });
    expect(refreshed).toEqual({ success: true, data: undefined });

    const records = await listRecords();
    const record = records['ws-wt']!;
    expect(record.git).toMatchObject({
      branch: 'branch-wt-1',
      dirty: true,
      // 3 lines from new-file.txt + 1 line from .gitignore; ignored.txt excluded.
      diffStats: { added: 4, deleted: 0 },
    });
  });

  it('refresh adopts hand-made worktrees and un-adopts vanished ones', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });
    const worktreePath = await makeWorktree(repoPath, root, 'hand-made');
    await fs.writeFile(
      path.join(worktreePath, '.emdash.json'),
      JSON.stringify({ scripts: { run: 'adopted run' } })
    );

    await wire.client.refresh({});
    let records = await listRecords();
    const adopted = Object.values(records).find((record) => record.path === worktreePath);
    expect(adopted).toMatchObject({
      kind: 'worktree',
      origin: 'adopted',
      parentId: 'ws-repo',
      gitAdminName: 'hand-made',
      observedStatus: 'present',
      config: { scripts: { run: true }, parseError: false },
    });

    // Deleted on disk: the adopted record follows the disk and disappears.
    await fs.rm(worktreePath, { recursive: true, force: true });
    await wire.client.refresh({});
    records = await listRecords();
    expect(Object.values(records).some((record) => record.path === worktreePath)).toBe(false);
  });

  it('refresh flips vanished registered workspaces to missing and back', async () => {
    const plain = path.join(root, 'plain');
    await fs.mkdir(plain);
    await wire.client.createWorkspace({ workspaceId: 'ws-dir', path: plain });

    await fs.rm(plain, { recursive: true, force: true });
    await wire.client.refresh({});
    let records = await listRecords();
    expect(records['ws-dir']).toMatchObject({ observedStatus: 'missing' });

    await fs.mkdir(plain);
    await wire.client.refresh({});
    records = await listRecords();
    expect(records['ws-dir']).toMatchObject({ observedStatus: 'present' });
  });

  it('refresh relinks a moved worktree by its admin name, preserving identity', async () => {
    const repoPath = await makeRepo(root, 'repo');
    const worktreePath = await makeWorktree(repoPath, root, 'movable');
    await wire.client.createWorkspace({ workspaceId: 'ws-moved', path: worktreePath });

    const movedPath = path.join(root, 'relocated');
    git(repoPath, 'worktree', 'move', worktreePath, movedPath);

    await wire.client.refresh({});
    const records = await listRecords();
    expect(records['ws-moved']).toMatchObject({
      id: 'ws-moved',
      path: await fs.realpath(movedPath),
      gitAdminName: 'movable',
      observedStatus: 'present',
    });
  });

  it('measureUsage reports total and reclaimable git-ignored artifact bytes by workspace id', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await fs.writeFile(path.join(repoPath, '.gitignore'), 'dist/\n');
    git(repoPath, 'add', '.gitignore');
    git(repoPath, 'commit', '-m', 'ignore dist');
    await fs.mkdir(path.join(repoPath, 'dist'));
    await fs.writeFile(path.join(repoPath, 'dist', 'bundle.js'), 'x'.repeat(4_096));
    await wire.client.createWorkspace({ workspaceId: 'ws-usage', path: repoPath });

    const measured = await wire.client.measureUsage({ workspaceId: 'ws-usage' });
    expect(measured).toMatchObject({ success: true, data: { errors: [] } });
    if (!measured.success) throw new Error('expected success');
    expect(measured.data.artifactBytes).toBeGreaterThan(0);
    expect(measured.data.totalBytes).toBeGreaterThanOrEqual(measured.data.artifactBytes);
  });

  it('measureUsage of an unknown workspaceId is a typed not-found error', async () => {
    const measured = await wire.client.measureUsage({ workspaceId: 'unknown' });
    expect(measured).toEqual({
      success: false,
      error: { type: 'workspace-not-found', workspaceId: 'unknown' },
    });
  });

  it('refresh of an unknown id is a typed not-found error', async () => {
    const refreshed = await wire.client.refresh({ workspaceId: 'unknown' });
    expect(refreshed).toEqual({
      success: false,
      error: { type: 'workspace-not-found', workspaceId: 'unknown' },
    });
  });

  it('createWorktree returns at agent-spawnable; artifacts and push land in the background', async () => {
    const repoPath = await makeRepo(root, 'repo');
    // The task starts from origin but publishes to a distinct project push remote.
    const originPath = path.join(root, 'origin.git');
    const forkPath = path.join(root, 'fork.git');
    git(root, 'init', '--bare', originPath);
    git(root, 'init', '--bare', forkPath);
    git(repoPath, 'remote', 'add', 'origin', originPath);
    git(repoPath, 'remote', 'add', 'fork', forkPath);
    git(repoPath, 'push', '-u', 'origin', 'main');
    // Gitignored artifacts: only the ones named in preservePatterns ride the
    // background copy; everything else ignored stays behind.
    await fs.writeFile(path.join(repoPath, '.gitignore'), '.env*\nnode_modules/\n');
    await fs.writeFile(
      path.join(repoPath, '.emdash.json'),
      JSON.stringify({ preservePatterns: ['.env.team'] })
    );
    await fs.writeFile(path.join(repoPath, '.env.personal'), 'PERSONAL=1\n');
    await fs.writeFile(path.join(repoPath, '.env.team'), 'TEAM=1\n');
    await fs.writeFile(path.join(repoPath, '.env.input'), 'INPUT=1\n');
    await fs.mkdir(path.join(repoPath, 'node_modules', 'dep'), { recursive: true });
    await fs.writeFile(path.join(repoPath, 'node_modules', 'dep', 'index.js'), 'ok\n');
    git(repoPath, 'add', '.gitignore', '.emdash.json');
    git(repoPath, 'commit', '-m', 'ignore env');
    git(repoPath, 'push', 'origin', 'main');
    await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });
    await wire.client.patchPersonalProjectConfig({
      workspaceId: 'ws-repo',
      patch: { preservePatterns: ['.env.personal'] },
    });

    const worktreePath = path.join(root, 'feature-wt');
    const created = await wire.client.createWorktree({
      workspaceId: 'ws-new',
      repositoryId: 'ws-repo',
      branch: 'feature/new',
      baseRef: 'origin/main',
      path: worktreePath,
      preservePatterns: ['.env.input'],
      publish: { remote: 'fork' },
    });
    // The verb returns at agent-spawnable: worktree checked out, background pending.
    expect(created).toMatchObject({
      success: true,
      data: {
        id: 'ws-new',
        kind: 'worktree',
        parentId: 'ws-repo',
        origin: 'registered',
        observedStatus: 'present',
        creation: { branch: 'feature/new', baseRef: 'origin/main', requestedPath: worktreePath },
        lastCreateOutcome: { status: 'succeeded' },
        git: { branch: 'feature/new' },
      },
    });
    if (!created.success) throw new Error('expected success');
    expect(created.data.gitAdminName).not.toBeNull();
    // No push happened on the critical path.
    expect(git(repoPath, 'ls-remote', '--heads', 'fork', 'feature/new')).toBe('');

    // The background steps settle: artifacts cloned, branch pushed, statuses durable.
    await eventually(async () => {
      const records = await listRecords();
      expect(lifecycleStep(records['ws-new'], 'copy-artifacts')).toMatchObject({
        status: 'succeeded',
      });
      expect(lifecycleStep(records['ws-new'], 'push-branch')).toMatchObject({
        status: 'succeeded',
      });
    });
    await fs.access(path.join(created.data.path, '.env.personal'));
    await expect(fs.access(path.join(created.data.path, '.env.team'))).rejects.toThrow();
    await expect(fs.access(path.join(created.data.path, '.env.input'))).rejects.toThrow();
    // The unnamed ignored artifact (node_modules) is deliberately not copied.
    await expect(fs.access(path.join(created.data.path, 'node_modules'))).rejects.toThrow();
    // The copy step records the matched entry count for the Activity description.
    const records = await listRecords();
    expect(lifecycleStep(records['ws-new'], 'copy-artifacts')).toMatchObject({
      params: { fileCount: 1 },
    });
    expect(git(repoPath, 'ls-remote', '--heads', 'fork', 'feature/new')).toContain(
      'refs/heads/feature/new'
    );
    expect(git(repoPath, 'ls-remote', '--heads', 'origin', 'feature/new')).toBe('');
    expect(git(repoPath, 'config', 'branch.feature/new.remote')).toBe('fork');
    expect(git(repoPath, 'config', 'branch.feature/new.merge')).toBe('refs/heads/feature/new');
    // git status in the new worktree stays clean — artifacts are all ignored.
    expect(git(created.data.path, 'status', '--porcelain')).toBe('');
  });

  it('concurrent worktree creations against one repository both succeed unserialized', async () => {
    // Spec (git concurrency model): per-repository creation serialization is dropped;
    // git's own locking suffices for parallel `worktree add` calls.
    const repoPath = await makeRepo(root, 'repo');
    await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });

    const [first, second] = await Promise.all([
      wire.client.createWorktree({
        workspaceId: 'wt-first',
        repositoryId: 'ws-repo',
        branch: 'parallel/first',
        baseRef: 'main',
        path: path.join(root, 'parallel-first'),
        preservePatterns: [],
      }),
      wire.client.createWorktree({
        workspaceId: 'wt-second',
        repositoryId: 'ws-repo',
        branch: 'parallel/second',
        baseRef: 'main',
        path: path.join(root, 'parallel-second'),
        preservePatterns: [],
      }),
    ]);

    expect(first).toMatchObject({ success: true, data: { observedStatus: 'present' } });
    expect(second).toMatchObject({ success: true, data: { observedStatus: 'present' } });
    const worktrees = git(repoPath, 'worktree', 'list', '--porcelain');
    expect(worktrees).toContain('parallel-first');
    expect(worktrees).toContain('parallel-second');
  });

  it('createWorktree failure records the stage durably and keeps the record', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });

    const worktreePath = path.join(root, 'doomed-wt');
    const created = await wire.client.createWorktree({
      workspaceId: 'ws-doomed',
      repositoryId: 'ws-repo',
      branch: 'feature/doomed',
      baseRef: 'refs/heads/does-not-exist',
      path: worktreePath,
      preservePatterns: [],
    });
    expect(created).toMatchObject({
      success: false,
      error: { type: 'stage-failed', stage: 'add-worktree' },
    });

    const records = await listRecords();
    expect(records['ws-doomed']).toMatchObject({
      observedStatus: 'missing',
      lastCreateOutcome: { status: 'failed', stage: 'add-worktree' },
    });
    // The failed pipeline leaves a failed lifecycle step carrying git's message.
    expect(lifecycleStep(records['ws-doomed'], 'create-worktree')).toMatchObject({
      status: 'failed',
    });
  });

  it('createWorktree replays: succeeded is a no-op, a failed push retries manually, divergent errors', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });
    const worktreePath = path.join(root, 'retry-wt');
    const input = {
      workspaceId: 'ws-retry',
      repositoryId: 'ws-repo',
      branch: 'feature/retry',
      baseRef: 'main',
      path: worktreePath,
      preservePatterns: [],
      // No remote: the background push fails, but never the creation itself.
      publish: { remote: 'origin' },
    };

    const first = await wire.client.createWorktree(input);
    expect(first).toMatchObject({
      success: true,
      data: { lastCreateOutcome: { status: 'succeeded' } },
    });

    // The push failure is a durable, non-blocking "branch not pushed" state.
    await eventually(async () => {
      const records = await listRecords();
      expect(lifecycleStep(records['ws-retry'], 'push-branch')).toMatchObject({
        status: 'failed',
      });
    });

    const replay = await wire.client.createWorktree(input);
    expect(replay).toMatchObject({
      success: true,
      data: { lastCreateOutcome: { status: 'succeeded' } },
    });

    // The transient condition clears; one manual retry pushes the branch.
    const originPath = path.join(root, 'origin.git');
    git(root, 'init', '--bare', originPath);
    git(repoPath, 'remote', 'add', 'origin', originPath);
    const retried = await wire.client.retryStep({ workspaceId: 'ws-retry', step: 'push-branch' });
    expect(retried).toMatchObject({ success: true });
    if (!retried.success) throw new Error('expected success');
    expect(lifecycleStep(retried.data, 'push-branch')).toMatchObject({ status: 'succeeded' });
    expect(git(repoPath, 'ls-remote', '--heads', 'origin', 'feature/retry')).toContain(
      'refs/heads/feature/retry'
    );

    const divergent = await wire.client.createWorktree({ ...input, baseRef: 'other-base' });
    expect(divergent).toMatchObject({
      success: false,
      error: { type: 'immutable-field-mismatch', workspaceId: 'ws-retry' },
    });
  });

  it('an interrupted creation reads as started with no overlay and retries to success', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });
    const worktreePath = path.join(root, 'interrupted-wt');

    // Simulated daemon crash mid-flight: the durable registration exists ('started'),
    // the pipeline never finished, and the rebuilt runtime has no overlay.
    const store = new WorkspaceRecordStore(handle);
    store.insert({
      id: 'ws-interrupted',
      kind: 'worktree',
      path: worktreePath,
      parentId: 'ws-repo',
      origin: 'registered',
      gitAdminName: null,
      observedStatus: 'missing',
      creation: { branch: 'feature/interrupted', baseRef: 'main', requestedPath: worktreePath },
      lastCreateOutcome: { status: 'started', at: 9_000 },
      lifecycle: null,
      lastRemovalAttempt: null,
      git: null,
      lastActivatedAt: null,
      createdAt: 9_000,
      updatedAt: 9_000,
      lastObservedAt: 9_000,
    });
    wire.dispose();
    runtime.dispose();
    runtime = new WorkspaceRegistryRuntime({ handle, clock });
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));

    const records = await listRecords();
    expect(records['ws-interrupted']).toMatchObject({
      lastCreateOutcome: { status: 'started' },
      observedStatus: 'missing',
      runtime: null,
    });

    // The host never re-converges on its own — only a client retry resolves it.
    const retried = await wire.client.createWorktree({
      workspaceId: 'ws-interrupted',
      repositoryId: 'ws-repo',
      branch: 'feature/interrupted',
      baseRef: 'main',
      path: worktreePath,
      preservePatterns: [],
    });
    expect(retried).toMatchObject({
      success: true,
      data: { observedStatus: 'present', lastCreateOutcome: { status: 'succeeded' } },
    });
  });

  it('createWorktree with gitSetup materializes the PR head branch and persists the block', async () => {
    const repoPath = await makeRepo(root, 'repo');
    // A local "remote" carrying a PR-style ref whose commit is not on main.
    const seed = await makeRepo(root, 'seed');
    git(seed, 'checkout', '-b', 'pr-source');
    await fs.writeFile(path.join(seed, 'pr-change.txt'), 'from the PR\n');
    git(seed, 'add', '.');
    git(seed, 'commit', '-m', 'pr change');
    const prHeadOid = git(seed, 'rev-parse', 'HEAD');
    const originPath = path.join(root, 'origin.git');
    git(root, 'init', '--bare', originPath);
    git(seed, 'push', originPath, 'main', 'HEAD:refs/pull/7/head');
    git(repoPath, 'remote', 'add', 'origin', originPath);
    await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });

    const worktreePath = path.join(root, 'pr-wt');
    const gitSetup = {
      fetchBranch: { remote: 'origin', sourceRef: 'refs/pull/7/head' },
      upstream: { remote: 'origin', mergeRef: 'refs/pull/7/head' },
      breadcrumb: { prUrl: 'https://github.com/acme/repo/pull/7' },
      followRef: true,
    };
    // baseRef omitted: fetchBranch materializes the branch instead.
    const created = await wire.client.createWorktree({
      workspaceId: 'ws-pr',
      repositoryId: 'ws-repo',
      branch: 'pr/7/fix',
      path: worktreePath,
      preservePatterns: [],
      gitSetup,
    });

    expect(created).toMatchObject({
      success: true,
      data: {
        observedStatus: 'present',
        creation: {
          branch: 'pr/7/fix',
          baseRef: null,
          requestedPath: worktreePath,
          gitSetup,
        },
        lastCreateOutcome: { status: 'succeeded' },
        git: { branch: 'pr/7/fix' },
      },
    });
    if (!created.success) throw new Error('expected success');
    // The branch sits at the fetched OID with the worktree checked out on it.
    expect(git(repoPath, 'rev-parse', 'refs/heads/pr/7/fix')).toBe(prHeadOid);
    expect(git(created.data.path, 'branch', '--show-current')).toBe('pr/7/fix');
    // Upstream tracking and the PR breadcrumb landed as branch-scoped config.
    expect(git(repoPath, 'config', 'branch.pr/7/fix.remote')).toBe('origin');
    expect(git(repoPath, 'config', 'branch.pr/7/fix.merge')).toBe('refs/pull/7/head');
    expect(git(repoPath, 'config', 'branch.pr/7/fix.emdash-pr-url')).toBe(
      'https://github.com/acme/repo/pull/7'
    );
    // Both new step ids appear in the lifecycle projection.
    expect(lifecycleStep(created.data, 'fetch-branch')).toMatchObject({ status: 'succeeded' });
    expect(lifecycleStep(created.data, 'configure-branch')).toMatchObject({
      status: 'succeeded',
    });
    // No baseRef, nothing to freshen: the advisory fetch-refs step never applies.
    expect(lifecycleStep(created.data, 'fetch-refs')).toBeUndefined();
  });

  it('createWorktree gitSetup fetch failure is a stage-tagged fetch-branch failure', async () => {
    const repoPath = await makeRepo(root, 'repo');
    const originPath = path.join(root, 'origin.git');
    git(root, 'init', '--bare', originPath);
    git(repoPath, 'remote', 'add', 'origin', originPath);
    await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });

    const created = await wire.client.createWorktree({
      workspaceId: 'ws-doomed',
      repositoryId: 'ws-repo',
      branch: 'pr/9/missing',
      path: path.join(root, 'doomed-wt'),
      preservePatterns: [],
      gitSetup: {
        fetchBranch: { remote: 'origin', sourceRef: 'refs/pull/9/head' },
        breadcrumb: { prUrl: 'https://github.com/acme/repo/pull/9' },
      },
    });
    expect(created).toMatchObject({
      success: false,
      error: { type: 'stage-failed', stage: 'fetch-branch' },
    });

    const records = await listRecords();
    expect(records['ws-doomed']).toMatchObject({
      observedStatus: 'missing',
      lastCreateOutcome: { status: 'failed', stage: 'fetch-branch' },
    });
    expect(lifecycleStep(records['ws-doomed'], 'fetch-branch')).toMatchObject({
      status: 'failed',
    });
    // Rollback left no debris branch from this attempt.
    expect(git(repoPath, 'branch', '--list', 'pr/9/missing')).toBe('');
  });

  it('replaying a gitSetup creation interrupted mid-pipeline reuses the branch and configures', async () => {
    const repoPath = await makeRepo(root, 'repo');
    const seed = await makeRepo(root, 'seed2');
    git(seed, 'checkout', '-b', 'pr-source');
    await fs.writeFile(path.join(seed, 'pr-change.txt'), 'from the PR\n');
    git(seed, 'add', '.');
    git(seed, 'commit', '-m', 'pr change');
    const prHeadOid = git(seed, 'rev-parse', 'HEAD');
    const originPath = path.join(root, 'origin.git');
    git(root, 'init', '--bare', originPath);
    git(seed, 'push', originPath, 'main', 'HEAD:refs/pull/7/head');
    git(repoPath, 'remote', 'add', 'origin', originPath);
    await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });

    // Simulated crash after fetch-branch, before add-worktree: the branch exists,
    // the record says 'started', and the rebuilt runtime has no overlay.
    git(repoPath, 'fetch', 'origin', 'refs/pull/7/head:refs/heads/pr/7/fix');
    const worktreePath = path.join(root, 'replayed-wt');
    const gitSetup = {
      fetchBranch: { remote: 'origin', sourceRef: 'refs/pull/7/head' },
      upstream: { remote: 'origin', mergeRef: 'refs/pull/7/head' },
      breadcrumb: { prUrl: 'https://github.com/acme/repo/pull/7' },
      followRef: true,
    };
    const store = new WorkspaceRecordStore(handle);
    store.insert({
      id: 'ws-replayed',
      kind: 'worktree',
      path: worktreePath,
      parentId: 'ws-repo',
      origin: 'registered',
      gitAdminName: null,
      observedStatus: 'missing',
      creation: { branch: 'pr/7/fix', baseRef: null, requestedPath: worktreePath, gitSetup },
      lastCreateOutcome: { status: 'started', at: 9_000 },
      lifecycle: null,
      lastRemovalAttempt: null,
      git: null,
      lastActivatedAt: null,
      createdAt: 9_000,
      updatedAt: 9_000,
      lastObservedAt: 9_000,
    });
    wire.dispose();
    runtime.dispose();
    runtime = new WorkspaceRegistryRuntime({ handle, clock });
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));

    const replayed = await wire.client.createWorktree({
      workspaceId: 'ws-replayed',
      repositoryId: 'ws-repo',
      branch: 'pr/7/fix',
      path: worktreePath,
      preservePatterns: [],
      gitSetup,
    });
    expect(replayed).toMatchObject({
      success: true,
      data: { observedStatus: 'present', lastCreateOutcome: { status: 'succeeded' } },
    });
    if (!replayed.success) throw new Error('expected success');
    // The fetched branch was reused untouched; configure-branch still applied.
    expect(git(repoPath, 'rev-parse', 'refs/heads/pr/7/fix')).toBe(prHeadOid);
    expect(git(repoPath, 'config', 'branch.pr/7/fix.remote')).toBe('origin');
    expect(git(repoPath, 'config', 'branch.pr/7/fix.emdash-pr-url')).toBe(
      'https://github.com/acme/repo/pull/7'
    );
    expect(lifecycleStep(replayed.data, 'fetch-branch')).toMatchObject({ status: 'skipped' });
    expect(lifecycleStep(replayed.data, 'configure-branch')).toMatchObject({
      status: 'succeeded',
    });
  });

  it('concurrent same-repository creations serialize and both succeed', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath });

    const [a, b] = await Promise.all([
      wire.client.createWorktree({
        workspaceId: 'ws-a',
        repositoryId: 'ws-repo',
        branch: 'feature/a',
        baseRef: 'main',
        path: path.join(root, 'wt-a'),
        preservePatterns: [],
      }),
      wire.client.createWorktree({
        workspaceId: 'ws-b',
        repositoryId: 'ws-repo',
        branch: 'feature/b',
        baseRef: 'main',
        path: path.join(root, 'wt-b'),
        preservePatterns: [],
      }),
    ]);
    expect(a).toMatchObject({
      success: true,
      data: { lastCreateOutcome: { status: 'succeeded' } },
    });
    expect(b).toMatchObject({
      success: true,
      data: { lastCreateOutcome: { status: 'succeeded' } },
    });
  });

  it('fs events refresh observations without any client call', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await wire.client.createWorkspace({ workspaceId: 'ws-live', path: repoPath });

    const watchService = createWatchService({ backend: nativeWatchBackend() });
    const scheduler = new WorkspaceScanScheduler({
      watcher: watchService,
      execute: (request) => runtime.executeScanRequest(request),
      listTargets: () => runtime.scanTargets(),
      isActive: () => false,
      debounceMs: 25,
      pollIntervalMs: 60 * 60_000,
    });
    runtime.setOnRecordsChanged(() => scheduler.syncWatches());
    scheduler.start();
    try {
      await fs.writeFile(path.join(repoPath, 'untracked.txt'), 'a\nb\n');
      await eventually(async () => {
        const records = await listRecords();
        expect(records['ws-live']?.git).toMatchObject({
          dirty: true,
          diffStats: { added: 2, deleted: 0 },
        });
      });
    } finally {
      await scheduler.dispose();
      await watchService.dispose();
    }
  }, 15_000);

  it('registry state survives a runtime rebuild over the same store', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await wire.client.createWorkspace({ workspaceId: 'ws-1', path: repoPath });

    // Simulated daemon restart: new runtime over the same durable store.
    wire.dispose();
    runtime.dispose();
    runtime = new WorkspaceRegistryRuntime({ handle, clock });
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));

    const records = await listRecords();
    expect(records['ws-1']).toMatchObject({ id: 'ws-1', kind: 'repository', path: repoPath });
  });
});
