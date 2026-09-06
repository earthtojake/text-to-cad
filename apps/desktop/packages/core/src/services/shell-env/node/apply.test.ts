import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { applyShellEnvCapture, ensureUserBinDirsInPath, mergePath } from './apply';
import type { ShellEnvCapture } from './types';

const originalPath = process.env.PATH;

afterEach(() => {
  process.env.PATH = originalPath;
});

describe('mergePath', () => {
  it('keeps shell entries first and appends current-only entries', () => {
    expect(mergePath('/usr/local/bin:/usr/bin', '/app/bin:/usr/bin', 'posix')).toBe(
      '/usr/local/bin:/usr/bin:/app/bin'
    );
  });
});

describe('ensureUserBinDirsInPath', () => {
  it('prepends existing POSIX user bin directories without duplicates', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-user-bin-'));
    process.env.PATH = '/usr/bin';

    expect(ensureUserBinDirsInPath(process.env, [dir], 'posix')).toEqual([dir]);
    expect(process.env.PATH).toBe(`${dir}:/usr/bin`);
    expect(ensureUserBinDirsInPath(process.env, [dir], 'posix')).toEqual([]);
  });
});

describe('applyShellEnvCapture', () => {
  it('applies captured env while preserving protected keys and merging PATH', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-user-bin-'));
    const target: NodeJS.ProcessEnv = {
      NODE_ENV: 'production',
      PATH: '/tmp/.mount_emdash/usr/bin:/usr/bin',
    };
    const capture: ShellEnvCapture = {
      env: {
        NODE_ENV: 'development',
        PATH: '/usr/local/bin:/usr/bin',
        FOO: 'bar',
      },
      source: 'login-shell',
      capturedAt: 1,
    };

    applyShellEnvCapture(
      target,
      capture,
      { preserveKeys: new Set(['NODE_ENV']), userBinDirs: [dir], platform: 'posix' },
      { mergeBaseEnv: { PATH: '/safe/bin:/usr/bin' } }
    );

    expect(target.NODE_ENV).toBe('production');
    expect(target.FOO).toBe('bar');
    expect(target.PATH).toBe(`${dir}:/usr/local/bin:/usr/bin:/safe/bin`);
  });

  it('handles Windows PATH casing case-insensitively', () => {
    const target: NodeJS.ProcessEnv = {
      NODE_ENV: 'production',
      Path: 'C:\\Windows\\System32',
    };
    const capture: ShellEnvCapture = {
      env: {
        NODE_ENV: 'development',
        PATH: 'C:\\Tools',
      },
      source: 'windows',
      capturedAt: 1,
    };

    applyShellEnvCapture(target, capture, {
      preserveKeys: new Set(['NODE_ENV']),
      userBinDirs: [],
      platform: 'windows',
    });

    expect(target.NODE_ENV).toBe('production');
    expect(target.Path).toBe('C:\\Tools;C:\\Windows\\System32');
    expect(target.PATH).toBeUndefined();
  });
});
