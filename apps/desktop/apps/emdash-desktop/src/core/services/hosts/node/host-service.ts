import type { ReleaseChannel } from '@emdash/core/workspace-server';
import type { Scope } from '@emdash/shared/concurrency';
import { waitWithSignal } from '@emdash/shared/scheduling';
import type { SshService } from '@core/primitives/ssh/api';
import type { SshClientProxy } from '@core/primitives/ssh/api/node/ssh-client-proxy';
import type {
  SshConnectionManager,
  SshConnectionManagerEvent,
} from '@core/primitives/ssh/api/node/ssh-connection-manager';
import type { HostInvalidation, HostPreparingPhase, MachineMutationEvents } from '../api';
import { HostServerOperations } from './server-operations';
import { HostStateModel } from './state-model';
import {
  createWireConnectionManager,
  type WorkspaceServerConnection,
} from './workspace-server/connect/wire-connection-manager';
import type { WorkspaceServerSshPort } from './workspace-server/ports';
import { RemoteWorkspaceServerDaemon } from './workspace-server/provision/daemon-control';
import { RemoteHostProbe } from './workspace-server/provision/host-probe';
import { WorkspaceServerInstaller } from './workspace-server/provision/installer';
import { WorkspaceServerProvisioner } from './workspace-server/provision/provisioner';

type HostServiceLog = {
  warn(message: string, metadata?: Record<string, unknown>): void;
};

export type CreateHostServiceDeps = {
  scope: Scope;
  ssh: {
    manager: SshConnectionManager;
    connect: Pick<SshService, 'ensureConnected'>;
  };
  machineEvents: MachineMutationEvents;
  installBaseUrl?: string;
  releaseChannel?: ReleaseChannel;
  devAutoUpdate?: boolean;
  client?: { id: string; appVersion: string };
  logger?: HostServiceLog;
};

export type HostClientOptions = {
  signal: AbortSignal;
  onPhase(phase: HostPreparingPhase): void;
};

/**
 * Orchestrates transport, provisioning, and lifecycle for remote runtime clients.
 * Machine persistence and CRUD remain owned by the feature-level MachinesService.
 */
export interface HostService {
  readonly stateModel: HostStateModel;
  client(connectionId: string, options?: HostClientOptions): Promise<WorkspaceServerConnection>;
  refreshServerState(connectionId: string, options?: { force?: boolean }): Promise<void>;
  installServer(connectionId: string): Promise<void>;
  startServer(connectionId: string): Promise<void>;
  stopServer(connectionId: string): Promise<void>;
  restartServer(connectionId: string): Promise<void>;
  updateServer(connectionId: string): Promise<void>;
  onInvalidate(listener: (event: HostInvalidation) => void): () => void;
  dispose(): Promise<void>;
}

export function createHostService(deps: CreateHostServiceDeps): HostService {
  const scope = deps.scope.child('host-service');
  const stateModel = scope.use(new HostStateModel());
  const ssh = createWorkspaceServerSshPort(deps.ssh);
  const host = new RemoteHostProbe(ssh);
  const wire = createWireConnectionManager({ scope, ssh, client: deps.client });
  const installer = new WorkspaceServerInstaller({
    ssh,
    baseUrl: deps.installBaseUrl,
    releaseChannel: deps.releaseChannel,
  });
  const daemon = new RemoteWorkspaceServerDaemon(ssh);
  const provisioner = new WorkspaceServerProvisioner({
    scope,
    ssh,
    host,
    installer,
    daemon,
    model: stateModel,
    wire,
    devAutoUpdate: deps.devAutoUpdate,
    logger: deps.logger,
  });
  const serverOperations = new HostServerOperations({
    scope,
    state: stateModel,
    host,
    installer,
    daemon,
    wire,
    provision: provisioner,
  });
  const invalidationListeners = new Set<(event: HostInvalidation) => void>();

  const handleSshEvent = (event: SshConnectionManagerEvent) => {
    if (event.type !== 'reconnect-failed') return;
    host.drop(event.connectionId);
    provisioner.drop(event.connectionId);
    stateModel.remove(event.connectionId);
    notify({ connectionId: event.connectionId, reason: 'reconnect-failed' });
    void wire.invalidateConnection(event.connectionId).catch((error: unknown) => {
      deps.logger?.warn('Host service SSH lifecycle handling failed', { error });
    });
  };
  deps.ssh.manager.on('connection-event', handleSshEvent);
  scope.add(() => {
    deps.ssh.manager.off('connection-event', handleSshEvent);
  });
  scope.add(
    deps.machineEvents.on('machine:mutated', (event) => {
      host.drop(event.connectionId);
      stateModel.remove(event.connectionId);
      notify({ connectionId: event.connectionId, reason: 'machine-mutation' });
      void Promise.all([
        provisioner.cancel(event.connectionId),
        wire.invalidateConnection(event.connectionId),
      ]).catch((error: unknown) => {
        deps.logger?.warn('Host service mutation lifecycle handling failed', { error });
      });
    })
  );
  scope.add(
    wire.onConnectionLost((target, error) => {
      if (target.kind !== 'ssh') return;
      provisioner.drop(target.sshConnectionId);
      stateModel.markConnectionLost(target.sshConnectionId);
      notify({
        connectionId: target.sshConnectionId,
        reason: 'connection-lost',
        target,
        error,
      });
    })
  );
  scope.add(() => invalidationListeners.clear());

  let disposePromise: Promise<void> | undefined;
  return {
    stateModel,
    async client(connectionId, options) {
      if (options) {
        options.onPhase('connecting');
        const connectionState = await waitWithSignal(
          deps.ssh.connect.ensureConnected(connectionId),
          options.signal
        );
        if (connectionState !== 'connected') {
          throw new Error('Host connection is not available');
        }
        options.onPhase('provisioning');
      }
      const target = options
        ? await waitWithSignal(provisioner.ensure(connectionId), options.signal)
        : await provisioner.ensure(connectionId);
      if (options) {
        options.onPhase('handshaking');
        return await waitWithSignal(wire.client(target), options.signal);
      }
      return wire.client(target);
    },
    refreshServerState: (connectionId, options) => serverOperations.refresh(connectionId, options),
    installServer: (connectionId) => serverOperations.install(connectionId),
    startServer: (connectionId) => serverOperations.start(connectionId),
    stopServer: (connectionId) => serverOperations.stop(connectionId),
    restartServer: (connectionId) => serverOperations.restart(connectionId),
    updateServer: (connectionId) => serverOperations.update(connectionId),
    onInvalidate(listener) {
      invalidationListeners.add(listener);
      return () => invalidationListeners.delete(listener);
    },
    dispose() {
      disposePromise ??= scope.dispose();
      return disposePromise;
    },
  };

  function notify(event: HostInvalidation): void {
    for (const listener of invalidationListeners) {
      try {
        listener(event);
      } catch {
        // One observer must not prevent lifecycle cleanup or remaining listeners.
      }
    }
  }
}

function createWorkspaceServerSshPort(ssh: CreateHostServiceDeps['ssh']): WorkspaceServerSshPort {
  return {
    async ensureProxy(connectionId: string): Promise<SshClientProxy> {
      await ssh.connect.ensureConnected(connectionId);
      const proxy = ssh.manager.getProxy(connectionId);
      if (!proxy?.isConnected) {
        throw new Error(`SSH connection '${connectionId}' did not provide a live proxy`);
      }
      return proxy;
    },
  };
}
