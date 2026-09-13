import { createTestWire } from '@emdash/wire/testing';
import { describe, expect, it } from 'vitest';
import { userShellEnvContract } from '#services/shell-env/api';
import { createUserShellEnvController } from './controller';

describe('createUserShellEnvController', () => {
  it('reads the current parent-owned snapshot on every request', async () => {
    let userEnv = { PATH: '/tools/old', USER_VALUE: 'before-refresh' };
    const wire = createTestWire(
      userShellEnvContract,
      createUserShellEnvController(async () => userEnv)
    );

    try {
      await expect(wire.client.get()).resolves.toEqual(userEnv);

      userEnv = { PATH: '/tools/new', USER_VALUE: 'after-refresh' };

      await expect(wire.client.get()).resolves.toEqual(userEnv);
    } finally {
      wire.dispose();
    }
  });

  it('waits for an in-flight refresh before responding', async () => {
    let release!: () => void;
    const refresh = new Promise<void>((resolve) => {
      release = resolve;
    });
    const wire = createTestWire(
      userShellEnvContract,
      createUserShellEnvController(async () => {
        await refresh;
        return { PATH: '/tools/new', USER_VALUE: 'after-refresh' };
      })
    );

    try {
      const request = wire.client.get();
      release();

      await expect(request).resolves.toEqual({
        PATH: '/tools/new',
        USER_VALUE: 'after-refresh',
      });
    } finally {
      wire.dispose();
    }
  });
});
