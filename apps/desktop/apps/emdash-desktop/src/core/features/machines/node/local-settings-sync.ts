import {
  formatHostRef,
  isLocalHostRef,
  type HostRef,
  type SerializedHostRef,
} from '@emdash/core/primitives/host/api';
import {
  runtimeResolveErrorAsError,
  type RuntimeBroker,
} from '@emdash/core/services/runtime-broker/api';

export type LocalSettingsSyncDeps = {
  runtimes: Pick<RuntimeBroker, 'client'>;
  /** The local value mirrored to hosts with sync ON (files.watcherExclude). */
  getWatcherExclude: () => Promise<readonly string[]>;
  /** Whether the host's "Sync local settings" toggle is ON (connection metadata). */
  isSyncEnabled: (connectionId: string) => Promise<boolean>;
  logger: { warn(message: string, metadata?: Record<string, unknown>): void };
};

/**
 * Mirrors this desktop's local settings to remote hosts whose "Sync local
 * settings" toggle is ON (spec: release-code-prep §6). Pushes happen on host
 * attach, on local-setting change, and when the toggle flips ON. Semantics are
 * last-writer-wins; toggling OFF keeps the last mirrored value on the host.
 */
export class LocalSettingsSync {
  private readonly attached = new Map<SerializedHostRef, HostRef>();

  constructor(private readonly deps: LocalSettingsSyncDeps) {}

  async attachHost(host: HostRef): Promise<void> {
    if (isLocalHostRef(host)) return;
    this.attached.set(formatHostRef(host), host);
    await this.pushIfEnabled(host);
  }

  detachHost(host: HostRef): void {
    this.attached.delete(formatHostRef(host));
  }

  /** A local app setting in the synced class changed: re-mirror to attached hosts. */
  async handleLocalSettingsChanged(): Promise<void> {
    await Promise.all([...this.attached.values()].map((host) => this.pushIfEnabled(host)));
  }

  /** The per-host toggle changed. ON mirrors immediately; OFF keeps the last value. */
  async handleSyncToggled(connectionId: string, enabled: boolean): Promise<void> {
    if (!enabled) return;
    const host = [...this.attached.values()].find(
      (candidate) => candidate.type === 'remote' && candidate.id === connectionId
    );
    if (!host) return;
    await this.push(host);
  }

  private async pushIfEnabled(host: HostRef): Promise<void> {
    try {
      if (!(await this.deps.isSyncEnabled(host.id))) return;
    } catch (error) {
      this.warn(host, error);
      return;
    }
    await this.push(host);
  }

  private async push(host: HostRef): Promise<void> {
    try {
      const watcherExclude = await this.deps.getWatcherExclude();
      const runtime = await this.deps.runtimes.client(host);
      if (!runtime.success) throw runtimeResolveErrorAsError(runtime.error);
      const result = await runtime.data.hostSettings.update({
        watcherExclude: [...watcherExclude],
      });
      if (!result.success) throw new Error(result.error.message);
    } catch (error) {
      this.warn(host, error);
    }
  }

  private warn(host: HostRef, error: unknown): void {
    this.deps.logger.warn('LocalSettingsSync: push failed', {
      host: formatHostRef(host),
      error: String(error),
    });
  }
}
