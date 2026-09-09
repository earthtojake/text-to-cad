import { mkdir } from 'node:fs/promises';
import { createJsonFileKeyValueStore } from '@emdash/core/primitives/kv/node';
import type { AcpApiContract } from '@emdash/core/runtimes/acp/api';
import { acpWorkerSpec } from '@emdash/core/runtimes/acp/node';
import type { AgentConfigContract } from '@emdash/core/runtimes/agent-config/api';
import { agentConfigWorkerSpec } from '@emdash/core/runtimes/agent-config/node';
import type { ConversationsContract } from '@emdash/core/runtimes/conversations/api';
import { conversationsWorkerSpec } from '@emdash/core/runtimes/conversations/node';
import type { FileSearchContract } from '@emdash/core/runtimes/file-search/api';
import { fileSearchWorkerSpec } from '@emdash/core/runtimes/file-search/node';
import type { FilesContract } from '@emdash/core/runtimes/files/api';
import { filesWorkerSpec } from '@emdash/core/runtimes/files/node';
import type { GitContract } from '@emdash/core/runtimes/git/api';
import { gitWorkerSpec } from '@emdash/core/runtimes/git/node';
import type { HostSettingsContract } from '@emdash/core/runtimes/host-settings/api';
import { hostSettingsWorkerSpec } from '@emdash/core/runtimes/host-settings/node';
import type { ResourceUsageContract } from '@emdash/core/runtimes/resource-usage/api';
import { resourceUsageWorkerSpec } from '@emdash/core/runtimes/resource-usage/node';
import type { ScriptsContract } from '@emdash/core/runtimes/scripts/api';
import { scriptsWorkerSpec } from '@emdash/core/runtimes/scripts/node';
import type { TerminalsContract } from '@emdash/core/runtimes/terminals/api';
import { terminalsWorkerSpec } from '@emdash/core/runtimes/terminals/node';
import type { TuiAgentsContract } from '@emdash/core/runtimes/tui-agents/api';
import { tuiAgentsWorkerSpec } from '@emdash/core/runtimes/tui-agents/node';
import type { WorkspaceRegistryContract } from '@emdash/core/runtimes/workspace-registry/api';
import { workspaceRegistryWorkerSpec } from '@emdash/core/runtimes/workspace-registry/node';
import { buildDescriptorFromProvider } from '@emdash/core/services/agent-plugins/api/plugins';
import { NodeExecutionContext } from '@emdash/core/services/exec/api';
import { fsWatchWorkerSpec } from '@emdash/core/services/fs-watch/node';
import {
  CORE_DEPENDENCIES,
  createHostDependenciesComponent,
  type HostDependenciesContract,
} from '@emdash/core/services/host-dependencies/node';
import {
  createUserShellEnvController,
  type ShellEnvManager,
} from '@emdash/core/services/shell-env/node';
import { pluginRegistry } from '@emdash/plugins/agents';
import type { Scope } from '@emdash/shared/concurrency';
import type { Logger } from '@emdash/shared/logger';
import type { ContractClient } from '@emdash/wire/rpc';
import { createWireWorkerHost } from '@emdash/wire/worker';
import { childProcessSpawner } from '@emdash/wire/worker/node';
import { workspaceServerRuntimePaths } from '../runtime/paths';
import { workspaceWorkerPath } from './worker-paths';

export type WorkspaceServerRuntimeClients = {
  acp: ContractClient<AcpApiContract>;
  agentConfig: ContractClient<AgentConfigContract>;
  conversations: ContractClient<ConversationsContract>;
  fileSearch: ContractClient<FileSearchContract>;
  files: ContractClient<FilesContract>;
  git: ContractClient<GitContract>;
  hostSettings: ContractClient<HostSettingsContract>;
  resourceUsage: ContractClient<ResourceUsageContract>;
  scripts: ContractClient<ScriptsContract>;
  terminals: ContractClient<TerminalsContract>;
  tuiAgents: ContractClient<TuiAgentsContract>;
  workspaceRegistry: ContractClient<WorkspaceRegistryContract>;
};

export type WorkspaceServerRuntimeHost = {
  runtimes: WorkspaceServerRuntimeClients;
  hostDependencies: ContractClient<HostDependenciesContract>;
};

export type CreateWorkspaceServerRuntimeHostOptions = {
  scope: Scope;
  socketPath?: string;
  shellEnv: ShellEnvManager;
  logger?: Logger;
};

const DETACHED_TERMINAL_GRACE_MS = 5 * 60_000;

export async function createWorkspaceServerRuntimeHost(
  options: CreateWorkspaceServerRuntimeHostOptions
): Promise<WorkspaceServerRuntimeHost> {
  const env = options.shellEnv.env;
  const userShellEnv = createUserShellEnvController(() => options.shellEnv.current());
  const paths = workspaceServerRuntimePaths(options.socketPath);
  await Promise.all([
    mkdir(paths.stateDirectory, { recursive: true }),
    mkdir(paths.attachmentsDirectory, { recursive: true }),
  ]);

  const workerHost = createWireWorkerHost({
    scope: options.scope.child('workers'),
    processSpawner: childProcessSpawner(),
  });
  const hostDependencies = createHostDependenciesComponent({
    store: createJsonFileKeyValueStore({ path: paths.hostDependenciesStore }),
    exec: new NodeExecutionContext({ env, refreshShellEnv: () => options.shellEnv.refresh() }),
    logger: options.logger,
  }).create({
    scope: options.scope.child('host-dependencies'),
    dependencies: {},
    config: {
      hostId: 'local',
      definitions: [
        ...CORE_DEPENDENCIES,
        ...pluginRegistry.getAll().map(buildDescriptorFromProvider),
      ],
    },
  });

  const conversationsPromise = workerHost.spawn(
    ...conversationsWorkerSpec({
      executable: workspaceWorkerPath('conversations'),
      env,
      databasePath: paths.conversationsDatabase,
    })
  );
  const watcherPromise = workerHost.spawn(
    ...fsWatchWorkerSpec({ executable: workspaceWorkerPath('fs-watch'), env })
  );
  const terminalsPromise = workerHost.spawn(
    ...terminalsWorkerSpec({
      executable: workspaceWorkerPath('terminals'),
      env,
      userEnv: userShellEnv,
      lifecycle: {
        terminal: { kind: 'while-attached', graceMs: DETACHED_TERMINAL_GRACE_MS },
      },
    })
  );
  const resourceUsagePromise = workerHost.spawn(
    ...resourceUsageWorkerSpec({
      executable: workspaceWorkerPath('resource-usage'),
      env,
    })
  );
  const hostSettingsPromise = workerHost.spawn(
    ...hostSettingsWorkerSpec({
      executable: workspaceWorkerPath('host-settings'),
      env,
      settingsPath: paths.hostSettingsFile,
    })
  );
  const scriptsPromise = workerHost.spawn(
    ...scriptsWorkerSpec({
      executable: workspaceWorkerPath('scripts'),
      env,
      userEnv: userShellEnv,
    })
  );
  const acpPromise = conversationsPromise.then((conversations) =>
    workerHost.spawn(
      ...acpWorkerSpec({
        pluginRegistry,
        executable: workspaceWorkerPath('acp'),
        env,
        dependencies: {
          hostDependencies: hostDependencies.client.resolver,
          conversations,
          userEnv: userShellEnv,
        },
        attachmentsDir: paths.attachmentsDirectory,
        intentsFilePath: paths.acpIntentsFile,
      })
    )
  );
  const agentConfigPromise = workerHost.spawn(
    ...agentConfigWorkerSpec({
      pluginRegistry,
      executable: workspaceWorkerPath('agent-config'),
      env,
      dependencies: {
        hostDependencies: hostDependencies.client.resolver,
        userEnv: userShellEnv,
      },
    })
  );
  const tuiAgentsPromise = conversationsPromise.then((conversations) =>
    workerHost.spawn(
      ...tuiAgentsWorkerSpec({
        pluginRegistry,
        executable: workspaceWorkerPath('tui-agents'),
        env,
        dependencies: {
          hostDependencies: hostDependencies.client.resolver,
          conversations,
          userEnv: userShellEnv,
        },
        intentsFilePath: paths.tuiAgentsIntentsFile,
      })
    )
  );

  const [
    conversations,
    watcher,
    terminals,
    resourceUsage,
    hostSettings,
    scripts,
    acp,
    agentConfig,
    tuiAgents,
  ] = await Promise.all([
    conversationsPromise,
    watcherPromise,
    terminalsPromise,
    resourceUsagePromise,
    hostSettingsPromise,
    scriptsPromise,
    acpPromise,
    agentConfigPromise,
    tuiAgentsPromise,
  ]);

  // Host-settings are already awaited above, so the per-host watcherExclude can
  // configure the files worker at spawn (restart-applied). Unset leaves
  // watchIgnore undefined and FilesRuntime falls back to the shared
  // DEFAULT_WATCHER_EXCLUDE — defaults live in code, never in the store.
  const hostSettingsState = await hostSettings.get();
  const filesPromise = workerHost.spawn(
    ...filesWorkerSpec({
      executable: workspaceWorkerPath('files'),
      env,
      dependencies: { watcher },
      watchIgnore: hostSettingsState.success
        ? hostSettingsState.data.settings.watcherExclude
        : undefined,
    })
  );
  const fileSearchPromise = workerHost.spawn(
    ...fileSearchWorkerSpec({
      executable: workspaceWorkerPath('file-search'),
      env,
      dependencies: { watcher, userEnv: userShellEnv },
      databasePath: paths.fileSearchDatabase,
      ripgrepPath: env['EMDASH_WS_RIPGREP_PATH'],
    })
  );
  const gitPromise = workerHost.spawn(
    ...gitWorkerSpec({
      executable: workspaceWorkerPath('git'),
      env,
      dependencies: {
        watcher,
        hostDependencies: hostDependencies.client.resolver,
        userEnv: userShellEnv,
      },
    })
  );
  const workspaceRegistryPromise = workerHost.spawn(
    ...workspaceRegistryWorkerSpec({
      executable: workspaceWorkerPath('workspace-registry'),
      env,
      dependencies: {
        watcher,
        acp,
        terminals,
        tuiAgents,
        scripts,
        hostSettings,
        userEnv: userShellEnv,
      },
      databasePath: paths.workspaceRegistryDatabase,
    })
  );

  const [files, fileSearch, git, workspaceRegistry] = await Promise.all([
    filesPromise,
    fileSearchPromise,
    gitPromise,
    workspaceRegistryPromise,
  ]);

  return {
    runtimes: {
      acp,
      agentConfig,
      conversations,
      fileSearch,
      files,
      git,
      hostSettings,
      resourceUsage,
      scripts,
      terminals,
      tuiAgents,
      workspaceRegistry,
    },
    hostDependencies: hostDependencies.client,
  };
}
