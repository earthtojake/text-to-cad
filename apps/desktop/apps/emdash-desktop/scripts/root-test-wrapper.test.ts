import { describe, expect, it, vi } from 'vitest';
import { DOCTOR_HINT, runRootTests } from '../../../tooling/scripts/test.mjs';

function spawnReturning(status: number | null) {
  return vi.fn().mockReturnValue({ status });
}

describe('runRootTests', () => {
  it('delegates to the Nx test targets across the workspace', () => {
    const spawn = spawnReturning(0);
    runRootTests({ argv: [], spawn, log: vi.fn() });

    expect(spawn).toHaveBeenCalledWith(
      'pnpm',
      ['exec', 'nx', 'run-many', '-t', 'test', '--all'],
      expect.objectContaining({ stdio: 'inherit' })
    );
  });

  it('forwards extra CLI arguments to nx', () => {
    const spawn = spawnReturning(0);
    runRootTests({ argv: ['--verbose'], spawn, log: vi.fn() });

    expect(spawn).toHaveBeenCalledWith(
      'pnpm',
      ['exec', 'nx', 'run-many', '-t', 'test', '--all', '--verbose'],
      expect.anything()
    );
  });

  it('returns 0 and stays quiet when the suite passes', () => {
    const log = vi.fn();
    expect(runRootTests({ argv: [], spawn: spawnReturning(0), log })).toBe(0);
    expect(log).not.toHaveBeenCalled();
  });

  it('surfaces the doctor referral and the exit code on failure', () => {
    const log = vi.fn();
    expect(runRootTests({ argv: [], spawn: spawnReturning(3), log })).toBe(3);
    expect(log).toHaveBeenCalledWith(expect.stringContaining('pnpm run doctor'));
  });

  it('returns 1 when the runner dies without an exit code', () => {
    const log = vi.fn();
    expect(runRootTests({ argv: [], spawn: spawnReturning(null), log })).toBe(1);
    expect(log).toHaveBeenCalledWith(expect.stringContaining(DOCTOR_HINT));
  });
});
