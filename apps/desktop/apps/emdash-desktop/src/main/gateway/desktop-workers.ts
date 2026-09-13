import { join } from 'node:path';
import { acpApiContract, type AcpApiContract } from '@emdash/core/runtimes/acp/api';
import { acpWorkerSpec } from '@emdash/core/runtimes/acp/node';
import {
  agentConfigContract,
  type AgentConfigContract,
} from '@emdash/core/runtimes/agent-config/api';
import { agentConfigWorkerSpec } from '@emdash/core/runtimes/agent-config/node';
import {
  conversationsContract,
  type ConversationsContract,
} from '@emdash/core/runtimes/conversations/api';
import { conversationsWorkerSpec } from '@emdash/core/runtimes/conversations/node';
import { fileSearchContract, type FileSearchContract } from '@emdash/core/runtimes/file-search/api';
import { fileSearchWorkerSpec } from '@emdash/core/runtimes/file-search/node';
import { filesContract, type FilesContract } from '@emdash/core/runtimes/files/api';
import { filesWorkerSpec } from '@emdash/core/runtimes/files/node';
import { gitContract, type GitContract } from '@emdash/core/runtimes/git/api';
import { gitWorkerSpec } from '@emdash/core/runtimes/git/node';
import {
  hostSettingsContract,
  type HostSettingsContract,
} from '@emdash/core/runtimes/host-settings/api';
import { hostSettingsWorkerSpec } from '@emdash/core/runtimes/host-settings/node';
import {
  resourceUsageContract,
  type ResourceUsageContract,
} from '@emdash/core/runtimes/resource-usage/api';
import { resourceUsageWorkerSpec } from '@emdash/core/runtimes/resource-usage/node';
import { scriptsContract, type ScriptsContract } from '@emdash/core/runtimes/scripts/api';
import { scriptsWorkerSpec } from '@emdash/core/runtimes/scripts/node';
import { terminalsContract, type TerminalsContract } from '@emdash/core/runtimes/terminals/api';
import { terminalsWorkerSpec } from '@emdash/core/runtimes/terminals/node';
import { tuiAgentsContract, type TuiAgentsContract } from '@emdash/core/runtimes/tui-agents/api';
import { tuiAgentsWorkerSpec } from '@emdash/core/runtimes/tui-agents/node';
import {
  workspaceRegistryContract,
  type WorkspaceRegistryContract,
} from '@emdash/core/runtimes/workspace-registry/api';
import { workspaceRegistryWorkerSpec } from '@emdash/core/runtimes/workspace-registry/node';
import { buildDescriptorFromProvider } from '@emdash/core/services/agent-plugins/api/plugins';
import { NodeExecutionContext } from '@emdash/core/services/exec/api';
import { fsWatchWorkerSpec } from '@emdash/core/services/fs-watch/node';
import {
  CORE_DEPENDENCIES,
  createHostDependenciesComponent,
  type HostDependenciesContract,
} from '@emdash/core/services/host-dependencies/node';
import { createUserShellEnvController } from '@emdash/core/services/shell-env/node';
import { pluginRegistry } from '@emdash/plugins/agents';
import type { Unsubscribe } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import { queuedClient, type ContractClient } from '@emdash/wire/rpc';
import {
  createVitalsCollectingSpawner,
  createWireWorkerHost,
  type WireWorkerState,
} from '@emdash/wire/worker';
import { childProcessSpawner } from '@emdash/wire/worker/node';
import { app } from 'electron';
import { GitHubApiAuthService } from '@core/features/github/api/node/services/github-api-auth-service';
import { githubApiBaseUrlForHost } from '@core/features/github/api/node/services/github-api-base-url';
import { mementoSweepPolicies } from '@core/manifests/shared/memento-catalog';
import { mementosWireContract, type MementosWireContract } from '@core/primitives/mementos/api';
import { mementosComponent } from '@core/services/mementos/node';
import { pullRequestsContract, type PullRequestsContract } from '@core/services/pull-requests/api';
import { pullRequestsComponent } from '@core/services/pull-requests/node';
import { createPullRequestsGitHubAuthController } from '@core/services/pull-requests/node/pull-requests-auth';
import { resolvePullRequestSyncIdentity } from '@core/services/pull-requests/node/sync-identity';
import { resolveFileSearchDatabasePath } from '@main/core/file-search/database-path';
import { providerAccountRegistry } from '@main/core/provider-accounts/provider-account-registry-instance';
import { sessionIntentFilePaths } from '@main/core/runtime/session-intent-stores';
import { getGitExecutable } from '@main/core/utils/exec';
import { desktopKeyValueStore } from '@main/db/kv';
import { withCadRuntimeOnPath } from '@main/host/cad/cad-runtime-service';
import { log } from '@main/lib/logger';
import { telemetryService } from '@main/lib/telemetry';
import { refreshUserEnv, userShellEnvManager } from '@main/lib/userEnv';
import { desktopWorkerPath } from './worker-paths';

export type AcpRuntimeClient = ContractClient<AcpApiContract>;
export type AgentConfigRuntimeClient = ContractClient<AgentConfigContract>;
export type ConversationsRuntimeClient = ContractClient<ConversationsContract>;
export type FileSearchRuntimeClient = ContractClient<FileSearchContract>;
export type FilesRuntimeClient = ContractClient<FilesContract>;
export type GitRuntimeClient = ContractClient<GitContract>;
export type HostSettingsRuntimeClient = ContractClient<HostSettingsContract>;
export type ResourceUsageRuntimeClient = ContractClient<ResourceUsageContract>;
export type ScriptsRuntimeClient = ContractClient<ScriptsContract>;
export type HostDependenciesClient = ContractClient<HostDependenciesContract>;
export type MementosRuntimeClient = ContractClient<MementosWireContract>;
export type PullRequestsRuntimeClient = ContractClient<PullRequestsContract>;
export type TerminalsRuntimeClient = ContractClient<TerminalsContract>;
export type TuiAgentsRuntimeClient = ContractClient<TuiAgentsContract>;
export type WorkspaceRegistryRuntimeClient = ContractClient<WorkspaceRegistryContract>;

export type DesktopRuntimeClients = {
  readonly acp: AcpRuntimeClient;
  readonly agentConfig: AgentConfigRuntimeClient;
  readonly conversations: ConversationsRuntimeClient;
  readonly fileSearch: FileSearchRuntimeClient;
  readonly files: FilesRuntimeClient;
  readonly git: GitRuntimeClient;
  readonly hostDependencies: HostDependenciesClient;
  readonly hostSettings: HostSettingsRuntimeClient;
  readonly mementos: MementosRuntimeClient;
  readonly pullRequests: PullRequestsRuntimeClient;
  readonly resourceUsage: ResourceUsageRuntimeClient;
  readonly scripts: ScriptsRuntimeClient;
  readonly terminals: TerminalsRuntimeClient;
  readonly tuiAgents: TuiAgentsRuntimeClient;
  readonly workspaceRegistry: WorkspaceRegistryRuntimeClient;
};

/**
 * Worker status visibility for consumers that project agent liveness into the
 * renderer. The backing worker may not exist yet when a consumer subscribes
 * (workers spawn behind the window under the window-first boot); the
 * subscription attaches as soon as the worker materializes.
 */
export type WorkerStatusSource = {
  onStateChanged(cb: (state: WireWorkerState) => void): Unsubscribe;
};

export type DesktopRuntimeWorkers = {
  readonly acp: WorkerStatusSource;
  readonly tuiAgents: WorkerStatusSource;
};

export type DesktopWorkersHandle = {
  readonly clients: DesktopRuntimeClients;
  readonly workers: DesktopRuntimeWorkers;
  /** Resolves after every local Host runtime has completed its Wire worker handshake. */
  runtimeReady(): Promise<void>;
  /**
   * Activate per-worker vitals self-sampling (telemetry-sampled sessions
   * only). Reaches every live worker and any worker spawned later.
   */
  startVitalsSampling(intervalMs: number): void;
  dispose(): Promise<void>;
};

export type StartDesktopWorkersDeps = {
  readonly scope: Scope;
  getFilesSettings(): Promise<{ watcherExclude: string[] }>;
};

/**
 * Creates every desktop worker and returns immediately with queueing
 * (barrier-style) clients: callers never wait for worker readiness here —
 * every client call internally awaits its own worker's `ready()` and a spawn
 * failure rejects that worker's queued and future calls (ticket 01's
 * queueing). Worker readiness continues to settle in the background.
 *
 * Spawn-capable workers resolve the current login-shell environment through a
 * parent-owned dependency (see agents/risky-areas/pty.md).
 */
export async function startDesktopWorkers(
  deps: StartDesktopWorkersDeps
): Promise<DesktopWorkersHandle> {
  const workerScope = deps.scope.child('wire-workers');
  const vitalsSpawner = createVitalsCollectingSpawner(childProcessSpawner(), {
    onReport: (workerName, vitals) => {
      telemetryService.capture('perf_vitals', { process_name: `worker_${workerName}`, ...vitals });
    },
  });
  const host = createWireWorkerHost({
    scope: workerScope,
    processSpawner: vitalsSpawner,
    logger: log,
  });
  try {
    const handle = startDesktopWorkersWithHost(deps, workerScope, host);
    return {
      ...handle,
      startVitalsSampling: (intervalMs) => vitalsSpawner.startSampling(intervalMs),
    };
  } catch (error) {
    await workerScope.dispose(error);
    throw error;
  }
}

function startDesktopWorkersWithHost(
  deps: StartDesktopWorkersDeps,
  workerScope: Scope,
  host: ReturnType<typeof createWireWorkerHost>
): Omit<DesktopWorkersHandle, 'startVitalsSampling'> {
  const workersStartedAt = Date.now();
  // Every worker spawns from this environment; the CAD runtime goes first on its
  // PATH so agents and terminals find the python that carries cadgen.
  const userShellEnv = createUserShellEnvController(async () =>
    withCadRuntimeOnPath(await userShellEnvManager.current())
  );
  // Logs readiness timing and observes rejection so a background readiness
  // failure never surfaces as an unhandled rejection: the failure reaches
  // callers through the queued clients' per-call rejections.
  const timedReady = <T>(name: string, ready: Promise<T>): Promise<T> => {
    const tracked = ready.then((value) => {
      log.info('boot-timeline worker ready', {
        worker: name,
        sinceWorkersStartMs: Date.now() - workersStartedAt,
      });
      return value;
    });
    tracked.catch((error: unknown) => {
      log.error('boot-timeline worker readiness failed', { worker: name, error });
    });
    return tracked;
  };
  const hostDependencies = createHostDependenciesComponent({
    store: desktopKeyValueStore,
    exec: new NodeExecutionContext({ env: process.env, refreshShellEnv: refreshUserEnv }),
    logger: log,
  }).create({
    scope: workerScope,
    dependencies: {},
    config: {
      hostId: 'local',
      definitions: [
        ...CORE_DEPENDENCIES,
        ...pluginRegistry.getAll().map(buildDescriptorFromProvider),
      ],
    },
  });
  const fsWatchWorker = host.create(
    ...fsWatchWorkerSpec({ executable: desktopWorkerPath('fs-watch'), env: process.env })
  );
  const conversationsWorker = host.create(
    ...conversationsWorkerSpec({
      executable: desktopWorkerPath('conversations'),
      env: process.env,
      databasePath: join(app.getPath('userData'), 'conversations.db'),
    })
  );
  const conversationsReady = timedReady('conversations', conversationsWorker.ready());
  const acpStart = conversationsReady.then(async (conversations) => {
    const worker = host.create(
      ...acpWorkerSpec({
        pluginRegistry,
        logger: log,
        executable: desktopWorkerPath('acp'),
        env: process.env,
        dependencies: {
          hostDependencies: hostDependencies.client.resolver,
          conversations,
          userEnv: userShellEnv,
        },
        attachmentsDir: join(app.getPath('userData'), 'acp-attachments'),
        intentsFilePath: sessionIntentFilePaths().acp,
      })
    );
    return { client: await worker.ready(), worker };
  });
  const agentConfigWorker = host.create(
    ...agentConfigWorkerSpec({
      pluginRegistry,
      logger: log,
      executable: desktopWorkerPath('agent-config'),
      env: process.env,
      dependencies: {
        hostDependencies: hostDependencies.client.resolver,
        userEnv: userShellEnv,
      },
    })
  );
  const mementosWorker = host.create(mementosComponent, {
    name: 'mementos',
    executable: desktopWorkerPath('mementos'),
    env: process.env,
    dependencies: {},
    config: {
      databasePath: join(app.getPath('userData'), 'mementos.db'),
      sweepPolicies: mementoSweepPolicies,
    },
  });
  const pullRequestsWorker = host.create(pullRequestsComponent, {
    name: 'pull-requests',
    executable: desktopWorkerPath('pull-requests'),
    env: process.env,
    dependencies: {
      // Identity is resolved per request through the seam bound during services
      // boot (spec: github-git-settings §8); until then requests fail closed.
      githubAuth: createPullRequestsGitHubAuthController(
        new GitHubApiAuthService(providerAccountRegistry),
        githubApiBaseUrlForHost,
        resolvePullRequestSyncIdentity
      ),
    },
    config: {
      databasePath: join(app.getPath('userData'), 'pull-requests.db'),
      incrementalIntervalMs: 5 * 60_000,
    },
  });
  const terminalsWorker = host.create(
    ...terminalsWorkerSpec({
      executable: desktopWorkerPath('terminals'),
      env: process.env,
      userEnv: userShellEnv,
      lifecycle: {
        terminal: { kind: 'always' },
      },
    })
  );
  const resourceUsageWorker = host.create(
    ...resourceUsageWorkerSpec({
      executable: desktopWorkerPath('resource-usage'),
      env: process.env,
    })
  );
  const hostSettingsWorker = host.create(
    ...hostSettingsWorkerSpec({
      executable: desktopWorkerPath('host-settings'),
      env: process.env,
      settingsPath: join(app.getPath('userData'), 'host-settings.json'),
    })
  );
  const hostSettingsReady = timedReady('host-settings', hostSettingsWorker.ready());
  const scriptsWorker = host.create(
    ...scriptsWorkerSpec({
      executable: desktopWorkerPath('scripts'),
      env: process.env,
      userEnv: userShellEnv,
    })
  );
  const scriptsReady = timedReady('scripts', scriptsWorker.ready());

  const watcherReady = timedReady('fs-watch', fsWatchWorker.ready());
  const acpReady = timedReady(
    'acp',
    acpStart.then((result) => result.client)
  );
  const agentConfigReady = timedReady('agent-config', agentConfigWorker.ready());
  const mementosReady = timedReady('mementos', mementosWorker.ready());
  const pullRequestsReady = timedReady('pull-requests', pullRequestsWorker.ready());
  const resourceUsageReady = timedReady('resource-usage', resourceUsageWorker.ready());
  const terminalsReady = timedReady('terminals', terminalsWorker.ready());
  const filesReady = timedReady(
    'files',
    watcherReady.then(async (watcher) => {
      const filesSettings = await deps.getFilesSettings();
      const worker = host.create(
        ...filesWorkerSpec({
          executable: desktopWorkerPath('files'),
          env: process.env,
          dependencies: { watcher },
          watchIgnore: filesSettings.watcherExclude,
        })
      );
      return await worker.ready();
    })
  );
  const fileSearchReady = timedReady(
    'file-search',
    watcherReady.then(async (watcher) => {
      const worker = host.create(
        ...fileSearchWorkerSpec({
          executable: desktopWorkerPath('file-search'),
          env: process.env,
          dependencies: { watcher, userEnv: userShellEnv },
          databasePath: resolveFileSearchDatabasePath(),
        })
      );
      return await worker.ready();
    })
  );
  const gitReady = timedReady(
    'git',
    watcherReady.then(async (watcher) => {
      const worker = host.create(
        ...gitWorkerSpec({
          executable: desktopWorkerPath('git'),
          env: process.env,
          dependencies: {
            watcher,
            hostDependencies: hostDependencies.client.resolver,
            userEnv: userShellEnv,
          },
          gitExecutable: getGitExecutable(),
        })
      );
      return await worker.ready();
    })
  );
  const tuiAgentsReady = timedReady(
    'tui-agents',
    conversationsReady.then(async (conversations) => {
      const worker = host.create(
        ...tuiAgentsWorkerSpec({
          pluginRegistry,
          logger: log,
          executable: desktopWorkerPath('tui-agents'),
          env: process.env,
          dependencies: {
            hostDependencies: hostDependencies.client.resolver,
            conversations,
            userEnv: userShellEnv,
          },
          intentsFilePath: sessionIntentFilePaths().tuiAgents,
        })
      );
      return { client: await worker.ready(), worker };
    })
  );
  const workspaceRegistryReady = timedReady(
    'workspace-registry',
    Promise.all([
      watcherReady,
      acpReady,
      terminalsReady,
      tuiAgentsReady,
      scriptsReady,
      hostSettingsReady,
    ]).then(async ([watcher, acp, terminals, tuiAgents, scripts, hostSettings]) => {
      const worker = host.create(
        ...workspaceRegistryWorkerSpec({
          executable: desktopWorkerPath('workspace-registry'),
          env: process.env,
          dependencies: {
            watcher,
            acp,
            terminals,
            tuiAgents: tuiAgents.client,
            scripts,
            hostSettings,
            userEnv: userShellEnv,
          },
          databasePath: join(app.getPath('userData'), 'workspace-registry.db'),
        })
      );
      return await worker.ready();
    })
  );
  const runtimeReady = Promise.all([
    acpReady,
    agentConfigReady,
    conversationsReady,
    fileSearchReady,
    filesReady,
    gitReady,
    hostSettingsReady,
    mementosReady,
    pullRequestsReady,
    resourceUsageReady,
    scriptsReady,
    terminalsReady,
    tuiAgentsReady,
    workspaceRegistryReady,
  ]).then(() => {});

  let disposePromise: Promise<void> | undefined;
  return {
    clients: {
      acp: queuedClient(acpApiContract, () => acpReady),
      agentConfig: queuedClient(agentConfigContract, () => agentConfigReady),
      conversations: queuedClient(conversationsContract, () => conversationsReady),
      fileSearch: queuedClient(fileSearchContract, () => fileSearchReady),
      files: queuedClient(filesContract, () => filesReady),
      git: queuedClient(gitContract, () => gitReady),
      hostDependencies: hostDependencies.client,
      hostSettings: queuedClient(hostSettingsContract, () => hostSettingsReady),
      mementos: queuedClient(mementosWireContract, () => mementosReady),
      pullRequests: queuedClient(pullRequestsContract, () => pullRequestsReady),
      resourceUsage: queuedClient(resourceUsageContract, () => resourceUsageReady),
      scripts: queuedClient(scriptsContract, () => scriptsReady),
      terminals: queuedClient(terminalsContract, () => terminalsReady),
      tuiAgents: queuedClient(tuiAgentsContract, () =>
        tuiAgentsReady.then((result) => result.client)
      ),
      workspaceRegistry: queuedClient(workspaceRegistryContract, () => workspaceRegistryReady),
    },
    workers: {
      acp: deferredWorkerStatus(acpStart.then((result) => result.worker)),
      tuiAgents: deferredWorkerStatus(tuiAgentsReady.then((result) => result.worker)),
    },
    runtimeReady: () => runtimeReady,
    dispose() {
      disposePromise ??= (async () => {
        await host.dispose();
      })();
      return disposePromise;
    },
  };
}

function deferredWorkerStatus(worker: Promise<WorkerStatusSource>): WorkerStatusSource {
  return {
    onStateChanged(cb) {
      let disposed = false;
      let unsubscribe: Unsubscribe | undefined;
      worker
        .then((resolved) => {
          if (disposed) return;
          unsubscribe = resolved.onStateChanged(cb);
        })
        .catch(() => {
          // The worker never materialized; the failure reaches consumers
          // through its queued client calls, not through status updates.
        });
      return () => {
        disposed = true;
        unsubscribe?.();
      };
    },
  };
}
