import { EMDASH_CONFIG_FILE } from '@emdash/core/primitives/emdash-config/api';
import type { ScriptRuns } from '@emdash/core/runtimes/scripts/api';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { toast } from '@emdash/ui/react/primitives';
import { ReplicaLog } from '@emdash/wire/live';
import { observe, pin, remote, type RemoteModel } from '@emdash/wire/state';
import type { Terminal } from '@xterm/xterm';
import { action, computed, makeObservable, observable, onBecomeObserved, runInAction } from 'mobx';
import { watchFileContent } from '@core/features/files/api/browser/file-content';
import { getProjectsWireClient } from '@core/features/projects/api/browser/client';
import type { FrontendPtyConnector } from '@core/features/terminals/api/browser/pty/pty';
import { PtySession } from '@core/features/terminals/api/browser/pty/pty-session';
import { createXtermLogSink } from '@core/features/terminals/api/browser/pty/xterm-log-sink';
import { resolveWorkspacePath } from '@core/features/workspaces/api/browser/workspace-path';
import { lifecycleScriptsWireContract } from '@core/features/workspaces/api/lifecycle-scripts-wire-contract';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { log } from '@core/primitives/logging/browser/logger';
import { makePtySessionId } from '@core/primitives/pty/api';
import { createLifecycleScriptTerminalId } from '@core/primitives/terminals/api';
import { type TabViewProvider } from '@core/primitives/workbench-shell/browser/tabs/generic-tab-view';
import {
  addTabId,
  setNextTabActive,
  setPreviousTabActive,
  setTabActive,
  setTabActiveIndex,
} from '@core/primitives/workbench-shell/browser/tabs/tab-utils';
import { getLifecycleScriptsClient, getProjectSettingsClient } from './client';

export type ScriptType = 'prepare' | 'setup' | 'run' | 'teardown';

export type LifecycleScriptData = {
  id: string;
  type: ScriptType;
  label: string;
  command: string;
};

export type LifecycleScriptStatus = 'idle' | 'running' | 'succeeded' | 'failed' | 'cancelled';

/**
 * One drawer tab, bound to the host scripts plane (spec:
 * activation-scripts-via-terminals): output streams from the scripts runtime's
 * PTY, run/stop go through the lifecycle-scripts domain, and status arrives
 * through the shared runs model — so activation-started runs show live here
 * exactly like manually started ones.
 */
export class LifecycleScriptStore {
  data: LifecycleScriptData;
  session: PtySession;
  status: LifecycleScriptStatus = 'idle';
  private readonly workspaceId: string;
  constructor(data: LifecycleScriptData, projectId: string, workspaceId: string) {
    this.data = data;
    this.workspaceId = workspaceId;
    this.session = new PtySession(
      makePtySessionId(projectId, workspaceId, data.id),
      undefined,
      undefined,
      undefined,
      createScriptsConnector(workspaceId, data.type)
    );
    makeObservable(this, {
      data: observable,
      session: observable,
      status: observable,
      isRunning: computed,
      setStatus: action,
    });
  }

  get isRunning(): boolean {
    return this.status === 'running';
  }

  setStatus(status: LifecycleScriptStatus): void {
    this.status = status;
  }

  /**
   * Starts a manual run; the host builds the request from the record. Progress
   * and the final status arrive through the runs model, never from this call.
   */
  async run(): Promise<void> {
    if (this.isRunning) return;
    const client = await getLifecycleScriptsClient();
    const result = await client.start({
      workspaceId: this.workspaceId,
      script: this.data.type,
      provenance: 'manual',
    });
    if (!result.success) {
      log.warn('lifecycle-scripts: start rejected', {
        script: this.data.type,
        error: result.error,
      });
      toast.error(`Could not start the ${this.data.label} script`, {
        description:
          'message' in result.error ? result.error.message : 'The workspace no longer exists',
      });
    }
  }

  stop(): void {
    void getLifecycleScriptsClient()
      .then(async (client) => {
        const result = await client.stop({ workspaceId: this.workspaceId, script: this.data.type });
        if (!result.success) {
          log.warn('lifecycle-scripts: stop failed', {
            script: this.data.type,
            error: result.error,
          });
        }
      })
      .catch((error) => {
        log.warn('lifecycle-scripts: failed to stop script', { script: this.data.type, error });
      });
  }

  dispose() {
    this.session.destroy();
  }
}

export class LifecycleScriptsStore implements TabViewProvider<LifecycleScriptStore, never> {
  private readonly projectId: string;
  private readonly workspaceId: string;
  private _loaded = false;
  private _disposed = false;
  private _refreshSeq = 0;
  private readonly _unsubscribes: Array<() => void> = [];
  private runsScope: Scope | null = null;
  private runsRemote: RemoteModel<typeof lifecycleScriptsWireContract.runs> | null = null;
  scripts = observable.map<string, LifecycleScriptStore>();
  tabOrder: string[] = [];
  activeTabId: string | undefined = undefined;

  constructor(
    projectId: string,
    workspaceId: string,
    workspacePath: string,
    sshConnectionId?: string
  ) {
    this.projectId = projectId;
    this.workspaceId = workspaceId;
    makeObservable(this, {
      scripts: observable,
      tabOrder: observable,
      activeTabId: observable,
      tabs: computed,
      activeTab: computed,
      runningScript: computed,
      failedScript: computed,
      setNextTabActive: action,
      setPreviousTabActive: action,
      setTabActiveIndex: action,
      setActiveTab: action,
    });
    onBecomeObserved(this, 'tabOrder', () => {
      if (this._loaded) return;
      void this.load();
    });
    void getProjectsWireClient().then(async (client) => {
      const unsubscribe = await client.events.subscribe(undefined, {
        onEvent: (event) => {
          if (event.projectId === this.projectId) this.reloadIfLoaded();
        },
        onGap: () => this.reloadIfLoaded(),
      });
      if (this._disposed) unsubscribe();
      else this._unsubscribes.push(unsubscribe);
    });
    void watchFileContent(
      hostFileRefFromNativePath(
        resolveWorkspacePath(workspacePath, EMDASH_CONFIG_FILE),
        sshConnectionId
      ),
      () => {
        this.reloadIfLoaded();
      }
    )
      .then((unsubscribe) => {
        if (this._disposed) unsubscribe();
        else this._unsubscribes.push(unsubscribe);
      })
      .catch(() => {});
    this.bindRunsState();
  }

  get tabs(): LifecycleScriptStore[] {
    return this.tabOrder
      .map((id) => this.scripts.get(id))
      .filter(Boolean) as LifecycleScriptStore[];
  }

  get activeTab(): LifecycleScriptStore | undefined {
    return this.activeTabId ? this.scripts.get(this.activeTabId) : undefined;
  }

  get runningScript(): LifecycleScriptStore | undefined {
    return this.tabs.find((script) => script.status === 'running');
  }

  get failedScript(): LifecycleScriptStore | undefined {
    return this.tabs.find((script) => script.status === 'failed');
  }

  setActiveTab(id: string): void {
    setTabActive(this, id);
  }

  setNextTabActive(): void {
    setNextTabActive(this);
  }

  setPreviousTabActive(): void {
    setPreviousTabActive(this);
  }

  setTabActiveIndex(index: number): void {
    setTabActiveIndex(this, index);
  }

  closeActiveTab(): void {
    // lifecycle scripts are not closeable
  }

  addTab(_args: never): void {
    // lifecycle scripts come from settings, not user actions
  }

  removeTab(_id: string): void {
    // lifecycle scripts are not removeable
  }

  reorderTabs(_fromIndex: number, _toIndex: number): void {
    // lifecycle scripts have a fixed order
  }

  private async load(): Promise<void> {
    if (this._disposed) return;
    this._loaded = true;
    await this.reload();
  }

  private reloadIfLoaded(): void {
    if (!this._loaded || this._disposed) return;
    void this.reload();
  }

  private async reload(): Promise<void> {
    if (this._disposed) return;
    const refreshSeq = ++this._refreshSeq;
    const result = await (
      await getProjectSettingsClient()
    ).getSettings({ workspaceId: this.workspaceId });
    if (this._disposed) return;
    if (!result.success) return;
    const settings = result.data;

    const entries: { type: ScriptType; command: string; label: string }[] = [];
    if (settings.scripts?.prepare) {
      entries.push({ type: 'prepare', command: settings.scripts.prepare, label: 'Prepare' });
    }
    if (settings.scripts?.setup) {
      entries.push({ type: 'setup', command: settings.scripts.setup, label: 'Setup' });
    }
    if (settings.scripts?.run) {
      entries.push({ type: 'run', command: settings.scripts.run, label: 'Run' });
    }
    if (settings.scripts?.teardown) {
      entries.push({ type: 'teardown', command: settings.scripts.teardown, label: 'Teardown' });
    }

    const resolved = entries.map((entry) => ({
      ...entry,
      id: createLifecycleScriptTerminalId(entry.type),
    }));
    if (refreshSeq !== this._refreshSeq || this._disposed) return;

    runInAction(() => {
      if (this._disposed) return;
      const incomingIds = new Set(resolved.map((entry) => entry.id));

      for (const id of Array.from(this.scripts.keys())) {
        if (incomingIds.has(id)) continue;
        this.scripts.get(id)?.dispose();
        this.scripts.delete(id);
        this.tabOrder = this.tabOrder.filter((tabId) => tabId !== id);
      }

      for (const entry of resolved) {
        const data = { id: entry.id, type: entry.type, label: entry.label, command: entry.command };
        const existing = this.scripts.get(entry.id);
        if (existing) {
          Object.assign(existing.data, data);
        } else {
          const store = new LifecycleScriptStore(data, this.projectId, this.workspaceId);
          this.scripts.set(entry.id, store);
          addTabId(this, entry.id);
        }
      }

      this.tabOrder = resolved.map((entry) => entry.id);
      if (!this.activeTabId && this.tabOrder.length > 0) {
        this.activeTabId = this.tabOrder[0];
      } else if (this.activeTabId && !this.scripts.has(this.activeTabId)) {
        this.activeTabId = this.tabOrder[0];
      }
    });
  }

  dispose(): void {
    if (this._disposed) return;
    this._disposed = true;
    this._refreshSeq++;
    for (const unsubscribe of this._unsubscribes) unsubscribe();
    void this.runsRemote?.dispose();
    this.runsScope = null;
    this.runsRemote = null;
    for (const script of this.scripts.values()) {
      script.dispose();
    }
    this.scripts.clear();
    this.tabOrder = [];
    this.activeTabId = undefined;
  }

  /**
   * Status comes from the scripts runtime's runs model — the same source the
   * Activity timeline observes host-side — so every run shows here regardless
   * of who started it.
   */
  private bindRunsState(): void {
    if (typeof window === 'undefined') return;
    void (async () => {
      const client = await getLifecycleScriptsClient();
      if (this._disposed) return;
      const scope = createScope({ label: `lifecycle-scripts:${this.workspaceId}` });
      const runs = remote(lifecycleScriptsWireContract.runs, client.runs, { scope });
      const model = runs({ workspaceId: this.workspaceId });
      pin(scope, [model.states.current]);
      observe(
        model.states.current,
        (current) => {
          if (current.value !== undefined) this.handleRunsState(current.value);
        },
        { scope }
      );
      this.runsScope = scope;
      this.runsRemote = runs;
      if (this._disposed) void runs.dispose();
    })();
  }

  private handleRunsState(runs: ScriptRuns): void {
    runInAction(() => {
      for (const script of this.scripts.values()) {
        const run = runs[script.data.type];
        script.setStatus(run ? toScriptStatus(run.status) : 'idle');
      }
    });
  }
}

function toScriptStatus(status: ScriptRuns[string]['status']): LifecycleScriptStatus {
  switch (status) {
    case 'running':
      return 'running';
    case 'succeeded':
      return 'succeeded';
    case 'cancelled':
      return 'cancelled';
    case 'failed':
    case 'timed-out':
      return 'failed';
  }
}

function createScriptsConnector(workspaceId: string, script: ScriptType): FrontendPtyConnector {
  let logBinding: ReplicaLog | null = null;
  let clientPromise: ReturnType<typeof getLifecycleScriptsClient> | null = null;
  const client = () => {
    clientPromise ??= getLifecycleScriptsClient();
    return clientPromise;
  };

  return {
    async connect(terminal: Terminal) {
      const runtime = await client();
      logBinding = new ReplicaLog(runtime.output.handle({ workspaceId, script }), {
        store: createXtermLogSink(terminal),
      });
      await logBinding.ready;
      return () => {
        void logBinding?.dispose();
        logBinding = null;
      };
    },
    sendInput(data: string) {
      void client()
        .then(async (runtime) => {
          const result = await runtime.sendInput({ workspaceId, script, data });
          if (!result.success) {
            log.warn('lifecycle-scripts: input failed', { script, error: result.error });
          }
        })
        .catch((error) => {
          log.warn('lifecycle-scripts: failed to send input', { script, error });
        });
    },
    resize(cols: number, rows: number) {
      void client()
        .then(async (runtime) => {
          const result = await runtime.resize({ workspaceId, script, cols, rows });
          if (!result.success) {
            log.warn('lifecycle-scripts: resize failed', { script, error: result.error });
          }
        })
        .catch((error) => {
          log.warn('lifecycle-scripts: failed to resize', { script, error });
        });
    },
  };
}
