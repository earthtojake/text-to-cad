import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import type { Scope } from '@emdash/shared/concurrency';
import type { Logger } from '@emdash/shared/logger';
import {
  createController,
  forwardController,
  type Contract,
  type ContractDefinitions,
  type ContractImpl,
  type Controller,
} from '@emdash/wire/rpc';
import { createAgentOperations } from '@core/features/agents/node/controller';
import { createAgentsWireController } from '@core/features/agents/node/wire-controller';
import {
  createBrowserWireController,
  type BrowserOperations,
} from '@core/features/browser/node/wire-controller';
import { createCatalogWireController } from '@core/features/catalog/node/wire-controller';
import type { CompensationRunner } from '@core/features/conversations/node/createConversation';
import { createConversationsWireController } from '@core/features/conversations/node/wire-controller';
import type { EditorBufferService } from '@core/features/editor/node/editor-buffer-service';
import { createEditorWireController } from '@core/features/editor/node/wire-controller';
import { createFilesWireController } from '@core/features/files/node/wire-controller';
import type { GitCredentialsService } from '@core/features/github/api/node/services/git-credentials-service';
import { createGithubWireController } from '@core/features/github/node/wire-controller';
import type { PromptLibraryService } from '@core/features/library/node/prompt-library-service';
import { createPromptLibraryWireController } from '@core/features/library/node/wire-controller';
import { createMachinesWireController } from '@core/features/machines/node/wire-controller';
import { createMcpWireController } from '@core/features/mcp/node/wire-controller';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import type { ProjectSettingsService } from '@core/features/projects/api/node/settings/project-settings-service';
import type { ProjectDeletionDependencies } from '@core/features/projects/node/operations/deleteProject';
import { getProjectById } from '@core/features/projects/node/operations/getProjects';
import { createProjectsWireController } from '@core/features/projects/node/wire-controller';
import { createRepositoryWireController } from '@core/features/repository/node/wire-controller';
import type { SearchService } from '@core/features/search/node/search-service';
import { createSearchWireController } from '@core/features/search/node/wire-controller';
import { createSkillsWireController } from '@core/features/skills/node/wire-controller';
import { createSourceControlWireController } from '@core/features/source-control/node/wire-controller';
import type { TaskService } from '@core/features/tasks/api/node/task-service';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import { TaskListService } from '@core/features/tasks/node/task-list-service';
import { createTasksWireController } from '@core/features/tasks/node/wire-controller';
import { createTelemetryWireController } from '@core/features/telemetry/node/wire-controller';
import {
  createTerminalsWireController,
  type CreateTerminalsWireControllerOptions,
} from '@core/features/terminals/node/wire-controller';
import {
  createUpdatesWireController,
  type UpdateOperations,
} from '@core/features/updates/node/wire-controller';
import {
  createDesktopHostWireController,
  type DesktopHostControllerOperations,
} from '@core/features/workbench/node/wire-controller';
import type { WorkspacePlacementResolver } from '@core/features/workspaces/api/node/placement/workspace-placement-resolver';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import type { WorkspaceIdentityService } from '@core/features/workspaces/api/node/workspace-identity-service';
import { createLifecycleScriptsWireController } from '@core/features/workspaces/node/lifecycle-scripts-wire-controller';
import {
  createProjectSettingsWireController,
  createProjectWorkspacesWireController,
} from '@core/features/workspaces/node/project-wire-controllers';
import { createWorkspaceRegistryWireController } from '@core/features/workspaces/node/registry-wire-controller';
import {
  createWorkspacesWireController,
  type CreateWorkspacesWireControllerOptions,
} from '@core/features/workspaces/node/wire-controller';
import { WorkspaceMutationService } from '@core/features/workspaces/node/workspace-mutation-service';
import type { SshServiceHandle } from '@core/manifests/node/ssh-service-handle';
import { desktopDomainContracts } from '@core/manifests/shared/domain-contracts';
import type { HostReachabilityProbe } from '@core/primitives/ssh/api';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { AppDb } from '@core/services/app-db/node/db';
import type { HostService } from '@core/services/hosts/node';
import type { HostAvailabilityService } from '@core/services/hosts/node/availability';
import { createHostsWireController } from '@core/services/hosts/node/wire-controller';
import {
  createLoggingWireController,
  type LoggingControllerOperations,
} from '@core/services/logging/node/wire-controller';
import type { NotificationService } from '@core/services/notifications/node';
import { createNotificationsWireController } from '@core/services/notifications/node/wire-controller';
import type { PullRequestsRuntimeClient } from '@core/services/pull-requests/api';
import type { ReconcileSweepHandle } from '@core/services/reconcile-sweep/node/reconcile-sweep-service';
import type { MementosRuntimeClient } from '@core/services/runtime-broker/api/clients';
import type { AppSettingsService } from '@core/services/settings/node';
import type { ProviderOverrideSettings } from '@core/services/settings/node/provider-settings-service';
import {
  createAppSettingsWireController,
  type SettingsRuntimePort,
} from '@core/services/settings/node/wire-controller';
import { createSshWireController } from '@core/services/ssh/node/controller';

export type DesktopControllerContext = {
  readonly agentDependencies: Omit<
    Parameters<typeof createAgentOperations>[0],
    'providerOverrideSettings'
  >;
  readonly appSettings: AppSettingsService;
  readonly browserOperations: BrowserOperations;
  readonly compensation: CompensationRunner;
  readonly db: AppDb;
  readonly editorBuffer: EditorBufferService;
  readonly github: Omit<Parameters<typeof createGithubWireController>[0], 'logger' | 'telemetry'>;
  readonly gitCredentials: GitCredentialsService;
  readonly hostAvailability: HostAvailabilityService;
  readonly hostIsReachable: HostReachabilityProbe;
  readonly hostOperations: DesktopHostControllerOperations;
  readonly logger: Logger;
  readonly loggingOperations: LoggingControllerOperations;
  readonly notifications: NotificationService;
  readonly projectDeletion: ProjectDeletionDependencies;
  readonly promptLibrary: PromptLibraryService;
  readonly projects: ProjectAttachmentManager;
  readonly projectSettings: ProjectSettingsService;
  readonly providerSettings: ProviderOverrideSettings;
  readonly reconcileSweep: ReconcileSweepHandle;
  readonly hosts: HostService;
  readonly runtimeClients: {
    getMementosRuntimeClient(): Promise<MementosRuntimeClient>;
    getPullRequestsRuntimeClient(): Promise<PullRequestsRuntimeClient>;
  };
  readonly scope: Scope;
  readonly search: SearchService;
  readonly runtimes: RuntimeBroker;
  readonly ssh: SshServiceHandle;
  readonly settingsRuntime: SettingsRuntimePort;
  readonly telemetry: TelemetryService;
  readonly taskService: TaskService;
  readonly taskSessions: TaskSessionManager;
  readonly terminalShell: CreateTerminalsWireControllerOptions['terminalShell'];
  readonly updateOperations: UpdateOperations;
  readonly workspaceIdentity: WorkspaceIdentityService;
  readonly workspacePlacement: WorkspacePlacementResolver;
  readonly workspaces: Omit<CreateWorkspacesWireControllerOptions, 'db' | 'mutations'>;
};

type DesktopDomain = Extract<keyof typeof desktopDomainContracts, string>;

export type DesktopNodeControllerContribution = {
  readonly create: (context: DesktopControllerContext) => Controller | Promise<Controller>;
};

function controllerFromImpl<Defs extends ContractDefinitions>(
  contract: Contract<Defs>,
  owner: { impl: ContractImpl<Defs>; dispose(): Promise<void> },
  scope: Scope
): Controller {
  scope.add(() => owner.dispose());
  return createController(contract, owner.impl);
}

export const desktopNodeControllers = {
  agents: {
    create: ({ agentDependencies, providerSettings, runtimes }) =>
      createAgentsWireController({
        operations: createAgentOperations({
          ...agentDependencies,
          providerOverrideSettings: providerSettings,
        }),
        runtimes,
      }),
  },
  appSettings: {
    create: ({ appSettings, settingsRuntime }) =>
      createAppSettingsWireController(appSettings, settingsRuntime),
  },
  editor: {
    create: ({ editorBuffer }) => createEditorWireController({ editorBuffer }),
  },
  files: {
    create: ({ runtimes }) => createFilesWireController({ runtimes }),
  },
  logging: {
    create: ({ loggingOperations }) => createLoggingWireController(loggingOperations),
  },
  machines: {
    create: ({ runtimes, ssh }) => createMachinesWireController(ssh.machines, runtimes),
  },
  projectSettings: {
    create: ({ runtimes, workspaceIdentity }) =>
      createProjectSettingsWireController({ runtimes, workspaceIdentity }),
  },
  projectWorkspaces: {
    create: ({ db, projects, runtimes, scope, taskService, taskSessions }) => {
      const controller = createProjectWorkspacesWireController({
        db,
        projects,
        runtimes,
        taskService,
        taskSessions,
      });
      scope.add(() => controller.dispose());
      return controller.controller;
    },
  },
  promptLibrary: {
    create: ({ promptLibrary }) => createPromptLibraryWireController(promptLibrary),
  },
  repository: {
    create: ({ db, projects }) =>
      createRepositoryWireController({
        projects,
        loadProject: (projectId) => getProjectById(db, projectId),
      }),
  },
  search: {
    create: ({ search }) => createSearchWireController(search),
  },
  telemetry: {
    create: ({ telemetry }) => createTelemetryWireController(telemetry),
  },
  sourceControl: {
    create: ({ gitCredentials, runtimes, workspaceIdentity, projects }) =>
      createSourceControlWireController({
        runtimes,
        workspaceIdentity,
        projects,
        mintOperationCredentials: gitCredentials.mintOperationCredentials,
      }),
  },
  mcp: {
    create: ({ runtimes }) => createMcpWireController({ runtimes }),
  },
  skills: {
    create: ({ runtimes }) => createSkillsWireController({ runtimes }),
  },
  terminals: {
    create: ({
      appSettings,
      db,
      gitCredentials,
      logger,
      projects,
      runtimes,
      telemetry,
      terminalShell,
      workspaceIdentity,
    }) =>
      createTerminalsWireController({
        db,
        projects,
        runtimes,
        settings: appSettings,
        logger,
        telemetry,
        terminalShell,
        workspaceIdentity,
        resolveSessionGitCredentials: gitCredentials.resolveSessionSpec,
      }),
  },
  mementos: {
    create: async ({ runtimeClients }) =>
      forwardController(
        desktopDomainContracts.mementos,
        await runtimeClients.getMementosRuntimeClient()
      ),
  },
  notifications: {
    create: ({ notifications }) => createNotificationsWireController(notifications),
  },
  pullRequests: {
    create: async ({ runtimeClients }) =>
      forwardController(
        desktopDomainContracts.pullRequests,
        await runtimeClients.getPullRequestsRuntimeClient()
      ),
  },
  catalog: {
    create: ({ scope }) =>
      controllerFromImpl(desktopDomainContracts.catalog, createCatalogWireController(), scope),
  },
  workspaces: {
    create: ({ db, projects, runtimes, scope, workspaces }) => {
      const mutations = new WorkspaceMutationService({ db, projects, runtimes });
      return controllerFromImpl(
        desktopDomainContracts.workspaces,
        createWorkspacesWireController({
          ...workspaces,
          db,
          mutations,
        }),
        scope
      );
    },
  },
  workspaceRegistry: {
    create: ({ db, reconcileSweep, runtimes }) =>
      createWorkspaceRegistryWireController({ db, runtimes, sweep: reconcileSweep }),
  },
  lifecycleScripts: {
    create: ({ runtimes, workspaceIdentity }) =>
      createLifecycleScriptsWireController({ runtimes, workspaceIdentity }),
  },
  projects: {
    create: ({
      db,
      gitCredentials,
      projectDeletion,
      projects,
      projectSettings,
      runtimes,
      scope,
      workspacePlacement,
    }) =>
      controllerFromImpl(
        desktopDomainContracts.projects,
        createProjectsWireController({
          db,
          placement: workspacePlacement,
          projectDeletion,
          projects,
          projectSettings,
          runtimes,
          mintCloneCredentials: gitCredentials.mintCloneCredentials,
        }),
        scope
      ),
  },
  browser: {
    create: ({ browserOperations }) => createBrowserWireController(browserOperations),
  },
  conversations: {
    create: ({
      compensation,
      db,
      hostIsReachable,
      logger,
      projects,
      providerSettings,
      runtimes,
      taskSessions,
      telemetry,
      workspaceIdentity,
    }) =>
      createConversationsWireController({
        db,
        logger,
        projects,
        getProviderEnv: async (providerId) => (await providerSettings.getItem(providerId))?.env,
        runtimes,
        taskSessions,
        telemetry,
        workspaceIdentity,
        withCompensation: compensation,
        hostIsReachable,
      }),
  },
  github: {
    create: ({ github, logger, telemetry }) =>
      createGithubWireController({ ...github, logger, telemetry }),
  },
  ssh: {
    create: ({ ssh }) => createSshWireController(ssh.ssh, ssh.connections),
  },
  hosts: {
    create: ({ hostAvailability, hosts, ssh }) =>
      createHostsWireController(hosts, hostAvailability, ssh.ssh),
  },
  tasks: {
    create: ({ db, scope, taskService, taskSessions, telemetry }) => {
      const taskList = new TaskListService({
        taskService,
        taskSessions,
        workspaces: createWorkspaceRegistry(db),
      });
      return controllerFromImpl(
        desktopDomainContracts.tasks,
        createTasksWireController({
          db,
          service: taskService,
          taskList,
          telemetry,
        }),
        scope
      );
    },
  },
  updates: {
    create: ({ updateOperations }) => createUpdatesWireController(updateOperations),
  },
  host: {
    create: ({ hostOperations }) => createDesktopHostWireController(hostOperations),
  },
} satisfies {
  readonly [Domain in DesktopDomain]: DesktopNodeControllerContribution;
};
