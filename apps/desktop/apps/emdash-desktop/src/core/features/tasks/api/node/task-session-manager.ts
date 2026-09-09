import { hostRefKey, type SerializedHostRef } from '@emdash/core/primitives/host/api';
import type { HostFileRef } from '@emdash/core/primitives/path/api';
import { makeTmuxSessionName } from '@emdash/core/services/pty/api';
import {
  runtimeResolveErrorAsError,
  type RuntimeBroker,
} from '@emdash/core/services/runtime-broker/api';
import { ok, type Result } from '@emdash/shared';
import {
  createLifecycleRegistry,
  type LifecycleRegistryState,
  type LifecycleRegistryStateChange,
} from '@emdash/shared/concurrency';
import { log } from '@emdash/shared/logger';
import { runWithTimeout, TimeoutError } from '@emdash/shared/scheduling';
import type {
  ProvisionResult,
  TaskProvider,
} from '@core/features/projects/api/node/project-provider';
import { getTaskSessionLeafIds } from '@core/features/tasks/node/session-targets';
import type { WorkspaceIdentity } from '@core/features/workspaces/api/node/workspace-identity-service';
import { HookCore, type Hookable } from '@core/primitives/hooks/api/hookable';
import { makePtySessionId } from '@core/primitives/pty/api';
import type { TaskBootstrapStatus } from '@core/primitives/tasks/api';
import type { WorkspaceType as SharedWorkspaceType } from '@core/primitives/workspaces/api';
import type { AppDb } from '@core/services/app-db/node/db';

const TASK_TIMEOUT_MS = 600_000;

export type ProvisionTaskError = { type: 'error'; message: string };
export type TeardownTaskError =
  | { type: 'timeout'; message: string; timeout: number }
  | { type: 'error'; message: string };

export type WorkspaceHint = {
  id: string;
  type: SharedWorkspaceType;
  path?: string;
};

type TeardownMode = 'detach' | 'terminate';

type StoredTask = ProvisionResult & { projectId: string };
type RuntimeStoredTask = StoredTask & {
  runtimeWorkspace?: HostFileRef;
};
type TaskStartInput = { taskId: string; stored: RuntimeStoredTask };
type TaskLifecycleState = LifecycleRegistryState<
  RuntimeStoredTask,
  ProvisionTaskError,
  TeardownTaskError
>;
type TaskLifecycleStateChange = LifecycleRegistryStateChange<
  RuntimeStoredTask,
  ProvisionTaskError,
  TeardownTaskError
>;

export type TaskSessionManagerDependencies = {
  db: AppDb;
  deactivateWorkspaceParticipants(identity: WorkspaceIdentity): Promise<void>;
  runtimes: RuntimeBroker;
  workspaceIdentity: {
    resolve(workspaceId: string): Promise<WorkspaceIdentity | null>;
  };
};

export type TaskManagerHooks = {
  'task:provisioned': (info: {
    projectId: string;
    taskId: string;
    branchName: string | undefined;
    workspaceId: string;
    worktreeGitDir?: string;
  }) => void | Promise<void>;
  'task:torn-down': (info: {
    projectId: string;
    taskId: string;
    workspaceId: string;
  }) => void | Promise<void>;
};

/**
 * Task-level teardown intent. Wider than {@link TeardownMode} because archive needs to
 * reap the running agent like `terminate` while keeping the workspace like `detach`:
 *
 * - `detach`: leave tmux sessions and agent processes running so the task can be
 *   remounted later (used on app/project shutdown when tmux is enabled).
 * - `terminate`: reap tmux sessions + agent processes and destroy the workspace
 *   (worktree removal, teardown script). Used by delete.
 * - `archive`: reap tmux sessions + agent processes like `terminate`, but keep the
 *   workspace/worktree (and the persisted `conversations.session_id`) so the task stays
 *   restorable. Without this, archiving a tmux-backed task leaked its session and agent
 *   process indefinitely (#2689).
 */
export type TaskTeardownMode = TeardownMode | 'archive';

export async function executeTeardown(
  _dependencies: TaskSessionManagerDependencies,
  task: TaskProvider,
  _workspaceId: string,
  mode: TaskTeardownMode,
  _runtimeWorkspace?: HostFileRef
): Promise<void> {
  if (mode === 'detach') {
    // Keep the tmux sessions and agent processes alive for a later remount.
    await task.conversations.detachAll();
  } else {
    // 'terminate' and 'archive' both reap the tmux sessions and agent processes.
    await task.conversations.destroyAll();
  }
}

async function cleanupDetachedSessions(
  runtimes: RuntimeBroker,
  db: AppDb,
  projectId: string,
  taskId: string,
  runtimeWorkspace?: HostFileRef
): Promise<void> {
  const host = runtimeWorkspace?.host;
  if (!host) return;
  const runtime = await runtimes.client(host);
  if (!runtime.success) {
    log.warn('cleanupDetachedSessions: could not resolve runtime', {
      projectId,
      taskId,
      error: runtimeResolveErrorAsError(runtime.error).message,
    });
    return;
  }
  const { conversationIds, terminalIds } = await getTaskSessionLeafIds(db, projectId, taskId);
  const sessionNames = [...conversationIds, ...terminalIds].map((leafId) =>
    makeTmuxSessionName(makePtySessionId(projectId, taskId, leafId))
  );
  if (sessionNames.length > 0) {
    await runtime.data.terminals.killTmuxSessions({ sessionNames });
  }
}

export class TaskSessionManager {
  private readonly _hooks = new HookCore<TaskManagerHooks>((name, e) =>
    log.error(`TaskManager: ${String(name)} hook error`, { error: e })
  );
  private readonly _lifecycle = createLifecycleRegistry<
    TaskStartInput,
    StoredTask,
    ProvisionTaskError,
    TaskTeardownMode,
    TeardownTaskError
  >({
    label: 'task-session-manager',
    keyOf: (input) => input.taskId,
    start: async (input) => ok(input.stored),
    stop: async (taskId, stored, mode) => this.stopTask(taskId, stored, mode ?? 'terminate'),
    onStateChanged: (change) => this.handleLifecycleStateChanged(change),
    onObserverError: ({ error }) => log.error('TaskManager: lifecycle observer error', { error }),
  });
  private readonly _tasksByProject = new Map<string, Set<string>>();

  readonly hooks: Hookable<TaskManagerHooks> = this._hooks;

  constructor(private readonly dependencies: TaskSessionManagerDependencies) {}

  /**
   * Registers a fully-provisioned task into the lifecycle map.
   * Idempotent — if the task is already registered, returns immediately.
   * Fires `task:provisioned` hook for telemetry, git watchers, PR sync.
   */
  async registerTask(
    taskId: string,
    result: ProvisionResult & { runtimeWorkspace?: HostFileRef },
    projectId: string
  ): Promise<void> {
    const stored: RuntimeStoredTask = {
      taskProvider: result.taskProvider,
      runtimeWorkspace: result.runtimeWorkspace,
      persistData: { ...result.persistData },
      projectId,
    };

    await this._lifecycle.register(taskId, stored);

    const byProject = this._tasksByProject.get(projectId) ?? new Set<string>();
    byProject.add(taskId);
    this._tasksByProject.set(projectId, byProject);

    this._hooks.callHookBackground('task:provisioned', {
      projectId,
      taskId,
      branchName: result.taskProvider.taskBranch,
      workspaceId: result.persistData.workspaceId,
      worktreeGitDir: result.persistData.worktreeGitDir,
    });
  }

  async teardownTask(
    taskId: string,
    mode: TaskTeardownMode = 'terminate'
  ): Promise<Result<void, TeardownTaskError>> {
    return this._lifecycle.stop(taskId, mode);
  }

  async forceRemoveTask(taskId: string, reason?: unknown): Promise<void> {
    await this._lifecycle.forceRemove(taskId, reason);
  }

  async teardownAllForProject(projectId: string, mode: TeardownMode): Promise<void> {
    const taskIds = Array.from(this._tasksByProject.get(projectId) ?? []);
    await Promise.all(taskIds.map((id) => this.teardownTask(id, mode)));
  }

  async destroySessionsAt(hostRef: SerializedHostRef, workspacePath: string): Promise<void> {
    const taskIds = [...this._tasksByProject.values()].flatMap((ids) => [...ids]);
    let matchedIdentity: WorkspaceIdentity | undefined;
    for (const taskId of taskIds) {
      const stored = this._lifecycle.get(taskId);
      if (!stored) continue;
      const identity = await this.dependencies.workspaceIdentity.resolve(
        stored.persistData.workspaceId
      );
      if (identity?.path !== workspacePath || hostRefKey(identity.host) !== hostRef) continue;
      matchedIdentity = identity;
      await stored.taskProvider.conversations.destroyAll().catch((error) => {
        log.warn('TaskManager: failed to destroy sessions before workspace operation', {
          taskId,
          error: String(error),
        });
      });
      await this._lifecycle.forceRemove(taskId, 'workspace operation');
    }
    if (matchedIdentity) {
      await this.dependencies.deactivateWorkspaceParticipants(matchedIdentity);
    }
  }

  getTask(taskId: string): TaskProvider | undefined {
    return this._lifecycle.get(taskId)?.taskProvider;
  }

  getWorkspaceId(taskId: string): string | undefined {
    return this._lifecycle.get(taskId)?.persistData.workspaceId;
  }

  getPersistData(taskId: string): ProvisionResult['persistData'] | undefined {
    return this._lifecycle.get(taskId)?.persistData;
  }

  getBootstrapStatus(taskId: string): TaskBootstrapStatus {
    const state = this._lifecycle.state(taskId);
    switch (state.kind) {
      case 'ready':
      case 'stopping':
      case 'stop-failed':
        return { status: 'ready' };
      case 'starting':
        return { status: 'bootstrapping' };
      case 'start-failed':
        return { status: 'error', message: state.error.message };
      case 'idle':
      case 'disposed':
        return { status: 'not-started' };
    }
  }

  getTeardownStatus(taskId: string): TaskBootstrapStatus {
    const state = this._lifecycle.state(taskId);
    switch (state.kind) {
      case 'stopping':
        return { status: 'bootstrapping' };
      case 'stop-failed':
        return { status: 'error', message: state.error.message };
      case 'idle':
      case 'starting':
      case 'ready':
      case 'start-failed':
      case 'disposed':
        return { status: 'not-started' };
    }
  }

  private async stopTask(
    taskId: string,
    { taskProvider, persistData, projectId, runtimeWorkspace }: RuntimeStoredTask,
    mode: TaskTeardownMode
  ): Promise<Result<void, TeardownTaskError>> {
    try {
      await runWithTimeout(
        async () => {
          await executeTeardown(
            this.dependencies,
            taskProvider,
            persistData.workspaceId,
            mode,
            runtimeWorkspace
          );
          this.removeTaskFromProjectIndex(projectId, taskId);
          if (!this.hasOtherTaskForWorkspace(taskId, persistData.workspaceId)) {
            const identity = await this.dependencies.workspaceIdentity.resolve(
              persistData.workspaceId
            );
            if (identity) {
              await this.dependencies.deactivateWorkspaceParticipants(identity);
              // Terminate/archive deactivate on the host (kill sessions + teardown
              // script); detach leaves the workspace active for a later remount.
              if (mode !== 'detach') await this.deactivateOnHost(identity);
            }
          }
        },
        {
          timeoutMs: TASK_TIMEOUT_MS,
        }
      );
      return ok();
    } catch (e) {
      log.error('TaskManager: failed to teardown task', { taskId, error: String(e) });
      await cleanupDetachedSessions(
        this.dependencies.runtimes,
        this.dependencies.db,
        projectId,
        taskId,
        runtimeWorkspace
      ).catch((cleanupError) => {
        log.warn('TaskManager: fallback cleanup failed', {
          taskId,
          error: String(cleanupError),
        });
      });
      return {
        success: false as const,
        error:
          e instanceof TimeoutError
            ? { type: 'timeout', message: e.message, timeout: e.durationMs }
            : { type: 'error', message: e instanceof Error ? e.message : String(e) },
      };
    }
  }

  /**
   * Best-effort host-side deactivation (registry verb: kill sessions + teardown
   * script). An unreachable host or an unregistered workspace only warns — desktop
   * teardown already reaped this task's own sessions.
   */
  private async deactivateOnHost(identity: WorkspaceIdentity): Promise<void> {
    const client = await this.dependencies.runtimes.client(identity.host);
    if (!client.success) {
      log.warn('TaskManager: could not resolve host for workspace deactivation', {
        workspaceId: identity.workspaceId,
        error: runtimeResolveErrorAsError(client.error).message,
      });
      return;
    }
    const deactivated = await client.data.workspaceRegistry
      .deactivateWorkspace({ workspaceId: identity.workspaceId })
      .catch((error) => ({ success: false as const, error }));
    if (!deactivated.success) {
      log.warn('TaskManager: host workspace deactivation failed', {
        workspaceId: identity.workspaceId,
        error: deactivated.error,
      });
    }
  }

  private hasOtherTaskForWorkspace(taskId: string, workspaceId: string): boolean {
    for (const taskIds of this._tasksByProject.values()) {
      for (const candidateId of taskIds) {
        if (candidateId === taskId) continue;
        if (this._lifecycle.get(candidateId)?.persistData.workspaceId === workspaceId) return true;
      }
    }
    return false;
  }

  private handleLifecycleStateChanged(change: TaskLifecycleStateChange): void {
    const stored = taskFromState(change.previous);
    if (!stored || !isRemovedState(change.current)) return;

    this.removeTaskFromProjectIndex(stored.projectId, change.key);

    this._hooks.callHookBackground('task:torn-down', {
      projectId: stored.projectId,
      taskId: change.key,
      workspaceId: stored.persistData.workspaceId,
    });
  }

  private removeTaskFromProjectIndex(projectId: string, taskId: string): void {
    const byProject = this._tasksByProject.get(projectId);
    byProject?.delete(taskId);
    if (byProject?.size === 0) this._tasksByProject.delete(projectId);
  }
}

function taskFromState(state: TaskLifecycleState): StoredTask | undefined {
  switch (state.kind) {
    case 'ready':
    case 'stopping':
    case 'stop-failed':
      return state.value;
    case 'idle':
    case 'starting':
    case 'start-failed':
    case 'disposed':
      return undefined;
  }
}

function isRemovedState(state: TaskLifecycleState): boolean {
  return state.kind === 'idle' || state.kind === 'disposed';
}
