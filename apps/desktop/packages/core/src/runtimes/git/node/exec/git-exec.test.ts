import { describe, expect, it } from 'vitest';
import type { BoundExec } from '#services/exec/api';
import { bindGitDir, createGitExec, gitEnv } from './git-exec';

describe('gitEnv', () => {
  it('pins git output locale for stable parsing and error classification', () => {
    expect(gitEnv({ LC_ALL: 'de_DE.UTF-8', LANG: 'de_DE.UTF-8' })).toMatchObject({
      LC_ALL: 'C',
      LANG: 'C',
      LANGUAGE: 'C',
      GIT_TERMINAL_PROMPT: '0',
    });
  });

  it('defaults SSH to batch mode without overriding caller configuration', () => {
    expect(gitEnv({ GIT_SSH_COMMAND: undefined }).GIT_SSH_COMMAND).toBe('ssh -o BatchMode=yes');
    expect(gitEnv({ GIT_SSH_COMMAND: 'ssh -F custom-config' }).GIT_SSH_COMMAND).toBe(
      'ssh -F custom-config'
    );
  });

  it('loads the current environment for every git subprocess', async () => {
    let env = { EMDASH_ENV_REVISION: 'before-refresh' };
    const exec = createGitExec({
      cwd: process.cwd(),
      executable: process.execPath,
      env: async () => env,
    });

    const before = await exec.exec(['-p', 'process.env.EMDASH_ENV_REVISION']);
    env = { EMDASH_ENV_REVISION: 'after-refresh' };
    const after = await exec.exec(['-p', 'process.env.EMDASH_ENV_REVISION']);

    expect(before.stdout.trim()).toBe('before-refresh');
    expect(after.stdout.trim()).toBe('after-refresh');
  });
});

describe('bindGitDir', () => {
  it('binds every execution mode to one Git directory', async () => {
    const calls: string[][] = [];
    const makeExec = (cwd: string): BoundExec => ({
      file: 'git',
      cwd,
      async exec(args) {
        calls.push(args);
        return { stdout: '', stderr: '' };
      },
      async execStreaming(args) {
        calls.push(args);
      },
      async execBuffer(args) {
        calls.push(args);
        return { stdout: Buffer.alloc(0), stderr: '' };
      },
      spawn(args) {
        calls.push(args);
        return {} as never;
      },
      withCwd: makeExec,
    });
    const exec = bindGitDir(makeExec('/runtime'), '/repo/.git');

    await exec.exec(['status']);
    await exec.execStreaming(['fetch'], () => {});
    await exec.execBuffer(['cat-file', 'blob', 'HEAD:file']);
    await exec.spawn(['cat-file', '--batch']);
    const moved = exec.withCwd('/other');
    await moved.exec(['branch']);

    expect(calls).toEqual([
      ['--git-dir=/repo/.git', 'status'],
      ['--git-dir=/repo/.git', 'fetch'],
      ['--git-dir=/repo/.git', 'cat-file', 'blob', 'HEAD:file'],
      ['--git-dir=/repo/.git', 'cat-file', '--batch'],
      ['--git-dir=/repo/.git', 'branch'],
    ]);
    expect(moved.cwd).toBe('/other');
  });
});
