import { describe, expect, it, vi } from 'vitest';
import { createTaskPaletteSource } from './task-palette-source';

describe('task palette source', () => {
  it('projects task notifications and current-task unseen conversations', () => {
    const source = createTaskPaletteSource({
      getSearchClient: vi.fn(),
      listNotificationTasks: () => [
        {
          projectId: 'project-1',
          taskId: 'task-active',
          title: 'Active task',
          status: 'completed',
          conversations: [
            {
              id: 'conversation-unseen',
              title: 'Finished work',
              seen: false,
              indicatorStatus: 'completed',
            },
            {
              id: 'conversation-seen',
              title: 'Already opened',
              seen: true,
              indicatorStatus: null,
            },
          ],
        },
        {
          projectId: 'project-2',
          taskId: 'task-error',
          title: 'Broken task',
          status: 'error',
          conversations: [],
        },
        {
          projectId: 'project-2',
          taskId: 'task-working',
          title: 'Busy task',
          status: 'working',
          conversations: [],
        },
      ],
      taskLastInteractedAt: () => undefined,
    });

    expect(
      source.notifications({
        projectId: 'project-1',
        taskId: 'task-active',
      })
    ).toEqual([
      {
        id: 'conversation:conversation-unseen',
        title: 'Finished work',
        target: {
          kind: 'conversation',
          projectId: 'project-1',
          taskId: 'task-active',
          conversationId: 'conversation-unseen',
          keepCurrentTask: true,
        },
      },
      {
        id: 'task:project-2:task-error',
        title: 'Broken task',
        target: {
          kind: 'task',
          projectId: 'project-2',
          taskId: 'task-error',
        },
      },
    ]);
  });

  it('delegates entity queries without broadening the requested kind', async () => {
    const searchPaletteEntities = vi.fn(async () => []);
    const source = createTaskPaletteSource({
      getSearchClient: async () => ({ searchPaletteEntities }),
      listNotificationTasks: () => [],
      taskLastInteractedAt: () => undefined,
    });
    const input = {
      kind: 'task' as const,
      query: 't',
      context: { projectId: 'project-1' },
      limit: 20,
    };

    await source.searchPaletteEntities(input);

    expect(searchPaletteEntities).toHaveBeenCalledWith(input);
  });
});
