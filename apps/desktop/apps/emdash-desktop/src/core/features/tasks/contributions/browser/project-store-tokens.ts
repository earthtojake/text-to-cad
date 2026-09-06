import type { TaskManagerStore } from '@core/features/tasks/api/browser/stores/task-manager';
import { scopedStoreToken } from '@core/primitives/scoped-stores/browser';

export const taskManagerStoreToken = scopedStoreToken<TaskManagerStore>('tasks.manager');
