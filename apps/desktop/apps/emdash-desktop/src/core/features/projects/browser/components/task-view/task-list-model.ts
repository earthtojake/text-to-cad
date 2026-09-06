import type { ExternalSelectionStore } from '@emdash/ui/react/patterns';
import { createListView, createTextMatcher } from '@emdash/ui/react/patterns';
import { taskAgentStatus } from '@core/features/conversations/api/browser/conversation-selectors';
import type { ProjectTaskSortBy } from '@core/features/projects/contributions/mementos';
import { type TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import type { RegisteredTaskData } from '@core/primitives/task-state/browser/task-state';

export type ReadyTask = TaskStore & { data: RegisteredTaskData };

export type TaskListTab = 'active' | 'archived';

function latestInstant(task: ReadyTask) {
  return task.data.lastInteractedAt ?? task.data.updatedAt;
}

function isUnread(task: ReadyTask) {
  const status = taskAgentStatus(task);
  return status === 'awaiting-input' || status === 'error' || status === 'completed';
}

/** Every sort ends in the same tiebreak: most recently touched first, then id. */
function byRecency(a: ReadyTask, b: ReadyTask) {
  const latestComparison = latestInstant(b).localeCompare(latestInstant(a));
  return latestComparison || a.data.id.localeCompare(b.data.id);
}

/**
 * Comparators encode the display order directly (the sort spec's `dir` stays
 * `asc`), matching the pre-CollectionView ordering exactly.
 */
export const TASK_SORT_COMPARATORS: Record<
  ProjectTaskSortBy,
  (a: ReadyTask, b: ReadyTask) => number
> = {
  'updated-at': byRecency,
  'created-at': (a, b) => b.data.createdAt.localeCompare(a.data.createdAt) || byRecency(a, b),
  // Keep the persisted legacy key readable while presenting it as the model-name sort.
  'pr-status': (a, b) => a.data.name.localeCompare(b.data.name) || byRecency(a, b),
  unread: (a, b) => Number(isUnread(b)) - Number(isUnread(a)) || byRecency(a, b),
};

/**
 * The list-view state layer for the project task list: sync source fed by a
 * reactive getter over the task manager's observable map, name search, the
 * Active/Archived tab as a filter model, the four task sort options, and
 * selection delegated to the project's `TaskViewStore` (an
 * `ExternalSelectionStore`) so the bulk bar and delete command keep reading
 * the same store.
 */
export function createTaskListView(options: {
  getTasks: () => ReadyTask[];
  initialTab: TaskListTab;
  initialSortBy: ProjectTaskSortBy;
  selection: ExternalSelectionStore;
}) {
  return createListView({
    getItemId: (task: ReadyTask) => task.data.id,
    source: { kind: 'sync', items: options.getTasks },
    search: {
      kind: 'sync',
      predicate: createTextMatcher((task: ReadyTask) => [task.data.name]),
    },
    filter: {
      kind: 'sync',
      initial: { tab: options.initialTab },
      apply: (task, model: { tab: TaskListTab }) =>
        (model.tab === 'archived') === Boolean(task.data.archivedAt),
    },
    sort: {
      keys: {
        'updated-at': { label: 'Last used', compare: TASK_SORT_COMPARATORS['updated-at'] },
        'created-at': { label: 'Created at', compare: TASK_SORT_COMPARATORS['created-at'] },
        'pr-status': { label: 'Chat name', compare: TASK_SORT_COMPARATORS['pr-status'] },
        unread: { label: 'Needs attention', compare: TASK_SORT_COMPARATORS.unread },
      },
      initial: { key: options.initialSortBy, dir: 'asc' },
    },
    selection: { kind: 'external', store: options.selection },
  });
}

export type TaskListViewModel = ReturnType<typeof createTaskListView>;
