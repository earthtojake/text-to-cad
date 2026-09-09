import type { TaskService } from '@core/features/tasks/api/node/task-service';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import type { WorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import type { TaskListData, TaskListRow } from '@core/primitives/tasks/api';

export interface TaskListOperations {
  load(projectId: string): Promise<TaskListData>;
}

export interface TaskListServiceDependencies {
  taskService: Pick<TaskService, 'getTasks'>;
  taskSessions: Pick<TaskSessionManager, 'getPersistData' | 'getTask'>;
  workspaces: Pick<WorkspaceRegistry, 'getLive'>;
}

export class TaskListService implements TaskListOperations {
  constructor(private readonly dependencies: TaskListServiceDependencies) {}

  async load(projectId: string): Promise<TaskListData> {
    return {
      tasks: (await this.dependencies.taskService.getTasks(projectId)).map((task) => {
        const row = toTaskRow(task);
        if (!this.dependencies.taskSessions.getTask(task.id)) return row;

        const workspaceId =
          this.dependencies.taskSessions.getPersistData(task.id)?.workspaceId ?? task.workspaceId;
        if (!workspaceId) return row;

        const workspace = this.dependencies.workspaces.getLive(workspaceId);
        if (!workspace?.path) return row;

        return {
          ...row,
          activeWorkspace: {
            workspaceId,
            path: workspace.path,
            ...(workspace.sshConnectionId ? { sshConnectionId: workspace.sshConnectionId } : {}),
          },
        };
      }),
    };
  }
}

function toTaskRow(task: Awaited<ReturnType<TaskService['getTasks']>>[number]): TaskListRow {
  const { prs: _prs, workspaceGit: _workspaceGit, ...row } = task;
  return row;
}
