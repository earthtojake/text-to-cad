import type { WireInitializeResult } from '@emdash/core/workspace-server';
import type { Scope } from '@emdash/shared/concurrency';
import {
  retry,
  retrySchedules,
  systemClock,
  throwIfAborted,
  type Clock,
} from '@emdash/shared/scheduling';
import type { SshWorkspaceServerTarget } from '../../../api/targets';
import type { HostStateModel } from '../../state-model';
import { WorkspaceServerProtocolError } from '../connect/protocol';
import type { WireConnectionManager } from '../connect/wire-connection-manager';
import { workspaceServerLayout, type WorkspaceServerLayout } from '../layout';
import type { WorkspaceServerSshPort } from '../ports';
import { sshWorkspaceServerTarget } from '../targets';
import type { RemoteWorkspaceServerDaemon } from './daemon-control';
import type { RemoteHostProbe } from './host-probe';
import { WorkspaceServerInstallError, type WorkspaceServerInstaller } from './installer';

export type WorkspaceServerProvisionErrorCode =
  | 'connection-failed'
  | 'unsupported-platform'
  | 'artifact-download-failed'
  | 'install-failed'
  | 'daemon-start-failed'
  | 'protocol-incompatible';

export class WorkspaceServerProvisionError extends Error {
  readonly name = 'WorkspaceServerProvisionError';

  constructor(
    readonly code: WorkspaceServerProvisionErrorCode,
    message: string,
    options?: ErrorOptions
  ) {
    super(message, options);
  }
}

type WorkspaceServerProvisionerDeps = {
  scope: Scope;
  ssh: WorkspaceServerSshPort;
  host: RemoteHostProbe;
  installer: WorkspaceServerInstaller;
  daemon: RemoteWorkspaceServerDaemon;
  model: HostStateModel;
  wire: Pick<WireConnectionManager, 'dialOnce'>;
  devAutoUpdate?: boolean;
  logger?: { warn(message: string, metadata?: Record<string, unknown>): void };
  clock?: Clock;
};

type EnsureRun = {
  token: symbol;
  scope: Scope;
  promise: Promise<SshWorkspaceServerTarget>;
};

type DialOutcome =
  | { kind: 'ready'; handshake: WireInitializeResult }
  | { kind: 'client-outdated'; error: WorkspaceServerProtocolError }
  | { kind: 'server-outdated'; error: WorkspaceServerProtocolError }
  | { kind: 'unreachable'; error: unknown };

const daemonReadyRetrySchedule = retrySchedules.sequence([100, 250, 500, 1_000, 2_000]);

export class WorkspaceServerProvisioner {
  private readonly runs = new Map<string, EnsureRun>();
  private readonly targets = new Map<string, SshWorkspaceServerTarget>();
  private readonly dialOnce: WireConnectionManager['dialOnce'];
  private readonly clock: Clock;

  constructor(private readonly deps: WorkspaceServerProvisionerDeps) {
    this.dialOnce = (target, options) => deps.wire.dialOnce(target, options);
    this.clock = deps.clock ?? systemClock;
  }

  ensure(connectionId: string): Promise<SshWorkspaceServerTarget> {
    const cached = this.targets.get(connectionId);
    if (cached && !this.deps.devAutoUpdate) return Promise.resolve(cached);
    const existing = this.runs.get(connectionId);
    if (existing) return existing.promise;

    const runScope = this.deps.scope.child(`ensure:${connectionId}`);
    const run = runScope.run('provision', (signal) => this.runEnsure(connectionId, signal));
    const token = Symbol(connectionId);
    const promise = run
      .value()
      .then((target) => {
        if (this.runs.get(connectionId)?.token === token && !this.deps.devAutoUpdate) {
          this.targets.set(connectionId, target);
        }
        return target;
      })
      .finally(() => {
        if (this.runs.get(connectionId)?.token === token) this.runs.delete(connectionId);
        void runScope.dispose();
      });
    const entry: EnsureRun = {
      token,
      scope: runScope,
      promise,
    };
    entry.promise.catch(() => {});
    this.runs.set(connectionId, entry);
    return entry.promise;
  }

  /**
   * Forgets a previously provisioned target so the next ensure() re-verifies
   * the remote daemon. Call whenever the daemon may no longer be running
   * (connection lost, reconnect failed, explicit lifecycle operations).
   */
  drop(connectionId: string): void {
    this.targets.delete(connectionId);
  }

  async cancel(connectionId: string): Promise<void> {
    this.targets.delete(connectionId);
    const run = this.runs.get(connectionId);
    if (!run) return;
    this.runs.delete(connectionId);
    this.deps.model.remove(connectionId);
    await run.scope.dispose(new Error(`Workspace-server ensure cancelled for ${connectionId}`));
  }

  private async runEnsure(
    connectionId: string,
    signal: AbortSignal
  ): Promise<SshWorkspaceServerTarget> {
    try {
      // Intentionally quiet until the outcome is known: routine ensures against
      // an already-running server must not flap the published status.
      let host;
      try {
        host = await this.deps.host.probe(connectionId, signal);
      } catch (error) {
        throw provisionError('connection-failed', 'Could not inspect the remote machine', error);
      }
      throwIfAborted(signal);

      const layout = workspaceServerLayout(host.home);
      const target = sshWorkspaceServerTarget(connectionId, layout);

      const outcome = await this.tryDial(target, signal);
      switch (outcome.kind) {
        case 'ready': {
          const handshake =
            (await this.maybeDevUpdateRunningDaemon(
              connectionId,
              layout,
              target,
              outcome.handshake,
              signal
            )) ?? outcome.handshake;
          this.publishHealthy(connectionId, handshake);
          return target;
        }
        case 'client-outdated':
          throw protocolError(outcome.error);
        case 'server-outdated':
          await this.install(connectionId, layout, signal);
          await this.restart(connectionId, layout, signal);
          this.publishHealthy(connectionId, await this.waitUntilReady(target, signal));
          return target;
        case 'unreachable':
          break;
      }

      await this.install(connectionId, layout, signal);
      await this.start(connectionId, layout, signal);

      this.publishHealthy(connectionId, await this.waitUntilReady(target, signal));
      return target;
    } catch (error) {
      if (signal.aborted) throw error;
      const failure =
        error instanceof WorkspaceServerProvisionError
          ? error
          : provisionError('connection-failed', 'Workspace-server provisioning failed', error);
      this.deps.model.set(connectionId, {
        status: 'failed',
        error: { code: failure.code, message: failure.message },
      });
      throw failure;
    }
  }

  private async maybeDevUpdateRunningDaemon(
    connectionId: string,
    layout: WorkspaceServerLayout,
    target: SshWorkspaceServerTarget,
    handshake: WireInitializeResult,
    signal: AbortSignal
  ): Promise<WireInitializeResult | null> {
    if (!this.deps.devAutoUpdate) return null;

    let availableVersion: string;
    try {
      availableVersion = await this.deps.installer.availableVersion(connectionId, signal);
    } catch (error) {
      this.deps.logger?.warn('Could not resolve latest workspace-server dev version', {
        connectionId,
        error: error instanceof Error ? error.message : String(error),
      });
      return null;
    }

    // Dev versions put a commit SHA before their timestamp, so SemVer order does not represent
    // build recency. Any different published dev artifact must replace the running one.
    if (availableVersion === handshake.server.appVersion) return null;
    await this.install(connectionId, layout, signal, availableVersion);
    await this.restart(connectionId, layout, signal);
    return await this.waitUntilReady(target, signal);
  }

  private async install(
    connectionId: string,
    layout: WorkspaceServerLayout,
    signal: AbortSignal,
    version?: string
  ): Promise<void> {
    this.deps.model.set(connectionId, {
      status: 'booting',
      detail: 'Installing workspace server',
    });
    try {
      await this.deps.installer.install({ connectionId, layout, signal, version });
    } catch (error) {
      if (error instanceof WorkspaceServerInstallError) {
        throw provisionError(error.code, error.message, error);
      }
      throw provisionError('install-failed', 'Workspace-server installation failed', error);
    }
  }

  private async start(
    connectionId: string,
    layout: WorkspaceServerLayout,
    signal: AbortSignal
  ): Promise<void> {
    this.deps.model.set(connectionId, {
      status: 'booting',
      detail: 'Starting workspace server',
    });
    try {
      await this.deps.daemon.start(connectionId, layout, signal);
    } catch (error) {
      throw provisionError('daemon-start-failed', 'Could not start the workspace server', error);
    }
  }

  private async restart(
    connectionId: string,
    layout: WorkspaceServerLayout,
    signal: AbortSignal
  ): Promise<void> {
    this.deps.model.set(connectionId, {
      status: 'booting',
      detail: 'Restarting workspace server',
    });
    try {
      await this.deps.daemon.restart(connectionId, layout, signal);
    } catch (error) {
      throw provisionError('daemon-start-failed', 'Could not restart the workspace server', error);
    }
  }

  private async waitUntilReady(
    target: SshWorkspaceServerTarget,
    signal: AbortSignal
  ): Promise<WireInitializeResult> {
    try {
      return await retry(() => this.dialOnce(target, { signal }), {
        clock: this.clock,
        schedule: daemonReadyRetrySchedule,
        signal,
        shouldRetry: (error) => !(error instanceof WorkspaceServerProtocolError),
      });
    } catch (error) {
      throwIfAborted(signal);
      if (error instanceof WorkspaceServerProtocolError) throw protocolError(error);
      throw provisionError(
        'daemon-start-failed',
        'The workspace server did not become ready',
        error
      );
    }
  }

  private async tryDial(
    target: SshWorkspaceServerTarget,
    signal: AbortSignal
  ): Promise<DialOutcome> {
    try {
      const handshake = await this.dialOnce(target, { signal });
      return { kind: 'ready', handshake };
    } catch (error) {
      throwIfAborted(signal);
      if (!(error instanceof WorkspaceServerProtocolError)) {
        return { kind: 'unreachable', error };
      }
      return error.details.action === 'upgrade-client'
        ? { kind: 'client-outdated', error }
        : { kind: 'server-outdated', error };
    }
  }

  private publishHealthy(connectionId: string, handshake: WireInitializeResult): void {
    this.deps.model.set(connectionId, {
      status: 'healthy',
      version: handshake.server.appVersion,
      startedAt: handshake.server.startedAt,
    });
  }
}

function protocolError(error: WorkspaceServerProtocolError): WorkspaceServerProvisionError {
  return provisionError('protocol-incompatible', error.message, error);
}

function provisionError(
  code: WorkspaceServerProvisionErrorCode,
  message: string,
  cause?: unknown
): WorkspaceServerProvisionError {
  const suffix = cause instanceof Error && cause.message !== message ? `: ${cause.message}` : '';
  return new WorkspaceServerProvisionError(code, `${message}${suffix}`, { cause });
}
