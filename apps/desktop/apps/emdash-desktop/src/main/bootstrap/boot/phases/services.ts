import { LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import { err, ok } from '@emdash/shared';
import { app } from 'electron';
import { getPluginMetadata } from '@core/features/agents/api/node/plugin-registry';
import { createConversationDeletionSweepKind } from '@core/features/conversations/node/sweep/conversation-deletion-sweep';
import { ConversationBackfillService } from '@core/features/conversations/node/sync/conversation-backfill';
import { ConversationSyncService } from '@core/features/conversations/node/sync/conversation-sync-service';
import { TuiConversationProvider } from '@core/features/conversations/node/tui-conversation-provider';
import {
  createGitCredentialsService,
  type GitCredentialsService,
} from '@core/features/github/api/node/services/git-credentials-service';
import { GitHubApiAuthService } from '@core/features/github/api/node/services/github-api-auth-service';
import { githubRepositoryResolver } from '@core/features/github/api/node/services/github-repository-resolver';
import { createProjectGitHubAccountResolver } from '@core/features/github/api/node/services/project-github-account-resolver';
import { GitHubAccountService } from '@core/features/github/node/accounts/github-account-service';
import { GitHubCliAccountImportService } from '@core/features/github/node/accounts/github-cli-account-import';
import { GitHubLegacyTokenImportStep } from '@core/features/github/node/accounts/github-legacy-token-import-step';
import { githubEvents } from '@core/features/github/node/event-host';
import { GitCredentialServer } from '@core/features/github/node/services/git-credential-server';
import {
  defaultGitHubDeviceAuthFactory,
  GitHubDeviceFlowService,
} from '@core/features/github/node/services/github-device-flow-service';
import { githubIdentityClient } from '@core/features/github/node/services/github-identity-client';
import { LegacyGitHubTokenMigrationStore } from '@core/features/github/node/services/legacy-github-token-migration-store';
import { clearOctokitCache } from '@core/features/github/node/services/octokit-cache';
import { createGitHubRepositoryService } from '@core/features/github/node/services/repo-service';
import {
  createPromptLibraryService,
  type PromptLibraryKV,
} from '@core/features/library/node/prompt-library-service';
import { LocalSettingsSync } from '@core/features/machines/node/local-settings-sync';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import { loadStoredGitSettings } from '@core/features/projects/api/node/settings/effective-settings';
import { ProjectSettingsService } from '@core/features/projects/api/node/settings/project-settings-service';
import type { ProjectDeletionDependencies } from '@core/features/projects/node/operations/deleteProject';
import {
  getProjectById,
  getProjectByPath,
} from '@core/features/projects/node/operations/getProjects';
import { createProjectAttachmentAdapter } from '@core/features/projects/node/project-attachment-adapter';
import { createProjectAttachmentManager } from '@core/features/projects/node/project-attachment-manager';
import { migrateAppWorktreeRootToLocalHostDefault } from '@core/features/projects/node/settings/migrations/app-worktree-root';
import { createSearchService } from '@core/features/search/node/search-service';
import { TaskService } from '@core/features/tasks/api/node/task-service';
import type { TaskSessionCleanup } from '@core/features/tasks/api/node/task-session-cleanup';
import { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import { installTaskTelemetry } from '@core/features/telemetry/node/task-telemetry';
import { desktopHostEvents } from '@core/features/workbench/node/event-host';
import {
  createWorkspaceLifecycleParticipants,
  deactivateWorkspaceParticipants,
} from '@core/features/workspaces/api/node/lifecycle-participants';
import { WorkspacePlacementResolver } from '@core/features/workspaces/api/node/placement/workspace-placement-resolver';
import { WorkspaceCreations } from '@core/features/workspaces/api/node/registry-verbs';
import { acquireWorkspaceRuntime } from '@core/features/workspaces/api/node/runtime-access';
import type { TaskProviderOpts } from '@core/features/workspaces/api/node/workspace-factory';
import { createWorkspaceDeletionSweepKind } from '@core/features/workspaces/node/sweep/workspace-deletion-sweep';
import { WorkspaceRegistryBackfillService } from '@core/features/workspaces/node/sync/workspace-registry-backfill';
import { WorkspaceRegistrySyncService } from '@core/features/workspaces/node/sync/workspace-registry-sync-service';
import { startPeriodicSweep } from '@core/primitives/periodic-sweep/node/periodic-sweep';
import { DEFAULT_AGENT_GIT_CREDENTIALS } from '@core/primitives/project-settings/api';
import type { HostReachabilityProbe } from '@core/primitives/ssh/api';
import { AppDbKeyValueStore } from '@core/services/app-db/node/key-value-store';
import { createNotificationService } from '@core/services/notifications/node';
import { PullRequestsRegistration } from '@core/services/pull-requests/node/pull-requests-registration';
import { bindPullRequestSyncIdentityResolver } from '@core/services/pull-requests/node/sync-identity';
import { ReconcileSweepService } from '@core/services/reconcile-sweep/node/reconcile-sweep-service';
import {
  createReconcileSweepTriggers,
  installReconcileSweepTriggers,
} from '@core/services/reconcile-sweep/node/reconcile-sweep-triggers';
import type { AppSettingsKey } from '@core/services/settings/api';
import { createProviderOverrideSettings } from '@core/services/settings/node/provider-settings-service';
import { createHostReachabilityProbe } from '@core/services/ssh/node/host-reachability';
import { agentStatusService } from '@main/core/agent-status/agent-status-service';
import { appService } from '@main/core/app/service';
import {
  createFileSearchRuntime,
  searchFileSearchRoot,
} from '@main/core/file-search/runtime-client';
import { GitRepositoryFetchService } from '@main/core/git/repository/fetch-service';
import { GitRepositoryService } from '@main/core/git/repository/service';
import { providerAccountRegistry } from '@main/core/provider-accounts/provider-account-registry-instance';
import { ensureAbsoluteDir } from '@main/core/runtime/files-helpers';
import {
  killLifecycleAcpSessions,
  killLifecycleTerminalSessions,
  resolveLifecycleSessionTargets,
  type SessionCleanupDependencies,
} from '@main/core/runtime/operations/session-cleanup';
import { sweepSessionHygiene } from '@main/core/runtime/operations/session-hygiene';
import { createDesktopSessionIntentStores } from '@main/core/runtime/session-intent-stores';
import { getTerminalColorEnv } from '@main/core/terminal-shell/color-env';
import { runLocalCommand } from '@main/core/utils/exec';
import { KV } from '@main/db/kv';
import { cleanupLegacyOperationsDatabases } from '@main/db/legacy-operations-cleanup';
import type { DesktopRuntimes } from '@main/gateway/desktop-runtimes';
import { createDesktopWorkspaceRuntimeAcquirer } from '@main/gateway/workspace-runtime';
import { setBrowserCorsRelaxationSettings } from '@main/host/browser/browser-profile-session';
import { browserWebContentsRegistry } from '@main/host/browser/browser-webcontents-registry';
import { HostAttachmentRegistry } from '@main/host/host-attachment-registry';
import { createSystemNotificationSink } from '@main/host/notifications/system-notification-sink';
import { encryptedAppSecretsStore } from '@main/host/secrets/encrypted-app-secrets-store';
import { toPlaintextSecretStore } from '@main/host/secrets/plaintext-secret-store';
import { installUpdateNotifications } from '@main/host/updates/update-notifications';
import { applyNativeTheme, isAppFocused } from '@main/host/window';
import { log } from '@main/lib/logger';
import { telemetryService } from '@main/lib/telemetry';
import { appScope } from '../../core/app-scope';
import { step } from '../../core/phase';
import { setCoreServiceInstances } from '../../core/service-instances';
import type { DatabaseBundle } from './database';
import type { InfrastructureBundle } from './infrastructure';

type GitHubKVSchema = { tokenSource: string };

export type ServicesBundle = {
  readonly github: {
    account: GitHubAccountService;
    cliImport: GitHubCliAccountImportService;
    deviceFlow: GitHubDeviceFlowService;
    legacyTokenImport: GitHubLegacyTokenImportStep;
    repositories: ReturnType<typeof createGitHubRepositoryService>;
  };
  readonly gitCredentials: GitCredentialsService;
  readonly hostIsReachable: HostReachabilityProbe;
  readonly hostAttachments: HostAttachmentRegistry;
  readonly notifications: ReturnType<typeof createNotificationService>;
  readonly promptLibrary: ReturnType<typeof createPromptLibraryService>;
  readonly projectDeletion: ProjectDeletionDependencies;
  readonly projects: ProjectAttachmentManager;
  readonly projectSettings: ProjectSettingsService;
  readonly providerSettings: ReturnType<typeof createProviderOverrideSettings>;
  readonly pullRequestsRegistration: PullRequestsRegistration;
  readonly search: ReturnType<typeof createSearchService>;
  readonly taskService: TaskService;
  readonly taskSessions: TaskSessionManager;
  readonly workspacePlacement: WorkspacePlacementResolver;
  readonly conversationSync: ConversationSyncService;
  readonly reconcileSweep: ReconcileSweepService;
};

export async function bootServices(
  database: DatabaseBundle,
  infrastructure: InfrastructureBundle,
  desktopRuntimes: DesktopRuntimes
): Promise<ServicesBundle> {
  const { appSettings: appSettingsService, db, sqlite, workspaceIdentity } = database;
  const { clients, broker: runtimes } = desktopRuntimes;
  const getMementosRuntimeClient = async () => clients.mementos;
  const getPullRequestsRuntimeClient = async () => clients.pullRequests;
  const getTerminalsRuntimeClient = async () => clients.terminals;
  const getTuiAgentsRuntimeClient = async () => clients.tuiAgents;
  const fileSearchRuntime = createFileSearchRuntime(runtimes, {
    getSearchExclusions: async () => (await appSettingsService.get('files')).searchExclude,
  });
  const handleFileSearchSettingsChanged = (key: AppSettingsKey) => {
    if (key === 'files') void fileSearchRuntime.refreshExclusions();
  };
  appSettingsService.on('app-settings:changed', handleFileSearchSettingsChanged);
  appScope.add(() => {
    appSettingsService.off('app-settings:changed', handleFileSearchSettingsChanged);
  });
  const providerOverrideSettings = createProviderOverrideSettings(db);
  const workspacePlacement = new WorkspacePlacementResolver({
    broker: runtimes,
    getSettings: () => appSettingsService,
    findProjectByPath: (host, projectPath) => getProjectByPath(db, host, projectPath),
    // Placement is record-only and must not depend on Host attachment.
    getStoredProjectWorktreeRoot: async (projectId) => {
      const stored = await loadStoredGitSettings(db, projectId);
      return stored.worktreeRoot;
    },
  });
  const lifecycleParticipants = createWorkspaceLifecycleParticipants({
    registerFileSearchRoot: fileSearchRuntime.registerRoot,
  });
  const taskSessionManager = new TaskSessionManager({
    db,
    runtimes,
    workspaceIdentity,
    deactivateWorkspaceParticipants: (identity) =>
      deactivateWorkspaceParticipants(lifecycleParticipants, identity),
  });
  const tuiConversationDependencies = {
    db,
    getProviderConfig: (providerId: string) => providerOverrideSettings.getItem(providerId),
    getTaskSettings: () => appSettingsService.get('tasks'),
    getTerminalColorEnv,
    // Late-bound: the git-credentials service is constructed further down in
    // this phase; sessions only call this after boot completes.
    resolveSessionGitCredentials: (params: { projectId: string; host: HostRef }) =>
      gitCredentials.resolveSessionSpec(params),
  };
  const projectAttachmentAdapter = createProjectAttachmentAdapter({
    db,
    taskSessions: taskSessionManager,
    createGitRepository: (client, repository, resolveEffectiveSettings) =>
      new GitRepositoryService(client, repository, resolveEffectiveSettings),
    createGitRepositoryFetch: (client, repository, getBaseRemote) =>
      new GitRepositoryFetchService(client, repository, getBaseRemote),
    ensureAbsoluteDir: (client, rootPath, absolutePath, options) =>
      ensureAbsoluteDir(async () => client, rootPath, absolutePath, options),
    runtimes,
    getProjectDefaults: async () => ({
      tmuxByDefault: (await appSettingsService.get('project')).tmuxByDefault,
    }),
    migrateAppWorktreeRoot: async () => {
      const local = await runtimes.client(LOCAL_HOST_REF);
      if (!local.success) throw new Error('local host runtime unavailable');
      const hostSettings = local.data.hostSettings;
      await migrateAppWorktreeRootToLocalHostDefault({
        getAppDefaultWorktreeDirectoryOverride: async () => {
          const { overrides } = await appSettingsService.getWithMeta('localProject');
          return Object.hasOwn(overrides, 'defaultWorktreeDirectory')
            ? overrides.defaultWorktreeDirectory
            : undefined;
        },
        clearAppDefaultWorktreeDirectory: () =>
          appSettingsService.resetField('localProject', 'defaultWorktreeDirectory'),
        localHostSettings: {
          getWorktreeRoot: async () => {
            const state = await hostSettings.get();
            return state.success
              ? { success: true, worktreeRoot: state.data.settings.worktreeRoot }
              : { success: false };
          },
          setWorktreeRoot: async (worktreeRoot) => {
            const result = await hostSettings.update({ worktreeRoot });
            return { success: result.success };
          },
        },
      });
    },
  });
  const projectManager = createProjectAttachmentManager({
    scope: appScope,
    availability: desktopRuntimes.hostAvailability,
    adapter: projectAttachmentAdapter,
  });
  const projectSettingsService = new ProjectSettingsService({
    db,
    projects: projectManager,
    workspaceIdentity,
  });
  const createConversationProvider = (options: TaskProviderOpts) =>
    new TuiConversationProvider(
      {
        projectId: options.projectId,
        taskId: options.taskId,
        taskPath: options.taskPath,
        host: options.host,
        files: options.files,
        tuiAgents: options.tuiAgents,
        tmux: options.tmuxEnabled,
        shellSetup: options.shellSetup,
        taskEnvVars: options.taskEnvVars,
      },
      tuiConversationDependencies
    );
  const workspaceCreations = new WorkspaceCreations();
  const sessionCleanupDependencies: SessionCleanupDependencies = {
    getAcpRuntimeClient: async () => clients.acp,
    getProjectTerminals: (projectId: string) => {
      const attached = projectManager.requireAttached(projectId);
      return attached.success ? attached.data.terminals : undefined;
    },
    getTerminalsRuntimeClient,
    getTuiAgentsRuntimeClient,
  };
  const lifecycleSessions: TaskSessionCleanup = {
    resolve: (database, scope, context) =>
      resolveLifecycleSessionTargets(sessionCleanupDependencies, database, scope, context),
    killAcp: (database, scope, targets) =>
      killLifecycleAcpSessions(sessionCleanupDependencies, database, scope, targets),
    killTerminals: (database, scope, context, targets) =>
      killLifecycleTerminalSessions(sessionCleanupDependencies, database, scope, context, targets),
  };
  // Legacy consumers still read raw SSH reachability. Task/workspace mutations use
  // ProjectAttachmentManager.requireAttached instead.
  const hostIsReachable = createHostReachabilityProbe(infrastructure.ssh.manager);
  const taskService = new TaskService({
    db,
    projects: projectManager,
    sessions: taskSessionManager,
    workspacePlacement,
    runtimes,
    lifecycleParticipants,
    createConversationProvider,
    workspaceIdentity,
    creations: workspaceCreations,
    // Plain task deletion (spec §3): no kernel submit; the host-artifact half rides
    // the workspace removal verbs and the reconcile-sweep tombstones.
    deletion: {
      db,
      runtimes,
      sessionCleanup: lifecycleSessions,
      getMementosRuntimeClient,
      telemetry: telemetryService,
      unregisterFileSearchRoot: fileSearchRuntime.unregisterRoot,
    },
  });
  const searchService = createSearchService({
    db,
    sqlite,
    acquireWorkspaceRuntime: (workspaceId) =>
      acquireWorkspaceRuntime(runtimes, workspaceIdentity, workspaceId),
    searchFileSearchRoot,
    getSearchExclusions: async () => (await appSettingsService.get('files')).searchExclude,
    tasks: taskService,
  });
  searchService.initialize();
  installTaskTelemetry(telemetryService, taskService, taskSessionManager);

  // Unmigrated string-typed consumers get the documented plaintext view over
  // the Secret-typed secrets store (see toPlaintextSecretStore).
  const plaintextSecrets = toPlaintextSecretStore(encryptedAppSecretsStore);
  const promptLibraryService = createPromptLibraryService({
    db,
    keyValueStore: new AppDbKeyValueStore<PromptLibraryKV>(db, 'prompt-library', log),
  });
  const notificationService = createNotificationService({
    db,
    settings: appSettingsService,
    isAppFocused,
    onAgentEvent: (handler) => agentStatusService.on('agent:event', handler),
    resolveProviderName: (providerId) => {
      try {
        return getPluginMetadata(providerId).name;
      } catch {
        return providerId;
      }
    },
    logger: log,
    createSystemSink: createSystemNotificationSink,
  });
  const githubKV = new KV<GitHubKVSchema>('github');
  const legacyGitHubTokens = new LegacyGitHubTokenMigrationStore(plaintextSecrets, {
    getTokenSource: () => githubKV.get('tokenSource'),
    clearTokenSource: () => githubKV.del('tokenSource'),
  });
  const githubCliImporter = new GitHubCliAccountImportService(
    providerAccountRegistry,
    runLocalCommand,
    githubIdentityClient
  );
  const githubAccountService = new GitHubAccountService(
    providerAccountRegistry,
    githubCliImporter,
    clearOctokitCache
  );
  const githubApiAuthService = new GitHubApiAuthService(providerAccountRegistry);
  const resolveProjectGitHubAccount = createProjectGitHubAccountResolver({
    getProjectById: (projectId) => getProjectById(db, projectId),
    getStoredGitSettings: (projectId) => loadStoredGitSettings(db, projectId),
    getRepoFacts: async (project) => {
      const attached = projectManager.requireAttached(project.id);
      return attached.success ? attached.data.repoFacts.get() : null;
    },
    listAccounts: () => githubAccountService.listAccounts(),
  });
  // Emdash git credential helper (spec: github-git-settings §4): loopback
  // server holding tokens desktop-side plus the policy seam consumed by the
  // terminals/source-control controllers and TUI sessions.
  const gitCredentialServer = new GitCredentialServer({
    resolveProjectGitHubAccount,
    listAccounts: () => githubAccountService.listAccounts(),
    getToken: (host, context) => githubApiAuthService.getToken(host, context),
    logger: log,
  });
  appScope.add(() => {
    gitCredentialServer.stop();
  });
  const gitCredentials = createGitCredentialsService({
    getAgentGitCredentialsSetting: async (projectId) => {
      const settings = await loadStoredGitSettings(db, projectId);
      return settings.agentGitCredentials ?? DEFAULT_AGENT_GIT_CREDENTIALS;
    },
    resolveProjectGitHubAccount,
    listAccounts: () => githubAccountService.listAccounts(),
    channels: gitCredentialServer,
    logger: log,
  });
  const pullRequestsRegistration = new PullRequestsRegistration({
    getClient: getPullRequestsRuntimeClient,
    onProjectOpened: (handler) => projectManager.on('projectOpened', handler),
    onProjectClosed: (handler) => projectManager.on('projectClosed', handler),
    onTaskProvisioned: (handler) => taskSessionManager.hooks.on('task:provisioned', handler),
    subscribeToProjectRemotes: (projectId, handler) => {
      const attached = projectManager.requireAttached(projectId);
      if (!attached.success || !attached.data.hasRepository) return undefined;
      return attached.data.gitRepository.subscribeRemotes(handler);
    },
    resolveProjectRepositoryUrls: async (projectId) => {
      const attached = projectManager.requireAttached(projectId);
      if (!attached.success || !attached.data.hasRepository) return [];
      const remotes = (
        await attached.data.git.repository.model
          .state(attached.data.repository, 'remotes')
          .snapshot()
      ).data.remotes;
      const resolved = await Promise.all(
        remotes.map(async (remote) => await githubRepositoryResolver.resolve(remote.url))
      );
      return [
        ...new Set(
          resolved.flatMap((repository) =>
            repository.success ? [repository.data.repositoryUrl] : []
          )
        ),
      ];
    },
    // Translates resolver provenance into the registration's structural
    // contract so per-sync identity fails closed with an honest status
    // (spec: github-git-settings §7/§8).
    resolveProjectAuthContext: async (projectId) => {
      const account = await resolveProjectGitHubAccount(projectId);
      if (account.value !== null) return ok({ accountId: account.value.accountId });
      switch (account.provenance.kind) {
        case 'set':
          return err({ type: 'disabled', message: 'GitHub is disabled for this project.' });
        case 'unresolvable':
        case 'broken-setting':
          return err({
            type: 'account_selection_failed',
            message: 'The selected GitHub account is no longer connected.',
          });
        default:
          return err({
            type: 'unconfigured',
            message: 'No GitHub account is configured for this project.',
          });
      }
    },
  });
  // Answers the PR worker's per-sync "as whom" requests through the blessed
  // resolver (spec: github-git-settings §8); before this binding, identity
  // requests fail closed and the worker skips the sync.
  bindPullRequestSyncIdentityResolver((repositoryUrl) =>
    pullRequestsRegistration.resolveSyncIdentity(repositoryUrl)
  );
  const githubRepositories = createGitHubRepositoryService(githubApiAuthService);
  const githubDeviceFlow = new GitHubDeviceFlowService({
    accountStore: providerAccountRegistry,
    identityClient: githubIdentityClient,
    publishEvent: (event) => githubEvents.emit(undefined, event),
    createDeviceAuth: defaultGitHubDeviceAuthFactory,
    config: {
      clientId: 'Ov23ligC35uHWopzCeWf',
      scopes: ['repo', 'read:user', 'read:org'],
    },
  });
  // Run-once upgrade step (spec: github-git-settings §10): the legacy
  // single-token import lives behind an app-DB done-flag instead of a
  // recurring startup backfill. The KV github-account backfill retired into
  // Drizzle data migration 0046.
  const githubLegacyTokenImport = new GitHubLegacyTokenImportStep(
    db,
    providerAccountRegistry,
    legacyGitHubTokens,
    githubIdentityClient
  );
  const githubServices = {
    account: githubAccountService,
    cliImport: githubCliImporter,
    deviceFlow: githubDeviceFlow,
    legacyTokenImport: githubLegacyTokenImport,
    repositories: githubRepositories,
  };
  setCoreServiceInstances({
    appSettings: appSettingsService,
    notifications: notificationService,
    promptLibrary: promptLibraryService,
    providerSettings: providerOverrideSettings,
  });
  try {
    await step('services:telemetry-init', () =>
      telemetryService.initialize({
        appVersion: app.getVersion(),
        isPackaged: app.isPackaged,
        installSource: app.isPackaged ? 'dmg' : 'dev',
      })
    );
  } catch (error) {
    log.warn('telemetry init failed:', error);
  }

  projectSettingsService.initialize();
  pullRequestsRegistration.initialize();
  appService.initialize({
    acquireWorkspaceRuntime: createDesktopWorkspaceRuntimeAcquirer(runtimes, workspaceIdentity),
    emitHostEvent: (event) => desktopHostEvents.emit(undefined, event),
  });
  await step('services:app-settings-init', () => appSettingsService.initialize());
  applyNativeTheme(await appSettingsService.get('theme'));
  await step('services:notifications-init', () => notificationService.initialize());
  installUpdateNotifications(notificationService);
  browserWebContentsRegistry.setKeyboardSettings(await appSettingsService.get('keyboard'));
  setBrowserCorsRelaxationSettings(await appSettingsService.get('browser'));
  await step('services:prompt-library-init', () => promptLibraryService.initialize());
  // Plain project deletion (spec §3): the cascade reuses the task session cleanup and
  // the workspace removal verbs; nothing submits to the operations kernel.
  const projectDeletion: ProjectDeletionDependencies = {
    db,
    runtimes,
    getMementosRuntimeClient,
    logger: log,
    projects: projectManager,
    pullRequests: pullRequestsRegistration,
    sessionCleanup: lifecycleSessions,
    telemetry: telemetryService,
  };
  // Push-based mirror of each host's workspace registry (ADR 0005).
  const workspaceRegistrySync = new WorkspaceRegistrySyncService({
    db,
    runtimes,
    scope: appScope,
    onError: (context, error) => log.warn(context, { error }),
  });
  const workspaceRegistryBackfill = new WorkspaceRegistryBackfillService({
    db,
    runtimes,
    onError: (context, error) => log.warn(context, { error }),
  });
  const conversationSync = new ConversationSyncService({
    db,
    runtimes,
    scope: appScope,
    onError: (context, error) => log.warn(context, { error }),
  });
  const conversationBackfill = new ConversationBackfillService({
    db,
    runtimes,
    onError: (context, error) => log.warn(context, { error }),
  });
  // The operations kernel is gone (ADR 0006 demolition): best-effort cleanup of the
  // orphaned SQLite store older builds left next to the app database.
  cleanupLegacyOperationsDatabases(log);
  // The reconcile sweep (ADR 0006): tombstoned mirror rows are the durable deletion
  // queue; they converge whenever their host is reachable. Boot trigger: the local
  // host attaches once its registry sync is up; the service's internal 10-minute
  // backstop is the retry vehicle (per-item backoff, no separate scheduler).
  const reconcileSweep = new ReconcileSweepService({
    scope: appScope,
    onError: (context, error) => log.warn(context, { error: String(error) }),
  });
  reconcileSweep.registerKind(createWorkspaceDeletionSweepKind({ db, runtimes }));
  // Conversations sweep after workspaces: the same-host ordering heuristic lets a
  // workspace cascade's freshly written conversation tombstones converge in the same
  // pass; correctness never depends on the order (ADR 0006).
  reconcileSweep.registerKind(createConversationDeletionSweepKind({ db, runtimes }));
  const hostAttachments = new HostAttachmentRegistry({
    scope: appScope,
    ssh: infrastructure.ssh.manager,
    hosts: infrastructure.hosts,
    logger: log,
  });
  // Registration order is the per-host convergence order. Backfills precede the
  // authoritative live subscription, and workspace convergence precedes deletion sweeps.
  hostAttachments.register({
    label: 'conversation-sync',
    async attach(host) {
      await conversationBackfill.backfillHost(host);
      await conversationSync.attachHost(host);
    },
    detach: (host) => conversationSync.detachHost(host),
  });
  hostAttachments.register({
    label: 'workspace-registry-sync',
    async attach(host) {
      const backfill = await workspaceRegistryBackfill.backfillHost(host);
      if (backfill.status !== 'complete') return;
      await workspaceRegistrySync.attachHost(host);
      reconcileSweep.attachHost(host);
    },
    detach(host) {
      workspaceRegistrySync.detachHost(host);
      reconcileSweep.detachHost(host);
    },
  });
  // "Sync local settings" (spec: release-code-prep §6): mirror the local
  // watcherExclude to hosts whose toggle is ON — on attach, on local change,
  // and when the toggle flips ON. Fire-and-forget so a slow host never blocks
  // the per-host attachment chain; failures are logged inside the service.
  const localSettingsSync = new LocalSettingsSync({
    runtimes,
    getWatcherExclude: async () => (await appSettingsService.get('files')).watcherExclude,
    isSyncEnabled: async (connectionId) => {
      const machines = await infrastructure.ssh.machines.getMachines();
      return machines.find((machine) => machine.id === connectionId)?.syncLocalSettings ?? false;
    },
    logger: log,
  });
  hostAttachments.register({
    label: 'local-settings-sync',
    attach: (host) => {
      void localSettingsSync.attachHost(host);
    },
    detach: (host) => localSettingsSync.detachHost(host),
  });
  const handleLocalSettingsSyncChanged = (key: AppSettingsKey) => {
    if (key === 'files') void localSettingsSync.handleLocalSettingsChanged();
  };
  appSettingsService.on('app-settings:changed', handleLocalSettingsSyncChanged);
  appScope.add(() => {
    appSettingsService.off('app-settings:changed', handleLocalSettingsSyncChanged);
  });
  appScope.add(
    infrastructure.ssh.machines.on('machine:sync-local-settings-changed', (event) => {
      void localSettingsSync.handleSyncToggled(event.connectionId, event.enabled);
    })
  );
  // Tombstoned-while-reachable trigger: constructed here (composition root) and
  // installed on the module bridge the tombstone write paths poke.
  const reconcileSweepTriggers = createReconcileSweepTriggers();
  installReconcileSweepTriggers(reconcileSweepTriggers);
  appScope.add(
    reconcileSweepTriggers.subscribe((host) => {
      void reconcileSweep.sweepHost(host);
    })
  );
  const sessionHygieneDependencies = {
    agentStatus: agentStatusService,
    createSessionIntentStores: createDesktopSessionIntentStores,
    logger: log,
  };
  const sessionHygieneSweep = startPeriodicSweep({
    scope: appScope,
    intervalMs: 10 * 60 * 1000,
    run: () => sweepSessionHygiene(db, sessionHygieneDependencies),
    onError: (error) => {
      log.warn('session hygiene sweep failed', { error: String(error) });
    },
  });
  void sessionHygieneSweep.runNow().catch((error) => {
    log.warn('session hygiene sweep failed', { error: String(error) });
  });
  return {
    github: githubServices,
    gitCredentials,
    hostIsReachable,
    hostAttachments,
    notifications: notificationService,
    promptLibrary: promptLibraryService,
    projectDeletion,
    projects: projectManager,
    projectSettings: projectSettingsService,
    providerSettings: providerOverrideSettings,
    pullRequestsRegistration,
    search: searchService,
    taskService,
    taskSessions: taskSessionManager,
    workspacePlacement,
    conversationSync,
    reconcileSweep,
  };
}
