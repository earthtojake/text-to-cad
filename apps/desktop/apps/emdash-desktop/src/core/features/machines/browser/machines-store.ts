import { hostRef } from '@emdash/core/primitives/host/api';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { observe, remote, whenReady } from '@emdash/wire/state';
import { action, computed, makeObservable, observable, runInAction } from 'mobx';
import {
  getMachinesClient as getMachinesDomainClient,
  type MachinesClient,
} from '@core/features/machines/api/browser/client';
import { Resource } from '@core/primitives/async-resource/browser/resource';
import { getHostDependencyErrorMessage } from '@core/primitives/host-dependencies/browser/error-message';
import type {
  ConnectionState,
  ConnectionTestResult,
  SshConfig,
  SshConfigHost,
  SshHealthState,
} from '@core/primitives/ssh/api';
import { runDesktopLiveJob } from '@core/primitives/wire/browser/run-live-job';
import { getHostsClient, type HostsClient } from '@core/services/hosts/api/client';
import { sshContract, type SshConnectionsRuntime } from '@core/services/ssh/api';
import { getSshClient as getSshDomainClient, type SshClient } from '@core/services/ssh/api/client';
import { machinesContract } from '../api';
import type {
  InstallMachineSystemDependenciesInput,
  InstallMachineSystemDependenciesResult,
} from '../api';

type SaveConnectionInput = Partial<Pick<SshConfig, 'id'>> &
  Omit<SshConfig, 'id'> & { password?: string; passphrase?: string };
export type SystemDependenciesStore = Pick<MachinesStore, 'installSystemDependencies'>;

export type MachinesStoreOptions = {
  sshClient?: SshClient;
  machinesClient?: MachinesClient;
  hostsClient?: Pick<HostsClient, 'disconnect' | 'requestReady'>;
};

export class MachinesStore {
  readonly connectionsResource: Resource<SshConfig[]>;

  private pendingMutations = 0;
  private started = false;
  private modelReady = false;
  private runtimeData: SshConnectionsRuntime = {};
  private modelScope: Scope | undefined;
  private startPromise: Promise<void> | undefined;
  private sshClientPromise: Promise<SshClient> | undefined;
  private hostsClientPromise: Promise<Pick<HostsClient, 'disconnect' | 'requestReady'>> | undefined;
  private machinesClientPromise: Promise<MachinesClient> | undefined;
  private readonly sshClientOverride?: SshClient;
  private readonly machinesClientOverride?: MachinesClient;
  private readonly hostsClientOverride?: Pick<HostsClient, 'disconnect' | 'requestReady'>;

  constructor({ sshClient, machinesClient, hostsClient }: MachinesStoreOptions = {}) {
    this.sshClientOverride = sshClient;
    this.machinesClientOverride = machinesClient;
    this.hostsClientOverride = hostsClient;
    this.connectionsResource = new Resource<SshConfig[]>(
      async () => (await this.getMachinesClient()).getMachines(undefined),
      []
    );

    makeObservable<MachinesStore, 'runtimeData' | 'modelReady' | 'pendingMutations' | 'started'>(
      this,
      {
        runtimeData: observable.ref,
        modelReady: observable,
        pendingMutations: observable,
        started: observable,
        connections: computed,
        connectionStates: computed,
        healthStates: computed,
        isLoading: computed,
        start: action,
        dispose: action,
      }
    );
  }

  get connections(): SshConfig[] {
    return this.connectionsResource.data ?? [];
  }

  get connectionStates(): Record<string, ConnectionState> {
    return Object.fromEntries(
      Object.entries(this.runtime).map(([connectionId, value]) => [connectionId, value.state])
    );
  }

  get healthStates(): Record<string, SshHealthState> {
    return Object.fromEntries(
      Object.entries(this.runtime).map(([connectionId, value]) => [connectionId, value.health])
    );
  }

  get isLoading(): boolean {
    return this.connectionsResource.loading || !this.modelReady || this.pendingMutations > 0;
  }

  start(): Promise<void> {
    if (this.startPromise) return this.startPromise;
    this.started = true;
    this.startPromise = Promise.all([
      this.connectionsResource.load(),
      this.initializeConnectionsModel(),
    ]).then(() => {});
    return this.startPromise;
  }

  dispose(): void {
    this.started = false;
    this.modelReady = false;
    this.startPromise = undefined;
    this.connectionsResource.dispose();
    const scope = this.modelScope;
    this.modelScope = undefined;
    this.runtimeData = {};
    if (scope) void scope.dispose();
  }

  stateFor(connectionId: string): ConnectionState {
    return this.runtime[connectionId]?.state ?? 'disconnected';
  }

  healthFor(connectionId: string): SshHealthState {
    return this.runtime[connectionId]?.health ?? { status: 'ok' };
  }

  async connect(connectionId: string): Promise<void> {
    await this.ensureConnectionsModel();
    await (
      await this.getHostsClient()
    ).requestReady({
      host: hostRef('remote', connectionId),
      cause: 'connect',
    });
  }

  async retry(connectionId: string): Promise<void> {
    await this.ensureConnectionsModel();
    await (
      await this.getHostsClient()
    ).requestReady({
      host: hostRef('remote', connectionId),
      cause: 'retry',
    });
  }

  async disconnect(connectionId: string): Promise<void> {
    await this.ensureConnectionsModel();
    await (
      await this.getHostsClient()
    ).disconnect({
      host: { type: 'remote', id: connectionId },
    });
  }

  async saveConnection(config: SaveConnectionInput): Promise<SshConfig> {
    return await this.withMutation(async () => {
      const savedConnection = await (await this.getMachinesClient()).saveMachine(config);
      this.connectionsResource.setValue(this.upsertConnection(savedConnection));
      return savedConnection;
    });
  }

  async setSyncLocalSettings(id: string, enabled: boolean): Promise<void> {
    await this.withMutation(async () => {
      const updated = await (await this.getMachinesClient()).setSyncLocalSettings({ id, enabled });
      this.connectionsResource.setValue(this.upsertConnection(updated));
    });
  }

  async getSshConfigHosts(): Promise<SshConfigHost[]> {
    return await (await this.getSshClient()).getSshConfigHosts(undefined);
  }

  async getSshConfigHost(alias: string): Promise<SshConfigHost> {
    return await (await this.getSshClient()).getSshConfigHost({ alias });
  }

  async renameConnection(id: string, name: string): Promise<void> {
    await this.withMutation(async () => {
      await (await this.getMachinesClient()).renameMachine({ id, name });
      const current = this.connectionsResource.data ?? [];
      this.connectionsResource.setValue(
        current.map((connection) => (connection.id === id ? { ...connection, name } : connection))
      );
    });
  }

  async deleteConnection(id: string): Promise<void> {
    await this.withMutation(async () => {
      await (await this.getMachinesClient()).deleteMachine({ id });
      const currentConnections = this.connectionsResource.data ?? [];
      this.connectionsResource.setValue(
        currentConnections.filter((connection) => connection.id !== id)
      );
    });
  }

  async testConnection(
    config: SshConfig & { password?: string; passphrase?: string }
  ): Promise<ConnectionTestResult> {
    return await (await this.getSshClient()).testConnection(config);
  }

  async installSystemDependencies(
    input: InstallMachineSystemDependenciesInput
  ): Promise<InstallMachineSystemDependenciesResult> {
    return await runSystemDependencyInstall(await this.getMachinesClient(), input);
  }

  private get runtime(): SshConnectionsRuntime {
    return this.runtimeData;
  }

  private getSshClient(): Promise<SshClient> {
    this.sshClientPromise ??= this.sshClientOverride
      ? Promise.resolve(this.sshClientOverride)
      : getSshDomainClient();
    return this.sshClientPromise;
  }

  private getMachinesClient(): Promise<MachinesClient> {
    this.machinesClientPromise ??= this.machinesClientOverride
      ? Promise.resolve(this.machinesClientOverride)
      : getMachinesDomainClient();
    return this.machinesClientPromise;
  }

  private getHostsClient(): Promise<Pick<HostsClient, 'disconnect' | 'requestReady'>> {
    this.hostsClientPromise ??= this.hostsClientOverride
      ? Promise.resolve(this.hostsClientOverride)
      : getHostsClient();
    return this.hostsClientPromise;
  }

  private async initializeConnectionsModel(): Promise<void> {
    const client = await this.getSshClient();
    if (!this.started) return;

    const scope = createScope({ label: 'machines-store:ssh-connections' });
    const connectionsRemote = remote(sshContract.connections, client.connections, {
      scope,
      lingerMs: 15_000,
    });
    const model = connectionsRemote(undefined);

    observe(
      model.states.runtime,
      (snapshot) => {
        const runtime = snapshot.value ?? {};
        runInAction(() => {
          this.runtimeData = runtime;
          if (snapshot.status !== 'loading') this.modelReady = true;
        });
      },
      { scope }
    );

    runInAction(() => {
      this.modelScope = scope;
    });
    await whenReady(model.states.runtime, { scope });

    if (!this.started || this.modelScope !== scope) {
      await scope.dispose();
      return;
    }
  }

  private async ensureConnectionsModel(): Promise<void> {
    await this.start();
    if (!this.modelReady) throw new Error('SSH connections model is not ready');
  }

  private upsertConnection(savedConnection: SshConfig): SshConfig[] {
    const current = this.connectionsResource.data ?? [];
    const index = current.findIndex((connection) => connection.id === savedConnection.id);
    if (index === -1) return [...current, savedConnection];

    const next = [...current];
    next[index] = savedConnection;
    return next;
  }

  private async withMutation<T>(run: () => Promise<T>): Promise<T> {
    runInAction(() => {
      this.pendingMutations += 1;
    });

    try {
      return await run();
    } finally {
      runInAction(() => {
        this.pendingMutations = Math.max(0, this.pendingMutations - 1);
      });
    }
  }
}

export function createSystemDependenciesStore(): SystemDependenciesStore {
  return {
    installSystemDependencies: async (input: InstallMachineSystemDependenciesInput) =>
      await runSystemDependencyInstall(await getMachinesDomainClient(), input),
  };
}

async function runSystemDependencyInstall(
  client: MachinesClient,
  input: InstallMachineSystemDependenciesInput
): Promise<InstallMachineSystemDependenciesResult> {
  const result = await runDesktopLiveJob(
    machinesContract.installSystemDependencies,
    client.installSystemDependencies,
    input
  );
  if (!result.success) throw new Error(getHostDependencyErrorMessage(result.error));
  return result.data;
}
