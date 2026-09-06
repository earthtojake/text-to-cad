import { describe, expect, it, vi } from 'vitest';
import {
  definePaletteProviderCatalog,
  PaletteController,
  type PaletteProviderDef,
} from '@core/primitives/palette/api';
import type { SearchItem } from '@core/primitives/search/api';
import {
  createTaskPaletteProviderDef,
  type TaskPaletteMatch,
  type TaskPaletteNotification,
  type TaskPaletteSource,
} from './task-palette-provider';

function task(
  id: string,
  title: string,
  options: Partial<Pick<SearchItem, 'projectId' | 'subtitle'>> = {}
): SearchItem {
  return {
    kind: 'task',
    id,
    projectId: options.projectId ?? 'project-1',
    taskId: null,
    title,
    subtitle: options.subtitle ?? '',
    score: 0,
  };
}

function source(items: readonly SearchItem[]): TaskPaletteSource {
  return {
    searchPaletteEntities: vi.fn(async () => [...items]),
    notifications: () => [],
    taskLastInteractedAt: () => undefined,
  };
}

function forController(
  provider: PaletteProviderDef<'tasks', TaskPaletteMatch>
): PaletteProviderDef {
  return { ...provider, render: () => null };
}

describe('task palette provider', () => {
  it('searches the kind-filtered task source from one character', async () => {
    const fixture = source([task('task-1', 'Theme task')]);
    const provider = createTaskPaletteProviderDef({
      source: fixture,
      render: () => null,
    });

    const matches = await provider.search({
      query: 't',
      context: { projectId: 'project-1', taskId: 'task-active' },
    });

    expect(provider.minQueryLength).toBe(1);
    expect(fixture.searchPaletteEntities).toHaveBeenCalledWith({
      kind: 'task',
      query: 't',
      context: { projectId: 'project-1', taskId: 'task-active' },
      limit: 50,
    });
    expect(matches).toMatchObject([
      {
        id: 'typed:task:project-1:task-1',
        title: 'Theme task',
        target: { kind: 'task', projectId: 'project-1', taskId: 'task-1' },
        relevance: { band: 'prefix' },
      },
    ]);
  });

  it('matches task titles as primary text and linked metadata as secondary text', async () => {
    const provider = createTaskPaletteProviderDef({
      source: source([
        task('title', 'Fix settings', { subtitle: 'ENG-100 Settings issue' }),
        task('metadata', 'Repair regression', { subtitle: 'ENG-200 Login issue' }),
        task('unrelated', 'Update documentation', { subtitle: 'DOC-1 Guides' }),
      ]),
      render: () => null,
    });

    const titleMatches = await provider.search({ query: 'settings', context: {} });
    const metadataMatches = await provider.search({ query: 'eng-200', context: {} });

    expect(titleMatches.map(({ id, relevance }) => [id, relevance.band])).toEqual([
      ['typed:task:project-1:title', 'substring'],
    ]);
    expect(metadataMatches.map(({ id, relevance }) => [id, relevance.band])).toEqual([
      ['typed:task:project-1:metadata', 'secondary'],
    ]);
  });

  it('uses active context and recency only to break equal text-match ties', async () => {
    const recency = new Map([
      ['active-project:active-task', '2025-01-01T00:00:00.000Z'],
      ['active-project:recent-task', '2026-01-01T00:00:00.000Z'],
      ['active-project:older-task', '2024-01-01T00:00:00.000Z'],
      ['other-project:other-task', '2027-01-01T00:00:00.000Z'],
    ]);
    const fixture = source([
      task('other-task', 'Fix login', { projectId: 'other-project' }),
      task('older-task', 'Fix login', { projectId: 'active-project' }),
      task('recent-task', 'Fix login', { projectId: 'active-project' }),
      task('active-task', 'Fix login', { projectId: 'active-project' }),
    ]);
    fixture.taskLastInteractedAt = (projectId, taskId) => recency.get(`${projectId}:${taskId}`);
    const provider = createTaskPaletteProviderDef({
      source: fixture,
      render: () => null,
    });
    const controller = new PaletteController(
      definePaletteProviderCatalog([forController(provider)])
    );

    await controller.setInput('fix login', {
      projectId: 'active-project',
      taskId: 'active-task',
    });

    expect(controller.getSnapshot().results.map(({ match }) => match.id)).toEqual([
      'typed:task:active-project:active-task',
      'typed:task:active-project:recent-task',
      'typed:task:active-project:older-task',
      'typed:task:other-project:other-task',
    ]);
  });

  it('does not let affinity or recency promote a weaker text-match band', async () => {
    const fixture = source([
      task('active-task', 'Miscellaneous work', {
        projectId: 'active-project',
        subtitle: 'Login',
      }),
      task('other-task', 'Login cleanup', { projectId: 'other-project' }),
    ]);
    fixture.taskLastInteractedAt = (projectId) =>
      projectId === 'active-project' ? '2027-01-01T00:00:00.000Z' : '2024-01-01T00:00:00.000Z';
    const provider = createTaskPaletteProviderDef({
      source: fixture,
      render: () => null,
    });
    const controller = new PaletteController(
      definePaletteProviderCatalog([forController(provider)])
    );

    await controller.setInput('login', {
      projectId: 'active-project',
      taskId: 'active-task',
    });

    expect(
      controller.getSnapshot().results.map(({ match }) => [match.id, match.relevance.band])
    ).toEqual([
      ['typed:task:other-project:other-task', 'prefix'],
      ['typed:task:active-project:active-task', 'secondary'],
    ]);
  });

  it('owns task notifications, unseen conversation notifications, and recent task sections', async () => {
    const notifications: TaskPaletteNotification[] = [
      {
        id: 'task:project-2:task-notification',
        title: 'Task needs attention',
        target: {
          kind: 'task',
          projectId: 'project-2',
          taskId: 'task-notification',
        },
      },
      {
        id: 'conversation:conversation-unseen',
        title: 'Unseen conversation',
        target: {
          kind: 'conversation',
          projectId: 'project-1',
          taskId: 'task-active',
          conversationId: 'conversation-unseen',
          keepCurrentTask: true,
        },
      },
    ];
    const fixture = source([task('recent-1', 'Recent one'), task('recent-2', 'Recent two')]);
    fixture.notifications = () => notifications;
    const provider = createTaskPaletteProviderDef({
      source: fixture,
      render: () => null,
    });

    const matches = await provider.idle!({
      projectId: 'project-1',
      taskId: 'task-active',
    });

    expect(fixture.searchPaletteEntities).toHaveBeenCalledWith({
      kind: 'task',
      query: '',
      context: { projectId: 'project-1', taskId: 'task-active' },
      limit: 5,
    });
    expect(matches.map(({ id, section, target }) => ({ id, section, target }))).toEqual([
      {
        id: 'notification:task:project-2:task-notification',
        section: 'Notifications',
        target: {
          kind: 'task',
          projectId: 'project-2',
          taskId: 'task-notification',
        },
      },
      {
        id: 'notification:conversation:conversation-unseen',
        section: 'Notifications',
        target: {
          kind: 'conversation',
          projectId: 'project-1',
          taskId: 'task-active',
          conversationId: 'conversation-unseen',
          keepCurrentTask: true,
        },
      },
      {
        id: 'recent:task:project-1:recent-1',
        section: 'Recent Tasks',
        target: {
          kind: 'task',
          projectId: 'project-1',
          taskId: 'recent-1',
        },
      },
      {
        id: 'recent:task:project-1:recent-2',
        section: 'Recent Tasks',
        target: {
          kind: 'task',
          projectId: 'project-1',
          taskId: 'recent-2',
        },
      },
    ]);
  });

  it('supports @tasks mode through the controller keyword cap', async () => {
    const fixture = source(
      Array.from({ length: 25 }, (_, index) => task(`task-${index}`, `Fix task ${index}`))
    );
    const provider = createTaskPaletteProviderDef({
      source: fixture,
      render: () => null,
    });
    const controller = new PaletteController(
      definePaletteProviderCatalog([forController(provider)])
    );

    await controller.setInput('@tasks fix', {});

    expect(controller.getSnapshot()).toMatchObject({
      query: 'fix',
      mode: { kind: 'tasks', keyword: '@tasks' },
    });
    expect(controller.getSnapshot().results).toHaveLength(20);
    expect(fixture.searchPaletteEntities).toHaveBeenCalledWith({
      kind: 'task',
      query: 'fix',
      context: {},
      limit: 50,
    });
  });

  it('keeps task notifications available when recent-task search fails', async () => {
    const fixture = source([]);
    vi.mocked(fixture.searchPaletteEntities).mockRejectedValue(new Error('host unavailable'));
    fixture.notifications = () => [
      {
        id: 'task:project-1:task-1',
        title: 'Task needs attention',
        target: { kind: 'task', projectId: 'project-1', taskId: 'task-1' },
      },
    ];
    const provider = createTaskPaletteProviderDef({
      source: fixture,
      render: () => null,
    });

    await expect(provider.idle!({ projectId: 'project-1' })).resolves.toMatchObject([
      {
        id: 'notification:task:project-1:task-1',
        section: 'Notifications',
      },
    ]);
  });
});
