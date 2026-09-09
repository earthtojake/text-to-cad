import { createScope } from '@emdash/shared/concurrency';
import type { Logger } from '@emdash/shared/logger';
import { describe, expect, it, vi } from 'vitest';
import type { AppDb } from '@core/services/app-db/node/db';
import type { SshCredentialService } from '@core/services/ssh/node/credentials/ssh-credential-service';
import { SshConnectionManager } from '@core/services/ssh/node/lifecycle/ssh-connection-manager';
import { createSshService } from './ssh-service-factory';

describe('createSshService', () => {
  it('owns a child scope and disconnects the manager exactly once', async () => {
    const scope = createScope({ label: 'ssh-factory-test' });
    const disconnectAll = vi
      .spyOn(SshConnectionManager.prototype, 'disconnectAll')
      .mockResolvedValue();
    const credentials = {
      getPassword: vi.fn(async () => null),
      getPassphrase: vi.fn(async () => null),
      storePassword: vi.fn(),
      storePassphrase: vi.fn(),
      deleteAllCredentials: vi.fn(),
    } as unknown as SshCredentialService;
    const logger = {
      debug: vi.fn(),
      info: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    } as unknown as Logger;

    const handle = createSshService({
      scope,
      db: {} as AppDb,
      credentials,
      logger,
      telemetry: { capture: vi.fn() },
    });

    expect(handle.ssh).toBeDefined();
    expect(handle.machines).toBeDefined();
    // The handle exposes the primitive interface; narrow to the concrete class
    // to drive the implementation-private createConnection path.
    const manager = handle.manager;
    if (!(manager instanceof SshConnectionManager)) {
      throw new Error('expected the concrete SshConnectionManager');
    }
    await expect(
      manager.createConnection('ssh-1', async () => {
        throw new Error('Resolver failed');
      })
    ).rejects.toThrow('Resolver failed');
    expect(handle.connections.snapshot()['ssh-1']).toEqual({
      state: 'connecting',
      health: { status: 'ok' },
    });

    await handle.dispose();
    await handle.dispose();
    await scope.dispose();

    expect(disconnectAll).toHaveBeenCalledTimes(1);
  });
});
