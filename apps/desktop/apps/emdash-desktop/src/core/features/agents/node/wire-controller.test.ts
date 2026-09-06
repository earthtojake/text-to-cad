import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { err, ok } from '@emdash/shared';
import { deferred } from '@emdash/shared/testing';
import { createLiveJobReplicaCache, LiveJobCancelledError } from '@emdash/wire/live';
import { encodeTopic, type LiveSource } from '@emdash/wire/rpc';
import { createTestWire } from '@emdash/wire/testing';
import { describe, expect, it, vi } from 'vitest';
import { agentsContract } from '../api';
import { createAgentsWireController } from './wire-controller';

const legacyOperations = vi.hoisted(() => ({
  list: vi.fn(async () => []),
}));

const remoteHost = hostRef('remote', 'ssh-1');

describe('createAgentsWireController', () => {
  it('maps a remote HostRef to the existing SSH connection identity', async () => {
    const hostDependencies = {};
    const client = vi.fn(async () => ok({ hostDependencies }));
    const controller = createAgentsWireController({
      operations: legacyOperations as never,
      runtimes: { client } as never,
    });

    await expect(controller.call('list', { host: remoteHost })).resolves.toEqual(ok([]));

    expect(client).toHaveBeenCalledWith(remoteHost);
    expect(legacyOperations.list).toHaveBeenCalledWith('ssh-1', hostDependencies);
  });

  it('serves static agent metadata without resolving a host runtime', async () => {
    const metadata = [{ id: 'claude', name: 'Claude Code' }];
    const listMetadata = vi.fn(async () => metadata);
    const client = vi.fn(async () => ok({}));
    const controller = createAgentsWireController({
      operations: { listMetadata } as never,
      runtimes: { client } as never,
    });

    await expect(controller.call('listMetadata', undefined)).resolves.toEqual(metadata);

    expect(listMetadata).toHaveBeenCalledOnce();
    expect(client).not.toHaveBeenCalled();
  });

  it('routes login procedures by HostRef', async () => {
    const refreshAuthStatus = vi.fn(async () => ok({ kind: 'unknown' as const }));
    const startLogin = vi.fn(async () => ok(undefined));
    const client = vi.fn(async () => ok({ agentConfig: { refreshAuthStatus, startLogin } }));
    const controller = createAgentsWireController({
      operations: legacyOperations as never,
      runtimes: { client } as never,
    });

    await expect(
      controller.call('refreshAuthStatus', { host: remoteHost, providerId: 'claude' })
    ).resolves.toEqual(ok({ kind: 'unknown' }));
    await expect(
      controller.call('startLogin', {
        host: remoteHost,
        providerId: 'claude',
        methodId: 'browser',
        cols: 137,
        rows: 41,
      })
    ).resolves.toEqual(ok(undefined));

    expect(client).toHaveBeenNthCalledWith(1, remoteHost);
    expect(client).toHaveBeenNthCalledWith(2, remoteHost);
    expect(refreshAuthStatus).toHaveBeenCalledWith({ providerId: 'claude' }, {});
    expect(startLogin).toHaveBeenCalledWith(
      { providerId: 'claude', methodId: 'browser', cols: 137, rows: 41 },
      {}
    );
  });

  it('returns RuntimeResolveError from fallible login procedures', async () => {
    const resolveError = {
      type: 'host-unavailable' as const,
      host: remoteHost,
      reason: 'runtime-unavailable' as const,
      message: 'Remote runtime sessions are not enabled',
    };
    const controller = createAgentsWireController({
      operations: legacyOperations as never,
      runtimes: {
        client: async () => err(resolveError),
      } as never,
    });

    await expect(
      controller.call('startLogin', {
        host: remoteHost,
        providerId: 'claude',
        methodId: 'browser',
      })
    ).resolves.toEqual(err(resolveError));
  });

  it('returns RuntimeResolveError from installation status procedures', async () => {
    const resolveError = {
      type: 'host-unavailable' as const,
      host: remoteHost,
      reason: 'runtime-unavailable' as const,
      message: 'Remote runtime sessions are not enabled',
    };
    const controller = createAgentsWireController({
      operations: legacyOperations as never,
      runtimes: {
        client: async () => err(resolveError),
      } as never,
    });

    await expect(
      controller.call('listAgentInstallationStatus', { host: remoteHost })
    ).resolves.toEqual(err(resolveError));
  });

  it('forwards remote hook status', async () => {
    const status = {
      state: 'installed' as const,
      resolvedRoot: '/remote/home/.claude',
    };
    const hooksStatus = vi.fn(async () => status);
    const client = vi.fn(async () => ok({ agentConfig: { hooksStatus } }));
    const controller = createAgentsWireController({
      operations: legacyOperations as never,
      runtimes: { client } as never,
    });

    await expect(
      controller.call('hooksStatus', { host: remoteHost, providerId: 'claude' })
    ).resolves.toEqual(ok(status));
    expect(hooksStatus).toHaveBeenCalledWith({ providerId: 'claude' }, {});
  });

  it('forwards local hook status', async () => {
    const status = {
      state: 'pending-install' as const,
      resolvedRoot: '/home/user/.claude',
    };
    const hooksStatus = vi.fn(async () => status);
    const client = vi.fn(async () => ok({ agentConfig: { hooksStatus } }));
    const controller = createAgentsWireController({
      operations: legacyOperations as never,
      runtimes: { client } as never,
    });

    await expect(
      controller.call('hooksStatus', { host: LOCAL_HOST_REF, providerId: 'claude' })
    ).resolves.toEqual(ok(status));
    expect(hooksStatus).toHaveBeenCalledWith({ providerId: 'claude' }, {});
  });

  it('passes the active host dependency client to install operations', async () => {
    const hostDependencies = {};
    const status = { id: 'claude' };
    const install = vi.fn(async () => ok(status));
    const client = vi.fn(async () => ok({ hostDependencies }));
    const controller = createAgentsWireController({
      operations: { install } as never,
      runtimes: { client } as never,
    });
    const wire = createTestWire(agentsContract, controller);
    const jobs = createLiveJobReplicaCache(agentsContract.install, wire.client.install);
    const lease = await jobs.start({
      host: remoteHost,
      id: 'claude',
      method: 'curl',
      elevate: true,
    });
    const job = await lease.ready();

    await expect(job.result).resolves.toEqual(status);

    expect(client).toHaveBeenCalledWith(remoteHost);
    expect(install).toHaveBeenCalledWith(
      'claude',
      'ssh-1',
      'curl',
      true,
      hostDependencies,
      expect.objectContaining({
        signal: expect.any(AbortSignal),
        progress: expect.any(Function),
      })
    );

    await lease.release();
    await jobs.dispose();
    await wire.dispose();
  });

  it('forwards live job cancellation to agent install operations', async () => {
    const receivedSignal = deferred<AbortSignal>();
    const install = vi.fn(async (_id, _connectionId, _method, _elevate, _manager, context) => {
      receivedSignal.resolve(context.signal);
      await new Promise<void>((resolve) =>
        context.signal.addEventListener('abort', () => resolve(), { once: true })
      );
      return err({ type: 'command-failed', message: 'cancelled', output: '' });
    });
    const controller = createAgentsWireController({
      operations: { install } as never,
      runtimes: {
        client: async () => ok({ hostDependencies: {} }),
      } as never,
    });
    const wire = createTestWire(agentsContract, controller);
    const jobs = createLiveJobReplicaCache(agentsContract.install, wire.client.install);
    const lease = await jobs.start({ host: remoteHost, id: 'claude' });
    const job = await lease.ready();
    const signal = await receivedSignal.promise;

    await job.cancel();

    expect(signal.aborted).toBe(true);
    await expect(job.result).rejects.toBeInstanceOf(LiveJobCancelledError);
    await lease.release();
    await jobs.dispose();
    await wire.dispose();
  });

  it('forwards login output without copying', async () => {
    const update = {
      generation: 1,
      sequence: 1,
      timestamp: 1,
      data: { baseOffset: 0, append: 'login output' },
    };
    const source = loginSource(update);
    const asLiveSource = vi.fn(() => source);
    const handle = vi.fn(() => ({ asLiveSource }));
    const client = vi.fn(async () => ok({ agentConfig: { loginOutput: { handle } } }));
    const controller = createAgentsWireController({
      operations: legacyOperations as never,
      runtimes: { client } as never,
    });
    const key = { host: remoteHost, providerId: 'claude' };
    const lease = controller.acquireLive(encodeTopic(agentsContract.loginOutput.id, key));

    const output = await lease?.ready();
    const received: unknown[] = [];
    const unsubscribe = await output?.subscribe((next) => received.push(next));

    expect(client).toHaveBeenCalledWith(remoteHost);
    expect(handle).toHaveBeenCalledWith({ providerId: 'claude' });
    expect(asLiveSource).toHaveBeenCalledOnce();
    expect(received[0]).toBe(update);

    unsubscribe?.();
    await lease?.release();
  });
});

function loginSource(update: unknown): LiveSource {
  return {
    snapshot: async () => ({
      generation: 1,
      sequence: 0,
      timestamp: 0,
      data: { baseOffset: 0, text: '', truncated: false },
    }),
    subscribe: (callback) => {
      callback(update as never);
      return () => {};
    },
  };
}
