import type { TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import type { ScopedStoreLookup } from '@core/primitives/scoped-stores/browser';

export type TaskScopedStoreContext = Readonly<{
  projectId: string;
  taskId: string;
  task: TaskStore;
  projectStores: ScopedStoreLookup;
}>;
