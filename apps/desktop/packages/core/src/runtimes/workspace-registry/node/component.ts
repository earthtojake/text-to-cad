import path from 'node:path';
import { observe, remote } from '@emdash/wire/state';
import { defineWireComponent, requireContract } from '@emdash/wire/worker';
import { z } from 'zod';
import { fsWatchContract } from '#services/fs-watch/api';
import { createProcessWatchServiceFromDependency } from '#services/fs-watch/node/process-watch-service';
import { hostRuntimesDefinitions } from '#services/runtime-broker/api';
import { userShellEnvContract } from '#services/shell-env/api';
import { workspaceRegistryContract } from '../api';
import { createWorkspaceRegistryController } from './api/controller';
import { workspaceRegistryStore } from './persistence/store';
import { RefFollowScheduler } from './ref-follow';
import { WorkspaceRegistryRuntime } from './runtime';
import { WorkspaceScanScheduler } from './scan/scheduler';
import { createSessionCounter, createSessionKiller } from './session-cleanup';
import { WorkspaceSessionGc } from './session-gc';

export const workspaceRegistryComponentConfigSchema = z.object({
  databasePath: z
    .string()
    .min(1)
    .refine((value) => value === ':memory:' || path.isAbsolute(value), {
      message: 'Workspace registry database path must be absolute or :memory:',
    }),
});

/**
 * The dedicated workspace registry worker (ADR 0005): owns `workspace-registry.db`
 * exclusively — the sole writer of the host's workspace index. The fs-watch dependency
 * feeds the freshness scheduler; the polling floor bounds staleness when watching fails.
 */
export const workspaceRegistryComponent = defineWireComponent({
  id: 'workspace-registry',
  contract: workspaceRegistryContract,
  requirements: {
    watcher: requireContract(fsWatchContract),
    // deactivateWorkspace owns kill-sessions; these are the session planes it sweeps.
    acp: requireContract(hostRuntimesDefinitions.acp),
    terminals: requireContract(hostRuntimesDefinitions.terminals),
    tuiAgents: requireContract(hostRuntimesDefinitions.tuiAgents),
    // The single script execution plane: activation runs execute here, and the
    // registry observes its run state to write durable script lifecycle steps.
    scripts: requireContract(hostRuntimesDefinitions.scripts),
    hostSettings: requireContract(hostRuntimesDefinitions.hostSettings),
    userEnv: requireContract(userShellEnvContract),
  },
  configSchema: workspaceRegistryComponentConfigSchema,
  create: ({ config, dependencies, instance, logger, scope }) => {
    const handle = workspaceRegistryStore.open(config.databasePath);
    scope.add(() => handle.close());

    const sessionClients = {
      acp: dependencies.acp,
      terminals: dependencies.terminals,
      tuiAgents: dependencies.tuiAgents,
    };
    const killSessions = createSessionKiller(sessionClients, logger);
    const runtime = new WorkspaceRegistryRuntime({
      handle,
      logger,
      killSessions,
      countSessions: createSessionCounter(sessionClients),
      scripts: dependencies.scripts,
      env: () => dependencies.userEnv.get(),
      getHostSettings: async () => {
        const result = await dependencies.hostSettings.get();
        return result.success ? result.data.settings : {};
      },
    });
    const hostSettings = remote(
      hostRuntimesDefinitions.hostSettings.state,
      dependencies.hostSettings.state,
      { scope }
    );
    observe(
      hostSettings().states.current,
      (snapshot) => {
        if (snapshot.status !== 'loading') runtime.hostSettingsChanged();
      },
      { scope }
    );
    // Sweeps sessions under vanished paths (moved from the retired workspace-host).
    const sessionGc = new WorkspaceSessionGc({
      clients: sessionClients,
      intervalMs: 60_000,
      scope,
      onError: (error) => logger.warn('workspace session GC failed', { error }),
    });
    sessionGc.start();
    scope.add(() => runtime.dispose());

    const watcher = createProcessWatchServiceFromDependency({
      client: dependencies.watcher,
      logger,
      scope,
    });
    const scheduler = new WorkspaceScanScheduler({
      watcher,
      execute: (request) => runtime.scanner.executeScanRequest(request),
      listTargets: () => runtime.scanTargets(),
      isActive: (id) => runtime.isWorkspaceActive(id),
      logger,
    });
    runtime.setOnRecordsChanged(() => scheduler.syncWatches());
    // Self-suppression: background steps mute their own watch events while writing.
    runtime.setScanMuter((id) => scheduler.mute(id));
    scheduler.start();
    scope.add(() => scheduler.dispose());

    // The autonomous ref-follow loop (spec: pr-workspace-model staleness): slow,
    // jittered, decoupled from the scan — it fetches; the scan never does.
    const refFollow = new RefFollowScheduler({
      runPass: () => runtime.runRefFollowPass(),
      logger,
    });
    refFollow.start();
    scope.add(() => refFollow.dispose());

    // Boot reconciliation: catch up with whatever changed while the daemon was down.
    void runtime.scanHost().catch((error) => {
      logger.warn?.(`initial workspace registry scan failed: ${String(error)}`);
    });

    return instance({
      scope,
      controller: createWorkspaceRegistryController(runtime),
    });
  },
});
