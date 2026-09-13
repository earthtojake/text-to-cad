import { createScope } from '@emdash/shared/concurrency';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { SshConnectionManagerEvent } from '@core/primitives/ssh/api/node/ssh-connection-manager';
import type { SshWorkspaceServerTarget } from '../api/targets';
import { createHostService } from './host-service';
import type { WorkspaceServerConnection } from './workspace-server/connect/wire-connection-manager';

const mocks = vi.hoisted(() => ({
  cancel: vi.fn(async () => {}),
  client: vi.fn(),
  drop: vi.fn(),
  dropTarget: vi.fn(),
  ensure: vi.fn(),
  invalidateConnection: vi.fn(async () => {}),
  connectionLostListener: undefined as
    | ((target: SshWorkspaceServerTarget, error: unknown) => void)
    | undefined,
}));

vi.mock('./workspace-server/connect/wire-connection-manager', () => ({
  createWireConnectionManager: () => ({
    client: mocks.client,
    dialOnce: vi.fn(),
    invalidateConnection: mocks.invalidateConnection,
    onConnectionLost(listener: (target: SshWorkspaceServerTarget, error: unknown) => void) {
      mocks.connectionLostListener = listener;
      return () => {
        mocks.connectionLostListener = undefined;
      };
    },
    dispose: vi.fn(async () => {}),
  }),
}));

vi.mock('./workspace-server/provision/host-probe', () => ({
  RemoteHostProbe: class {
    drop = mocks.drop;
  },
}));

vi.mock('./workspace-server/provision/provisioner', () => ({
  WorkspaceServerProvisioner: class {
    ensure = mocks.ensure;
    cancel = mocks.cancel;
    drop = mocks.dropTarget;
  },
}));

const target: SshWorkspaceServerTarget = {
  kind: 'ssh',
  sshConnectionId: 'ssh-1',
  socketPath: '/run/emdash/workspace-server.sock',
};

function connection(): WorkspaceServerConnection {
  return { target, client: {} } as WorkspaceServerConnection;
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.connectionLostListener = undefined;
  mocks.ensure.mockResolvedValue(target);
  mocks.client.mockResolvedValue(connection());
});

describe('HostService', () => {
  it('ensures the remote server before resolving the pinned Wire client', async () => {
    const fixture = createFixture();

    try {
      const resolved = await fixture.service.client('ssh-1');
      expect(mocks.ensure).toHaveBeenCalledWith('ssh-1');
      expect(mocks.client).toHaveBeenCalledWith(target);
      expect(resolved.target).toBe(target);
      expect(fixture.ensureConnected).not.toHaveBeenCalled();
    } finally {
      await fixture.dispose();
    }
  });

  it('reports connection, provisioning, and handshake phases through the readiness path', async () => {
    const fixture = createFixture();
    const onPhase = vi.fn();

    try {
      await fixture.service.client('ssh-1', {
        signal: new AbortController().signal,
        onPhase,
      });

      expect(fixture.ensureConnected).toHaveBeenCalledWith('ssh-1');
      expect(mocks.ensure).toHaveBeenCalledWith('ssh-1');
      expect(mocks.client).toHaveBeenCalledWith(target);
      expect(onPhase.mock.calls).toEqual([['connecting'], ['provisioning'], ['handshaking']]);
    } finally {
      await fixture.dispose();
    }
  });

  it.each(['disconnected', 'reconnecting', 'reconnected'] as const)(
    'does not invalidate a stable session on %s',
    async (type) => {
      const fixture = createFixture();
      const event =
        type === 'reconnecting'
          ? { type, connectionId: 'ssh-1', attempt: 1, delayMs: 1 }
          : type === 'reconnected'
            ? { type, connectionId: 'ssh-1', proxy: {} as never }
            : { type, connectionId: 'ssh-1' };

      try {
        fixture.sshEventListener?.(event);
        await Promise.resolve();

        expect(mocks.drop).not.toHaveBeenCalled();
        expect(mocks.invalidateConnection).not.toHaveBeenCalled();
        expect(fixture.invalidations).toEqual([]);
      } finally {
        await fixture.dispose();
      }
    }
  );

  it('drops cached host data and invalidates Wire after SSH reconnect exhaustion', async () => {
    const fixture = createFixture();

    try {
      fixture.sshEventListener?.({ type: 'reconnect-failed', connectionId: 'ssh-1' });
      await vi.waitFor(() => expect(mocks.invalidateConnection).toHaveBeenCalledWith('ssh-1'));

      expect(mocks.drop).toHaveBeenCalledWith('ssh-1');
      expect(fixture.invalidations).toEqual([
        { connectionId: 'ssh-1', reason: 'reconnect-failed' },
      ]);
    } finally {
      await fixture.dispose();
    }
  });

  it('resolves the replacement Wire connection after SSH reconnect exhaustion', async () => {
    const fixture = createFixture();
    const first = { ...connection(), client: { generation: 1 } as never };
    const recovered = { ...connection(), client: { generation: 2 } as never };
    mocks.client.mockResolvedValueOnce(first).mockResolvedValueOnce(recovered);

    try {
      await expect(fixture.service.client('ssh-1')).resolves.toBe(first);
      fixture.sshEventListener?.({ type: 'reconnect-failed', connectionId: 'ssh-1' });
      await vi.waitFor(() => expect(mocks.invalidateConnection).toHaveBeenCalledWith('ssh-1'));

      await expect(fixture.service.client('ssh-1')).resolves.toBe(recovered);
      expect(mocks.client).toHaveBeenCalledTimes(2);
    } finally {
      await fixture.dispose();
    }
  });

  it('cancels provisioning and invalidates Wire after a machine mutation', async () => {
    const fixture = createFixture();

    try {
      fixture.machineMutationListener?.({ connectionId: 'ssh-1' });
      await vi.waitFor(() => expect(mocks.cancel).toHaveBeenCalledWith('ssh-1'));

      expect(mocks.drop).toHaveBeenCalledWith('ssh-1');
      expect(mocks.invalidateConnection).toHaveBeenCalledWith('ssh-1');
      expect(fixture.invalidations).toEqual([
        { connectionId: 'ssh-1', reason: 'machine-mutation' },
      ]);
    } finally {
      await fixture.dispose();
    }
  });

  it('reports an affected remote session after Wire connection loss', async () => {
    const fixture = createFixture();
    const error = new Error('retry budget exhausted');

    try {
      mocks.connectionLostListener?.(target, error);

      expect(fixture.invalidations).toEqual([
        {
          connectionId: 'ssh-1',
          reason: 'connection-lost',
          target,
          error,
        },
      ]);
    } finally {
      await fixture.dispose();
    }
  });

  it('continues notifying observers when one observer throws', async () => {
    const fixture = createFixture();
    fixture.service.onInvalidate(() => {
      throw new Error('observer failed');
    });

    try {
      fixture.sshEventListener?.({ type: 'reconnect-failed', connectionId: 'ssh-1' });
      await vi.waitFor(() => expect(mocks.invalidateConnection).toHaveBeenCalledWith('ssh-1'));

      expect(fixture.invalidations).toEqual([
        { connectionId: 'ssh-1', reason: 'reconnect-failed' },
      ]);
    } finally {
      await fixture.dispose();
    }
  });
});

function createFixture() {
  const parentScope = createScope({ label: 'host-service-test' });
  let sshEventListener: ((event: SshConnectionManagerEvent) => void) | undefined;
  let machineMutationListener: ((event: { connectionId: string }) => void) | undefined;
  const manager = {
    on: vi.fn((_event: string, listener: (event: SshConnectionManagerEvent) => void) => {
      sshEventListener = listener;
    }),
    off: vi.fn(),
    getProxy: vi.fn(),
  };
  const ensureConnected = vi.fn(async () => 'connected' as const);
  const service = createHostService({
    scope: parentScope,
    ssh: {
      manager: manager as never,
      connect: { ensureConnected },
    },
    machineEvents: {
      on: vi.fn((_event, listener) => {
        machineMutationListener = listener;
        return () => {
          machineMutationListener = undefined;
        };
      }),
    },
  });
  const invalidations: unknown[] = [];
  service.onInvalidate((event) => invalidations.push(event));

  return {
    service,
    ensureConnected,
    invalidations,
    get sshEventListener() {
      return sshEventListener;
    },
    get machineMutationListener() {
      return machineMutationListener;
    },
    async dispose() {
      await service.dispose();
      await parentScope.dispose();
    },
  };
}
