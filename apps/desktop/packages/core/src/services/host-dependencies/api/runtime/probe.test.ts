import { describe, expect, it, vi } from 'vitest';
import type { IExecutionContext } from '#primitives/exec/api';
import { probeHostElevation } from './probe';

describe('probeHostElevation', () => {
  it('returns null on windows without probing', async () => {
    const exec = createExec();
    await expect(probeHostElevation(exec, 'win32')).resolves.toBeNull();
    expect(exec.exec).not.toHaveBeenCalled();
  });

  it('returns root when the process is root', async () => {
    const exec = createExec({ uid: '0' });
    await expect(probeHostElevation(exec, 'linux')).resolves.toBe('root');
  });

  it('returns passwordless-sudo when passwordless sudo works', async () => {
    const exec = createExec({ uid: '1000', sudo: true });
    await expect(probeHostElevation(exec, 'linux')).resolves.toBe('passwordless-sudo');
  });

  it('returns unavailable when sudo is missing', async () => {
    const exec = createExec({ uid: '1000', sudo: false });
    await expect(probeHostElevation(exec, 'linux')).resolves.toBe('unavailable');
  });

  it('returns unavailable when sudo requires a password', async () => {
    const exec = createExec({ uid: '1000', sudo: 'password' });
    await expect(probeHostElevation(exec, 'darwin')).resolves.toBe('unavailable');
  });
});

function createExec(
  options: { uid?: string; sudo?: boolean | 'password' } = {}
): IExecutionContext {
  return {
    root: '',
    supportsLocalSpawn: true,
    exec: vi.fn(async (command, args = []) => {
      if (command === 'id' && args[0] === '-u') {
        return { stdout: `${options.uid ?? '1000'}\n`, stderr: '' };
      }
      if (command === 'which' && args[0] === 'sudo') {
        if (options.sudo === false) throw new Error('not found');
        return { stdout: '/usr/bin/sudo\n', stderr: '' };
      }
      if (
        (command === '/usr/bin/sudo' || command === 'sudo') &&
        args[0] === '-n' &&
        args[1] === 'true'
      ) {
        if (options.sudo === 'password' || options.sudo === false) {
          throw new Error('sudo: a password is required');
        }
        return { stdout: '', stderr: '' };
      }
      throw new Error(`Unexpected exec: ${command} ${args.join(' ')}`);
    }),
    execStreaming: vi.fn(),
    dispose: vi.fn(),
  };
}
