import { workspaceWireContract, type WireInitializeResult } from '@emdash/core/workspace-server';
import type { PendingLease } from '@emdash/shared';
import { createResourceCache, createScope, type Scope } from '@emdash/shared/concurrency';
import {
  retrySchedules,
  runWithTimeout,
  waitWithSignal,
  type Clock,
  type RetrySchedule,
} from '@emdash/shared/scheduling';
import {
  client as createClient,
  connect,
  reconnectingTransport,
  type Connection,
  type ContractClient,
  type ReconnectingTransport,
  type WireTransport,
} from '@emdash/wire/rpc';
import type { WorkspaceServerTarget } from '../../../api/targets';
import type { WorkspaceServerSshPort } from '../ports';
import { workspaceServerTargetKey } from '../targets';
import { openLocalWorkspaceServerTransport } from './local-socket-transport';
import { initializeWorkspaceServerTransport, WorkspaceServerProtocolError } from './protocol';
import { openSshWorkspaceServerTransport } from './ssh-streamlocal-transport';

export type WorkspaceServerConnection = {
  target: WorkspaceServerTarget;
  client: ContractClient<typeof workspaceWireContract>;
  connection: Connection;
  ready(): Promise<WireInitializeResult>;
  currentHandshake(): WireInitializeResult | undefined;
};

export interface WireConnectionManager {
  client(target: WorkspaceServerTarget): Promise<WorkspaceServerConnection>;
  dialOnce(
    target: WorkspaceServerTarget,
    options?: { signal?: AbortSignal; timeoutMs?: number }
  ): Promise<WireInitializeResult>;
  invalidateConnection(connectionId: string): Promise<void>;
  onConnectionLost(listener: (target: WorkspaceServerTarget, error: unknown) => void): () => void;
  dispose(): Promise<void>;
}

export type CreateWireConnectionManagerOptions = {
  scope?: Scope;
  clock?: Clock;
  idleTtlMs?: number;
  retrySchedule?: RetrySchedule;
  protocolVersion?: string;
  client?: { id: string; appVersion: string };
  ssh?: WorkspaceServerSshPort;
  openTransport?: (target: WorkspaceServerTarget) => Promise<WireTransport>;
};

export type OpenWorkspaceServerTransportOptions = {
  ssh?: WorkspaceServerSshPort;
};

type PinnedConnection = {
  target: WorkspaceServerTarget;
  lease: PendingLease<WorkspaceServerConnection>;
};

export class WorkspaceServerConfigurationError extends Error {
  readonly name = 'WorkspaceServerConfigurationError';
}

export const workspaceServerReconnectSchedule = retrySchedules.sequence([
  500, 1_000, 2_000, 5_000, 10_000, 15_000, 20_000, 30_000, 30_000,
]);

const DEFAULT_DIAL_TIMEOUT_MS = 5_000;

export function createWireConnectionManager(
  options: CreateWireConnectionManagerOptions = {}
): WireConnectionManager {
  const scope = options.scope
    ? options.scope.child('wire-connection-manager')
    : createScope({ label: 'wire-connection-manager', clock: options.clock });
  const targetsByKey = new Map<string, WorkspaceServerTarget>();
  const targetKeysByConnection = new Map<string, Set<string>>();
  const pinnedConnections = new Map<string, PinnedConnection>();
  const connectionLostListeners = new Set<
    (target: WorkspaceServerTarget, error: unknown) => void
  >();
  const cache = createResourceCache<WorkspaceServerTarget, WorkspaceServerConnection>({
    key: workspaceServerTargetKey,
    scope,
    label: 'workspace-server-clients',
    clock: options.clock,
    idleTtlMs: options.idleTtlMs ?? 30_000,
    create: (target, connectionScope) => {
      trackTarget(target, connectionScope);
      return createWorkspaceServerConnection(target, connectionScope, options, (error) => {
        if (connectionScope.disposed) return;
        void handleConnectionLost(target, error).catch(() => {});
      });
    },
  });

  scope.add(() => releasePinnedConnections());
  scope.add(() => {
    targetsByKey.clear();
    targetKeysByConnection.clear();
    connectionLostListeners.clear();
  });

  let disposePromise: Promise<void> | undefined;
  return {
    async client(target) {
      const key = workspaceServerTargetKey(target);
      let pinned = pinnedConnections.get(key);
      if (!pinned) {
        pinned = { target, lease: cache.acquire(target) };
        pinnedConnections.set(key, pinned);
      }

      try {
        return await pinned.lease.ready();
      } catch (error) {
        if (pinnedConnections.get(key) === pinned) pinnedConnections.delete(key);
        await pinned.lease.release();
        throw error;
      }
    },
    dialOnce: (target, dialOptions = {}) => dialOnce(target, options, dialOptions),
    async invalidateConnection(connectionId) {
      await releasePinnedConnections(connectionId);
      const targetKeys = [...(targetKeysByConnection.get(connectionId) ?? [])];
      const targets = targetKeys.flatMap((key) => {
        const target = targetsByKey.get(key);
        return target ? [target] : [];
      });
      await Promise.all(targets.map((target) => cache.invalidate(target)));
    },
    onConnectionLost(listener) {
      connectionLostListeners.add(listener);
      return () => {
        connectionLostListeners.delete(listener);
      };
    },
    dispose() {
      disposePromise ??= scope.dispose();
      return disposePromise;
    },
  };

  function trackTarget(target: WorkspaceServerTarget, connectionScope: Scope): void {
    if (target.kind !== 'ssh') return;
    const key = workspaceServerTargetKey(target);
    targetsByKey.set(key, target);
    const targetKeys = targetKeysByConnection.get(target.sshConnectionId) ?? new Set<string>();
    targetKeys.add(key);
    targetKeysByConnection.set(target.sshConnectionId, targetKeys);
    connectionScope.add(() => pruneTarget(target));
  }

  function pruneTarget(target: WorkspaceServerTarget): void {
    if (target.kind !== 'ssh') return;
    const key = workspaceServerTargetKey(target);
    targetsByKey.delete(key);
    const targetKeys = targetKeysByConnection.get(target.sshConnectionId);
    targetKeys?.delete(key);
    if (targetKeys?.size === 0) targetKeysByConnection.delete(target.sshConnectionId);
  }

  async function handleConnectionLost(
    target: WorkspaceServerTarget,
    error: unknown
  ): Promise<void> {
    try {
      const key = workspaceServerTargetKey(target);
      const pinned = pinnedConnections.get(key);
      if (pinned) {
        pinnedConnections.delete(key);
        await pinned.lease.release();
      }
      await cache.invalidate(target);
    } finally {
      notifyConnectionLost(target, error);
    }
  }

  function notifyConnectionLost(target: WorkspaceServerTarget, error: unknown): void {
    for (const listener of connectionLostListeners) {
      try {
        listener(target, error);
      } catch {
        // Error reporting must not interfere with connection teardown.
      }
    }
  }

  async function releasePinnedConnections(connectionId?: string): Promise<void> {
    const releases: Promise<void>[] = [];
    for (const [key, pinned] of pinnedConnections) {
      if (
        connectionId &&
        (pinned.target.kind !== 'ssh' || pinned.target.sshConnectionId !== connectionId)
      ) {
        continue;
      }
      pinnedConnections.delete(key);
      releases.push(pinned.lease.release());
    }
    await Promise.all(releases);
  }
}

async function createWorkspaceServerConnection(
  target: WorkspaceServerTarget,
  scope: Scope,
  options: CreateWireConnectionManagerOptions,
  onConnectionLost: (error: unknown) => void
): Promise<WorkspaceServerConnection> {
  let handshake: WireInitializeResult | undefined;
  const openTransport =
    options.openTransport ??
    ((nextTarget: WorkspaceServerTarget) => openWorkspaceServerTransport(nextTarget, options));
  const transport = reconnectingTransport(
    async () => {
      const candidate = await openTransport(target);
      const nextHandshake = await initializeWorkspaceServerTransport(
        candidate,
        options.protocolVersion,
        options.client
      );
      handshake = nextHandshake;
      return candidate;
    },
    {
      clock: options.clock,
      retrySchedule: options.retrySchedule ?? workspaceServerReconnectSchedule,
      shouldRetry: (error) =>
        !(error instanceof WorkspaceServerProtocolError) &&
        !(error instanceof WorkspaceServerConfigurationError),
    }
  );
  scope.add(() => transport.close());

  const connection = connect(transport);
  scope.add(() => connection.dispose());
  scope.add(
    connection.onDisconnect(() => {
      void transport.ready().catch(onConnectionLost);
    })
  );
  const client = createClient(workspaceWireContract, connection);

  try {
    await transport.ready();
  } catch (error) {
    onConnectionLost(error);
    throw error;
  }
  requireHandshake(handshake);

  return {
    target,
    client,
    connection,
    ready: () => readyHandshake(transport, () => handshake),
    currentHandshake: () => handshake,
  };
}

export function openWorkspaceServerTransport(
  target: WorkspaceServerTarget,
  options: OpenWorkspaceServerTransportOptions = {}
): Promise<WireTransport> {
  switch (target.kind) {
    case 'local-socket':
      return openLocalWorkspaceServerTransport(target);
    case 'ssh':
      if (!options.ssh) {
        throw new WorkspaceServerConfigurationError(
          'An SSH service is required for an SSH workspace-server target'
        );
      }
      return openSshWorkspaceServerTransport(target, options.ssh);
  }
}

async function dialOnce(
  target: WorkspaceServerTarget,
  managerOptions: CreateWireConnectionManagerOptions,
  options: { signal?: AbortSignal; timeoutMs?: number }
): Promise<WireInitializeResult> {
  const open =
    managerOptions.openTransport ??
    ((next: WorkspaceServerTarget) => openWorkspaceServerTransport(next, managerOptions));
  const openPromise = Promise.resolve().then(() => open(target));
  let transport: WireTransport | undefined;

  try {
    return await runWithTimeout(
      async (timeoutSignal) => {
        const candidate = await waitWithSignal(openPromise, timeoutSignal);
        transport = candidate;
        return await waitWithSignal(
          initializeWorkspaceServerTransport(
            candidate,
            managerOptions.protocolVersion,
            managerOptions.client
          ),
          timeoutSignal
        );
      },
      {
        timeoutMs: options.timeoutMs ?? DEFAULT_DIAL_TIMEOUT_MS,
        signal: options.signal,
        clock: managerOptions.clock,
      }
    );
  } finally {
    if (transport) {
      transport.close?.();
    } else {
      void openPromise.then(
        (lateTransport) => lateTransport.close?.(),
        () => {}
      );
    }
  }
}

async function readyHandshake(
  transport: ReconnectingTransport,
  current: () => WireInitializeResult | undefined
): Promise<WireInitializeResult> {
  await transport.ready();
  const handshake = current();
  requireHandshake(handshake);
  return handshake;
}

function requireHandshake(
  handshake: WireInitializeResult | undefined
): asserts handshake is WireInitializeResult {
  if (!handshake) {
    throw new Error('Workspace server transport became ready without an initialize response');
  }
}
