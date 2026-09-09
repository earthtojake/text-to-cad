import type { AgentStatus } from '@core/primitives/agents/api';
import type { PaletteEntitySearchQuery, SearchItem } from '@core/primitives/search/api';
import type { TaskPaletteNotification, TaskPaletteSource } from './task-palette-provider';

interface TaskPaletteSearchClient {
  searchPaletteEntities(input: PaletteEntitySearchQuery): Promise<readonly SearchItem[]>;
}

export interface TaskPaletteNotificationTask {
  readonly projectId: string;
  readonly taskId: string;
  readonly title: string;
  readonly status: AgentStatus | null;
  readonly conversations: readonly {
    readonly id: string;
    readonly title: string;
    readonly seen: boolean;
    readonly indicatorStatus: AgentStatus | null;
  }[];
}

export interface TaskPaletteSourceDependencies {
  readonly getSearchClient: () => Promise<TaskPaletteSearchClient>;
  readonly listNotificationTasks: () => readonly TaskPaletteNotificationTask[];
  readonly taskLastInteractedAt: (projectId: string, taskId: string) => string | undefined;
}

export function createTaskPaletteSource(
  dependencies: TaskPaletteSourceDependencies
): TaskPaletteSource {
  return {
    searchPaletteEntities: async (input) => {
      const client = await dependencies.getSearchClient();
      return client.searchPaletteEntities(input);
    },
    notifications: (context) => {
      const notifications: TaskPaletteNotification[] = [];

      for (const task of dependencies.listNotificationTasks()) {
        if (!task.status || task.status === 'idle' || task.status === 'working') continue;

        if (task.projectId === context.projectId && task.taskId === context.taskId) {
          for (const conversation of task.conversations) {
            if (conversation.seen || !conversation.indicatorStatus) continue;
            notifications.push({
              id: `conversation:${conversation.id}`,
              title: conversation.title,
              target: {
                kind: 'conversation',
                projectId: task.projectId,
                taskId: task.taskId,
                conversationId: conversation.id,
                keepCurrentTask: true,
              },
            });
          }
          continue;
        }

        notifications.push({
          id: `task:${task.projectId}:${task.taskId}`,
          title: task.title,
          target: {
            kind: 'task',
            projectId: task.projectId,
            taskId: task.taskId,
          },
        });
      }

      return notifications;
    },
    taskLastInteractedAt: dependencies.taskLastInteractedAt,
  };
}
