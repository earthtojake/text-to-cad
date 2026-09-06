import { EventEmitter } from 'node:events';
import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { deferred } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import { HostAttachmentRegistry } from './host-attachment-registry';

describe('HostAttachmentRegistry', () => {
  it('replays SSH hosts that connected before registry construction', async () => {
    const fixture = createFixture({ connectedIds: ['ssh-1'] });
    const attach = vi.fn();

    fixture.registry.register({ label: 'late', attach, detach: vi.fn() });

    await vi.waitFor(() => {
      expect(attach).toHaveBeenCalledWith(LOCAL_HOST_REF);
      expect(attach).toHaveBeenCalledWith(hostRef('remote', 'ssh-1'));
    });
    await fixture.registry.dispose();
  });

  it('replays attached hosts to late participants', async () => {
    const fixture = createFixture();
    const attach = vi.fn();

    fixture.ssh.emit('connection-event', connected('ssh-1'));
    fixture.registry.register({ label: 'late', attach, detach: vi.fn() });

    await vi.waitFor(() => {
      expect(attach).toHaveBeenCalledWith(LOCAL_HOST_REF);
      expect(attach).toHaveBeenCalledWith(hostRef('remote', 'ssh-1'));
    });
    await fixture.registry.dispose();
  });

  it('serializes attach and detach for each host', async () => {
    const fixture = createFixture();
    const attached = deferred<void>();
    const calls: string[] = [];
    fixture.registry.register({
      label: 'serialized',
      async attach(host) {
        if (host.type === 'local') return;
        calls.push('attach:start');
        await attached.promise;
        calls.push('attach:end');
      },
      detach(host) {
        if (host.type === 'remote') calls.push('detach');
      },
    });

    fixture.ssh.emit('connection-event', connected('ssh-1'));
    await vi.waitFor(() => expect(calls).toEqual(['attach:start']));
    fixture.invalidate({ connectionId: 'ssh-1', reason: 'connection-lost' });
    await Promise.resolve();
    expect(calls).toEqual(['attach:start']);

    attached.resolve();
    await vi.waitFor(() => expect(calls).toEqual(['attach:start', 'attach:end', 'detach']));
    await fixture.registry.dispose();
  });

  it('detaches on remote-machine invalidation but not an ordinary SSH disconnect', async () => {
    const fixture = createFixture();
    const detach = vi.fn();
    fixture.registry.register({ label: 'lifecycle', attach: vi.fn(), detach });
    fixture.ssh.emit('connection-event', connected('ssh-1'));
    await vi.waitFor(() =>
      expect(fixture.registry.attachedHosts()).toContainEqual(hostRef('remote', 'ssh-1'))
    );

    fixture.ssh.emit('connection-event', { type: 'disconnected', connectionId: 'ssh-1' });
    await Promise.resolve();
    expect(detach).not.toHaveBeenCalledWith(hostRef('remote', 'ssh-1'));
    expect(fixture.registry.attachedHosts()).toContainEqual(hostRef('remote', 'ssh-1'));

    fixture.invalidate({ connectionId: 'ssh-1', reason: 'connection-lost' });
    await vi.waitFor(() => expect(detach).toHaveBeenCalledWith(hostRef('remote', 'ssh-1')));
    expect(fixture.registry.attachedHosts()).not.toContainEqual(hostRef('remote', 'ssh-1'));
    await fixture.registry.dispose();
  });

  it('isolates participant failures and includes the participant label in the log', async () => {
    const fixture = createFixture();
    const healthyAttach = vi.fn();
    fixture.registry.register({
      label: 'broken',
      attach: () => {
        throw new Error('boom');
      },
      detach: vi.fn(),
    });
    fixture.registry.register({ label: 'healthy', attach: healthyAttach, detach: vi.fn() });

    fixture.ssh.emit('connection-event', connected('ssh-1'));

    await vi.waitFor(() => expect(healthyAttach).toHaveBeenCalledWith(hostRef('remote', 'ssh-1')));
    expect(fixture.logger.warn).toHaveBeenCalledWith(
      'Host attachment participant failed',
      expect.objectContaining({ participant: 'broken', operation: 'attach' })
    );
    await fixture.registry.dispose();
  });
});

function createFixture({ connectedIds = [] }: { connectedIds?: string[] } = {}) {
  const ssh = new EventEmitter();
  const connected = new Set(connectedIds);
  Object.assign(ssh, {
    getConnectionIds: () => [...connected],
    isConnected: (connectionId: string) => connected.has(connectionId),
  });
  let invalidate = (_event: { connectionId: string; reason: 'connection-lost' }): void => {};
  const logger = { warn: vi.fn() };
  const registry = new HostAttachmentRegistry({
    ssh: ssh as never,
    hosts: {
      onInvalidate(listener) {
        invalidate = listener as typeof invalidate;
        return () => {
          invalidate = () => {};
        };
      },
    },
    logger,
  });
  return {
    ssh,
    registry,
    logger,
    invalidate: (event: Parameters<typeof invalidate>[0]) => invalidate(event),
  };
}

function connected(connectionId: string) {
  return { type: 'connected', connectionId, proxy: {} };
}
