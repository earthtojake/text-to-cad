import { describe, expect, it, vi } from 'vitest';
import { NodeExecutionContext } from './node-execution-context';

describe('NodeExecutionContext', () => {
  it('delegates shell env refresh when configured', async () => {
    const refreshShellEnv = vi.fn(async () => {});
    const context = new NodeExecutionContext({ refreshShellEnv });

    await context.refreshShellEnv?.();

    expect(refreshShellEnv).toHaveBeenCalledOnce();
  });

  it('returns the exit code from a streaming command', async () => {
    const context = new NodeExecutionContext();

    const result = await context.execStreaming(
      process.execPath,
      ['-e', "process.stdout.write('ok'); process.exit(7);"],
      () => true
    );

    expect(result).toEqual({ exitCode: 7 });
  });

  it('returns zero for a successful streaming command', async () => {
    const context = new NodeExecutionContext();

    const result = await context.execStreaming(
      process.execPath,
      ['-e', "process.stdout.write('ok');"],
      () => true
    );

    expect(result).toEqual({ exitCode: 0 });
  });

  it('resolves the current environment for every command spawn', async () => {
    let env = { EMDASH_ENV_REVISION: 'before-refresh' };
    const context = new NodeExecutionContext({ env: async () => env });

    const before = await context.exec(process.execPath, ['-p', 'process.env.EMDASH_ENV_REVISION']);
    env = { EMDASH_ENV_REVISION: 'after-refresh' };
    const after = await context.exec(process.execPath, ['-p', 'process.env.EMDASH_ENV_REVISION']);

    expect(before.stdout.trim()).toBe('before-refresh');
    expect(after.stdout.trim()).toBe('after-refresh');
  });
});
