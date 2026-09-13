import { execFile } from 'node:child_process';
import { promises as fs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
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

const execFileAsync = promisify(execFile);
const TEST_USER_ENV = Object.fromEntries(
  Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined)
);

// Contract-seam tests for the activation lifecycle (ADR 0005): activate returns at the
// session-gating point (prepare); setup and run continue in the background and are
// observable only through the records overlay; script failures are notices, never verb
// errors; deactivate owns kill-sessions + time-boxed non-fatal teardown; activation is
// ephemeral — a daemon restart leaves only lastActivatedAt. Scripts execute on a real
// in-process scripts runtime (spec: activation-scripts-via-terminals) whose run state
// the registry observes to write durable lifecycle steps.

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

describe('workspace registry activation lifecycle', () => {
  let root: string;
  let handle: TempStoreHandle<WorkspaceRegistryDb>;
  let clock: ManualClock;
  let scriptsRuntime: ScriptsRuntime;
  let scriptsWire: TestWire<typeof scriptsContract>;
  let runtime: WorkspaceRegistryRuntime;
  let wire: TestWire<typeof workspaceRegistryContract>;
  let killedPaths: string[];

  function createRegistryRuntime(): WorkspaceRegistryRuntime {
    return new WorkspaceRegistryRuntime({
      handle,
      clock,
      killSessions: async (workspacePath) => {
        killedPaths.push(workspacePath);
      },
      scripts: scriptsWire.client,
      activation: { teardownTimeoutMs: 500 },
    });
  }

  beforeEach(async () => {
    root = await fs.realpath(await fs.mkdtemp(path.join(os.tmpdir(), 'ws-activation-')));
    handle = await workspaceRegistryStore.openTemp();
    clock = new ManualClock(10_000);
    killedPaths = [];
    scriptsRuntime = new ScriptsRuntime({
      spawner: new ChildProcessPtySpawner(),
      userEnv: async () => TEST_USER_ENV,
    });
    scriptsWire = createTestWire(scriptsContract, createScriptsController(scriptsRuntime));
    runtime = createRegistryRuntime();
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

  async function makeWorkspace(
    name: string,
    scripts: Partial<Record<'prepare' | 'setup' | 'run' | 'teardown', string>>,
    shellSetup?: string
  ): Promise<string> {
    const workspacePath = path.join(root, name);
    await fs.mkdir(workspacePath, { recursive: true });
    await execFileAsync('git', ['init', '--quiet', workspacePath]);
    await fs.writeFile(
      path.join(workspacePath, '.emdash.json'),
      JSON.stringify({ scripts, shellSetup })
    );
    const created = await wire.client.createWorkspace({
      workspaceId: `ws-${name}`,
      path: workspacePath,
    });
    expect(created.success).toBe(true);
    if (scripts.run) {
      const toggled = await wire.client.patchPersonalProjectConfig({
        workspaceId: `ws-${name}`,
        patch: { autoRunRun: true },
      });
      expect(toggled.success).toBe(true);
    }
    return workspacePath;
  }

  it('activate returns after prepare; setup and run progress through the overlay', async () => {
    const workspacePath = await makeWorkspace('staged', {
      prepare: 'echo prepared > prepare-marker',
      setup: 'until [ -f gate ]; do sleep 0.05; done; echo done > setup-marker',
      run: 'echo ran > run-marker',
    });

    const activated = await wire.client.activateWorkspace({ workspaceId: 'ws-staged' });
    if (!activated.success) throw new Error('activate failed');

    // The verb returned at the session-gating point: prepare is done, setup is not.
    await expect(fs.readFile(path.join(workspacePath, 'prepare-marker'), 'utf8')).resolves.toBe(
      'prepared\n'
    );
    expect(activated.data.lastActivatedAt).toBe(10_000);
    expect(activated.data.runtime?.activation).toMatchObject({
      phase: 'active',
      activatedAt: 10_000,
      scripts: { prepare: 'succeeded' },
    });
    expect(['pending', 'running']).toContain(activated.data.runtime?.activation?.scripts.setup);
    await expect(fs.stat(path.join(workspacePath, 'setup-marker'))).rejects.toThrow();

    // Releasing the gate lets setup finish; run waits on setup success, then exits.
    await fs.writeFile(path.join(workspacePath, 'gate'), '');
    await eventually(async () => {
      const records = await listRecords();
      expect(records['ws-staged']?.runtime?.activation?.scripts).toEqual({
        prepare: 'succeeded',
        setup: 'succeeded',
        run: 'exited',
      });
    });
    await expect(fs.readFile(path.join(workspacePath, 'run-marker'), 'utf8')).resolves.toBe(
      'ran\n'
    );
  });

  it('a failing prepare script yields a notice, never a verb error', async () => {
    await makeWorkspace('broken', { prepare: 'echo broken >&2; exit 7' });

    const activated = await wire.client.activateWorkspace({ workspaceId: 'ws-broken' });
    if (!activated.success) throw new Error('activate failed');

    expect(activated.data.runtime?.activation).toMatchObject({
      phase: 'active',
      scripts: { prepare: 'failed' },
    });
    expect(activated.data.runtime?.notices).toEqual([
      expect.objectContaining({ kind: 'script-failed', script: 'prepare' }),
    ]);
  });

  it('a failed setup keeps run from starting', async () => {
    const workspacePath = await makeWorkspace('half', {
      setup: 'exit 1',
      run: 'echo ran > run-marker',
    });

    const activated = await wire.client.activateWorkspace({ workspaceId: 'ws-half' });
    expect(activated.success).toBe(true);

    await eventually(async () => {
      const records = await listRecords();
      expect(records['ws-half']?.runtime?.activation?.scripts).toEqual({
        prepare: 'skipped',
        setup: 'failed',
        run: 'skipped',
      });
    });
    await expect(fs.stat(path.join(workspacePath, 'run-marker'))).rejects.toThrow();
  });

  it('deactivate kills sessions, runs teardown exactly once, and clears activation', async () => {
    const workspacePath = await makeWorkspace('lifecycle', {
      teardown: 'echo teardown >> teardown-log',
    });

    const activated = await wire.client.activateWorkspace({ workspaceId: 'ws-lifecycle' });
    expect(activated.success).toBe(true);

    const deactivated = await wire.client.deactivateWorkspace({ workspaceId: 'ws-lifecycle' });
    expect(deactivated).toEqual({ success: true, data: undefined });
    expect(killedPaths).toEqual([workspacePath]);
    await expect(fs.readFile(path.join(workspacePath, 'teardown-log'), 'utf8')).resolves.toBe(
      'teardown\n'
    );
    const records = await listRecords();
    expect(records['ws-lifecycle']?.runtime?.activation ?? null).toBeNull();

    // Teardown joins the Activity timeline like every other lifecycle step.
    await eventually(async () => {
      const current = await listRecords();
      expect(current['ws-lifecycle']?.runtime?.lifecycle).toEqual([
        expect.objectContaining({
          id: 'teardown',
          status: 'succeeded',
          params: { provenance: 'activation' },
        }),
      ]);
    });

    // Idempotent on inactive workspaces: sessions are swept again, teardown is not re-run.
    const again = await wire.client.deactivateWorkspace({ workspaceId: 'ws-lifecycle' });
    expect(again.success).toBe(true);
    await expect(fs.readFile(path.join(workspacePath, 'teardown-log'), 'utf8')).resolves.toBe(
      'teardown\n'
    );
  });

  it('a hanging teardown is cut off at the time-box and deactivation still succeeds', async () => {
    await makeWorkspace('hanging', { teardown: 'sleep 30' });
    const activated = await wire.client.activateWorkspace({ workspaceId: 'ws-hanging' });
    expect(activated.success).toBe(true);

    const startedAt = Date.now();
    const deactivated = await wire.client.deactivateWorkspace({ workspaceId: 'ws-hanging' });
    expect(deactivated.success).toBe(true);
    expect(Date.now() - startedAt).toBeLessThan(10_000);

    const records = await listRecords();
    expect(records['ws-hanging']?.runtime?.notices).toEqual([
      expect.objectContaining({ kind: 'script-failed', script: 'teardown' }),
    ]);
    expect(records['ws-hanging']?.runtime?.activation ?? null).toBeNull();
  });

  it('script steps are durable: a failed setup survives a restart and reactivation overwrites', async () => {
    const workspacePath = await makeWorkspace('outcomes', {
      prepare: 'echo prepared',
      setup: '[ -f fixed ] || { echo setup broke >&2; exit 3; }',
      run: 'echo ran',
    });

    expect((await wire.client.activateWorkspace({ workspaceId: 'ws-outcomes' })).success).toBe(
      true
    );
    await eventually(async () => {
      const records = await listRecords();
      expect(records['ws-outcomes']?.runtime?.lifecycle).toEqual([
        expect.objectContaining({
          id: 'prepare',
          status: 'succeeded',
          startedAt: 10_000,
          finishedAt: 10_000,
        }),
        // Failure messages fold in the run's output tail — the popover says why.
        expect.objectContaining({
          id: 'setup',
          status: 'failed',
          message: expect.stringContaining('setup broke'),
        }),
        // Run never started (setup gates it): a settled skipped step, not a phantom run.
        expect.objectContaining({ id: 'run', status: 'skipped' }),
      ]);
    });

    // Simulated daemon restart: the overlay dies, the durable steps do not.
    wire.dispose();
    runtime.dispose();
    runtime = createRegistryRuntime();
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));
    const restarted = (await listRecords())['ws-outcomes'];
    expect(restarted?.runtime?.activation ?? null).toBeNull();
    expect(restarted?.runtime?.lifecycle).toEqual([
      expect.objectContaining({ id: 'prepare', status: 'succeeded' }),
      expect.objectContaining({ id: 'setup', status: 'failed' }),
      expect.objectContaining({ id: 'run', status: 'skipped' }),
    ]);

    // Reactivating overwrites the script steps wholesale — no history accumulates.
    await fs.writeFile(path.join(workspacePath, 'fixed'), '');
    await clock.advanceBy(7_000);
    expect((await wire.client.activateWorkspace({ workspaceId: 'ws-outcomes' })).success).toBe(
      true
    );
    await eventually(async () => {
      const records = await listRecords();
      expect(records['ws-outcomes']?.runtime?.lifecycle).toEqual([
        expect.objectContaining({ id: 'prepare', status: 'succeeded', finishedAt: 17_000 }),
        expect.objectContaining({ id: 'setup', status: 'succeeded', finishedAt: 17_000 }),
        expect.objectContaining({ id: 'run', status: 'succeeded', finishedAt: 17_000 }),
      ]);
    });
  });

  it('a manual run routed through the registry lands in the timeline', async () => {
    await makeWorkspace('manual', { setup: 'echo manual' });

    const started = await wire.client.runScript({
      workspaceId: 'ws-manual',
      script: 'setup',
      provenance: 'manual',
    });
    expect(started.success).toBe(true);

    // No activation happened — observation alone mirrors the run into the timeline.
    await eventually(async () => {
      const records = await listRecords();
      expect(records['ws-manual']?.runtime?.lifecycle).toEqual([
        expect.objectContaining({
          id: 'setup',
          status: 'succeeded',
          params: { provenance: 'manual' },
        }),
      ]);
    });
  });

  it('runScript brokers a manual run host-side and it lands in the timeline', async () => {
    const workspacePath = await makeWorkspace(
      'brokered',
      { setup: 'printf "$STRICT_EXECUTOR_VALUE" > shell-setup-marker' },
      'export STRICT_EXECUTOR_VALUE=resolved'
    );

    const started = await wire.client.runScript({
      workspaceId: 'ws-brokered',
      script: 'setup',
      provenance: 'retry',
    });
    expect(started.success).toBe(true);
    await eventually(async () => {
      await expect(
        fs.readFile(path.join(workspacePath, 'shell-setup-marker'), 'utf8')
      ).resolves.toBe('resolved');
    });

    await eventually(async () => {
      const records = await listRecords();
      expect(records['ws-brokered']?.runtime?.lifecycle).toEqual([
        expect.objectContaining({
          id: 'setup',
          status: 'succeeded',
          params: { provenance: 'retry' },
        }),
      ]);
    });

    // The registry built the request from its record: the run saw record facts.
    const run = await scriptsWire.client.wait({ workspacePath, script: 'setup' });
    expect(run.success && run.data.provenance === 'retry').toBe(true);
  });

  it('uses one personal config for auto-run toggles and manual Play commands', async () => {
    const workspacePath = await makeWorkspace('personal-policy', {
      run: 'echo team > team-marker',
    });
    const patched = await wire.client.patchPersonalProjectConfig({
      workspaceId: 'ws-personal-policy',
      patch: {
        scripts: { run: 'echo personal > personal-marker' },
        autoRunRun: false,
      },
    });
    expect(patched.success).toBe(true);

    expect(
      (await wire.client.activateWorkspace({ workspaceId: 'ws-personal-policy' })).success
    ).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 50));
    await expect(fs.stat(path.join(workspacePath, 'personal-marker'))).rejects.toThrow();
    await expect(fs.stat(path.join(workspacePath, 'team-marker'))).rejects.toThrow();

    expect(
      (
        await wire.client.runScript({
          workspaceId: 'ws-personal-policy',
          script: 'run',
          provenance: 'manual',
        })
      ).success
    ).toBe(true);
    await eventually(async () => {
      await expect(fs.readFile(path.join(workspacePath, 'personal-marker'), 'utf8')).resolves.toBe(
        'personal\n'
      );
    });
    await expect(fs.stat(path.join(workspacePath, 'team-marker'))).rejects.toThrow();
  });

  it('runScript rejects unknown workspaces and unconfigured scripts', async () => {
    await makeWorkspace('rejects', { setup: 'echo ok' });

    const missing = await wire.client.runScript({
      workspaceId: 'ws-nope',
      script: 'setup',
      provenance: 'manual',
    });
    expect(!missing.success && missing.error.type === 'workspace-not-found').toBe(true);

    const unconfigured = await wire.client.runScript({
      workspaceId: 'ws-rejects',
      script: 'prepare',
      provenance: 'manual',
    });
    expect(!unconfigured.success && unconfigured.error.type === 'script-not-configured').toBe(true);
  });

  it('deactivation stops an in-flight run script and its step settles as cancelled', async () => {
    await makeWorkspace('stopped', { run: 'sleep 30' });

    expect((await wire.client.activateWorkspace({ workspaceId: 'ws-stopped' })).success).toBe(true);
    await eventually(async () => {
      const records = await listRecords();
      expect(records['ws-stopped']?.runtime?.activation?.scripts.run).toBe('running');
    });

    const startedAt = Date.now();
    const deactivated = await wire.client.deactivateWorkspace({ workspaceId: 'ws-stopped' });
    expect(deactivated.success).toBe(true);
    // The stop verb killed the dev-server-shaped run; deactivation never waited it out.
    expect(Date.now() - startedAt).toBeLessThan(10_000);

    await eventually(async () => {
      const records = await listRecords();
      expect(records['ws-stopped']?.runtime?.lifecycle).toEqual([
        expect.objectContaining({ id: 'run', status: 'cancelled', message: 'Stopped' }),
      ]);
    });
  });

  it('workspaces without configured scripts get no script steps', async () => {
    await makeWorkspace('scriptless', { prepare: 'echo prepared' });
    expect((await wire.client.activateWorkspace({ workspaceId: 'ws-scriptless' })).success).toBe(
      true
    );
    await eventually(async () => {
      const records = await listRecords();
      expect(records['ws-scriptless']?.runtime?.lifecycle?.map((step) => step.id)).toEqual([
        'prepare',
      ]);
    });
  });

  it('a daemon restart leaves no activation state and preserves lastActivatedAt', async () => {
    await makeWorkspace('restarted', {});
    const activated = await wire.client.activateWorkspace({ workspaceId: 'ws-restarted' });
    expect(activated.success).toBe(true);

    wire.dispose();
    runtime.dispose();
    runtime = createRegistryRuntime();
    wire = createTestWire(workspaceRegistryContract, createWorkspaceRegistryController(runtime));

    const records = await listRecords();
    expect(records['ws-restarted']).toMatchObject({
      lastActivatedAt: 10_000,
      runtime: null,
    });
  });

  it('concurrent activate and deactivate on one workspace serialize via the claim', async () => {
    const workspacePath = await makeWorkspace('contended', {
      prepare:
        'echo started > prepare-started; until [ -f prepare-release ]; do sleep 0.01; done; echo prepare >> order-log',
      teardown: 'echo teardown >> order-log',
    });

    const activating = wire.client.activateWorkspace({ workspaceId: 'ws-contended' });
    await eventually(async () => {
      await expect(fs.readFile(path.join(workspacePath, 'prepare-started'), 'utf8')).resolves.toBe(
        'started\n'
      );
    });
    const deactivating = wire.client.deactivateWorkspace({ workspaceId: 'ws-contended' });
    await fs.writeFile(path.join(workspacePath, 'prepare-release'), '');

    const [activated, deactivated] = await Promise.all([activating, deactivating]);
    expect(activated.success).toBe(true);
    expect(deactivated.success).toBe(true);
    await expect(fs.readFile(path.join(workspacePath, 'order-log'), 'utf8')).resolves.toBe(
      'prepare\nteardown\n'
    );
    const records = await listRecords();
    expect(records['ws-contended']?.runtime?.activation ?? null).toBeNull();
  });

  it('activate errors on unknown ids and missing workspaces; deactivate errors on unknown ids', async () => {
    expect(await wire.client.activateWorkspace({ workspaceId: 'ws-nope' })).toEqual({
      success: false,
      error: { type: 'workspace-not-found', workspaceId: 'ws-nope' },
    });
    expect(await wire.client.deactivateWorkspace({ workspaceId: 'ws-nope' })).toEqual({
      success: false,
      error: { type: 'workspace-not-found', workspaceId: 'ws-nope' },
    });

    const workspacePath = await makeWorkspace('gone', {});
    await fs.rm(workspacePath, { recursive: true, force: true });
    const refreshed = await wire.client.refresh({ workspaceId: 'ws-gone' });
    expect(refreshed.success).toBe(true);
    expect(await wire.client.activateWorkspace({ workspaceId: 'ws-gone' })).toEqual({
      success: false,
      error: { type: 'workspace-missing', workspaceId: 'ws-gone' },
    });
  });
});
