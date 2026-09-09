import { promises as fs } from 'node:fs';
import { remote, snapshot } from '@emdash/wire/state';
import { createTestWire, type TestWire } from '@emdash/wire/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { scriptsContract, startScriptRunInputSchema } from '#runtimes/scripts/api';
import { ScriptsRuntime } from '#runtimes/scripts/node/runtime';
import { FakePtySpawner } from '#services/pty/testing';
import { createScriptsController } from './controller';

const WORKSPACE = '/work/trees/task-1';
const FACTS = { workspaceId: 'ws-1', repositoryPath: '/repos/app', branch: 'feature-x' };

describe('scripts runtime contract', () => {
  let spawner: FakePtySpawner;
  let runtime: ScriptsRuntime;
  let wire: TestWire<typeof scriptsContract>;

  beforeEach(() => {
    spawner = new FakePtySpawner();
    runtime = new ScriptsRuntime({
      spawner,
      userEnv: async () => ({
        HOME: '/home/test',
        PATH: '/usr/bin',
        SHELL: '/bin/sh',
        USER_VALUE: 'kept',
      }),
    });
    wire = createTestWire(scriptsContract, createScriptsController(runtime));
  });

  afterEach(() => {
    wire.dispose();
    runtime.dispose();
  });

  async function runsFor(workspacePath: string) {
    const runs = remote(scriptsContract.runs, wire.client.runs);
    const model = runs({ workspacePath });
    try {
      await model.states.current.refresh();
      return snapshot(model.states.current).value ?? {};
    } finally {
      await runs.dispose();
    }
  }

  function start(script: 'prepare' | 'setup' | 'run', overrides: Record<string, unknown> = {}) {
    const commands = {
      prepare: 'echo prepare',
      setup: 'pnpm install',
      run: 'pnpm dev',
    };
    return wire.client.start({
      workspacePath: WORKSPACE,
      script,
      provenance: 'activation',
      facts: FACTS,
      command: commands[script],
      shellSetup: '',
      ...overrides,
    });
  }

  it('requires callers to supply command and resolved shellSetup', () => {
    const input = {
      workspacePath: WORKSPACE,
      script: 'setup',
      provenance: 'manual',
      facts: FACTS,
      command: 'pnpm install',
      shellSetup: '',
    };
    expect(startScriptRunInputSchema.safeParse(input).success).toBe(true);
    const { command: _command, ...withoutCommand } = input;
    expect(startScriptRunInputSchema.safeParse(withoutCommand).success).toBe(false);
    const { shellSetup: _shellSetup, ...withoutShellSetup } = input;
    expect(startScriptRunInputSchema.safeParse(withoutShellSetup).success).toBe(false);
  });

  it('runs a script to success: spawn spec, run state, exit code, and tail retention', async () => {
    const started = await start('setup', { provenance: 'manual' });
    expect(started.success && started.data.status).toBe('running');

    const spec = spawner.specs[0]!;
    expect(spec.args?.slice(-1)[0]).toBe('pnpm install');
    expect(spec.cwd).toBe(WORKSPACE);
    expect(spec.env).toMatchObject({
      EMDASH_TASK_ID: 'ws-1',
      EMDASH_TASK_NAME: 'feature-x',
      EMDASH_ROOT_PATH: '/repos/app',
    });
    expect(spec.env?.USER_VALUE).toBe('kept');
    expect(spec.env?.ELECTRON_RUN_AS_NODE).toBeUndefined();
    expect(spec.env?.NODE_ENV).toBeUndefined();

    spawner.processes[0]!.emitData('installing...\n');
    spawner.processes[0]!.emitExit({ exitCode: 0, signal: null });

    const settled = await wire.client.wait({ workspacePath: WORKSPACE, script: 'setup' });
    expect(settled.success && settled.data).toMatchObject({
      status: 'succeeded',
      provenance: 'manual',
      exitCode: 0,
      outputTail: 'installing...\n',
    });

    // The tail and the run record survive the exit in the live model.
    const runs = await runsFor(WORKSPACE);
    expect(runs.setup).toMatchObject({ status: 'succeeded', outputTail: 'installing...\n' });
  });

  it('loads the current user env for each newly started script', async () => {
    let userEnv = { PATH: '/tools/old', USER_VALUE: 'before-refresh' };
    const refreshedSpawner = new FakePtySpawner();
    const refreshedRuntime = new ScriptsRuntime({
      spawner: refreshedSpawner,
      userEnv: async () => userEnv,
    });

    try {
      await refreshedRuntime.start({
        workspacePath: WORKSPACE,
        script: 'setup',
        provenance: 'manual',
        facts: FACTS,
        command: 'tool-before-refresh',
        shellSetup: '',
      });

      userEnv = { PATH: '/tools/new', USER_VALUE: 'after-refresh' };
      await refreshedRuntime.start({
        workspacePath: WORKSPACE,
        script: 'prepare',
        provenance: 'manual',
        facts: FACTS,
        command: 'tool-after-refresh',
        shellSetup: '',
      });

      expect(refreshedSpawner.specs[0]!.env).toMatchObject({
        PATH: '/tools/old',
        USER_VALUE: 'before-refresh',
      });
      expect(refreshedSpawner.specs[1]!.env).toMatchObject({
        PATH: '/tools/new',
        USER_VALUE: 'after-refresh',
      });
    } finally {
      refreshedRuntime.dispose();
    }
  });

  it('rejects a second start of a running script; different scripts run concurrently', async () => {
    await start('run');
    const again = await start('run');
    expect(!again.success && again.error.type).toBe('run-in-flight');

    const other = await start('setup');
    expect(other.success).toBe(true);
    expect(spawner.processes).toHaveLength(2);
  });

  it('stop settles the run as cancelled regardless of who started it', async () => {
    await start('run');
    const stopped = await wire.client.stop({ workspacePath: WORKSPACE, script: 'run' });
    expect(stopped.success).toBe(true);

    const settled = await wire.client.wait({ workspacePath: WORKSPACE, script: 'run' });
    expect(settled.success && settled.data.status).toBe('cancelled');
  });

  it('a timed-out run settles as timed-out, distinct from failed and cancelled', async () => {
    await start('prepare', { timeoutMs: 20 });
    const settled = await wire.client.wait({ workspacePath: WORKSPACE, script: 'prepare' });
    expect(settled.success && settled.data.status).toBe('timed-out');
    expect(settled.success && settled.data.message).toContain('Timed out');
  });

  it('a non-zero exit settles as failed with the exit code and message', async () => {
    await start('setup');
    spawner.processes[0]!.emitData('boom\n');
    spawner.processes[0]!.emitExit({ exitCode: 3, signal: null });

    const settled = await wire.client.wait({ workspacePath: WORKSPACE, script: 'setup' });
    expect(settled.success && settled.data).toMatchObject({
      status: 'failed',
      exitCode: 3,
      outputTail: 'boom\n',
    });
    expect(settled.success && settled.data.message).toContain('code 3');
  });

  it('a re-run replaces the previous run record', async () => {
    await start('setup');
    spawner.processes[0]!.emitExit({ exitCode: 1, signal: null });
    await wire.client.wait({ workspacePath: WORKSPACE, script: 'setup' });

    const second = await start('setup', { provenance: 'retry' });
    expect(second.success).toBe(true);
    spawner.processes[1]!.emitExit({ exitCode: 0, signal: null });
    const settled = await wire.client.wait({ workspacePath: WORKSPACE, script: 'setup' });
    expect(settled.success && settled.data).toMatchObject({
      status: 'succeeded',
      provenance: 'retry',
    });

    const runs = await runsFor(WORKSPACE);
    expect(runs.setup?.status).toBe('succeeded');
  });

  it('executes the supplied command', async () => {
    const result = await start('setup', { command: 'echo personal setup' });
    expect(result.success).toBe(true);
    expect(spawner.specs[0]!.args?.slice(-1)[0]).toBe('echo personal setup');
  });

  it('stop and wait on a workspace with no runs return not-found', async () => {
    const stopped = await wire.client.stop({ workspacePath: '/nowhere', script: 'run' });
    expect(!stopped.success && stopped.error.type).toBe('not-found');
    const waited = await wire.client.wait({ workspacePath: '/nowhere', script: 'run' });
    expect(!waited.success && waited.error.type).toBe('not-found');
  });

  it('uses exactly the supplied command and shellSetup without reading config files', async () => {
    const readFile = vi.spyOn(fs, 'readFile');
    try {
      await start('setup', {
        command: 'echo supplied command',
        shellSetup: 'source /supplied/profile',
      });
      expect(spawner.specs[0]!.args?.slice(-1)[0]).toBe(
        'source /supplied/profile\necho supplied command'
      );
      expect(readFile).not.toHaveBeenCalled();
    } finally {
      readFile.mockRestore();
    }
  });
});
