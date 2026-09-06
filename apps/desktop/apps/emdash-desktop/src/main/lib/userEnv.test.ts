import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const spawnSyncMock = vi.fn();

vi.mock('node:child_process', () => ({
  spawnSync: spawnSyncMock,
}));

const {
  ensureUserBinDirsInPath,
  ensureWindowsNpmGlobalBinInPath,
  getUserShellEnv,
  refreshUserEnv,
} = await import('./userEnv');

const originalPath = process.env.PATH;

function mockShellCapture(stdout: string): void {
  spawnSyncMock.mockImplementationOnce(() => {
    return {
      error: undefined,
      status: 0,
      stderr: '',
      stdout,
    };
  });
}

afterEach(() => {
  process.env.PATH = originalPath;
});

describe('ensureUserBinDirsInPath', () => {
  it('prepends existing user bin directories to process PATH', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-user-bin-'));
    process.env.PATH = '/usr/bin';

    const added = ensureUserBinDirsInPath([dir]);

    expect(added).toEqual([dir]);
    expect(process.env.PATH?.split(path.delimiter).slice(0, 2)).toEqual([dir, '/usr/bin']);
  });

  it('does not duplicate existing path entries', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-user-bin-'));
    process.env.PATH = [dir, '/usr/bin'].join(path.delimiter);

    const added = ensureUserBinDirsInPath([dir]);

    expect(added).toEqual([]);
    expect(process.env.PATH).toBe([dir, '/usr/bin'].join(path.delimiter));
  });
});

describe('ensureWindowsNpmGlobalBinInPath', () => {
  it('uses APPDATA case-insensitively when prepending npm global bin', () => {
    const env: NodeJS.ProcessEnv = {
      appdata: 'C:\\Users\\test\\AppData\\Roaming',
      Path: 'C:\\Windows\\System32',
    };

    const added = ensureWindowsNpmGlobalBinInPath(env);

    expect(added).toBe('C:\\Users\\test\\AppData\\Roaming\\npm');
    expect(env.Path).toBe('C:\\Users\\test\\AppData\\Roaming\\npm;C:\\Windows\\System32');
  });
});

describe('refreshUserEnv (runtime env boundary)', () => {
  it('keeps Electron controls in the app process but excludes them from the user snapshot', async () => {
    const previousElectronRunAsNode = process.env.ELECTRON_RUN_AS_NODE;
    const previousNodeEnv = process.env.NODE_ENV;
    process.env.ELECTRON_RUN_AS_NODE = '1';
    process.env.NODE_ENV = 'production';
    spawnSyncMock.mockReset();
    mockShellCapture('PATH=/usr/local/bin:/usr/bin\nUSER_VALUE=kept\n');

    try {
      await refreshUserEnv();

      const probeOptions = spawnSyncMock.mock.calls[0]?.[2] as
        | { env?: NodeJS.ProcessEnv }
        | undefined;
      expect(probeOptions?.env?.ELECTRON_RUN_AS_NODE).toBeUndefined();
      expect(probeOptions?.env?.NODE_ENV).toBeUndefined();
      expect(process.env.ELECTRON_RUN_AS_NODE).toBe('1');
      expect(process.env.NODE_ENV).toBe('production');
      expect(getUserShellEnv()).toMatchObject({ USER_VALUE: 'kept' });
      expect(getUserShellEnv().ELECTRON_RUN_AS_NODE).toBeUndefined();
      expect(getUserShellEnv().NODE_ENV).toBeUndefined();
    } finally {
      if (previousElectronRunAsNode === undefined) delete process.env.ELECTRON_RUN_AS_NODE;
      else process.env.ELECTRON_RUN_AS_NODE = previousElectronRunAsNode;
      if (previousNodeEnv === undefined) delete process.env.NODE_ENV;
      else process.env.NODE_ENV = previousNodeEnv;
    }
  });
});

describe('refreshUserEnv (AppImage env scrub)', () => {
  const SCRUBBED_KEYS = [
    'APPIMAGE',
    'APPDIR',
    'ARGV0',
    'OWD',
    'CHROME_DESKTOP',
    'GSETTINGS_SCHEMA_DIR',
  ] as const;
  const PATH_LIKE_KEYS = ['PATH', 'LD_LIBRARY_PATH', 'XDG_DATA_DIRS'] as const;
  const savedEnv: Partial<
    Record<(typeof SCRUBBED_KEYS)[number] | (typeof PATH_LIKE_KEYS)[number], string | undefined>
  > = {};

  beforeEach(() => {
    spawnSyncMock.mockReset();
    mockShellCapture('');
    for (const key of [...SCRUBBED_KEYS, ...PATH_LIKE_KEYS]) {
      savedEnv[key] = process.env[key];
    }
  });

  afterEach(() => {
    for (const [key, value] of Object.entries(savedEnv)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });

  it('strips AppImage runtime vars and /tmp/.mount_* path entries from the probe shell env and final PATH', async () => {
    spawnSyncMock.mockReset();
    mockShellCapture('PATH=/usr/local/bin:/usr/bin\n');
    process.env.APPIMAGE = '/home/user/emdash.AppImage';
    process.env.APPDIR = '/tmp/.mount_emdashTest';
    process.env.ARGV0 = '/home/user/emdash.AppImage';
    process.env.OWD = '/home/user';
    process.env.CHROME_DESKTOP = 'emdash.desktop';
    process.env.GSETTINGS_SCHEMA_DIR = '/tmp/.mount_emdashTest/usr/share/glib-2.0/schemas';
    process.env.PATH = '/tmp/.mount_emdashTest/usr/bin:/usr/local/bin:/usr/bin';
    process.env.LD_LIBRARY_PATH = '/tmp/.mount_emdashTest/usr/lib:/usr/lib';
    process.env.XDG_DATA_DIRS = '/tmp/.mount_emdashTest/usr/share:/usr/local/share:/usr/share';

    await refreshUserEnv();

    expect(spawnSyncMock).toHaveBeenCalledTimes(1);
    const opts = spawnSyncMock.mock.calls[0]?.[2] as
      | {
          detached?: boolean;
          env?: NodeJS.ProcessEnv;
          stdio?: unknown;
        }
      | undefined;
    expect(opts?.env).toBeDefined();
    expect(opts?.detached).toBe(true);
    expect(opts?.stdio).toEqual(['ignore', 'pipe', 'pipe']);
    const probeEnv = opts!.env!;
    for (const key of SCRUBBED_KEYS) {
      expect(probeEnv[key]).toBeUndefined();
    }
    for (const key of PATH_LIKE_KEYS) {
      expect(probeEnv[key] ?? '').not.toContain('/tmp/.mount_');
    }
    expect(process.env.PATH ?? '').not.toContain('/tmp/.mount_');
    // Helper hint vars must still be set so oh-my-zsh / tmux plugins stay quiet.
    expect(probeEnv.DISABLE_AUTO_UPDATE).toBe('true');
    expect(probeEnv.ZSH_TMUX_AUTOSTART).toBe('false');
  });
});
