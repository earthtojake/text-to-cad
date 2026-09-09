import { describe, expect, it } from 'vitest';
import { createDependencyManagerResolver } from './dependency-managers';

describe('getDependencyManager', () => {
  it('returns a typed host-unavailable error for remote dependencies', async () => {
    const getDependencyManager = createDependencyManagerResolver({} as never);
    await expect(getDependencyManager('ssh-1')).resolves.toEqual({
      success: false,
      error: {
        type: 'host-unavailable',
        host: { type: 'remote', id: 'ssh-1' },
        reason: 'runtime-unavailable',
        message: 'Remote host dependencies require the workspace server.',
      },
    });
  });
});
