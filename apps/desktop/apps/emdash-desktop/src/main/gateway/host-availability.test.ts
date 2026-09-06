import { LOCAL_HOST_REF, hostRef } from '@emdash/core/primitives/host/api';
import type { RuntimeUnavailableReason } from '@emdash/core/primitives/runtime-resolution/api';
import { createScope } from '@emdash/shared/concurrency';
import { deferred } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import type {
  SshConnectionManager,
  SshConnectionManagerListener,
} from '@core/primitives/ssh/api/node/ssh-connection-manager';
import type { HostInvalidation } from '@core/services/hosts/api';
import type { HostService } from '@core/services/hosts/node';
import {
  WorkspaceServerProtocolError,
  WorkspaceServerProvisionError,
} from '@core/services/hosts/node/workspace-server';
import {
  createDesktopHostAvailability as createProductionHostAvailability,
  type CreateDesktopHostAvailabilityOptions,
} from './host-availability';

function createDesktopHostAvailability(
  options: Omit<CreateDesktopHostAvailabilityOptions, 'connectSsh' | 'sshEvents' | 'runtimes'> & {
    connectSsh?: CreateDesktopHostAvailabilityOptions['connectSsh'];
    runtimes?: CreateDesktopHostAvailabilityOptions['runtimes'];
    sshEvents?: CreateDesktopHostAvailabilityOptions['sshEvents'];
  }
) {
  return createProductionHostAvailability({
    ...options,
    connectSsh: options.connectSsh ?? (async () => 'connected'),
    runtimes: options.runtimes ?? { rebind: vi.fn() },
    sshEvents:
      options.sshEvents ??
      ({
        on: () => {},
        off: () => {},
      } as unknown as CreateDesktopHostAvailabilityOptions['sshEvents']),
  });
}

describe('desktop Host availability', () => {
  it.each(['connected', 'reconnected'] as const)(
    'forwards an SSH %s edge to demanded Host recovery',
    async (type) => {
      const scope = createScope({ label: 'desktop-host-availability-test' });
      let listener: SshConnectionManagerListener | undefined;
      const off = vi.fn();
      const sshEvents = {
        on(_event: 'connection-event', nextListener: SshConnectionManagerListener) {
          listener = nextListener;
          return this;
        },
        off(_event: 'connection-event', nextListener: SshConnectionManagerListener) {
          if (listener === nextListener) listener = undefined;
          off();
          return this;
        },
      } as Pick<SshConnectionManager, 'on' | 'off'>;
      const availability = createDesktopHostAvailability({
        scope,
        hosts: {
          client: vi.fn(async () => ({})),
          onInvalidate: () => () => {},
        } as unknown as HostService,
        sshEvents,
        localReady: async () => {},
      });
      const wake = vi.spyOn(availability, 'wake');

      listener?.({
        type,
        connectionId: 'ssh-1',
        proxy: {},
      } as Parameters<SshConnectionManagerListener>[0]);

      expect(wake).toHaveBeenCalledWith(hostRef('remote', 'ssh-1'), 'ssh-edge');
      await scope.dispose();
      expect(off).toHaveBeenCalledOnce();
    }
  );

  it.each(['connect', 'retry'] as const)(
    'records explicit SSH connection intent before %s prepares runtime readiness',
    async (cause) => {
      const scope = createScope({ label: 'desktop-host-availability-test' });
      const order: string[] = [];
      const availability = createDesktopHostAvailability({
        scope,
        hosts: {
          client: vi.fn(async () => {
            order.push('runtime');
            return {};
          }),
          onInvalidate: () => () => {},
        } as unknown as HostService,
        connectSsh: vi.fn(async () => {
          order.push('transport');
          return 'connected' as const;
        }),
        localReady: async () => {},
      });

      availability.requestReady(hostRef('remote', 'ssh-1'), cause);
      await vi.waitFor(() =>
        expect(availability.stateFor(hostRef('remote', 'ssh-1')).kind).toBe('ready')
      );

      expect(order).toEqual(['transport', 'runtime']);
      await scope.dispose();
    }
  );

  it('uses the existing SSH provisioner and Wire handshake before publishing ready', async () => {
    const scope = createScope({ label: 'desktop-host-availability-test' });
    const provisioning = deferred<void>();
    const handshake = deferred<void>();
    const runtimeClient = {};
    const wireConnection = {};
    const rebind = vi.fn();
    const client = vi.fn(
      async (
        _connectionId: string,
        options: {
          signal: AbortSignal;
          onPhase(phase: 'provisioning' | 'handshaking'): void;
        }
      ) => {
        options.onPhase('provisioning');
        provisioning.resolve();
        options.onPhase('handshaking');
        await handshake.promise;
        return { client: runtimeClient, connection: wireConnection };
      }
    );
    const availability = createDesktopHostAvailability({
      scope,
      hosts: { client, onInvalidate: () => () => {} } as unknown as HostService,
      runtimes: { rebind },
      localReady: async () => {},
    });
    const host = hostRef('remote', 'ssh-1');

    const pending = availability.ensureReady(host, 'demand');
    await provisioning.promise;

    expect(client).toHaveBeenCalledWith(
      'ssh-1',
      expect.objectContaining({
        signal: expect.any(AbortSignal),
        onPhase: expect.any(Function),
      })
    );
    expect(availability.stateFor(host)).toEqual({
      kind: 'preparing',
      phase: 'handshaking',
      attempt: 1,
    });

    handshake.resolve();
    await expect(pending).resolves.toMatchObject({ success: true });
    expect(rebind).toHaveBeenCalledWith(host, {
      client: runtimeClient,
      connection: wireConnection,
    });

    await scope.dispose();
  });

  it('invalidates a ready generation when the Host runtime connection is lost', async () => {
    const scope = createScope({ label: 'desktop-host-availability-test' });
    let invalidate: ((event: HostInvalidation) => void) | undefined;
    const hosts = {
      client: vi.fn(async () => ({})),
      onInvalidate(listener: (event: HostInvalidation) => void) {
        invalidate = listener;
        return () => {
          invalidate = undefined;
        };
      },
    } as unknown as HostService;
    const availability = createDesktopHostAvailability({
      scope,
      hosts,
      localReady: async () => {},
    });
    const host = hostRef('remote', 'ssh-1');
    await expect(availability.ensureReady(host, 'demand')).resolves.toMatchObject({
      success: true,
      data: { generation: 1 },
    });

    invalidate?.({ connectionId: 'ssh-1', reason: 'connection-lost' });

    expect(availability.stateFor(host)).toEqual({
      kind: 'unavailable',
      recovery: 'eligible',
    });
    await expect(availability.ensureReady(host, 'ssh-edge')).resolves.toMatchObject({
      success: true,
      data: { generation: 2 },
    });

    await scope.dispose();
  });

  it.each([
    ['connection-failed', new WorkspaceServerProvisionError('connection-failed', 'raw')],
    ['daemon-start-failed', new WorkspaceServerProvisionError('daemon-start-failed', 'raw')],
    [
      'artifact-download-failed',
      new WorkspaceServerProvisionError('artifact-download-failed', 'raw'),
    ],
    ['install-failed', new WorkspaceServerProvisionError('install-failed', 'raw')],
    ['unsupported-platform', new WorkspaceServerProvisionError('unsupported-platform', 'raw')],
    [
      'protocol-upgrade-client',
      new WorkspaceServerProvisionError('protocol-incompatible', 'raw', {
        cause: new WorkspaceServerProtocolError({
          type: 'protocol-incompatible',
          action: 'upgrade-client',
          clientProtocolVersion: '2.0.0',
          serverProtocolVersion: '1.0.0',
        }),
      }),
    ],
    [
      'protocol-upgrade-server',
      new WorkspaceServerProvisionError('protocol-incompatible', 'raw', {
        cause: new WorkspaceServerProtocolError({
          type: 'protocol-incompatible',
          action: 'upgrade-server',
          clientProtocolVersion: '1.0.0',
          serverProtocolVersion: '2.0.0',
        }),
      }),
    ],
  ] as const)(
    'preserves the %s runtime reason without parsing messages',
    async (reason: RuntimeUnavailableReason, failure: Error) => {
      const scope = createScope({ label: 'desktop-host-availability-test' });
      const availability = createDesktopHostAvailability({
        scope,
        hosts: {
          client: async () => {
            throw failure;
          },
          onInvalidate: () => () => {},
        } as unknown as HostService,
        localReady: async () => {},
      });

      const host = hostRef('remote', 'ssh-1');
      const pending = availability.ensureReady(host, 'demand');
      if (reason === 'connection-failed' || reason === 'daemon-start-failed') {
        await vi.waitFor(() =>
          expect(availability.stateFor(host)).toMatchObject({
            kind: 'unavailable',
            issue: { type: 'host-unavailable', reason },
            recovery: 'waiting',
          })
        );
        availability.suspend(host);
        await pending;
      } else {
        await expect(pending).resolves.toMatchObject({
          success: false,
          error: { type: 'host-unavailable', reason },
        });
      }

      await scope.dispose();
    }
  );

  it('waits for the existing local Wire workers before publishing local readiness', async () => {
    const scope = createScope({ label: 'desktop-host-availability-test' });
    const handshake = deferred<void>();
    const connectSsh = vi.fn(async () => 'connected' as const);
    const availability = createDesktopHostAvailability({
      scope,
      hosts: { onInvalidate: () => () => {} } as unknown as HostService,
      connectSsh,
      localReady: () => handshake.promise,
    });

    const pending = availability.ensureReady(LOCAL_HOST_REF, 'demand');

    expect(availability.stateFor(LOCAL_HOST_REF)).toEqual({
      kind: 'preparing',
      phase: 'handshaking',
      attempt: 1,
    });
    handshake.resolve();
    await expect(pending).resolves.toMatchObject({ success: true });
    expect(connectSsh).not.toHaveBeenCalled();

    await scope.dispose();
  });
});
