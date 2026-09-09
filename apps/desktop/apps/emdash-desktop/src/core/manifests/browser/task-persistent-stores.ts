import { sourceControlPersistentTaskStoreContributions } from '@core/features/source-control/contributions/browser/task-stores';
import type { TaskScopedStoreContext } from '@core/features/tasks/contributions/browser/task-stores';
import type { ScopedStoreContribution } from '@core/primitives/scoped-stores/browser';

/** Lightweight feature state that survives session teardown for as long as the task row exists. */
export const taskPersistentStoreContributions: readonly ScopedStoreContribution<TaskScopedStoreContext>[] =
  [...sourceControlPersistentTaskStoreContributions];
