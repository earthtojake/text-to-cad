import { hostRef } from '@emdash/core/primitives/host/api';
import type { HostRuntimesClient } from '@emdash/core/services/runtime-broker/api';
import { describe, expect, it, vi } from 'vitest';
import type { HostService } from '@core/services/hosts/node';
import { WorkspaceServerProvisionError } from '@core/services/hosts/node/workspace-server';
import { createDesktopRuntimeBroker } from './runtime-broker';

describe('desktop runtime broker remote sessions', () => {
  it('routes remote client resolution through the host service', async () => {
    const runtimeClient = { files: { getHomeDir: vi.fn() } } as unknown as HostRuntimesClient;
    const client = vi.fn(async () => ({ client: runtimeClient }));
    const hosts = {
      client,
    } as unknown as HostService;
    const broker = createDesktopRuntimeBroker({} as never, hosts);
    const host = hostRef('remote', 'ssh-1');

    const [firstResult, secondResult] = await Promise.all([
      broker.client(host),
      broker.client(host),
    ]);
    expect(firstResult.success).toBe(true);
    expect(secondResult.success).toBe(true);
    if (!firstResult.success || !secondResult.success) {
      throw new Error('Expected remote Host runtimes');
    }
    expect(secondResult.data).toBe(firstResult.data);
    await firstResult.data.files.getHomeDir(undefined);
    expect(runtimeClient.files.getHomeDir).toHaveBeenCalledOnce();
    expect(client).toHaveBeenCalledTimes(2);
    expect(client).toHaveBeenCalledWith('ssh-1');
  });

  it('reports unavailable when a remote runtime connection fails', async () => {
    const broker = createDesktopRuntimeBroker(
      {} as never,
      {
        client: async () => {
          throw new Error('connection failed');
        },
      } as never
    );

    await expect(broker.client(hostRef('remote', 'ssh-1'))).resolves.toMatchObject({
      success: false,
      error: {
        type: 'host-unavailable',
        reason: 'runtime-unavailable',
        message: 'connection failed',
      },
    });
  });

  it('preserves typed Host provisioning reasons for existing runtime callers', async () => {
    const broker = createDesktopRuntimeBroker(
      {} as never,
      {
        client: async () => {
          throw new WorkspaceServerProvisionError('install-failed', 'raw lower-level message');
        },
      } as never
    );

    await expect(broker.client(hostRef('remote', 'ssh-1'))).resolves.toMatchObject({
      success: false,
      error: {
        type: 'host-unavailable',
        reason: 'install-failed',
        message: 'Host runtime installation failed',
      },
    });
  });
});
