import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { existsSyncMock, spawnMock, userInfoMock } = vi.hoisted(() => ({
  existsSyncMock: vi.fn(),
  spawnMock: vi.fn(),
  userInfoMock: vi.fn(),
}));

vi.mock('node:child_process', () => ({
  spawn: spawnMock,
}));

vi.mock('node:fs', () => ({
  existsSync: existsSyncMock,
  statSync: vi.fn(() => ({ isDirectory: () => false })),
}));

vi.mock('node:os', () => ({
  default: {
    homedir: () => '/home/test',
    userInfo: userInfoMock,
  },
}));

const { createShellEnvManager } = await import('./manager');

type SpawnResult =
  | { readonly status: number; readonly stdout: string; readonly stderr?: string }
  | { readonly error: Error };

const spawnResults: SpawnResult[] = [];

function queueSpawn(result: SpawnResult): void {
  spawnResults.push(result);
}

function createCompletingChild(): EventEmitter & {
  readonly stdout: PassThrough;
  readonly stderr: PassThrough;
  readonly kill: ReturnType<typeof vi.fn>;
  readonly pid: number;
  readonly exitCode: null;
  readonly signalCode: null;
} {
  const child = Object.assign(new EventEmitter(), {
    stdout: new PassThrough(),
    stderr: new PassThrough(),
    kill: vi.fn(),
    pid: 42_425,
    exitCode: null,
    signalCode: null,
  });
  const result = spawnResults.shift();
  queueMicrotask(() => {
    if (!result) {
      child.emit('error', new Error('No queued shell result'));
      return;
    }
    if ('error' in result) {
      child.emit('error', result.error);
      return;
    }
    child.stdout.write(result.stdout);
    if (result.stderr) child.stderr.write(result.stderr);
    child.emit('close', result.status);
  });
  return child;
}

beforeEach(() => {
  spawnResults.length = 0;
  spawnMock.mockReset();
  spawnMock.mockImplementation(createCompletingChild);
  existsSyncMock.mockReset();
  userInfoMock.mockReset();
  userInfoMock.mockReturnValue({ shell: '/bin/bash' });
  existsSyncMock.mockReturnValue(true);
});

describe('createShellEnvManager', () => {
  it('starts and awaits the initial capture from current()', async () => {
    queueSpawn({
      status: 0,
      stdout: 'PATH=/shell/bin\nFOO=initial\n',
    });
    const manager = createShellEnvManager({
      target: { PATH: '/worker/bin' },
      baseEnvForProbe: () => ({ SHELL: '/bin/bash', PATH: '/worker/bin' }),
    });

    await expect(manager.current()).resolves.toMatchObject({
      FOO: 'initial',
      PATH: '/shell/bin:/worker/bin',
    });
    expect(spawnMock).toHaveBeenCalledOnce();
  });

  it('coalesces concurrent refreshes', async () => {
    queueSpawn({
      status: 0,
      stdout: 'PATH=/usr/local/bin\nFOO=bar\n',
    });
    const target: NodeJS.ProcessEnv = { PATH: '/usr/bin' };
    const manager = createShellEnvManager({
      target,
      baseEnvForProbe: () => ({ SHELL: '/bin/bash', PATH: '/usr/bin' }),
    });

    await Promise.all([manager.refresh(), manager.refresh()]);

    expect(spawnMock).toHaveBeenCalledTimes(1);
    expect(target.FOO).toBe('bar');
    expect(target.PATH).toBe('/usr/local/bin:/usr/bin');
    expect(manager.getUserShellEnv()).toMatchObject({
      FOO: 'bar',
      PATH: '/usr/local/bin:/usr/bin',
    });
  });

  it('keeps runtime controls in the host env but excludes them from the user snapshot', async () => {
    queueSpawn({
      status: 0,
      stdout: 'PATH=/shell/bin\nUSER_VALUE=kept\n',
    });
    const target: NodeJS.ProcessEnv = {
      PATH: '/worker/bin',
      NODE_ENV: 'production',
      ELECTRON_RUN_AS_NODE: '1',
    };
    const manager = createShellEnvManager({ target });

    await manager.refresh();

    expect(target.NODE_ENV).toBe('production');
    expect(target.ELECTRON_RUN_AS_NODE).toBe('1');
    expect(manager.getUserShellEnv()).toEqual({
      PATH: '/shell/bin:/worker/bin',
      USER_VALUE: 'kept',
    });
  });

  it('preserves a runtime-named variable when the login shell explicitly exports it', async () => {
    queueSpawn({
      status: 0,
      stdout: 'PATH=/shell/bin\nNODE_ENV=development\n',
    });
    const target: NodeJS.ProcessEnv = { PATH: '/worker/bin', NODE_ENV: 'production' };
    const manager = createShellEnvManager({ target });

    await manager.refresh();

    expect(target.NODE_ENV).toBe('production');
    expect(manager.getUserShellEnv().NODE_ENV).toBe('development');
  });

  it('retains the last snapshot until an in-flight refresh publishes atomically', async () => {
    queueSpawn({
      status: 0,
      stdout: 'PATH=/tools/old\nUSER_VALUE=before-refresh\n',
    });
    const manager = createShellEnvManager({
      target: { PATH: '/worker/bin' },
      baseEnvForProbe: () => ({ SHELL: '/bin/bash', PATH: '/worker/bin' }),
    });
    await manager.refresh();

    queueSpawn({
      status: 0,
      stdout: 'PATH=/tools/new\nUSER_VALUE=after-refresh\n',
    });
    const refresh = manager.refresh();

    expect(manager.getUserShellEnv()).toMatchObject({
      PATH: '/tools/old:/worker/bin',
      USER_VALUE: 'before-refresh',
    });
    await expect(manager.current()).resolves.toMatchObject({
      PATH: '/tools/new:/worker/bin',
      USER_VALUE: 'after-refresh',
    });
    await refresh;
  });

  it('logs and keeps the existing env when capture fails', async () => {
    const warn = vi.fn();
    queueSpawn({ error: new Error('spawn failed') });
    const target: NodeJS.ProcessEnv = { PATH: '/usr/bin' };
    const manager = createShellEnvManager({
      target,
      baseEnvForProbe: () => ({ SHELL: '/bin/bash', PATH: '/probe/bin' }),
      logger: { warn },
    });

    await expect(manager.refresh()).resolves.toBeUndefined();

    expect(warn).toHaveBeenCalledWith(
      '[shell-env] Failed to resolve login-shell env',
      expect.objectContaining({ shell: '/bin/bash', error: 'spawn failed' })
    );
    expect(target).toEqual({ PATH: '/usr/bin' });
    await expect(manager.current()).resolves.toEqual({
      PATH: '/probe/bin',
      SHELL: '/bin/bash',
    });
  });

  it('retains the last known-good snapshot when a later refresh fails', async () => {
    queueSpawn({
      status: 0,
      stdout: 'PATH=/tools/good\nUSER_VALUE=known-good\n',
    });
    const manager = createShellEnvManager({
      target: { PATH: '/worker/bin' },
      baseEnvForProbe: () => ({ SHELL: '/bin/bash', PATH: '/worker/bin' }),
    });
    await manager.refresh();

    queueSpawn({ error: new Error('refresh failed') });
    await manager.refresh();

    await expect(manager.current()).resolves.toMatchObject({
      PATH: '/tools/good:/worker/bin',
      USER_VALUE: 'known-good',
    });
  });
});
