import { err, ok } from '@emdash/shared';
import { deferred } from '@emdash/shared/testing';
import { WireError, type Connection } from '@emdash/wire/rpc';
import { describe, expect, it, vi } from 'vitest';
import { LOCAL_HOST_REF, hostRef } from '../../../primitives/host/api';
import {
  RuntimeBroker,
  type HostRuntimesClient,
  type RuntimeSessionResolution,
} from './runtime-broker';

describe('RuntimeBroker', () => {
  it('delegates direct client resolution without changing client identity', async () => {
    const client = {} as HostRuntimesClient;
    const resolve = vi.fn(() => ok(client));
    const broker = new RuntimeBroker({ resolve });

    const first = await broker.client(LOCAL_HOST_REF);
    const second = await broker.client(LOCAL_HOST_REF);

    expect(first.success).toBe(true);
    expect(second.success).toBe(true);
    if (!first.success || !second.success) throw new Error('Expected local Host runtimes');
    expect(second.data).toBe(first.data);
    expect(resolve).toHaveBeenCalledTimes(2);
  });

  it('keeps an acquired client bound to the latest resolved Host runtime', async () => {
    const host = hostRef('remote', 'remote-1');
    const firstCall = vi.fn(async () => 'first');
    const secondCall = vi.fn(async () => 'second');
    let current = {
      client: {} as HostRuntimesClient,
      connection: connection(vi.fn(), firstCall),
    };
    const broker = new RuntimeBroker({ resolve: () => ok(current) });

    const retained = await broker.client(host);
    expect(retained.success).toBe(true);
    if (!retained.success) throw new Error('Expected the first Host runtime');
    await expect(retained.data.files.getHomeDir(undefined)).resolves.toBe('first');

    current = {
      client: {} as HostRuntimesClient,
      connection: connection(vi.fn(), secondCall),
    };
    const recovered = await broker.client(host);
    expect(recovered.success).toBe(true);
    if (!recovered.success) throw new Error('Expected the recovered Host runtime');

    expect(recovered.data).toBe(retained.data);
    await expect(retained.data.files.getHomeDir(undefined)).resolves.toBe('second');
    expect(firstCall).toHaveBeenCalledOnce();
    expect(secondCall).toHaveBeenCalledOnce();
  });

  it('reattaches retained live handles to a recovered Host connection', async () => {
    const host = hostRef('remote', 'remote-1');
    const firstDetach = vi.fn();
    const secondDetach = vi.fn();
    const firstConnection = connection(vi.fn(async () => firstDetach));
    const secondAttach = vi.fn(async () => secondDetach);
    const secondConnection = connection(secondAttach);
    let current = {
      client: {} as HostRuntimesClient,
      connection: firstConnection,
    };
    const broker = new RuntimeBroker({ resolve: () => ok(current) });
    const retained = await broker.client(host);
    expect(retained.success).toBe(true);
    if (!retained.success) throw new Error('Expected the first Host runtime');
    const reattached = vi.fn();
    const handle = retained.data.files.tree.model.state({} as never, 'tree');
    const detach = await handle.attach(vi.fn(), { onReattach: reattached });

    current = {
      client: {} as HostRuntimesClient,
      connection: secondConnection,
    };
    await broker.client(host);

    await vi.waitFor(() => expect(secondAttach).toHaveBeenCalledOnce());
    expect(firstDetach).toHaveBeenCalledOnce();
    expect(reattached).toHaveBeenCalledOnce();

    detach();
    expect(secondDetach).toHaveBeenCalledOnce();
  });

  it('moves a superseded in-flight live attachment to the recovered connection', async () => {
    const host = hostRef('remote', 'remote-1');
    const firstAttach = deferred<() => void>();
    const secondDetach = vi.fn();
    const secondAttach = vi.fn(async () => secondDetach);
    let current = {
      client: {} as HostRuntimesClient,
      connection: connection(() => firstAttach.promise),
    };
    const broker = new RuntimeBroker({ resolve: () => ok(current) });
    const retained = await broker.client(host);
    expect(retained.success).toBe(true);
    if (!retained.success) throw new Error('Expected the first Host runtime');
    const handle = retained.data.files.tree.model.state({} as never, 'tree');
    const pendingAttach = handle.attach(vi.fn());

    current = {
      client: {} as HostRuntimesClient,
      connection: connection(secondAttach),
    };
    await broker.client(host);
    firstAttach.reject(new WireError('DISCONNECTED', 'Old Host connection disposed'));

    const detach = await pendingAttach;
    expect(secondAttach).toHaveBeenCalledOnce();

    detach();
    expect(secondDetach).toHaveBeenCalledOnce();
  });

  it('disposes retained attachments when an incompatible binding replaces them', async () => {
    const host = hostRef('remote', 'remote-1');
    const detach = vi.fn();
    const broker = new RuntimeBroker({
      resolve: () =>
        ok({
          client: {} as HostRuntimesClient,
          connection: connection(vi.fn(async () => detach)),
        }),
    });
    const retained = await broker.client(host);
    expect(retained.success).toBe(true);
    if (!retained.success) throw new Error('Expected the first Host runtime');
    const handle = retained.data.files.tree.model.state({} as never, 'tree');
    await handle.attach(vi.fn());

    broker.rebind(host, {} as HostRuntimesClient);

    expect(detach).toHaveBeenCalledOnce();
  });

  it('disposes all retained bindings idempotently', async () => {
    const host = hostRef('remote', 'remote-1');
    const detach = vi.fn();
    const broker = new RuntimeBroker({
      resolve: () =>
        ok({
          client: {} as HostRuntimesClient,
          connection: connection(vi.fn(async () => detach)),
        }),
    });
    const retained = await broker.client(host);
    expect(retained.success).toBe(true);
    if (!retained.success) throw new Error('Expected the first Host runtime');
    const handle = retained.data.files.tree.model.state({} as never, 'tree');
    await handle.attach(vi.fn());

    broker.dispose();
    broker.dispose();

    expect(detach).toHaveBeenCalledOnce();
    await expect(handle.attach(vi.fn())).rejects.toMatchObject({ code: 'DISCONNECTED' });
  });

  it('ignores a client resolution superseded by an explicit Host rebind', async () => {
    const host = hostRef('remote', 'remote-1');
    const staleResolution = deferred<RuntimeSessionResolution>();
    const currentCall = vi.fn(async () => 'current');
    const broker = new RuntimeBroker({ resolve: () => staleResolution.promise });

    const stale = broker.client(host);
    const retained = broker.rebind(host, {
      client: {} as HostRuntimesClient,
      connection: connection(vi.fn(), currentCall),
    });
    staleResolution.resolve(
      ok({
        client: {} as HostRuntimesClient,
        connection: connection(
          vi.fn(),
          vi.fn(async () => 'stale')
        ),
      })
    );

    const resolved = await stale;
    expect(resolved.success).toBe(true);
    if (!resolved.success) throw new Error('Expected the rebound Host runtime');
    expect(resolved.data).toBe(retained);
    await expect(resolved.data.files.getHomeDir(undefined)).resolves.toBe('current');
    expect(currentCall).toHaveBeenCalledOnce();
  });

  it('returns typed host resolution failures as client values', async () => {
    const remote = hostRef('remote', 'remote-1');
    const broker = new RuntimeBroker({
      resolve: (host) =>
        err({
          type: 'host-unavailable',
          host,
          reason: 'runtime-unavailable',
          message: 'Remote runtime sessions are not enabled',
        }),
    });

    await expect(broker.client(remote)).resolves.toEqual(
      err({
        type: 'host-unavailable',
        host: remote,
        reason: 'runtime-unavailable',
        message: 'Remote runtime sessions are not enabled',
      })
    );
  });

  it('delegates invalidation when the resolver has lifecycle state below it', async () => {
    const invalidate = vi.fn(async () => {});
    const broker = new RuntimeBroker({
      resolve: () => ok({} as HostRuntimesClient),
      invalidate,
    });

    await broker.invalidate(LOCAL_HOST_REF);

    expect(invalidate).toHaveBeenCalledWith(LOCAL_HOST_REF);
  });
});

function connection(attach: Connection['attach'], call: Connection['call'] = vi.fn()): Connection {
  return {
    call,
    openBlobConsumer: vi.fn(),
    openBlobProducer: vi.fn(),
    snapshot: vi.fn(),
    attach,
    onDisconnect: vi.fn(() => () => {}),
    dispose: vi.fn(),
  } as unknown as Connection;
}
