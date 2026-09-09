import path from 'node:path';
import type { FsError } from '@emdash/core/runtimes/files/api';
import {
  isRuntimeResolveError,
  runtimeResolveErrorAsError,
  type RuntimeBroker,
  type RuntimeResolveError,
} from '@emdash/core/services/runtime-broker/api';
import { err, ok, type Result } from '@emdash/shared';
import {
  ProjectProvider,
  type GitRepositoryFetchPort,
  type GitRepositoryPort,
  type ProjectProviderTransport,
} from '@core/features/projects/api/node/project-provider';
import { resolveProjectEffectiveSettings } from '@core/features/projects/api/node/settings/effective-settings';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import {
  hostPathFromNative,
  nativePathFromHost,
  relativeRuntimePath,
} from '@core/primitives/desktop-runtime/api';
import {
  builtInWorktreeRootFor,
  type EffectiveSettings,
} from '@core/primitives/project-settings/api';
import { projectHostRef, type Project } from '@core/primitives/projects/api';
import type { AppDb } from '@core/services/app-db/node/db';
import type {
  FilesRuntimeClient,
  GitRuntimeClient,
} from '@core/services/runtime-broker/api/clients';
import {
  fileKey,
  filesClientScope,
  fsErrorMessage,
} from '@core/services/runtime-broker/node/files';
import {
  checkoutSelector,
  gitFilePath,
  repositorySelector,
} from '@core/services/runtime-broker/node/git';
import { hostSettingsDefaults } from '@core/services/runtime-broker/node/host-settings';
import { ensureEmdashGitExcludedSafe } from './ensure-emdash-excluded';
import { migrateProjectSettingsOnAttachment } from './settings/migrations/migrate-project-settings-on-attachment';
import { ProjectSettingsRepository } from './settings/project-settings-storage';
import { HostProjectSettingsProvider } from './settings/providers/host-project-settings-provider';
import { createRepoFactsCache } from './settings/repo-facts';

export type CreateProviderError = { type: 'error'; message: string } | RuntimeResolveError;

export type CreateProjectProviderDependencies = {
  db: AppDb;
  createGitRepository(
    client: GitRuntimeClient,
    repository: ReturnType<typeof repositorySelector>,
    resolveEffectiveSettings: () => Promise<EffectiveSettings>
  ): GitRepositoryPort;
  createGitRepositoryFetch(
    client: GitRuntimeClient,
    repository: ReturnType<typeof repositorySelector>,
    getBaseRemote: () => Promise<string | null>
  ): GitRepositoryFetchPort;
  ensureAbsoluteDir(
    client: FilesRuntimeClient,
    rootPath: string,
    absolutePath: string,
    options?: { recursive?: boolean }
  ): Promise<Result<void, FsError>>;
  runtimes: Pick<RuntimeBroker, 'client'>;
  getProjectDefaults(): Promise<{
    tmuxByDefault: boolean;
  }>;
  taskSessions: Pick<TaskSessionManager, 'teardownAllForProject'>;
  /**
   * Lazy migration 5 (spec: github-git-settings §10): one-time move of the
   * app-wide defaultWorktreeDirectory into the local host default. Injected
   * from the composition root since it spans app settings and the local
   * host-settings runtime.
   */
  migrateAppWorktreeRoot?: () => Promise<void>;
};

export async function createProvider(
  dependencies: CreateProjectProviderDependencies,
  project: Project
): Promise<Result<ProjectProvider, CreateProviderError>> {
  try {
    const host = projectHostRef(project);
    const runtime = await dependencies.runtimes.client(host);
    if (!runtime.success) throw runtimeResolveErrorAsError(runtime.error);
    const git = runtime.data.git;
    const filesClient = runtime.data.files;
    const terminals = runtime.data.terminals;
    const projectFiles = filesClientScope(filesClient, project.path);
    const repository = repositorySelector(project.path);
    const checkout = checkoutSelector(project.path);
    const repositoryInspection = await git.inspectPath({ path: hostPathFromNative(project.path) });
    const hasRepository =
      !repositoryInspection.success || repositoryInspection.data.kind === 'repository';
    const gitInspector = {
      isFileCleanlyTracked: async (filePath: string) => {
        try {
          const relative = gitFilePath(relativeRuntimePath(checkout.checkout, filePath));
          const [index, status] = await Promise.all([
            git.checkout.getFile({ ...checkout, path: relative, source: { kind: 'index' } }),
            git.checkout.model.state(checkout, 'status').snapshot(),
          ]);
          if (!index.success || index.data.content === null || status.data.kind !== 'ok') {
            return false;
          }
          const entry = status.data.entries[relative];
          return !entry || (entry.index === 'unmodified' && entry.worktree === 'unmodified');
        } catch {
          return false;
        }
      },
    };
    const repoFacts = createRepoFactsCache(git, repository, hasRepository);
    const settings = new HostProjectSettingsProvider(
      project.id,
      project.path,
      project.baseRef,
      projectFiles,
      {
        git: gitInspector,
        storage: new ProjectSettingsRepository(dependencies.db),
        getRepoFacts: () => repoFacts.get(),
        // Placement layers below per-project overrides, answered on the
        // project's host. Worktree root uses the host default then its built-in
        // home-based path; tmux uses the host default then the desktop app
        // default. The retired desktop-wide worktree path is deliberately
        // absent — applying a desktop path to SSH hosts was a latent bug.
        placementContext: async () => {
          const [home, hostDefaults, appDefaults] = await Promise.all([
            filesClient.getHomeDir(),
            hostSettingsDefaults(runtime.data.hostSettings),
            dependencies.getProjectDefaults(),
          ]);
          const homeDirectory = nativePathFromHost(home.path);
          return {
            hostWorktreeRoot: hostDefaults.worktreeRoot ?? null,
            builtInWorktreeRoot: builtInWorktreeRootFor(homeDirectory),
            homeDirectory,
            hostTmux: hostDefaults.tmux ?? null,
            appDefaultTmux: appDefaults.tmuxByDefault,
          };
        },
        worktreeDirectoryFileSystem: {
          mkdir: async (targetPath, options) => {
            const result = await dependencies.ensureAbsoluteDir(
              filesClient,
              path.dirname(targetPath),
              targetPath,
              options
            );
            return result.success ? ok() : err({ message: fsErrorMessage(result.error) });
          },
          realPath: async (targetPath) => {
            const targetFiles = filesClientScope(filesClient, targetPath);
            const result = await filesClient.fs.realPath(fileKey(targetFiles, targetPath));
            return result.success
              ? ok(nativePathFromHost(result.data.path))
              : err({ message: fsErrorMessage(result.error) });
          },
        },
      }
    );
    await settings.ensure();
    await migrateProjectSettingsOnAttachment(project, settings, runtime.data.workspaceRegistry, {
      migrateAppWorktreeRoot: dependencies.migrateAppWorktreeRoot,
    });

    const repositoryService = dependencies.createGitRepository(git, repository, () =>
      resolveProjectEffectiveSettings({ settings, repoFacts, projectId: project.id })
    );

    ensureEmdashGitExcludedSafe(projectFiles, project.path, project.id);

    const transport: ProjectProviderTransport = {
      kind: project.type,
      defaultWorkspaceType:
        project.type === 'ssh'
          ? { kind: 'ssh', connectionId: project.connectionId }
          : { kind: 'local' },
      files: projectFiles,
      projectConfigPath: path.join(project.path, '.hardcore.json'),
      resolveProjectPath: (relativePath) => path.join(project.path, relativePath),
      configPathForDirectory: (directoryPath) => path.join(directoryPath, '.hardcore.json'),
      settings,
      workspaceRegistry: runtime.data.workspaceRegistry,
      repoFacts,
    };
    const fetchService = dependencies.createGitRepositoryFetch(git, repository, () =>
      repositoryService.getBaseRemote()
    );
    if (hasRepository) fetchService.start();

    const provider = new ProjectProvider(
      project,
      transport,
      repositoryService,
      fetchService,
      hasRepository,
      git,
      terminals,
      repository,
      dependencies.taskSessions,
      () => {}
    );
    return ok(provider);
  } catch (error) {
    return err(toCreateProviderError(error));
  }
}

function toCreateProviderError(error: unknown): CreateProviderError {
  if (isRuntimeResolveError(error)) return error;
  return { type: 'error', message: error instanceof Error ? error.message : String(error) };
}
