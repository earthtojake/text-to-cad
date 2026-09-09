import { isNewerRelease, type WireInitializeResult } from '@emdash/core/workspace-server';
import type { Scope } from '@emdash/shared/concurrency';
import { retry, retrySchedules, systemClock, type Clock } from '@emdash/shared/scheduling';
import type { HostStateModel } from './state-model';
import { WorkspaceServerProtocolError } from './workspace-server/connect/protocol';
import type { WireConnectionManager } from './workspace-server/connect/wire-connection-manager';
import { workspaceServerLayout, type WorkspaceServerLayout } from './workspace-server/layout';
import {
  WorkspaceServerDaemonError,
  type RemoteWorkspaceServerDaemon,
} from './workspace-server/provision/daemon-control';
import type { RemoteHostProbe } from './workspace-server/provision/host-probe';
import {
  WorkspaceServerInstallError,
  type WorkspaceServerInstaller,
} from './workspace-server/provision/installer';
import { sshWorkspaceServerTarget } from './workspace-server/targets';

type HostServerOperationsDeps = {
  scope: Scope;
  state: HostStateModel;
  host: Pick<RemoteHostProbe, 'probe'>;
  installer: Pick<WorkspaceServerInstaller, 'availableVersion' | 'installedVersion' | 'install'>;
  daemon: Pick<RemoteWorkspaceServerDaemon, 'start' | 'stop'>;
  wire: Pick<WireConnectionManager, 'dialOnce' | 'invalidateConnection'>;
  /** Cached provisioned targets; dropped whenever an operation changes daemon state. */
  provision: { drop(connectionId: string): void };
  clock?: Clock;
};

type PendingOperation = {
  action: string;
  promise: Promise<void>;
};

type RefreshOptions = {
  force?: boolean;
};

type LatestVersionCacheEntry = {
  version: string;
  checkedAt: number;
};

const serverReadyRetrySchedule = retrySchedules.sequence([100, 250, 500, 1_000, 2_000]);
const latestVersionCacheTtlMs = 5 * 60_000;

export class HostServerOperations {
  private readonly operations = new Map<string, PendingOperation>();
  private readonly latestVersions = new Map<string, LatestVersionCacheEntry>();
  private readonly clock: Clock;

  constructor(private readonly deps: HostServerOperationsDeps) {
    this.clock = deps.clock ?? systemClock;
  }

  refresh(connectionId: string, options: RefreshOptions = {}): Promise<void> {
    const action = options.force ? 'refresh:force' : 'refresh';
    return this.serialized(connectionId, action, (signal) =>
      this.refreshUnserialized(connectionId, signal, options)
    );
  }

  install(connectionId: string): Promise<void> {
    return this.serialized(connectionId, 'install', async (signal) => {
      this.deps.provision.drop(connectionId);
      const layout = await this.resolveLayout(connectionId, signal);
      this.deps.state.set(connectionId, {
        status: 'booting',
        detail: 'Installing workspace server',
      });
      await this.deps.installer.install({ connectionId, layout, signal });
      const version = await this.deps.installer.installedVersion(connectionId, layout, signal);
      this.deps.state.set(connectionId, {
        status: 'booting',
        version,
        detail: 'Starting workspace server',
      });
      await this.deps.daemon.start(connectionId, layout, signal);
      await this.publishWhenReady(connectionId, layout, signal);
    });
  }

  start(connectionId: string): Promise<void> {
    return this.serialized(connectionId, 'start', async (signal) => {
      this.deps.provision.drop(connectionId);
      const { layout, version } = await this.resolveInstalled(connectionId, signal);
      this.deps.state.set(connectionId, {
        status: 'booting',
        version,
        detail: 'Starting workspace server',
      });
      await this.deps.daemon.start(connectionId, layout, signal);
      await this.publishWhenReady(connectionId, layout, signal);
    });
  }

  stop(connectionId: string): Promise<void> {
    return this.serialized(connectionId, 'stop', async (signal) => {
      this.deps.provision.drop(connectionId);
      const { layout, version } = await this.resolveInstalled(connectionId, signal);
      this.deps.state.set(connectionId, {
        status: 'shutting-down',
        version,
        detail: 'Shutting down workspace server',
      });
      await this.deps.wire.invalidateConnection(connectionId);
      await this.deps.daemon.stop(connectionId, layout, signal);
      this.deps.state.set(connectionId, {
        status: 'stopped',
        version,
        ...latestVersionState(this.cachedLatestVersion(connectionId), version),
      });
    });
  }

  restart(connectionId: string): Promise<void> {
    return this.serialized(connectionId, 'restart', async (signal) => {
      this.deps.provision.drop(connectionId);
      const { layout, version } = await this.resolveInstalled(connectionId, signal);
      this.deps.state.set(connectionId, {
        status: 'shutting-down',
        version,
        detail: 'Restarting workspace server',
      });
      await this.deps.wire.invalidateConnection(connectionId);
      await this.deps.daemon.stop(connectionId, layout, signal).catch(() => {});
      this.deps.state.set(connectionId, {
        status: 'booting',
        version,
        detail: 'Restarting workspace server',
      });
      await this.deps.daemon.start(connectionId, layout, signal);
      await this.publishWhenReady(connectionId, layout, signal);
    });
  }

  update(connectionId: string): Promise<void> {
    return this.serialized(connectionId, 'update', async (signal) => {
      this.deps.provision.drop(connectionId);
      const layout = await this.resolveLayout(connectionId, signal);
      this.deps.state.set(connectionId, {
        status: 'booting',
        detail: 'Updating workspace server',
      });
      await this.deps.installer.install({ connectionId, layout, signal });
      const version = await this.deps.installer.installedVersion(connectionId, layout, signal);
      this.deps.state.set(connectionId, {
        status: 'shutting-down',
        version,
        detail: 'Restarting workspace server',
      });
      await this.deps.wire.invalidateConnection(connectionId);
      await this.deps.daemon.stop(connectionId, layout, signal).catch(() => {});
      this.deps.state.set(connectionId, {
        status: 'booting',
        version,
        detail: 'Restarting workspace server',
      });
      await this.deps.daemon.start(connectionId, layout, signal);
      await this.publishWhenReady(connectionId, layout, signal);
    });
  }

  private async refreshUnserialized(
    connectionId: string,
    signal: AbortSignal,
    options: RefreshOptions
  ): Promise<void> {
    // Do not clear the current entry first: every branch below ends with a
    // full set(), and blanking the state would flicker the UI on each refresh.
    try {
      const layout = await this.resolveLayout(connectionId, signal);
      const version = await this.deps.installer.installedVersion(connectionId, layout, signal);
      if (!version) {
        this.deps.provision.drop(connectionId);
        this.deps.state.set(connectionId, { status: 'not-installed' });
        return;
      }
      const latestVersion = await this.resolveLatestVersion(connectionId, signal, options);

      try {
        const handshake = await this.deps.wire.dialOnce(
          sshWorkspaceServerTarget(connectionId, layout),
          { signal }
        );
        this.publishHealthy(connectionId, handshake, latestVersion);
      } catch (error) {
        this.deps.provision.drop(connectionId);
        if (error instanceof WorkspaceServerProtocolError) {
          this.publishFailure(connectionId, error, { version, latestVersion });
        } else {
          this.deps.state.set(connectionId, {
            status: 'stopped',
            version,
            ...latestVersionState(latestVersion, version),
          });
        }
      }
    } catch (error) {
      this.deps.provision.drop(connectionId);
      this.publishFailure(connectionId, error);
      throw error;
    }
  }

  private async resolveLayout(
    connectionId: string,
    signal: AbortSignal
  ): Promise<WorkspaceServerLayout> {
    const host = await this.deps.host.probe(connectionId, signal);
    return workspaceServerLayout(host.home);
  }

  private async resolveInstalled(
    connectionId: string,
    signal: AbortSignal
  ): Promise<{ layout: WorkspaceServerLayout; version: string }> {
    const layout = await this.resolveLayout(connectionId, signal);
    const version = await this.deps.installer.installedVersion(connectionId, layout, signal);
    if (!version) {
      this.deps.state.set(connectionId, { status: 'not-installed' });
      throw new HostServerOperationError('not-installed', 'The workspace server is not installed');
    }
    return { layout, version };
  }

  private async publishWhenReady(
    connectionId: string,
    layout: WorkspaceServerLayout,
    signal: AbortSignal
  ): Promise<void> {
    const target = sshWorkspaceServerTarget(connectionId, layout);
    const handshake = await retry(() => this.deps.wire.dialOnce(target, { signal }), {
      clock: this.clock,
      schedule: serverReadyRetrySchedule,
      signal,
      shouldRetry: (error) => !(error instanceof WorkspaceServerProtocolError),
    });
    this.publishHealthy(connectionId, handshake);
  }

  private publishHealthy(
    connectionId: string,
    handshake: WireInitializeResult,
    latestVersion = this.cachedLatestVersion(connectionId)
  ): void {
    this.deps.state.set(connectionId, {
      status: 'healthy',
      version: handshake.server.appVersion,
      ...latestVersionState(latestVersion, handshake.server.appVersion),
      startedAt: handshake.server.startedAt,
    });
  }

  private publishFailure(
    connectionId: string,
    error: unknown,
    metadata: { version?: string; latestVersion?: string } = {}
  ): void {
    const failure = operationFailure(error);
    if (failure.code === 'not-installed') return;
    const current = this.deps.state.get(connectionId);
    const version = metadata.version ?? current?.version;
    const latestVersion = metadata.latestVersion ?? this.cachedLatestVersion(connectionId);
    if (isProtocolFailure(failure.code)) {
      this.deps.state.set(connectionId, {
        status: 'healthy',
        ...versionState(version),
        ...latestVersionState(latestVersion, version),
        ...startedAtState(current?.startedAt),
        error: failure,
      });
      return;
    }
    this.deps.state.set(connectionId, {
      status: 'failed',
      ...versionState(version),
      ...latestVersionState(latestVersion, version),
      error: failure,
    });
  }

  private async resolveLatestVersion(
    connectionId: string,
    signal: AbortSignal,
    options: RefreshOptions
  ): Promise<string | undefined> {
    const cached = this.latestVersions.get(connectionId);
    if (
      !options.force &&
      cached !== undefined &&
      this.clock.now() - cached.checkedAt < latestVersionCacheTtlMs
    ) {
      return cached.version;
    }

    try {
      const version = await this.deps.installer.availableVersion(connectionId, signal);
      this.latestVersions.set(connectionId, { version, checkedAt: this.clock.now() });
      return version;
    } catch {
      return cached?.version;
    }
  }

  private cachedLatestVersion(connectionId: string): string | undefined {
    return this.latestVersions.get(connectionId)?.version;
  }

  private serialized(
    connectionId: string,
    action: string,
    operation: (signal: AbortSignal) => Promise<void>
  ): Promise<void> {
    const existing = this.operations.get(connectionId);
    if (existing?.action === action) return existing.promise;

    const predecessor = existing?.promise.catch(() => {});
    const promise = (predecessor ?? Promise.resolve())
      .then(() => this.deps.scope.run(`${action}:${connectionId}`, operation).value())
      .catch((error: unknown) => {
        this.publishFailure(connectionId, error);
        throw error;
      })
      .finally(() => {
        if (this.operations.get(connectionId)?.promise === promise) {
          this.operations.delete(connectionId);
        }
      });
    this.operations.set(connectionId, { action, promise });
    return promise;
  }
}

class HostServerOperationError extends Error {
  readonly name = 'HostServerOperationError';

  constructor(
    readonly code: string,
    message: string
  ) {
    super(message);
  }
}

function operationFailure(error: unknown): { code: string; message: string } {
  if (error instanceof HostServerOperationError) {
    return { code: error.code, message: error.message };
  }
  if (error instanceof WorkspaceServerInstallError) {
    return { code: error.code, message: error.message };
  }
  if (error instanceof WorkspaceServerProtocolError) {
    return { code: `protocol-${error.details.action}`, message: error.message };
  }
  if (error instanceof WorkspaceServerDaemonError) {
    return { code: 'daemon-operation-failed', message: error.message };
  }
  return {
    code: 'connection-failed',
    message: error instanceof Error ? error.message : String(error),
  };
}

function isProtocolFailure(code: string): boolean {
  return code === 'protocol-upgrade-client' || code === 'protocol-upgrade-server';
}

function latestVersionState(
  latestVersion: string | undefined,
  installedVersion: string | undefined
): { latestVersion?: string; updateAvailable?: true } {
  if (latestVersion === undefined) return {};
  if (installedVersion === undefined || !isNewerRelease(latestVersion, installedVersion)) {
    return { latestVersion };
  }
  return { latestVersion, updateAvailable: true };
}

function versionState(version: string | undefined): { version?: string } {
  return version === undefined ? {} : { version };
}

function startedAtState(startedAt: number | undefined): { startedAt?: number } {
  return startedAt === undefined ? {} : { startedAt };
}
