import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
}));

vi.mock('node:os', () => ({
  default: {
    userInfo: userInfoMock,
  },
}));

const { captureShellEnv, parseEnvOutput, resolveLoginShell } = await import('./capture');

type FakeChild = EventEmitter & {
  readonly pid: number;
  readonly stdout: PassThrough;
  readonly stderr: PassThrough;
  readonly kill: ReturnType<typeof vi.fn>;
  exitCode: number | null;
  signalCode: NodeJS.Signals | null;
};

function createChild(pid = 42_424): FakeChild {
  return Object.assign(new EventEmitter(), {
    pid,
    stdout: new PassThrough(),
    stderr: new PassThrough(),
    kill: vi.fn(),
    exitCode: null,
    signalCode: null,
  });
}

beforeEach(() => {
  existsSyncMock.mockReset();
  spawnMock.mockReset();
  userInfoMock.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('parseEnvOutput', () => {
  it('parses shell env output and ignores invalid keys', () => {
    expect(parseEnvOutput('PATH=/usr/bin\nBAD-KEY=value\nFOO=a=b\n')).toEqual({
      PATH: '/usr/bin',
      FOO: 'a=b',
    });
  });
});

describe('resolveLoginShell', () => {
  it('falls back from SHELL to the account shell', () => {
    userInfoMock.mockReturnValueOnce({ shell: '/bin/fish' });
    existsSyncMock.mockImplementation((candidate) => candidate === '/bin/fish');

    expect(resolveLoginShell({ SHELL: '/missing' })).toBe('/bin/fish');
  });
});

describe('captureShellEnv', () => {
  it('captures login-shell env asynchronously with guard variables', async () => {
    const child = createChild();
    userInfoMock.mockReturnValueOnce({ shell: '/bin/bash' });
    existsSyncMock.mockReturnValue(true);
    spawnMock.mockReturnValueOnce(child);

    const resultPromise = captureShellEnv({
      baseEnv: { SHELL: '/bin/bash', PATH: '/usr/bin' },
      now: () => 123,
    });
    child.stdout.write(
      'PATH=/usr/local/bin:/usr/bin\nFOO=bar\nDISABLE_AUTO_UPDATE=true\n' +
        'ZSH_TMUX_AUTOSTART=false\nZSH_TMUX_AUTOSTARTED=true\n'
    );
    child.emit('close', 0);

    await expect(resultPromise).resolves.toEqual({
      success: true,
      data: {
        env: { PATH: '/usr/local/bin:/usr/bin', FOO: 'bar' },
        source: 'login-shell',
        capturedAt: 123,
      },
    });
    expect(spawnMock).toHaveBeenCalledWith(
      '/bin/bash',
      ['-ilc', 'env'],
      expect.objectContaining({
        detached: true,
        env: expect.objectContaining({
          DISABLE_AUTO_UPDATE: 'true',
          ZSH_TMUX_AUTOSTART: 'false',
          ZSH_TMUX_AUTOSTARTED: 'true',
        }),
        stdio: ['ignore', 'pipe', 'pipe'],
      })
    );
  });

  it('returns a capture error when the shell exits non-zero', async () => {
    const child = createChild();
    userInfoMock.mockReturnValueOnce({ shell: '/bin/bash' });
    existsSyncMock.mockReturnValue(true);
    spawnMock.mockReturnValueOnce(child);

    const resultPromise = captureShellEnv({ baseEnv: { SHELL: '/bin/bash' } });
    child.stderr.write('broken rc file');
    child.emit('close', 2);

    await expect(resultPromise).resolves.toEqual({
      success: false,
      error: {
        type: 'capture-failed',
        shell: '/bin/bash',
        message: 'broken rc file',
      },
    });
  });

  it('times out without blocking and escalates termination for the process group', async () => {
    vi.useFakeTimers();
    const child = createChild();
    const processKill = vi.spyOn(process, 'kill').mockReturnValue(true);
    userInfoMock.mockReturnValueOnce({ shell: '/bin/bash' });
    existsSyncMock.mockReturnValue(true);
    spawnMock.mockReturnValueOnce(child);

    const resultPromise = captureShellEnv({
      baseEnv: { SHELL: '/bin/bash' },
      timeoutMs: 50,
    });
    let settled = false;
    void resultPromise.then(() => {
      settled = true;
    });

    await vi.advanceTimersByTimeAsync(49);
    expect(settled).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    await expect(resultPromise).resolves.toEqual({
      success: false,
      error: {
        type: 'capture-failed',
        shell: '/bin/bash',
        message: 'shell env capture timed out after 50ms',
      },
    });
    expect(processKill).toHaveBeenCalledWith(-child.pid, 'SIGTERM');

    await vi.advanceTimersByTimeAsync(250);
    expect(processKill).toHaveBeenCalledWith(-child.pid, 'SIGKILL');
  });

  it('lets the event loop advance while a shell probe is pending', async () => {
    const child = createChild();
    userInfoMock.mockReturnValueOnce({ shell: '/bin/bash' });
    existsSyncMock.mockReturnValue(true);
    spawnMock.mockReturnValueOnce(child);

    const resultPromise = captureShellEnv({
      baseEnv: { SHELL: '/bin/bash' },
      timeoutMs: 1_000,
    });
    let settled = false;
    void resultPromise.then(() => {
      settled = true;
    });

    await new Promise<void>((resolve) => setImmediate(resolve));
    expect(settled).toBe(false);

    child.stdout.write('PATH=/usr/bin\n');
    child.emit('close', 0);
    await expect(resultPromise).resolves.toMatchObject({ success: true });
  });

  it('bounds captured output and terminates an overflowing probe', async () => {
    const child = createChild();
    const processKill = vi.spyOn(process, 'kill').mockReturnValue(true);
    userInfoMock.mockReturnValueOnce({ shell: '/bin/bash' });
    existsSyncMock.mockReturnValue(true);
    spawnMock.mockReturnValueOnce(child);

    const resultPromise = captureShellEnv({ baseEnv: { SHELL: '/bin/bash' } });
    child.stdout.write('x'.repeat(1024 * 1024 + 1));

    await expect(resultPromise).resolves.toEqual({
      success: false,
      error: {
        type: 'capture-failed',
        shell: '/bin/bash',
        message: 'shell env capture stdout exceeded maxBuffer',
      },
    });
    expect(processKill).toHaveBeenCalledWith(-child.pid, 'SIGTERM');
  });
});
