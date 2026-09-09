import { describe, expect, it } from 'vitest';
import { terminalsContract } from './contract';
import { startTerminalSpecSchema } from './schemas';

describe('startTerminalSpecSchema shell intent', () => {
  it('accepts a spec carrying only shell intent', () => {
    const parsed = startTerminalSpecSchema.parse({
      cwd: '/repo',
      env: {},
      shellIntent: 'zsh',
    });

    expect(parsed.shellIntent).toBe('zsh');
  });

  it('treats a missing shell intent as target-default', () => {
    const parsed = startTerminalSpecSchema.parse({ cwd: '/repo', env: {} });

    expect(parsed.shellIntent).toBeUndefined();
  });

  it('rejects an unknown shell intent', () => {
    const result = startTerminalSpecSchema.safeParse({
      cwd: '/repo',
      env: {},
      shellIntent: 'nushell',
    });

    expect(result.success).toBe(false);
  });

  it('exposes a host-agnostic getShellAvailability procedure', () => {
    expect(terminalsContract.getShellAvailability).toBeDefined();
    expect(terminalsContract.getShellAvailability.input.safeParse(undefined).success).toBe(true);
  });
});
