import { describe, expect, it, vi } from 'vitest';
import type { IExecutionContext } from '#primitives/exec/api';
import {
  buildInstallCommandInvocation,
  isPermissionDeniedOutput,
  resolveElevationDecision,
} from './install-execution';

describe('buildInstallCommandInvocation', () => {
  it('builds and previews the exact passwordless sudo argv', () => {
    expect(buildInstallCommandInvocation('npm install -g fake-agent', 'sudo', 'linux')).toEqual({
      command: 'sudo',
      args: ['-n', '-H', '/bin/sh', '-c', 'npm install -g fake-agent'],
      preview: "sudo -n -H /bin/sh -c 'npm install -g fake-agent'",
    });
  });

  it('builds the interactive sudo preview from the same command builder', () => {
    expect(
      buildInstallCommandInvocation('npm install -g fake-agent', 'sudo-interactive', 'linux')
    ).toEqual({
      command: 'sudo',
      args: ['/bin/sh', '-c', 'npm install -g fake-agent'],
      preview: "sudo /bin/sh -c 'npm install -g fake-agent'",
    });
  });
});

describe('isPermissionDeniedOutput', () => {
  it.each(['EACCES', 'eperm', 'Permission denied', 'Operation not permitted'])(
    'recognises %s',
    (output) => {
      expect(isPermissionDeniedOutput(output)).toBe(true);
    }
  );

  it('leaves unrelated failures alone', () => {
    expect(isPermissionDeniedOutput('package not found')).toBe(false);
  });
});

describe('resolveElevationDecision', () => {
  it('keeps never-elevated commands plain without probing sudo', async () => {
    const exec = createFakeExec('passwordless-sudo');

    await expect(resolveElevationDecision('never', false, exec)).resolves.toEqual({
      success: true,
      elevated: false,
      hostElevation: null,
    });
    expect(exec.exec).not.toHaveBeenCalled();
  });

  it.each([
    ['root', false],
    ['passwordless-sudo', true],
  ] as const)('resolves always-elevated commands for %s', async (hostElevation, elevated) => {
    await expect(
      resolveElevationDecision('always', false, createFakeExec(hostElevation))
    ).resolves.toEqual({
      success: true,
      elevated,
      hostElevation,
    });
  });

  it('rejects always-elevated commands when sudo is unavailable', async () => {
    await expect(
      resolveElevationDecision('always', false, createFakeExec('unavailable'))
    ).resolves.toMatchObject({
      success: false,
      hostElevation: 'unavailable',
    });
  });
});

function createFakeExec(hostElevation: 'root' | 'passwordless-sudo' | 'unavailable') {
  return {
    root: '',
    supportsLocalSpawn: true,
    exec: vi.fn(async (command: string, args: string[] = []) => {
      if (command === 'id' && args[0] === '-u') {
        return { stdout: hostElevation === 'root' ? '0\n' : '1000\n', stderr: '' };
      }
      if (command === 'which' && args[0] === 'sudo') {
        if (hostElevation === 'unavailable') throw new Error('not found');
        return { stdout: '/usr/bin/sudo\n', stderr: '' };
      }
      if (command === '/usr/bin/sudo' && args[0] === '-n' && args[1] === 'true') {
        if (hostElevation !== 'passwordless-sudo') throw new Error('sudo unavailable');
        return { stdout: '', stderr: '' };
      }
      throw new Error(`Unexpected exec: ${command} ${args.join(' ')}`);
    }),
    execStreaming: vi.fn(),
    refreshShellEnv: vi.fn(),
    dispose: vi.fn(),
  } satisfies IExecutionContext;
}
