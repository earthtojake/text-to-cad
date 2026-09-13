import { execFileSync } from 'node:child_process';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ManualClock } from '@emdash/shared/testing';
import { remote, snapshot } from '@emdash/wire/state';
import { createTestWire, type TestWire } from '@emdash/wire/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type { TempStoreHandle } from '#primitives/sqlite-store/api';
// oxlint-disable-next-line emdash/core-module-boundaries -- contract tests wire a real scripts runtime behind the registry, mirroring host composition (activation-scripts-via-terminals spec)
import { scriptsContract } from '#runtimes/scripts/api';
// oxlint-disable-next-line emdash/core-module-boundaries -- see above
import { createScriptsController } from '#runtimes/scripts/node/api/controller';
// oxlint-disable-next-line emdash/core-module-boundaries -- see above
import { ScriptsRuntime } from '#runtimes/scripts/node/runtime';
// oxlint-disable-next-line emdash/core-module-boundaries -- see above
import { ChildProcessPtySpawner } from '#runtimes/scripts/node/script-test-support';
import { workspaceRegistryContract } from '#runtimes/workspace-registry/api';
import {
  workspaceRegistryStore,
  type WorkspaceRegistryDb,
} from '#runtimes/workspace-registry/node/persistence/store';
import { WorkspaceRegistryRuntime } from '#runtimes/workspace-registry/node/runtime';
import { createWorkspaceRegistryController } from './controller';

const TEST_USER_ENV = Object.fromEntries(
  Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined)
);

// Contract-seam tests for the `.emdash.json` config live model (spec:
// workspace-lifecycle-v2). The model is internal — behavior is asserted through the
// registry verbs and records, never by inspecting the cache: activation gates which
// script steps exist on the model (a disk edit without a scan is invisible to the
// verb), a settled scan picks the edit up, worktrees diverge from their repository,
// an unparseable file degrades to the empty default plus a notice, and the wire
// record carries a config summary that vanishes with the workspace.

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

describe('workspace registry config live model', () => {
  let root: string;
  let handle: TempStoreHandle<WorkspaceRegistryDb>;
  let clock: ManualClock;
  let scriptsRuntime: ScriptsRuntime;
  let scriptsWire: TestWire<typeof scriptsContract>;
  let runtime: WorkspaceRegistryRuntime;
  let wire: TestWire<typeof workspaceRegistryContract>;

  beforeEach(async () => {
    root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'ws-config-')));
    handle = await workspaceRegistryStore.openTemp();
    clock = new ManualClock(10_000);
    scriptsRuntime = new ScriptsRuntime({
      spawner: new ChildProcessPtySpawner(),
      userEnv: async () => TEST_USER_ENV,
    });
    scriptsWire = createTestWire(scriptsContract, createScriptsController(scriptsRuntime));
    runtime = new WorkspaceRegistryRuntime({ handle, clock, scripts: scriptsWire.client });
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));
  });

  afterEach(async () => {
    wire.dispose();
    runtime.dispose();
    scriptsWire.dispose();
    scriptsRuntime.dispose();
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

  async function writeConfig(dir: string, config: unknown): Promise<void> {
    await fs.writeFile(
      path.join(dir, '.emdash.json'),
      typeof config === 'string' ? config : JSON.stringify(config)
    );
  }

  it('publishes creation with config loaded and resolves without rereading the file', async () => {
    const workspacePath = path.join(root, 'created');
    await fs.mkdir(workspacePath, { recursive: true });
    await writeConfig(workspacePath, { scripts: { run: 'original run' } });

    const created = await wire.client.createWorkspace({
      workspaceId: 'ws-created',
      path: workspacePath,
    });
    expect(created).toMatchObject({
      success: true,
      data: {
        observedStatus: 'present',
        config: {
          scripts: { run: true },
          parseError: false,
        },
      },
    });

    await writeConfig(workspacePath, { scripts: { run: 'edited run' } });
    const resolved = await wire.client.getProjectConfig({ workspaceId: 'ws-created' });
    expect(resolved).toMatchObject({
      success: true,
      data: { resolved: { run: { value: 'original run', from: 'team' } } },
    });
  });

  it('hydrates persisted present records before boot-time config resolution', async () => {
    const workspacePath = path.join(root, 'booted');
    await fs.mkdir(workspacePath, { recursive: true });
    await writeConfig(workspacePath, { scripts: { setup: 'boot setup' } });
    expect(
      (await wire.client.createWorkspace({ workspaceId: 'ws-booted', path: workspacePath })).success
    ).toBe(true);

    wire.dispose();
    runtime.dispose();
    runtime = new WorkspaceRegistryRuntime({ handle, clock, scripts: scriptsWire.client });
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));

    const resolved = await wire.client.getProjectConfig({ workspaceId: 'ws-booted' });
    expect(resolved).toMatchObject({
      success: true,
      data: { resolved: { setup: { value: 'boot setup', from: 'team' } } },
    });
    expect((await listRecords())['ws-booted']).toMatchObject({
      observedStatus: 'present',
      config: { scripts: { setup: true }, parseError: false },
    });
  });

  it('activation gates script steps on the model, not the disk; a scan picks edits up', async () => {
    const workspacePath = path.join(root, 'plain');
    await fs.mkdir(workspacePath, { recursive: true });
    await writeConfig(workspacePath, {});
    expect(
      (await wire.client.createWorkspace({ workspaceId: 'ws-plain', path: workspacePath })).success
    ).toBe(true);

    // Disk edit with no scan in between: the verb must serve the model's state.
    // (Also proves no config read happens inside the activation verb.)
    await eventually(async () => {
      expect((await listRecords())['ws-plain']?.config?.scripts.prepare).toBe(false);
    });
    await writeConfig(workspacePath, { scripts: { prepare: 'echo ran >> which-config' } });
    expect((await wire.client.activateWorkspace({ workspaceId: 'ws-plain' })).success).toBe(true);
    await expect(fs.stat(path.join(workspacePath, 'which-config'))).rejects.toThrow();
    expect((await wire.client.deactivateWorkspace({ workspaceId: 'ws-plain' })).success).toBe(true);

    // A settled scan (what the working-tree watcher requests) refreshes the model;
    // the next activation sees the edit without a restart.
    expect((await wire.client.refresh({ workspaceId: 'ws-plain' })).success).toBe(true);
    expect((await wire.client.activateWorkspace({ workspaceId: 'ws-plain' })).success).toBe(true);
    await expect(fs.readFile(path.join(workspacePath, 'which-config'), 'utf8')).resolves.toBe(
      'ran\n'
    );
  });

  it('refreshes a known config write before personal fields clear and activation', async () => {
    const workspacePath = path.join(root, 'shared');
    await fs.mkdir(workspacePath, { recursive: true });
    await writeConfig(workspacePath, { scripts: { setup: 'echo A > activation-command' } });
    expect(
      (await wire.client.createWorkspace({ workspaceId: 'ws-shared', path: workspacePath })).success
    ).toBe(true);
    expect(
      (
        await wire.client.patchPersonalProjectConfig({
          workspaceId: 'ws-shared',
          patch: { scripts: { setup: 'echo B > activation-command' } },
        })
      ).success
    ).toBe(true);

    const configs = remote(workspaceRegistryContract.projectConfig, wire.client.projectConfig);
    const model = configs({ workspaceId: 'ws-shared' });
    await model.states.current.refresh();
    expect(snapshot(model.states.current).value?.resolved.setup?.value).toBe(
      'echo B > activation-command'
    );

    await writeConfig(workspacePath, { scripts: { setup: 'echo B > activation-command' } });
    const refreshed = await wire.client.refreshProjectConfig({ workspaceId: 'ws-shared' });
    expect(refreshed).toMatchObject({
      success: true,
      data: { resolved: { setup: { value: 'echo B > activation-command', from: 'personal' } } },
    });
    const cleared = await wire.client.patchPersonalProjectConfig({
      workspaceId: 'ws-shared',
      patch: { scripts: { setup: null } },
    });
    expect(cleared).toMatchObject({
      success: true,
      data: { resolved: { setup: { value: 'echo B > activation-command', from: 'team' } } },
    });
    expect(snapshot(model.states.current).value?.resolved.setup).toEqual({
      value: 'echo B > activation-command',
      from: 'team',
    });

    expect((await wire.client.activateWorkspace({ workspaceId: 'ws-shared' })).success).toBe(true);
    await eventually(async () => {
      await expect(
        fs.readFile(path.join(workspacePath, 'activation-command'), 'utf8')
      ).resolves.toBe('B\n');
    });
    await configs.dispose();
  });

  it('a worktree with a divergent config activates with its own scripts', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await writeConfig(repoPath, { scripts: { prepare: 'echo repo >> ../which' } });
    expect(
      (await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath })).success
    ).toBe(true);

    const worktreePath = path.join(root, 'diverged');
    const created = await wire.client.createWorktree({
      workspaceId: 'wt-diverged',
      repositoryId: 'ws-repo',
      path: worktreePath,
      branch: 'diverged',
      baseRef: 'main',
      preservePatterns: [],
    });
    expect(created.success).toBe(true);

    // The branch diverges its own config; the scan folds it into the model.
    await writeConfig(worktreePath, { scripts: { prepare: 'echo worktree >> ../which' } });
    expect((await wire.client.refresh({ workspaceId: 'wt-diverged' })).success).toBe(true);

    expect((await wire.client.activateWorkspace({ workspaceId: 'wt-diverged' })).success).toBe(
      true
    );
    expect((await wire.client.activateWorkspace({ workspaceId: 'ws-repo' })).success).toBe(true);
    await expect(fs.readFile(path.join(root, 'which'), 'utf8')).resolves.toBe('worktree\nrepo\n');
  });

  it('an unparseable config degrades to the empty default plus a notice; activation proceeds', async () => {
    const workspacePath = path.join(root, 'broken');
    await fs.mkdir(workspacePath, { recursive: true });
    await writeConfig(workspacePath, '{ not json');
    expect(
      (await wire.client.createWorkspace({ workspaceId: 'ws-broken', path: workspacePath })).success
    ).toBe(true);

    await eventually(async () => {
      const record = (await listRecords())['ws-broken'];
      expect(record?.config).toMatchObject({ parseError: true, preservePatterns: [] });
      expect(record?.runtime?.notices).toEqual([
        expect.objectContaining({ kind: 'config-invalid' }),
      ]);
    });

    // Empty default config: activation succeeds with no script steps.
    expect((await wire.client.activateWorkspace({ workspaceId: 'ws-broken' })).success).toBe(true);
    expect((await listRecords())['ws-broken']?.runtime?.lifecycle ?? null).toBeNull();

    // Fixing the file clears the notice on the next scan.
    await writeConfig(workspacePath, {});
    expect((await wire.client.refresh({ workspaceId: 'ws-broken' })).success).toBe(true);
    const fixed = (await listRecords())['ws-broken'];
    expect(fixed?.config?.parseError).toBe(false);
    expect(fixed?.runtime?.notices ?? []).toEqual([]);
  });

  it('the wire record carries the config summary and drops it when the workspace vanishes', async () => {
    const workspacePath = path.join(root, 'summarized');
    await fs.mkdir(workspacePath, { recursive: true });
    await writeConfig(workspacePath, {
      preservePatterns: ['.env'],
      scripts: { setup: 'true', run: 'true' },
    });
    expect(
      (await wire.client.createWorkspace({ workspaceId: 'ws-summarized', path: workspacePath }))
        .success
    ).toBe(true);

    await eventually(async () => {
      expect((await listRecords())['ws-summarized']?.config).toEqual({
        scripts: { prepare: false, setup: true, run: true, teardown: false },
        preservePatterns: ['.env'],
        parseError: false,
      });
    });

    await fs.rm(workspacePath, { recursive: true, force: true });
    expect((await wire.client.refresh({ workspaceId: 'ws-summarized' })).success).toBe(true);
    const vanished = (await listRecords())['ws-summarized'];
    expect(vanished?.observedStatus).toBe('missing');
    expect(vanished?.config ?? null).toBeNull();
  });

  it('creation unions preserve patterns from the source repository config entry', async () => {
    const repoPath = await makeRepo(root, 'repo');
    await fs.appendFile(path.join(repoPath, '.gitignore'), '.env\n');
    git(repoPath, 'add', '.gitignore');
    git(repoPath, 'commit', '-m', 'ignore env');
    await fs.writeFile(path.join(repoPath, '.env'), 'SECRET=1\n');
    await writeConfig(repoPath, { preservePatterns: ['.env'] });
    expect(
      (await wire.client.createWorkspace({ workspaceId: 'ws-repo', path: repoPath })).success
    ).toBe(true);

    // The caller passes no patterns; the source repository's `.emdash.json` entry
    // still drives the copy (spec: patterns resolve against the source checkout).
    const created = await wire.client.createWorktree({
      workspaceId: 'wt-carried',
      repositoryId: 'ws-repo',
      path: path.join(root, 'carried'),
      branch: 'carried',
      baseRef: 'main',
      preservePatterns: [],
    });
    expect(created.success).toBe(true);
    if (!created.success) return;
    expect(created.data.runtime?.lifecycle?.some((step) => step.id === 'copy-artifacts')).toBe(
      true
    );

    await eventually(async () => {
      await expect(fs.readFile(path.join(root, 'carried', '.env'), 'utf8')).resolves.toBe(
        'SECRET=1\n'
      );
    });
  });
});
