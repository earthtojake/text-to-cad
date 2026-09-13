import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { isRuntimeResolveError } from '@emdash/core/services/runtime-broker/api';
import { err, ok, type Result } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import {
  createLiveJobReplicaCache,
  LiveJobCancelledError,
  LiveJobFailedError,
} from '@emdash/wire/live';
import { remote, type RemoteModel } from '@emdash/wire/state';
import { makeObservable, observable, runInAction } from 'mobx';
import { getGithubClient } from '@core/features/github/api/browser/client';
import { projectsWireContract, type ProjectCreationProgress } from '@core/features/projects/api';
import { getProjectsWireClient } from '@core/features/projects/api/browser/client';
import {
  createRegisteredProject,
  createUnregisteredProject,
  isUnregisteredProject,
  type ProjectCreationStage,
  type ProjectStore,
} from '@core/features/projects/api/browser/stores/project';
import { ProjectContext } from '@core/features/projects/browser/stores/project-context';
import type { ProjectScopedStoreContext } from '@core/features/projects/contributions/project-stores';
import { projectSubject } from '@core/features/projects/contributions/subject';
import { projectViewDef } from '@core/features/projects/contributions/views';
import { taskManagerStoreToken } from '@core/features/tasks/contributions/browser/project-store-tokens';
import { taskSubject } from '@core/features/tasks/contributions/subject';
import { homeViewDef } from '@core/features/workbench/contributions/views';
import { log } from '@core/primitives/logging/browser/logger';
import { getMementoClient } from '@core/primitives/mementos/browser';
import {
  getNavigation,
  getNavigationHistory,
} from '@core/primitives/navigation/browser/navigation-selectors';
import { type LocalProject, type SshProject } from '@core/primitives/projects/api';
import { splitNameWithOwner } from '@core/primitives/repository/api';
import type { ScopedStoreContribution } from '@core/primitives/scoped-stores/browser';
import { captureTelemetry } from '@core/primitives/telemetry/browser/telemetry-client';
import { observeReadableInAction } from '@core/primitives/wire/browser/mobx-readable';
import { hostsContract } from '@core/services/hosts/api';
import { getHostsClient } from '@core/services/hosts/api/client';
import type {
  ModeData,
  ProjectCreationCompletion,
  ProjectCreationError,
  ProjectType,
  StartProjectCreationOptions,
  StartProjectCreationResult,
} from '../../../browser/stores/project-creation-types';

interface ProjectContextHydration {
  readonly identity: object;
  readonly promise: Promise<void>;
}

export class ProjectManagerStore {
  projects = observable.map<string, ProjectStore>();
  pendingCreationIds = observable.set<string>();
  private _projectCreationJobs = new Map<string, { cancel(): Promise<void> }>();
  private _projectContextHydrations = new Map<string, ProjectContextHydration>();
  private _loadPromise: Promise<void> | null = null;
  private readonly _projectListScope: Scope = createScope({ label: 'project-list-replica' });
  private readonly _projectContextScope: Scope = createScope({ label: 'project-contexts' });
  private _projectListRemote: RemoteModel<typeof projectsWireContract.projectList> | null = null;
  private _attachmentsRemote: RemoteModel<typeof projectsWireContract.attachments> | null = null;
  private _attachmentsRemotePromise: Promise<
    RemoteModel<typeof projectsWireContract.attachments>
  > | null = null;
  private _hostAvailabilityRemote: RemoteModel<typeof hostsContract.availability> | null = null;
  private _hostAvailabilityRemotePromise: Promise<
    RemoteModel<typeof hostsContract.availability>
  > | null = null;
  private _disposed = false;

  constructor(
    private readonly projectStoreContributions: readonly ScopedStoreContribution<ProjectScopedStoreContext>[]
  ) {
    makeObservable(this, { projects: observable, pendingCreationIds: observable });
  }

  dispose(): void {
    if (this._disposed) return;
    this._disposed = true;
    this._projectContextHydrations.clear();
    runInAction(() => {
      for (const project of this.projects.values()) {
        if (project.context?.kind === 'available') void project.context.context.dispose();
      }
      this.projects.clear();
    });
    void this._projectContextScope.dispose();
    void this._projectListScope.dispose();
    void this._projectListRemote?.dispose();
  }

  /**
   * Resolves once the first project-list snapshot has been applied, so callers
   * can rely on the sidebar being populated. Project contexts start here but
   * complete in the background; the boot gate awaits only the desktop context
   * required by the last-active view.
   */
  load(): Promise<void> {
    if (!this._loadPromise) {
      this._loadPromise = this._doLoad();
    }
    return this._loadPromise;
  }

  private async _doLoad(): Promise<void> {
    const client = await getProjectsWireClient();
    this._projectListRemote ??= remote(projectsWireContract.projectList, client.projectList, {
      scope: this._projectListScope,
      lingerMs: 15_000,
    });
    const member = this._projectListRemote(undefined);
    await new Promise<void>((resolve, reject) => {
      let resolved = false;
      observeReadableInAction(
        member.states.list,
        (current) => {
          if (current.status === 'error') {
            reject(current.error);
            return;
          }
          if (!current.value) return;
          this._applyProjectListSnapshot(current.value.projects);
          if (resolved) return;
          resolved = true;
          resolve();
        },
        { scope: this._projectListScope }
      );
    });
  }

  private _applyProjectListSnapshot(rows: readonly (LocalProject | SshProject)[]): void {
    if (this._disposed) return;
    const seen = new Set(rows.map((project) => project.id));
    for (const project of rows) {
      this._applyProjectSnapshot(project);
    }
    runInAction(() => {
      for (const [projectId, project] of this.projects) {
        if (seen.has(projectId) || this.pendingCreationIds.has(projectId)) continue;
        this.projects.delete(projectId);
        this._projectContextHydrations.delete(projectId);
        if (project.context?.kind === 'available') void project.context.context.dispose();
      }
    });
  }

  private _applyProjectSnapshot(project: LocalProject | SshProject): void {
    let store: ProjectStore | undefined;
    runInAction(() => {
      const current = this.projects.get(project.id);
      if (!current) {
        store = createRegisteredProject(project);
        this.projects.set(project.id, store);
        return;
      }
      store = current;
      if (isUnregisteredProject(current)) {
        current.register(project);
        return;
      }
      current.updateData(project);
    });
    if (store?.data && store.context === null) {
      void this._startOrReuseProjectContext(store.id);
    }
  }

  private _startOrReuseProjectContext(projectId: string): Promise<void> {
    if (this._disposed) return Promise.resolve();
    const inFlight = this._projectContextHydrations.get(projectId);
    if (inFlight) return inFlight.promise;
    const store = this.projects.get(projectId);
    if (!store?.data || store.context?.kind === 'available') return Promise.resolve();

    const project = store.data;
    const identity = {};
    runInAction(() => {
      store.context = { kind: 'hydrating', project };
    });
    const promise = ProjectContext.hydrate(project, this.projectStoreContributions)
      .then(async (result) => {
        if (!this._isCurrentProjectContextHydration(projectId, identity, store)) {
          if (result.success) await result.data.dispose();
          return;
        }
        if (!result.success) {
          runInAction(() => {
            if (this._isCurrentProjectContextHydration(projectId, identity, store)) {
              store.context = {
                kind: 'failed',
                project,
                error: result.error,
              };
            }
          });
          return;
        }

        const context = result.data;
        runInAction(() => {
          if (this._isCurrentProjectContextHydration(projectId, identity, store)) {
            store.context = { kind: 'available', context };
          }
        });
        if (store.context?.kind !== 'available' || store.context.context !== context) {
          await context.dispose();
          return;
        }
        void this._hydrateProjectContext(context).catch((error: unknown) => {
          if (this.projects.get(projectId)?.context?.kind !== 'available') return;
          log.error('Failed to hydrate Project context tasks', { projectId, error });
        });
        try {
          await this._trackProjectContextHostAccess(projectId, store, context);
        } catch (error) {
          if (!this._disposed) {
            log.error('Failed to track project attachment', { projectId, error });
          }
        }
      })
      .finally(() => {
        if (this._projectContextHydrations.get(projectId)?.identity === identity) {
          this._projectContextHydrations.delete(projectId);
        }
      });
    this._projectContextHydrations.set(projectId, { identity, promise });
    return promise;
  }

  private _isCurrentProjectContextHydration(
    projectId: string,
    identity: object,
    store: ProjectStore
  ): boolean {
    return (
      !this._disposed &&
      this._projectContextHydrations.get(projectId)?.identity === identity &&
      this.projects.get(projectId) === store
    );
  }

  private _disposeMissingProjectContext(
    projectId: string,
    store: ProjectStore,
    context: ProjectContext
  ): void {
    if (
      this.projects.get(projectId) !== store ||
      store.context?.kind !== 'available' ||
      store.context.context !== context
    ) {
      return;
    }
    const projectIds = [...this.projects.keys()];
    const missingIndex = projectIds.indexOf(projectId);
    const adjacentProjectId =
      projectIds[missingIndex + 1] ?? projectIds[missingIndex - 1] ?? undefined;
    runInAction(() => {
      this.projects.delete(projectId);
      this._projectContextHydrations.delete(projectId);
    });
    const navigation = getNavigation();
    const current = navigation.currentRef;
    const currentProjectId =
      current.viewId === 'project' || current.viewId === 'task'
        ? (current.params as { projectId?: string }).projectId
        : undefined;
    if (currentProjectId === projectId) {
      navigation.navigate(
        adjacentProjectId ? projectViewDef({ projectId: adjacentProjectId }) : homeViewDef()
      );
    }
    navigation.invalidateSubject(projectSubject({ projectId }));
    getNavigationHistory().prune((entry) => {
      const params = entry.ref.params as { projectId?: string };
      return params.projectId === projectId;
    });
    void context.dispose().catch(() => log.error('Failed to dispose a missing Project context'));
  }

  private async _trackProjectContextHostAccess(
    projectId: string,
    store: ProjectStore,
    context: ProjectContext
  ): Promise<void> {
    const [availability, attachments] = await Promise.all([
      this._getHostAvailabilityRemote(),
      this._getAttachmentsRemote(),
    ]);
    if (
      this._disposed ||
      this.projects.get(projectId) !== store ||
      store.context?.kind !== 'available' ||
      store.context.context !== context
    ) {
      return;
    }
    context.trackHostAccess(
      availability,
      attachments,
      async () => (await getProjectsWireClient()).recoverAttachment({ projectId }),
      () => this._disposeMissingProjectContext(projectId, store, context)
    );
  }

  private _getAttachmentsRemote(): Promise<RemoteModel<typeof projectsWireContract.attachments>> {
    if (this._attachmentsRemote) return Promise.resolve(this._attachmentsRemote);
    this._attachmentsRemotePromise ??= getProjectsWireClient().then((client) => {
      if (this._disposed) throw new Error('ProjectManagerStore is disposed');
      return (this._attachmentsRemote ??= remote(
        projectsWireContract.attachments,
        client.attachments,
        {
          scope: this._projectContextScope,
          lingerMs: 0,
        }
      ));
    });
    return this._attachmentsRemotePromise;
  }

  private _getHostAvailabilityRemote(): Promise<RemoteModel<typeof hostsContract.availability>> {
    if (this._hostAvailabilityRemote) return Promise.resolve(this._hostAvailabilityRemote);
    this._hostAvailabilityRemotePromise ??= getHostsClient().then((client) => {
      if (this._disposed) throw new Error('ProjectManagerStore is disposed');
      return (this._hostAvailabilityRemote ??= remote(
        hostsContract.availability,
        client.availability,
        {
          scope: this._projectContextScope,
          lingerMs: 0,
        }
      ));
    });
    return this._hostAvailabilityRemotePromise;
  }

  private _applyRegisteredProjectSnapshot(project: LocalProject | SshProject): void {
    this._applyProjectSnapshot(project);
  }

  async createProject(
    projectType: ProjectType,
    data: ModeData,
    id?: string
  ): Promise<string | undefined> {
    const result = await this.startProjectCreation(projectType, data, { id });
    if (result.kind === 'existing') return result.projectId;

    const completion = await result.completion;
    return completion.success ? result.projectId : undefined;
  }

  async startProjectCreation(
    projectType: ProjectType,
    data: ModeData,
    options: StartProjectCreationOptions = {}
  ): Promise<StartProjectCreationResult> {
    const isSsh = projectType.type === 'ssh';
    const projectId = options.id ?? crypto.randomUUID();
    const targetPathResult =
      data.mode === 'pick'
        ? ok(data.path)
        : await (
            await getProjectsWireClient()
          ).resolveRepositoryDestination({
            host: isSsh ? hostRef('remote', projectType.connectionId) : LOCAL_HOST_REF,
            name: data.name,
            chosenDir: data.path,
          });
    if (!targetPathResult.success) {
      runInAction(() => {
        this.projects.set(
          projectId,
          createUnregisteredProject(
            projectId,
            data.name,
            { kind: 'running', stage: initialCreationStage(data.mode) },
            data.mode
          )
        );
      });
      this._markCreationError(projectId, targetPathResult.error);
      return {
        kind: 'creating',
        projectId,
        completion: Promise.resolve(err(targetPathResult.error)),
      };
    }
    const targetPath = targetPathResult.data;
    const inspection = await (
      await getProjectsWireClient()
    ).inspectProjectPath(
      isSsh
        ? { type: 'ssh', path: targetPath, connectionId: projectType.connectionId }
        : { type: 'local', path: targetPath }
    );
    if (inspection.existingProject) {
      return { kind: 'existing', projectId: inspection.existingProject.id };
    }

    runInAction(() => {
      this.pendingCreationIds.add(projectId);
      this.projects.set(
        projectId,
        createUnregisteredProject(
          projectId,
          data.name,
          { kind: 'running', stage: initialCreationStage(data.mode) },
          data.mode
        )
      );
    });

    const completion = this._doCreateProject(projectType, data, projectId, targetPath).finally(
      () => {
        runInAction(() => this.pendingCreationIds.delete(projectId));
      }
    );

    return { kind: 'creating', projectId, completion };
  }

  private async _doCreateProject(
    projectType: ProjectType,
    data: ModeData,
    projectId: string,
    targetPath: string
  ): Promise<ProjectCreationCompletion> {
    const projectsClient = await getProjectsWireClient();
    const isSsh = projectType.type === 'ssh';
    const projectTelemetryType: 'local' | 'ssh' = isSsh ? 'ssh' : 'local';
    const projectTelemetryStrategy: 'open' | 'create' | 'clone' =
      data.mode === 'clone' ? 'clone' : data.mode === 'new' ? 'create' : 'open';

    let result: ProjectCreationCompletion;
    try {
      switch (data.mode) {
        case 'pick': {
          const projectResult =
            projectType.type === 'ssh'
              ? await projectsClient.createProject({
                  type: 'ssh',
                  id: projectId,
                  path: targetPath,
                  name: data.name,
                  connectionId: projectType.connectionId,
                  initGitRepository: data.initGitRepository,
                })
              : await projectsClient.createProject({
                  type: 'local',
                  id: projectId,
                  path: targetPath,
                  name: data.name,
                  initGitRepository: data.initGitRepository,
                });
          if (!projectResult.success) {
            result = err(projectResult.error);
            break;
          }

          const project = projectResult.data;
          if (data.initGitRepository) {
            await this._saveInitialGitHubAccountSetting(project.id, data.githubAccountId);
          }
          this._applyRegisteredProjectSnapshot(project);
          result = ok();
          break;
        }

        case 'clone': {
          const projectResult = await this._createProjectFromRemote({
            projectId,
            host:
              projectType.type === 'ssh'
                ? { type: 'ssh', connectionId: projectType.connectionId }
                : { type: 'local' },
            mode: 'clone',
            repositoryUrl: data.repositoryUrl,
            targetPath,
            name: data.name,
          });
          if (!projectResult.success) {
            result = err(projectResult.error);
            break;
          }

          this._applyRegisteredProjectSnapshot(projectResult.data);
          result = ok();
          break;
        }

        case 'new': {
          const repoResult = await (
            await getGithubClient()
          ).createRepository({
            name: data.repositoryName,
            owner: data.repositoryOwner,
            isPrivate: data.repositoryVisibility === 'private',
            accountId: data.githubAccountId ?? undefined,
          });
          if (!repoResult.success) {
            result = err({
              type: 'repository-create-failed',
              message: repoResult.error?.trim() || 'Repository creation failed',
            });
            break;
          }
          if (!repoResult.nameWithOwner || !repoResult.cloneUrl) {
            result = err({
              type: 'repository-response-incomplete',
              message: 'Repository creation response was incomplete',
            });
            break;
          }

          const projectResult = await this._cloneAndCreateGitHubProject({
            projectType,
            projectId,
            targetPath,
            name: data.name,
            cloneUrl: repoResult.cloneUrl,
            repositoryNameWithOwner: repoResult.nameWithOwner,
            githubAccountId: data.githubAccountId,
          });
          if (!projectResult.success) {
            result = err(projectResult.error);
            break;
          }

          const project = projectResult.data;
          await this._saveInitialGitHubAccountSetting(project.id, data.githubAccountId);
          this._applyRegisteredProjectSnapshot(project);
          result = ok();
          break;
        }
      }
    } catch (error) {
      this._markUnexpectedCreationError(projectId, error);
      captureTelemetry('project_added', {
        type: projectTelemetryType,
        strategy: projectTelemetryStrategy,
        success: false,
      });
      throw error;
    }

    if (!result.success) {
      if (result.error.type === 'cancelled') {
        this.removeUnregisteredProject(projectId);
      } else {
        this._markCreationError(projectId, result.error);
      }
    }
    captureTelemetry('project_added', {
      type: projectTelemetryType,
      strategy: projectTelemetryStrategy,
      success: result.success,
    });
    return result;
  }

  hydrateProjectContext(projectId: string): Promise<void> {
    return this._startOrReuseProjectContext(projectId);
  }

  private async _hydrateProjectContext(context: ProjectContext): Promise<void> {
    const taskManager = context.get(taskManagerStoreToken);
    await taskManager.loadTasks();
    const currentContext = this.projects.get(context.project.id)?.context;
    if (
      this._disposed ||
      currentContext?.kind !== 'available' ||
      currentContext.context !== context
    ) {
      return;
    }

    const nav = getNavigation();
    const navParams = nav.currentRef.params as {
      projectId?: string;
      taskId?: string;
    };
    const navTaskId =
      nav.currentViewId === 'task' && navParams.projectId === context.project.id
        ? navParams.taskId
        : undefined;
    if (navTaskId) void taskManager.provisionTask(navTaskId).catch(() => {});
  }

  async deleteProject(projectId: string): Promise<void> {
    const snapshot = this.projects.get(projectId);
    const contextWasHydrating = snapshot?.context?.kind === 'hydrating';
    const taskIds = [
      ...(snapshot?.context?.kind === 'available'
        ? snapshot.context.context.get(taskManagerStoreToken).tasks.keys()
        : []),
    ];
    const projectIds = [...this.projects.keys()];
    const deletedIndex = projectIds.indexOf(projectId);
    const adjacentProjectId =
      projectIds[deletedIndex + 1] ?? projectIds[deletedIndex - 1] ?? undefined;
    const current = getNavigation().currentRef;
    const currentProjectId =
      current.viewId === 'project' || current.viewId === 'task'
        ? (current.params as { projectId?: string }).projectId
        : undefined;
    if (currentProjectId === projectId) {
      getNavigation().navigate(
        adjacentProjectId ? projectViewDef({ projectId: adjacentProjectId }) : homeViewDef()
      );
    }

    runInAction(() => {
      this.projects.delete(projectId);
      this._projectContextHydrations.delete(projectId);
    });
    try {
      const result = await (await getProjectsWireClient()).delete({ projectId });
      if (!result.success) throw new Error(result.error.message);
      for (const taskId of taskIds) {
        getNavigation().invalidateSubject(taskSubject({ taskId }));
      }
      getNavigation().invalidateSubject(projectSubject({ projectId }));
      // Prune any task refs not represented in the loaded desktop Task records.
      getNavigationHistory().prune((entry) => {
        const params = entry.ref.params as { projectId?: string };
        return params.projectId === projectId;
      });
      if (snapshot?.context?.kind === 'available') {
        await snapshot.context.context.dispose();
      }
      const mementos = getMementoClient();
      const subjects = [
        projectSubject({ projectId }),
        ...taskIds.map((taskId) => taskSubject({ taskId })),
      ];
      const cleanupResults = await Promise.allSettled(
        subjects.map(async (subject) => await mementos.deleteBySubject(subject))
      );
      for (const cleanupResult of cleanupResults) {
        if (cleanupResult.status === 'rejected') mementos.reportError(cleanupResult.reason);
      }
    } catch (err) {
      runInAction(() => {
        if (snapshot) {
          if (contextWasHydrating) snapshot.context = null;
          this.projects.set(projectId, snapshot);
        }
      });
      if (contextWasHydrating) void this._startOrReuseProjectContext(projectId);
      throw err;
    }
  }

  async updateProjectConnection(projectId: string, newConnectionId: string): Promise<void> {
    await (
      await getProjectsWireClient()
    ).updateProjectConnection({
      projectId,
      connectionId: newConnectionId,
    });

    const store = this.projects.get(projectId);
    const data = store?.data;
    if (!store || !data || data.type !== 'ssh') return;

    runInAction(() => {
      store.updateData({ ...data, connectionId: newConnectionId });
    });
    if (store.context?.kind === 'available') {
      await this._trackProjectContextHostAccess(
        projectId,
        store,
        store.context.context as ProjectContext
      );
    }
  }

  removeUnregisteredProject(projectId: string): void {
    runInAction(() => {
      const store = this.projects.get(projectId);
      if (store && isUnregisteredProject(store)) {
        this.projects.delete(projectId);
      }
    });
  }

  cancelProjectCreation(projectId: string): void {
    void this._projectCreationJobs.get(projectId)?.cancel();
  }

  private async _saveInitialGitHubAccountSetting(
    projectId: string,
    githubAccountId?: string
  ): Promise<void> {
    if (githubAccountId === undefined) return;

    const result = await (
      await getProjectsWireClient()
    ).updateProjectSettings({
      projectId,
      patch: {
        gitIdentity: {
          stored: { githubAccount: { kind: 'account', accountId: githubAccountId } },
        },
      },
    });
    if (!result.success) {
      log.error('Failed to save initial GitHub account for project', {
        projectId,
        error: result.error,
      });
    }
  }

  private async _rollbackCreatedGitHubRepository(
    nameWithOwner: string,
    githubAccountId?: string
  ): Promise<void> {
    try {
      const { owner, repo } = splitNameWithOwner(nameWithOwner);
      const result = await (
        await getGithubClient()
      ).deleteRepository({
        owner,
        name: repo,
        accountId: githubAccountId ?? undefined,
      });
      if (!result.success) {
        log.error('Failed to delete GitHub repository after project creation failure', {
          nameWithOwner,
          error: result.error,
        });
      }
    } catch (error) {
      log.error('Failed to delete GitHub repository after project creation failure', {
        nameWithOwner,
        error,
      });
    }
  }

  private async _createProjectFromRemote(opts: {
    projectId: string;
    host: { type: 'local' } | { type: 'ssh'; connectionId: string };
    mode: 'clone' | 'new';
    repositoryUrl: string;
    targetPath: string;
    name: string;
  }): Promise<Result<LocalProject | SshProject, ProjectCreationError>> {
    const client = await getProjectsWireClient();
    const jobs = createLiveJobReplicaCache(projectsWireContract.create, client.create);
    const lease = await jobs.start({
      projectId: opts.projectId,
      host: opts.host,
      mode: opts.mode,
      repositoryUrl: opts.repositoryUrl,
      targetPath: opts.targetPath,
      name: opts.name,
    });
    const job = await lease.ready();
    this._projectCreationJobs.set(opts.projectId, job);
    const unsubscribe = job.onProgress((progress) => {
      this._updatePhase(
        opts.projectId,
        progress.phase === 'registering' ? 'registering' : 'cloning',
        progress
      );
    });

    try {
      return ok(await job.result);
    } catch (error) {
      return err(projectWireErrorToCreationError(error));
    } finally {
      unsubscribe();
      if (this._projectCreationJobs.get(opts.projectId) === job) {
        this._projectCreationJobs.delete(opts.projectId);
      }
      await lease.release();
      await jobs.dispose();
    }
  }

  private async _cloneAndCreateGitHubProject(opts: {
    projectType: ProjectType;
    projectId: string;
    targetPath: string;
    name: string;
    cloneUrl: string;
    repositoryNameWithOwner: string;
    githubAccountId?: string;
  }): Promise<Result<LocalProject | SshProject, ProjectCreationError>> {
    let result: Result<LocalProject | SshProject, ProjectCreationError>;
    try {
      result = await this._createProjectFromRemote({
        projectId: opts.projectId,
        host:
          opts.projectType.type === 'ssh'
            ? { type: 'ssh', connectionId: opts.projectType.connectionId }
            : { type: 'local' },
        mode: 'new',
        repositoryUrl: opts.cloneUrl,
        targetPath: opts.targetPath,
        name: opts.name,
      });
    } catch (error) {
      await this._rollbackCreatedGitHubRepository(
        opts.repositoryNameWithOwner,
        opts.githubAccountId
      );
      throw error;
    }

    if (!result.success) {
      await this._rollbackCreatedGitHubRepository(
        opts.repositoryNameWithOwner,
        opts.githubAccountId
      );
    }
    return result;
  }

  private _updatePhase(
    id: string,
    stage: ProjectCreationStage,
    progress?: ProjectCreationProgress
  ): void {
    runInAction(() => {
      const store = this.projects.get(id);
      if (store && isUnregisteredProject(store)) {
        store.updateCreationProgress(stage, progress);
      }
    });
  }

  private _markCreationError(id: string, error: ProjectCreationError): void {
    runInAction(() => {
      const store = this.projects.get(id);
      if (store && isUnregisteredProject(store)) {
        const message =
          error.type === 'not-repository'
            ? 'Directory is not a git repository. Enable "Initialize git repository" to continue.'
            : error.type === 'inspect-failed'
              ? `Could not inspect directory: ${error.message}`
              : error.message;
        store.failCreation(message);
      }
    });
  }

  private _markUnexpectedCreationError(id: string, error: unknown): void {
    runInAction(() => {
      const store = this.projects.get(id);
      if (store && isUnregisteredProject(store)) {
        store.failCreation(error instanceof Error ? error.message : String(error));
      }
    });
  }
}

function initialCreationStage(mode: ModeData['mode']): ProjectCreationStage {
  switch (mode) {
    case 'pick':
      return 'registering';
    case 'clone':
      return 'cloning';
    case 'new':
      return 'creating-repo';
  }
}

function projectWireErrorToCreationError(error: unknown): ProjectCreationError {
  if (error instanceof LiveJobCancelledError) {
    return { type: 'cancelled', message: 'Project creation was cancelled' };
  }

  const payload = error instanceof LiveJobFailedError ? error.error : error;
  if (isRuntimeResolveError(payload)) return payload;
  if (typeof payload === 'object' && payload !== null) {
    const type = (payload as { type?: unknown }).type;
    const message = (payload as { message?: unknown }).message;
    const fallback = typeof message === 'string' ? message : 'Project creation failed';
    if (type === 'cancelled') return { type: 'cancelled', message: fallback };
    if (type === 'initialize-failed') return { type: 'initialize-failed', message: fallback };
    if (type === 'not-repository') return { type: 'not-repository', path: '' };
    if (type === 'inspect-failed') {
      return {
        type: 'inspect-failed',
        path: '',
        message: fallback,
      };
    }
    if (type === 'invalid-directory') {
      return {
        type: 'invalid-directory',
        path: '',
        message: fallback,
      };
    }
    return { type: 'clone-failed', message: fallback };
  }
  return {
    type: 'clone-failed',
    message: error instanceof Error ? error.message : String(error),
  };
}
