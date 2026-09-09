import { sshConnectionIdOf } from '@emdash/core/primitives/host/api';
import { parseAbsolute } from '@emdash/core/primitives/path/api';
import type { HostRuntimesClient, RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { err, ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import { and, eq, isNull, sql } from 'drizzle-orm';
import type { ConversationProvider } from '@core/features/conversations/api/node/types';
import {
  PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE,
  type ProjectAttachmentError,
} from '@core/features/projects/api';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import type {
  ProjectProvider,
  ProvisionResult as SessionProvisionResult,
} from '@core/features/projects/api/node/project-provider';
import { buildTaskFromWorkspace } from '@core/features/tasks/api/node/task-provider-assembly';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import { mapTaskRowToTask } from '@core/features/tasks/api/node/utils/utils';
import {
  activateWorkspaceParticipants,
  deactivateWorkspaceParticipants,
  type WorkspaceLifecycleParticipant,
} from '@core/features/workspaces/api/node/lifecycle-participants';
import type { WorkspacePlacementResolver } from '@core/features/workspaces/api/node/placement/workspace-placement-resolver';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import {
  createWorktreeThroughRegistry,
  type WorkspaceCreationOutcome,
  type WorkspaceCreations,
} from '@core/features/workspaces/api/node/registry-verbs';
import { tryAcquireWorkspaceRuntime } from '@core/features/workspaces/api/node/runtime-access';
import { deriveBranchName } from '@core/features/workspaces/api/node/workspace-branch';
import type { TaskProviderOpts } from '@core/features/workspaces/api/node/workspace-factory';
import type { WorkspaceIdentityService } from '@core/features/workspaces/api/node/workspace-identity-service';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { HookCore, type Hookable } from '@core/primitives/hooks/api/hookable';
import type { LinkedIssue } from '@core/primitives/linked-issues/api';
import type {
  CreateTaskError,
  CreateTaskParams,
  CreateTaskSuccess,
  DeleteTaskOptions,
  ProvisionTaskResult,
  ProvisionWorkspaceError,
  RenameTaskError,
  RenameTaskSuccess,
  Task,
} from '@core/primitives/tasks/api';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import { compileWorktreeGitPlan } from '@core/primitives/workspaces/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { tasks, type WorkspaceRow } from '@core/services/app-db/node/schema';
import { archiveTask } from '../../node/operations/archiveTask';
import { createTask, resolveProjectPreservePatterns } from '../../node/operations/createTask';
import {
  deleteTask,
  type DeleteTaskInput,
  type TaskDeletionDependencies,
  type TaskDeletionResult,
} from '../../node/operations/deleteTask';
import { getDeletePreflight } from '../../node/operations/getDeletePreflight';
import { getTasks } from '../../node/operations/getTasks';
import { renameTask } from '../../node/operations/renameTask';
import { restoreTask } from '../../node/operations/restoreTask';
import { setTaskPinned } from '../../node/operations/setTaskPinned';
import { updateLinkedIssue } from '../../node/operations/updateLinkedIssue';
import { updateTaskStatus } from '../../node/operations/updateTaskStatus';
import type { TeardownTaskError } from './task-session-manager';

type ProvisionResult = ProvisionTaskResult & { sshConnectionId?: string };
type ActivatedTask = SessionProvisionResult & {
  path: string;
  runtimeWorkspace: ReturnType<typeof hostFileRefFromNativePath>;
};

export type TaskLifecycleHooks = {
  'task:created': (task: Task, params: CreateTaskParams) => void | Promise<void>;
  'task:updated': (task: Task) => void | Promise<void>;
  'task:archived': (taskId: string, projectId: string) => void | Promise<void>;
  'task:deleted': (taskId: string, projectId: string) => void | Promise<void>;
  'task:workspace-ready': (taskId: string, result: ProvisionResult) => void | Promise<void>;
  /** Fires after a full (non-fast-path) provision succeeds, with the wall-clock cost. */
  'task:provision-timing': (info: { taskId: string; durationMs: number }) => void | Promise<void>;
};

export class TaskService implements Hookable<TaskLifecycleHooks> {
  private readonly _hooks = new HookCore<TaskLifecycleHooks>((name, e) =>
    log.error(`TaskService: ${String(name)} hook error`, { error: e })
  );

  constructor(
    private readonly dependencies: {
      db: AppDb;
      projects: Pick<ProjectAttachmentManager, 'requireAttached'>;
      sessions: TaskSessionManager;
      workspacePlacement: WorkspacePlacementResolver;
      runtimes: RuntimeBroker;
      lifecycleParticipants: readonly WorkspaceLifecycleParticipant[];
      createConversationProvider(options: TaskProviderOpts): ConversationProvider;
      workspaceIdentity: WorkspaceIdentityService;
      creations: WorkspaceCreations;
      deletion: TaskDeletionDependencies;
    }
  ) {}

  on<K extends keyof TaskLifecycleHooks>(name: K, handler: TaskLifecycleHooks[K]) {
    return this._hooks.on(name, handler);
  }

  async createTask(params: CreateTaskParams): Promise<Result<CreateTaskSuccess, CreateTaskError>> {
    const result = await createTask(
      this.dependencies.db,
      this.dependencies.projects,
      this.dependencies.workspacePlacement,
      this.dependencies.runtimes,
      this.dependencies.creations,
      params
    );
    if (result.success) {
      this.notifyTaskCreated(result.data.task, params);
    }
    return result;
  }

  /** Fires the task:created hook. Call this after committing a task insert
   *  that was performed outside of `createTask` (e.g. inside an external transaction). */
  notifyTaskCreated(task: Task, params: CreateTaskParams): void {
    this._hooks.callHookBackground('task:created', task, params);
  }

  /**
   * Provisions the workspace for a task: ensures the path is on disk, acquires
   * the workspace (running lifecycle scripts), builds task providers, and
   * registers the task session. Idempotent — fast-paths when already provisioned.
   * Fires the `task:workspace-ready` hook on success so the workspaces wire host
   * can publish durable status to renderer replicas.
   */
  async provisionWorkspace(
    taskId: string,
    signal?: AbortSignal
  ): Promise<Result<ProvisionResult, ProvisionWorkspaceError>> {
    const [row] = await this.dependencies.db
      .select()
      .from(tasks)
      .where(and(eq(tasks.id, taskId), isNull(tasks.deletedAt)))
      .limit(1);
    if (!row) throw new Error(`Task not found: ${taskId}`);
    // Idempotency: task is already live — return current state.
    const existingTask = this.dependencies.sessions.getTask(taskId);
    if (existingTask) {
      const pd = this.dependencies.sessions.getPersistData(taskId);
      const wsId = pd?.workspaceId ?? '';
      const identity = wsId ? await this.dependencies.workspaceIdentity.resolve(wsId) : null;
      const provisionResult: ProvisionResult = {
        path: identity?.path ?? '',
        workspaceId: wsId,
        sshConnectionId: pd?.sshConnectionId,
      };
      this._hooks.callHookBackground('task:workspace-ready', taskId, provisionResult);
      return ok(provisionResult);
    }

    const attached = this.dependencies.projects.requireAttached(row.projectId);
    if (!attached.success) return err(provisionProjectError(attached.error));

    const startedAt = Date.now();
    const result = await this._activateWorkspace(row, attached.data, signal);
    if (!result.success) return err(result.error);

    await this._registerAndPersist(taskId, result.data);

    const provisionResult: ProvisionResult = {
      path: result.data.path,
      workspaceId: result.data.persistData.workspaceId,
      sshConnectionId: result.data.persistData.sshConnectionId,
    };

    this._hooks.callHookBackground('task:provision-timing', {
      taskId,
      durationMs: Date.now() - startedAt,
    });
    this._hooks.callHookBackground('task:workspace-ready', taskId, provisionResult);
    return ok(provisionResult);
  }

  private async _activateWorkspace(
    taskRow: typeof tasks.$inferSelect,
    project: ProjectProvider,
    signal?: AbortSignal
  ): Promise<Result<ActivatedTask, ProvisionWorkspaceError>> {
    if (!taskRow.workspaceId) return err({ type: 'missing-workspace' });
    const registry = createWorkspaceRegistry(this.dependencies.db);
    const workspaceRow = registry.getLive(taskRow.workspaceId);
    if (!workspaceRow?.path) return err({ type: 'missing-workspace' });

    // Creation gate (ADR 0005): a creation still in flight is awaited; a durably
    // failed creation — or a provenance worktree whose artifact is not observed
    // present — is replayed through the registry verb with the identical stored spec.
    const pendingCreation = this.dependencies.creations.pending(workspaceRow.id);
    const needsReplay =
      (workspaceRow.lastCreateOutcome && workspaceRow.lastCreateOutcome.status !== 'succeeded') ||
      (workspaceRow.observedStatus !== 'present' &&
        workspaceRow.config?.workspace.kind === 'new-worktree');
    if (pendingCreation) {
      const outcome = await pendingCreation;
      if (signal?.aborted) {
        return err({ type: 'cancelled', message: 'Workspace activation was cancelled' });
      }
      if (!outcome.success) {
        return err({
          type: 'setup-failed',
          stepKind: 'activation-gate',
          stepErrorType: outcome.error.stage,
          message: outcome.error.message,
        });
      }
    } else if (needsReplay) {
      const replayed = await this.replayWorktreeCreation(workspaceRow, project);
      if (signal?.aborted) {
        return err({ type: 'cancelled', message: 'Workspace activation was cancelled' });
      }
      if (!replayed.success) {
        return err({
          type: 'setup-failed',
          stepKind: 'activation-gate',
          stepErrorType: replayed.error.stage,
          message: replayed.error.message,
        });
      }
    }

    const access = await tryAcquireWorkspaceRuntime(
      this.dependencies.runtimes,
      this.dependencies.workspaceIdentity,
      workspaceRow.id
    );
    if (!access.success) return access;
    if (!access.data) return err({ type: 'missing-workspace' });
    const workspacePath = parseAbsolute(workspaceRow.path);
    if (!workspacePath.success) {
      return err({
        type: 'setup-failed',
        stepKind: 'activation-gate',
        stepErrorType: 'invalid-path',
        message: workspacePath.error.message,
      });
    }
    const activated = await this.activateOnRegistry(
      access.data.client.workspaceRegistry,
      workspaceRow.id,
      workspaceRow.path
    );
    if (!activated.success) return activated;
    if (signal?.aborted) {
      return err({ type: 'cancelled', message: 'Workspace activation was cancelled' });
    }

    const task = mapTaskRowToTask(taskRow);
    await activateWorkspaceParticipants(
      this.dependencies.lifecycleParticipants,
      access.data.identity
    );
    let built: Awaited<ReturnType<typeof buildTaskFromWorkspace>>;
    try {
      built = await buildTaskFromWorkspace(
        task,
        {
          id: workspaceRow.id,
          host: access.data.identity.host,
          path: workspaceRow.path,
          files: access.data.files,
          tuiAgents: access.data.client.tuiAgents,
          workspaceRegistry: access.data.client.workspaceRegistry,
        },
        project.projectId,
        project.repoPath,
        project.settings,
        project.repoFacts,
        this.dependencies.createConversationProvider,
        workspaceRow.config ? (deriveBranchName(workspaceRow.config.git) ?? undefined) : undefined
      );
    } catch (error) {
      await deactivateWorkspaceParticipants(
        this.dependencies.lifecycleParticipants,
        access.data.identity
      );
      throw error;
    }
    if (!built.success) {
      await deactivateWorkspaceParticipants(
        this.dependencies.lifecycleParticipants,
        access.data.identity
      );
      return built;
    }
    return ok({
      path: workspaceRow.path,
      runtimeWorkspace: hostFileRefFromNativePath(
        workspaceRow.path,
        sshConnectionIdOf(access.data.identity.host)
      ),
      taskProvider: built.data.taskProvider,
      persistData: {
        workspaceId: workspaceRow.id,
        sshConnectionId: sshConnectionIdOf(access.data.identity.host),
      },
    });
  }

  /** Activates one already-registered Workspace; unknown identity is an invariant failure. */
  private async activateOnRegistry(
    registry: Pick<HostRuntimesClient['workspaceRegistry'], 'activateWorkspace'>,
    workspaceId: string,
    _workspacePath: string
  ): Promise<Result<void, ProvisionWorkspaceError>> {
    const activated = await registry.activateWorkspace({ workspaceId });
    if (activated.success) return ok(undefined);
    if (activated.error.type === 'workspace-missing') {
      return err({ type: 'missing-workspace' });
    }
    return err({
      type: 'setup-failed',
      stepKind: 'activate-workspace',
      stepErrorType: activated.error.type,
      message:
        activated.error.type === 'workspace-not-found'
          ? `Workspace identity ${workspaceId} is unknown to the Host registry`
          : 'Workspace activation failed on the host',
    });
  }

  /**
   * Replays a durably failed worktree creation through the registry verb with the
   * identical spec recompiled from stored provenance (idempotent per ADR 0005).
   */
  private async replayWorktreeCreation(
    workspaceRow: WorkspaceRow,
    project: ProjectProvider
  ): Promise<WorkspaceCreationOutcome> {
    const config = workspaceRow.config;
    if (!config || !workspaceRow.path || workspaceRow.kind !== 'worktree') {
      return err({ stage: 'replay', message: 'Workspace provenance is incomplete.' });
    }
    if (config.git.kind === 'none') {
      return err({
        stage: 'replay',
        message: 'A Git branch is required when creating a worktree.',
      });
    }
    const { baseRemote, pushRemote } = await project.gitRepository.getEffectiveRemotes();
    if (baseRemote === null && config.git.kind === 'pr-branch') {
      return err({
        stage: 'replay',
        message: 'The repository has no git remotes, so a pull request cannot be checked out.',
      });
    }
    const preservePatterns = workspaceRow.parentId
      ? await resolveProjectPreservePatterns(project, workspaceRow.parentId)
      : null;
    if (preservePatterns === null) {
      return err({
        stage: 'replay',
        message: 'The project configuration could not be resolved.',
      });
    }
    let gitPlan: ReturnType<typeof compileWorktreeGitPlan>;
    try {
      gitPlan = compileWorktreeGitPlan(config.git, { baseRemote, pushRemote });
    } catch (error) {
      return err({
        stage: 'replay',
        message: error instanceof Error ? error.message : String(error),
      });
    }
    const workspacePath = workspaceRow.path;
    return this.dependencies.creations.run(workspaceRow.id, () =>
      createWorktreeThroughRegistry(this.dependencies.runtimes, {
        host: project.host,
        repositoryWorkspaceId: workspaceRow.parentId,
        repositoryPath: project.repoPath,
        workspaceId: workspaceRow.id,
        branch: gitPlan.branch,
        ...(gitPlan.baseRef !== undefined && { baseRef: gitPlan.baseRef }),
        path: workspacePath,
        preservePatterns,
        ...(gitPlan.publish !== undefined && { publish: gitPlan.publish }),
        ...(gitPlan.gitSetup !== undefined && { gitSetup: gitPlan.gitSetup }),
      })
    );
  }

  /**
   * User-requested reprovision: optionally force-removes the current artifact through
   * `deleteWorktree` (sessions killed, teardown run, record unregistered), then replays
   * the creation with the identical stored spec. The mirror row survives throughout —
   * it is the durable intent the replay recompiles from.
   */
  async reprovisionWorkspace(
    workspaceId: string,
    options: { removeFirst?: boolean } = {}
  ): Promise<Result<Record<string, never>, { type: string; message: string }>> {
    const workspaceRow = createWorkspaceRegistry(this.dependencies.db).getLive(workspaceId);
    if (!workspaceRow?.path || workspaceRow.kind !== 'worktree' || !workspaceRow.config) {
      return err({
        type: 'workspace-not-reprovisionable',
        message: 'Workspace provenance is incomplete.',
      });
    }
    const [task] = await this.dependencies.db
      .select({ projectId: tasks.projectId })
      .from(tasks)
      .where(and(eq(tasks.workspaceId, workspaceRow.id), isNull(tasks.deletedAt)))
      .limit(1);
    if (!task) {
      return err({
        type: 'project-missing',
        message: 'The Project for this workspace was not found.',
      });
    }
    const attached = this.dependencies.projects.requireAttached(task.projectId);
    if (!attached.success) {
      const unavailable = provisionProjectError(attached.error);
      return err({
        type: unavailable.type,
        message:
          unavailable.type === 'project-missing'
            ? 'The Project for this workspace was not found.'
            : unavailable.message,
      });
    }
    if (options.removeFirst) {
      const removed = await attached.data.workspaceRegistry.deleteWorktree({
        workspaceId,
        deleteBranch: false,
      });
      if (!removed.success) {
        return err({ type: 'delete-failed', message: `Removal failed (${removed.error.type}).` });
      }
    }
    const replayed = await this.replayWorktreeCreation(workspaceRow, attached.data);
    if (!replayed.success) {
      return err({ type: replayed.error.stage, message: replayed.error.message });
    }
    appDbPokes.workspaces.poke({});
    return ok({});
  }

  private async _registerAndPersist(taskId: string, data: ActivatedTask): Promise<void> {
    const [row] = await this.dependencies.db
      .select()
      .from(tasks)
      .where(and(eq(tasks.id, taskId), isNull(tasks.deletedAt)))
      .limit(1);
    if (!row) throw new Error(`Task not found: ${taskId}`);

    const task = mapTaskRowToTask(row);
    await this.dependencies.sessions.registerTask(taskId, data, task.projectId);

    await this.dependencies.db
      .update(tasks)
      .set({ lastInteractedAt: sql`CURRENT_TIMESTAMP`, workspaceId: data.persistData.workspaceId })
      .where(eq(tasks.id, taskId));
    appDbPokes.tasks.poke({ projectId: task.projectId, taskId });
  }

  async teardown(
    projectId: string,
    taskId: string,
    mode: Parameters<TaskSessionManager['teardownTask']>[1] = 'terminate'
  ): Promise<
    Result<
      void,
      TeardownTaskError | { type: 'project-missing' | 'project-unavailable'; message: string }
    >
  > {
    const [task] = await this.dependencies.db
      .select({ projectId: tasks.projectId })
      .from(tasks)
      .where(and(eq(tasks.id, taskId), isNull(tasks.deletedAt)))
      .limit(1);
    if (!task || task.projectId !== projectId) {
      return err({ type: 'project-missing', message: 'Project was not found.' });
    }
    const attached = this.dependencies.projects.requireAttached(task.projectId);
    if (!attached.success) {
      return err({
        type: attached.error.type === 'project-missing' ? 'project-missing' : 'project-unavailable',
        message:
          attached.error.type === 'project-missing'
            ? 'Project was not found.'
            : PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE,
      });
    }
    return this.dependencies.sessions.teardownTask(taskId, mode);
  }

  async getDeletePreflight(taskIds: string[]) {
    return getDeletePreflight(this.dependencies.db, this.dependencies.projects, taskIds);
  }

  /**
   * The wire `delete` mutation's entry point: the plain task deletion (no kernel
   * submit), surfacing the Result unchanged so duplicate/absence stays non-throwing.
   */
  async delete(input: DeleteTaskInput): Promise<TaskDeletionResult> {
    const [row] = await this.dependencies.db
      .select({ projectId: tasks.projectId })
      .from(tasks)
      .where(eq(tasks.id, input.taskId))
      .limit(1);
    const result = await deleteTask(this.dependencies.deletion, input);
    if (result.success && row) this.notifyTaskDeleted(input.taskId, row.projectId);
    return result;
  }

  async deleteTask(projectId: string, taskId: string, options?: DeleteTaskOptions): Promise<void> {
    const result = await deleteTask(this.dependencies.deletion, {
      taskId,
      deleteWorktree: options?.deleteWorktree,
      deleteBranch: options?.deleteBranch,
      deleteConversations: options?.deleteConversations,
    });
    if (!result.success && result.error.type !== 'task-not-found') {
      throw new Error(result.error.message);
    }
    this.notifyTaskDeleted(taskId, projectId);
  }

  notifyTaskDeleted(taskId: string, projectId: string): void {
    this._hooks.callHookBackground('task:deleted', taskId, projectId);
  }

  async deleteTasks(
    projectId: string,
    taskIds: string[],
    options?: DeleteTaskOptions
  ): Promise<void> {
    // Notify per deletion: one failure must not suppress taskDeleted for the
    // already-removed tasks, or the renderer rollback would resurrect them.
    const results = await Promise.allSettled(
      taskIds.map((id) => this.deleteTask(projectId, id, options))
    );
    const failure = results.find(
      (result): result is PromiseRejectedResult => result.status === 'rejected'
    );
    if (failure) throw failure.reason;
  }

  async archiveTask(
    projectId: string,
    taskId: string,
    telemetry: Pick<TelemetryService, 'capture'>
  ): Promise<void> {
    const [task] = await this.dependencies.db
      .select({ projectId: tasks.projectId })
      .from(tasks)
      .where(and(eq(tasks.id, taskId), isNull(tasks.deletedAt)))
      .limit(1);
    if (task && task.projectId !== projectId) throw new Error('Project was not found.');
    await archiveTask(
      this.dependencies.db,
      this.dependencies.sessions,
      projectId,
      taskId,
      telemetry
    );
    this._hooks.callHookBackground('task:archived', taskId, projectId);
  }

  async restoreTask(id: string): Promise<void> {
    const task = await restoreTask(this.dependencies.db, id);
    if (task) this._hooks.callHookBackground('task:updated', task);
  }

  async renameTask(
    projectId: string,
    taskId: string,
    newName: string
  ): Promise<Result<RenameTaskSuccess, RenameTaskError>> {
    const result = await renameTask(this.dependencies.db, projectId, taskId, newName);
    if (result.success) this._hooks.callHookBackground('task:updated', result.data.task);
    return result;
  }

  async updateLinkedIssue(
    taskId: string,
    issue: LinkedIssue | undefined,
    telemetry: Pick<TelemetryService, 'capture'>
  ): Promise<void> {
    const task = await updateLinkedIssue(this.dependencies.db, taskId, issue, telemetry);
    if (task) this._hooks.callHookBackground('task:updated', task);
  }

  async convertAutomationTask(taskId: string): Promise<Task | null> {
    const [row] = await this.dependencies.db
      .update(tasks)
      .set({ type: 'task', updatedAt: sql`CURRENT_TIMESTAMP` })
      .where(eq(tasks.id, taskId))
      .returning();
    if (!row) return null;

    const task: Task = { ...mapTaskRowToTask(row), prs: [], conversations: {} };
    appDbPokes.tasks.poke({ projectId: row.projectId, taskId });
    this._hooks.callHookBackground('task:updated', task);
    return task;
  }

  // Operations with no hook — thin pass-throughs
  updateTaskStatus(
    taskId: string,
    status: Parameters<typeof updateTaskStatus>[2],
    telemetry: Pick<TelemetryService, 'capture'>
  ) {
    return updateTaskStatus(this.dependencies.db, taskId, status, telemetry);
  }
  setTaskPinned = (taskId: string, isPinned: boolean) =>
    setTaskPinned(this.dependencies.db, taskId, isPinned);
  getTasks = (projectId?: string) => getTasks(this.dependencies.db, projectId);
}

function provisionProjectError(
  error: ProjectAttachmentError
): Extract<ProvisionWorkspaceError, { type: 'project-missing' | 'project-unavailable' }> {
  return error.type === 'project-missing'
    ? error
    : {
        type: 'project-unavailable',
        reason: error.type,
        message: PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE,
      };
}
