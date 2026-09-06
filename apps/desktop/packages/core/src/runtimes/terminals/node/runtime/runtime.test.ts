import { createScope } from '@emdash/shared/concurrency';
import { noopLogger } from '@emdash/shared/logger';
import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import type { IExecutionContext } from '#primitives/exec/api';
import { LOCAL_HOST_REF } from '#primitives/host/api';
import {
  hostFileRef,
  parseAbsolute,
  resourceKeyFromFileRef,
  type HostFileRef,
} from '#primitives/path/api';
import type {
  ResolvedShellProfile,
  ShellFallbackEvent,
  TerminalShellAvailability,
  TerminalShellId,
  TerminalShellResolver,
} from '#primitives/terminal-shell/api';
import type { TerminalSessionState } from '#runtimes/terminals/api';
import { FakePtySpawner } from '#services/pty/testing';
import {
  expectNoSessionResidue,
  mapContainer,
  type LeakCheckContainer,
} from '#services/session-lifecycle/node/testing';
import { TerminalsRuntime } from './runtime';

function posixShellProfile(overrides: Partial<ResolvedShellProfile> = {}): ResolvedShellProfile {
  return {
    id: 'zsh',
    resolvedShellId: 'zsh',
    resolvedFromSystem: false,
    executable: '/usr/bin/zsh',
    available: true,
    family: 'posix',
    interactiveArgs: ['-il'],
    commandArgs: ['-lc'],
    ...overrides,
  };
}

class FakeShellResolver implements TerminalShellResolver {
  readonly resolveCalls: TerminalShellId[] = [];

  constructor(
    private readonly options: {
      profile?: ResolvedShellProfile;
      availability?: TerminalShellAvailability[];
      fallback?: ShellFallbackEvent;
      availabilityError?: Error;
    } = {}
  ) {}

  async resolveWithSystemFallback(input: {
    intent: TerminalShellId;
    onFallback?: (event: ShellFallbackEvent) => void;
  }): Promise<ResolvedShellProfile> {
    this.resolveCalls.push(input.intent);
    if (this.options.fallback) input.onFallback?.(this.options.fallback);
    return this.options.profile ?? posixShellProfile();
  }

  async getAvailability(): Promise<TerminalShellAvailability[]> {
    if (this.options.availabilityError) throw this.options.availabilityError;
    return this.options.availability ?? [];
  }
}

describe('TerminalsRuntime', () => {
  it('builds PTY env from the injected user env, not the worker process env', async () => {
    const previousElectronRunAsNode = process.env.ELECTRON_RUN_AS_NODE;
    const previousNodeEnv = process.env.NODE_ENV;
    process.env.ELECTRON_RUN_AS_NODE = '1';
    process.env.NODE_ENV = 'production';

    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals-env-boundary' });
    const runtime = new TerminalsRuntime({
      spawner,
      scope,
      userEnv: async () => ({
        HOME: '/home/test',
        PATH: '/usr/bin',
        SHELL: '/bin/sh',
        USER_VALUE: 'kept',
      }),
    });

    try {
      await runtime.start({
        key: { workspace: testWorkspace(), id: 'terminal-1' },
        spec: { cwd: '/repo', env: { EMDASH_TASK_ID: 'task-1' } },
      });

      expect(spawner.specs[0]!.env).toMatchObject({
        USER_VALUE: 'kept',
        EMDASH_TASK_ID: 'task-1',
      });
      expect(spawner.specs[0]!.env?.ELECTRON_RUN_AS_NODE).toBeUndefined();
      expect(spawner.specs[0]!.env?.NODE_ENV).toBeUndefined();
    } finally {
      runtime.dispose();
      await scope.dispose();
      if (previousElectronRunAsNode === undefined) delete process.env.ELECTRON_RUN_AS_NODE;
      else process.env.ELECTRON_RUN_AS_NODE = previousElectronRunAsNode;
      if (previousNodeEnv === undefined) delete process.env.NODE_ENV;
      else process.env.NODE_ENV = previousNodeEnv;
    }
  });

  it('loads the current user env for each newly started terminal', async () => {
    let userEnv = { PATH: '/tools/old', USER_VALUE: 'before-refresh' };
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals-env-refresh' });
    const runtime = new TerminalsRuntime({
      spawner,
      scope,
      userEnv: async () => userEnv,
    });

    try {
      await runtime.start({
        key: { workspace: testWorkspace(), id: 'terminal-before-refresh' },
        spec: { cwd: '/repo', env: {} },
      });

      userEnv = { PATH: '/tools/new', USER_VALUE: 'after-refresh' };
      await runtime.start({
        key: { workspace: testWorkspace(), id: 'terminal-after-refresh' },
        spec: { cwd: '/repo', env: {} },
      });

      expect(spawner.specs[0]!.env).toMatchObject({
        PATH: '/tools/old',
        USER_VALUE: 'before-refresh',
      });
      expect(spawner.specs[1]!.env).toMatchObject({
        PATH: '/tools/new',
        USER_VALUE: 'after-refresh',
      });
    } finally {
      runtime.dispose();
      await scope.dispose();
    }
  });

  it('retains exited terminals with scrollback instead of evicting them', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const runtime = new TerminalsRuntime({ spawner, userEnv: async () => testUserEnv(), scope });
    const workspace = testWorkspace();
    const key = { workspace, id: 'terminal-1' };
    const sessionKey = `${workspaceKey(workspace)}:terminal-1`;
    await runtime.start({ key, spec: { cwd: '/repo', env: {} } });
    spawner.processes[0]!.emitData('scrollback line\n');

    spawner.processes[0]!.emitExit({ exitCode: 0, signal: null });

    const list = await sessions(runtime);
    expect(list[sessionKey]).toMatchObject({ status: 'exited', exit: { exitCode: 0 } });
    const snapshot = await runtime.outputLog(key).snapshot();
    expect(JSON.stringify(snapshot)).toContain('scrollback line');
    await scope.dispose();
  });

  it('kill evicts the session: list entry removed and no per-key map holds the key', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const runtime = new TerminalsRuntime({ spawner, userEnv: async () => testUserEnv(), scope });
    const workspace = testWorkspace();
    const key = { workspace, id: 'terminal-1' };
    const sessionKey = `${workspaceKey(workspace)}:terminal-1`;
    await runtime.start({ key, spec: { cwd: '/repo', env: {} } });
    spawner.processes[0]!.emitData('output\n');

    const result = await runtime.kill(key);

    expect(result.success).toBe(true);
    expect(spawner.processes[0]!.isExited).toBe(true);
    expect(await sessions(runtime)).toEqual({});
    expectNoSessionResidue(sessionKey, leakContainers(runtime));
    await scope.dispose();
  });

  it('kill also evicts a retained exited terminal', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const runtime = new TerminalsRuntime({ spawner, userEnv: async () => testUserEnv(), scope });
    const workspace = testWorkspace();
    const key = { workspace, id: 'terminal-1' };
    const sessionKey = `${workspaceKey(workspace)}:terminal-1`;
    await runtime.start({ key, spec: { cwd: '/repo', env: {} } });
    spawner.processes[0]!.emitExit({ exitCode: 0, signal: null });
    expect((await sessions(runtime))[sessionKey]).toBeDefined();

    const result = await runtime.kill(key);

    expect(result.success).toBe(true);
    expect(await sessions(runtime)).toEqual({});
    expectNoSessionResidue(sessionKey, leakContainers(runtime));
    await scope.dispose();
  });

  it('kill on an unknown terminal returns not-found', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const runtime = new TerminalsRuntime({ spawner, userEnv: async () => testUserEnv(), scope });

    const result = await runtime.kill({ workspace: testWorkspace(), id: 'missing' });

    expect(result).toMatchObject({ success: false, error: { type: 'not-found' } });
    await scope.dispose();
  });

  it('restarting an exited terminal evicts the old entry, then creates a fresh one', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const runtime = new TerminalsRuntime({ spawner, userEnv: async () => testUserEnv(), scope });
    const workspace = testWorkspace();
    const key = { workspace, id: 'terminal-1' };
    const sessionKey = `${workspaceKey(workspace)}:terminal-1`;
    await runtime.start({ key, spec: { cwd: '/repo', env: {} } });
    spawner.processes[0]!.emitData('first run\n');
    spawner.processes[0]!.emitExit({ exitCode: 0, signal: null });
    const firstLog = await runtime.outputLog(key).snapshot();
    expect(JSON.stringify(firstLog)).toContain('first run');

    await runtime.start({ key, spec: { cwd: '/repo', env: {} } });

    expect(spawner.processes).toHaveLength(2);
    const entry = (await sessions(runtime))[sessionKey];
    expect(entry).toMatchObject({ status: 'running', startCount: 2 });
    // The eviction replaced the log source: scrollback starts fresh.
    const secondLog = await runtime.outputLog(key).snapshot();
    expect(JSON.stringify(secondLog)).not.toContain('first run');
    await scope.dispose();
  });

  it('workspace deactivation (kill per session) evicts every terminal under the workspace', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const runtime = new TerminalsRuntime({ spawner, userEnv: async () => testUserEnv(), scope });
    const workspace = testWorkspace();
    const keys = [
      { workspace, id: 'terminal-1' },
      { workspace, id: 'terminal-2' },
    ];
    for (const key of keys) {
      await runtime.start({ key, spec: { cwd: '/repo', env: {} } });
    }
    spawner.processes[1]!.emitExit({ exitCode: 0, signal: null });

    for (const entry of Object.values(await sessions(runtime))) {
      await runtime.kill(entry.key);
    }

    expect(await sessions(runtime)).toEqual({});
    for (const key of keys) {
      expectNoSessionResidue(`${workspaceKey(workspace)}:${key.id}`, leakContainers(runtime));
    }
    await scope.dispose();
  });

  it('kills detached interactive terminals after the configured grace period', async () => {
    const clock = createManualClock(0);
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const runtime = new TerminalsRuntime({
      spawner,
      userEnv: async () => testUserEnv(),
      scope,
      clock,
      lifecycle: {
        terminal: { kind: 'while-attached', graceMs: 1_000 },
        sweepIntervalMs: 100,
      },
    });
    const workspace = testWorkspace();
    const key = { workspace, id: 'terminal-1' };
    const sessionKey = `${workspaceKey(workspace)}:terminal-1`;
    await runtime.start({ key, spec: { cwd: '/repo', env: {} } });
    const unsubscribe = await runtime.outputLog(key).subscribe(() => {});
    unsubscribe();

    await clock.advanceBy(1_200);

    expect(spawner.processes[0]!.isExited).toBe(true);
    // Sweeper deactivation is a full evict, not just a kill.
    expect(await sessions(runtime)).toEqual({});
    expectNoSessionResidue(sessionKey, leakContainers(runtime));
    await scope.dispose();
  });

  it('killTmuxSessions calls killTmuxSession for each session name', async () => {
    const exec = fakeExec();
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const runtime = new TerminalsRuntime({
      spawner,
      userEnv: async () => testUserEnv(),
      exec,
      scope,
    });

    const result = await runtime.killTmuxSessions({
      sessionNames: ['emdash-session1', 'emdash-session2'],
    });

    expect(result).toEqual({ success: true, data: undefined });
    expect(exec.exec).toHaveBeenCalledTimes(2);
    expect(exec.exec).toHaveBeenCalledWith('tmux', ['kill-session', '-t', 'emdash-session1']);
    expect(exec.exec).toHaveBeenCalledWith('tmux', ['kill-session', '-t', 'emdash-session2']);
    await scope.dispose();
  });

  it('killTmuxSessions succeeds even when sessions are missing', async () => {
    const exec = fakeExec();
    exec.exec.mockRejectedValue(new Error('no session'));
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const runtime = new TerminalsRuntime({
      spawner,
      userEnv: async () => testUserEnv(),
      exec,
      scope,
    });

    const result = await runtime.killTmuxSessions({
      sessionNames: ['emdash-missing'],
    });

    expect(result).toEqual({ success: true, data: undefined });
    await scope.dispose();
  });

  it('killTmuxSessions returns ok without calling exec when no exec is injected', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const runtime = new TerminalsRuntime({ spawner, userEnv: async () => testUserEnv(), scope });

    const result = await runtime.killTmuxSessions({
      sessionNames: ['emdash-session1'],
    });

    expect(result).toEqual({ success: true, data: undefined });
    await scope.dispose();
  });

  it('resolves shell intent on the runtime host and spawns the resolved shell', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const shellResolver = new FakeShellResolver({
      profile: posixShellProfile({ executable: '/opt/homebrew/bin/zsh' }),
    });
    const runtime = new TerminalsRuntime({
      spawner,
      userEnv: async () => testUserEnv(),
      scope,
      shellResolver,
    });
    const workspace = testWorkspace();

    await runtime.start({
      key: { workspace, id: 'terminal-1' },
      spec: { cwd: '/repo', env: {}, shellIntent: 'zsh' },
    });

    expect(shellResolver.resolveCalls).toEqual(['zsh']);
    expect(spawner.specs[0]!.command).toBe('/opt/homebrew/bin/zsh');
    expect(spawner.specs[0]!.args).toEqual(['-il']);
    await scope.dispose();
  });

  it('does not consult the shell resolver when no intent is provided', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const shellResolver = new FakeShellResolver();
    const runtime = new TerminalsRuntime({
      spawner,
      userEnv: async () => testUserEnv(),
      scope,
      shellResolver,
    });
    const workspace = testWorkspace();

    await runtime.start({
      key: { workspace, id: 'terminal-1' },
      spec: { cwd: '/repo', env: {} },
    });

    expect(shellResolver.resolveCalls).toEqual([]);
    await scope.dispose();
  });

  it('logs a fallback when the requested shell is unavailable on the host', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const warn = vi.fn();
    const shellResolver = new FakeShellResolver({
      profile: posixShellProfile({ id: 'target-default', resolvedFromSystem: true }),
      fallback: { shell: 'fish', message: 'fish is not available on this host' },
    });
    const runtime = new TerminalsRuntime({
      spawner,
      userEnv: async () => testUserEnv(),
      scope,
      shellResolver,
      logger: { ...noopLogger, warn },
    });
    const workspace = testWorkspace();

    await runtime.start({
      key: { workspace, id: 'terminal-1' },
      spec: { cwd: '/repo', env: {}, shellIntent: 'fish' },
    });

    expect(warn).toHaveBeenCalledWith(
      'terminals: falling back to system shell',
      expect.objectContaining({ terminalId: 'terminal-1', shell: 'fish' })
    );
    await scope.dispose();
  });

  it('returns host shell availability from the injected resolver', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const availability: TerminalShellAvailability[] = [
      { id: 'system', label: 'zsh', isSystemDefault: true, available: true },
      { id: 'bash', label: 'bash', isSystemDefault: false, available: true },
    ];
    const runtime = new TerminalsRuntime({
      spawner,
      userEnv: async () => testUserEnv(),
      scope,
      shellResolver: new FakeShellResolver({ availability }),
    });

    await expect(runtime.getShellAvailability()).resolves.toEqual({
      success: true,
      data: availability,
    });
    await scope.dispose();
  });

  it('fails shell availability when no resolver is configured', async () => {
    const spawner = new FakePtySpawner();
    const scope = createScope({ label: 'test-terminals' });
    const runtime = new TerminalsRuntime({ spawner, userEnv: async () => testUserEnv(), scope });

    await expect(runtime.getShellAvailability()).resolves.toMatchObject({
      success: false,
      error: { type: 'shell-availability-failed' },
    });
    await scope.dispose();
  });
});

function testWorkspace(): HostFileRef {
  return hostFileRef(LOCAL_HOST_REF, parseAbsoluteWorkspace('/repo'));
}

function parseAbsoluteWorkspace(path: string) {
  const parsed = parseAbsolute(path, { profile: { style: 'posix' } });
  if (!parsed.success) throw new Error(parsed.error.message);
  return parsed.data;
}

function testUserEnv(): Record<string, string> {
  return Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined)
  );
}

function fakeExec(): IExecutionContext & { exec: ReturnType<typeof vi.fn> } {
  return {
    root: '',
    supportsLocalSpawn: true,
    exec: vi.fn().mockResolvedValue({ stdout: '', stderr: '' }),
    execStreaming: vi.fn().mockResolvedValue({ exitCode: 0 }),
    dispose: vi.fn(),
  };
}

type RuntimeInternals = {
  logs: Map<string, unknown>;
  sessionKeys: Map<string, unknown>;
  interactiveConfigs: Map<string, unknown>;
  startCounts: Map<string, unknown>;
  registry: { get(key: string): unknown };
};

/** Reflects over the runtime's per-key maps so the shared leak check can see them. */
function leakContainers(runtime: TerminalsRuntime): LeakCheckContainer[] {
  const internals = runtime as unknown as RuntimeInternals;
  return [
    mapContainer('logs', internals.logs),
    mapContainer('sessionKeys', internals.sessionKeys),
    mapContainer('interactiveConfigs', internals.interactiveConfigs),
    mapContainer('startCounts', internals.startCounts),
    { name: 'ptyRegistry', has: (key) => internals.registry.get(key) !== undefined },
  ];
}

async function sessions(runtime: TerminalsRuntime): Promise<Record<string, TerminalSessionState>> {
  const lease = runtime.sessionsHost.acquireState(undefined, 'list');
  try {
    const source = await lease.ready();
    return (await source.snapshot()).data as Record<string, TerminalSessionState>;
  } finally {
    await lease.release();
  }
}

function workspaceKey(workspace: HostFileRef): string {
  return resourceKeyFromFileRef(workspace);
}
