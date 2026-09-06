import { err, ok } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import type { Contract, ContractImpl } from '@emdash/wire/rpc';
import { expose, family, query } from '@emdash/wire/state';
import { and, eq, inArray, isNull } from 'drizzle-orm';
import { tasksWireContract } from '@core/features/tasks/api';
import type { TaskService } from '@core/features/tasks/api/node/task-service';
import {
  liveWorkspaces,
  workspaceRegistryTable as workspaces,
} from '@core/features/workspaces/api/node/registry';
import type { TaskStatsData } from '@core/primitives/tasks/api';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes, matchProject } from '@core/services/app-db/node/pokes';
import { tasks } from '@core/services/app-db/node/schema';
import { createTaskOperations } from './controller';
import type { TaskListOperations } from './task-list-service';

type ContractDefinitionsOf<TContract> = TContract extends Contract<infer Defs> ? Defs : never;
type TasksWireImpl = ContractImpl<ContractDefinitionsOf<typeof tasksWireContract>>;

export type TasksWireController = {
  impl: TasksWireImpl;
  dispose(): Promise<void>;
};

export function createTasksWireController(options: {
  db: AppDb;
  service: TaskService;
  taskList: TaskListOperations;
  telemetry: TelemetryService;
}): TasksWireController {
  const taskOperations = createTaskOperations(options);
  const taskListFamily = family(
    ({ projectId }: { projectId: string }, scope) =>
      query({
        fetch: () => options.taskList.load(projectId),
        pokes: [
          appDbPokes.tasks.subscription(matchProject(projectId)),
          appDbPokes.conversations.subscription(matchProject(projectId)),
          appDbPokes.workspaces.subscription(matchProject(projectId)),
        ],
        scope,
      }),
    { name: 'task-list' }
  );
  const taskStatsFamily = family(
    ({ projectId }: { projectId: string }, scope) =>
      query<TaskStatsData>({
        fetch: async () => loadTaskStats(options.db, projectId),
        pokes: [appDbPokes.workspaces.subscription(matchProject(projectId))],
        scope,
      }),
    { name: 'task-stats' }
  );
  const taskListProvider = expose(
    tasksWireContract.taskList,
    {
      list: (key: { projectId: string }, scope: Scope) => {
        scope.add(taskListFamily.retain(key));
        return taskListFamily(key);
      },
    },
    {
      mutations: {
        async rename(context) {
          const result = await options.service.renameTask(
            context.key.projectId,
            context.input.taskId,
            context.input.newName
          );
          if (!result.success) return result;
          await context.observed(
            'list',
            taskListFamily(context.key).refresh({ mutationIds: [context.mutationId] })
          );
          return result;
        },
        async setStatus(context) {
          await options.service.updateTaskStatus(
            context.input.taskId,
            context.input.status,
            options.telemetry
          );
          await context.observed(
            'list',
            taskListFamily(context.key).refresh({ mutationIds: [context.mutationId] })
          );
          return ok<void>();
        },
        async setPinned(context) {
          await options.service.setTaskPinned(context.input.taskId, context.input.isPinned);
          await context.observed(
            'list',
            taskListFamily(context.key).refresh({ mutationIds: [context.mutationId] })
          );
          return ok<void>();
        },
        async setLinkedIssue(context) {
          await options.service.updateLinkedIssue(
            context.input.taskId,
            context.input.issue,
            options.telemetry
          );
          await context.observed(
            'list',
            taskListFamily(context.key).refresh({ mutationIds: [context.mutationId] })
          );
          return ok<void>();
        },
        async convertAutomation(context) {
          const task = await options.service.convertAutomationTask(context.input.taskId);
          await context.observed(
            'list',
            taskListFamily(context.key).refresh({ mutationIds: [context.mutationId] })
          );
          return ok(task);
        },
        async archive(context) {
          await options.service.archiveTask(
            context.key.projectId,
            context.input.taskId,
            options.telemetry
          );
          await context.observed(
            'list',
            taskListFamily(context.key).refresh({ mutationIds: [context.mutationId] })
          );
          return ok<void>();
        },
        async restore(context) {
          await options.service.restoreTask(context.input.taskId);
          await context.observed(
            'list',
            taskListFamily(context.key).refresh({ mutationIds: [context.mutationId] })
          );
          return ok<void>();
        },
      },
    }
  );
  const taskStatsProvider = expose(tasksWireContract.taskStats, {
    stats: (key, scope: Scope) => {
      scope.add(taskStatsFamily.retain(key));
      return taskStatsFamily(key);
    },
  });
  return {
    impl: {
      createTask: (input) => taskOperations.createTask(input),
      getDeletePreflight: ({ projectId, taskIds }) =>
        taskOperations.getDeletePreflight(projectId, taskIds),
      deleteTask: ({ projectId, taskId, options }) =>
        taskOperations.deleteTask(projectId, taskId, options),
      deleteTasks: ({ projectId, taskIds, options }) =>
        taskOperations.deleteTasks(projectId, taskIds, options),
      teardownTask: ({ projectId, taskId }) => taskOperations.teardownTask(projectId, taskId),
      generateTaskName: (input) => taskOperations.generateTaskName(input),
      taskList: taskListProvider,
      taskStats: taskStatsProvider,
      // Plain deletion (no kernel submit); the contract's mutation-result shape stays
      // for wire compatibility, with no operation id to report.
      delete: async (input) => {
        const result = await options.service.delete(input);
        return result.success ? ok({}) : err(result.error);
      },
    },
    async dispose() {
      await taskListProvider.dispose();
      await taskStatsProvider.dispose();
      await taskListFamily.dispose();
      await taskStatsFamily.dispose();
    },
  };
}

async function loadTaskStats(db: AppDb, projectId: string): Promise<TaskStatsData> {
  const taskRows = await db
    .select({ workspaceId: tasks.workspaceId })
    .from(tasks)
    .where(and(eq(tasks.projectId, projectId), isNull(tasks.deletedAt)));
  const workspaceIds = taskRows.map((row) => row.workspaceId).filter((id): id is string => !!id);
  if (workspaceIds.length === 0) return { byWorkspaceId: {} };
  const rows = await db
    .select({
      id: workspaces.id,
      path: workspaces.path,
      observedStatus: workspaces.observedStatus,
      observedGit: workspaces.observedGit,
      observedAt: workspaces.observedAt,
      runtimeOverlay: workspaces.runtimeOverlay,
      lastCreateOutcome: workspaces.lastCreateOutcome,
    })
    .from(workspaces)
    .where(and(inArray(workspaces.id, workspaceIds), liveWorkspaces()));
  return {
    observedAt: rows.reduce<number | null>(
      (latest, row) =>
        row.observedAt == null ? latest : Math.max(latest ?? row.observedAt, row.observedAt),
      null
    ),
    // Mirror diff stats; untracked files' lines count as additions.
    byWorkspaceId: Object.fromEntries(
      rows.flatMap((row) => {
        const stats = row.observedGit?.diffStats;
        return stats == null
          ? []
          : [[row.id, { linesAdded: stats.added, linesDeleted: stats.deleted }]];
      })
    ),
    workspaceById: Object.fromEntries(
      rows.map((row) => [
        row.id,
        {
          path: row.path,
          observedAt: row.observedAt,
          observedStatus: row.observedStatus,
          creation: row.runtimeOverlay?.creation ?? null,
          lastCreateOutcome: row.lastCreateOutcome
            ? {
                status: row.lastCreateOutcome.status,
                stage: row.lastCreateOutcome.stage,
                message: row.lastCreateOutcome.message,
              }
            : null,
          lifecycle: row.runtimeOverlay?.lifecycle ?? null,
          // Raw PR-association and drift facts; a null observedGit (old host /
          // v1 payload) projects null, degrading association to branch matching
          // only and checkout drift to unknown.
          observedPr: row.observedGit
            ? {
                branch: row.observedGit.branch,
                prBreadcrumb: row.observedGit.prBreadcrumb,
                upstream: row.observedGit.upstream
                  ? {
                      mergeRef: row.observedGit.upstream.mergeRef,
                      remoteUrl: row.observedGit.upstream.remoteUrl,
                    }
                  : null,
                headOid: row.observedGit.headOid,
                ahead: row.observedGit.ahead,
                behind: row.observedGit.behind,
              }
            : null,
        },
      ])
    ),
  };
}
