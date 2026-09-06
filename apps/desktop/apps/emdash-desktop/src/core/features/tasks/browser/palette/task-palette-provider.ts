import type { ComponentType } from 'react';
import {
  matchPaletteText,
  type PaletteContext,
  type PaletteProviderDef,
  type PaletteProviderMatch,
  type PaletteProviderRenderProps,
} from '@core/primitives/palette/api';
import type { PaletteEntitySearchQuery, SearchItem } from '@core/primitives/search/api';

const TASK_SOURCE_LIMIT = 50;
const RECENT_TASK_LIMIT = 5;
const RECENCY_CEILING = Date.parse('2100-01-01T00:00:00.000Z');

export type TaskPaletteTarget =
  | {
      readonly kind: 'task';
      readonly projectId: string;
      readonly taskId: string;
    }
  | {
      readonly kind: 'conversation';
      readonly projectId: string;
      readonly taskId: string;
      readonly conversationId: string;
      readonly keepCurrentTask: boolean;
    };

export interface TaskPaletteMatch extends PaletteProviderMatch {
  readonly target: TaskPaletteTarget;
}

export interface TaskPaletteNotification {
  readonly id: string;
  readonly title: string;
  readonly subtitle?: string;
  readonly target: TaskPaletteTarget;
}

export interface TaskPaletteSource {
  searchPaletteEntities(input: PaletteEntitySearchQuery): Promise<readonly SearchItem[]>;
  notifications(context: PaletteContext): readonly TaskPaletteNotification[];
  taskLastInteractedAt(projectId: string, taskId: string): string | undefined;
}

export function createTaskPaletteProviderDef({
  source,
  render,
}: {
  readonly source: TaskPaletteSource;
  readonly render: ComponentType<PaletteProviderRenderProps<TaskPaletteMatch>>;
}): PaletteProviderDef<'tasks', TaskPaletteMatch> {
  return {
    kind: 'tasks',
    keyword: '@tasks',
    minQueryLength: 1,
    idle: async (context) => {
      const notifications = source.notifications(context).map(
        (notification): TaskPaletteMatch => ({
          id: `notification:${notification.id}`,
          title: notification.title,
          subtitle: notification.subtitle,
          section: 'Notifications',
          relevance: { band: 'exact', score: 1 },
          target: notification.target,
        })
      );
      let recentItems: readonly SearchItem[] = [];
      try {
        recentItems = await source.searchPaletteEntities({
          kind: 'task',
          query: '',
          context,
          limit: RECENT_TASK_LIMIT,
        });
      } catch {
        return notifications;
      }
      const recentTasks = recentItems.flatMap((item): TaskPaletteMatch[] => {
        if (item.kind !== 'task' || !item.projectId) return [];
        return [
          {
            id: `recent:task:${item.projectId}:${item.id}`,
            title: item.title,
            subtitle: item.subtitle || undefined,
            section: 'Recent Tasks',
            relevance: { band: 'fuzzy', score: 0 },
            target: {
              kind: 'task',
              projectId: item.projectId,
              taskId: item.id,
            },
          },
        ];
      });
      return [...notifications, ...recentTasks];
    },
    search: async ({ query, context }) => {
      const items = await source.searchPaletteEntities({
        kind: 'task',
        query,
        context,
        limit: TASK_SOURCE_LIMIT,
      });

      return items.flatMap((item): TaskPaletteMatch[] => {
        if (item.kind !== 'task' || !item.projectId) return [];
        const relevance = matchPaletteText(query, {
          primary: [item.title],
          secondary: [item.subtitle],
        });
        if (!relevance) return [];
        const lastInteractedAt = source.taskLastInteractedAt(item.projectId, item.id);

        return [
          {
            id: `typed:task:${item.projectId}:${item.id}`,
            title: item.title,
            subtitle: item.subtitle || undefined,
            relevance: {
              ...relevance,
              contextAffinity: contextAffinity(item.projectId, item.id, context),
              recency: normalizedRecency(lastInteractedAt),
            },
            target: {
              kind: 'task',
              projectId: item.projectId,
              taskId: item.id,
            },
          },
        ];
      });
    },
    render,
  };
}

function contextAffinity(projectId: string, taskId: string, context: PaletteContext): number {
  if (taskId === context.taskId && projectId === context.projectId) return 1;
  if (projectId === context.projectId) return 0.5;
  return 0;
}

function normalizedRecency(value: string | undefined): number {
  if (!value) return 0;
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return 0;
  return Math.max(0, Math.min(1, timestamp / RECENCY_CEILING));
}
