import type { TaskCompositionHandle } from '@core/features/workbench/api/browser/task-composition-handle';
import { scopedStoreToken } from '@core/primitives/scoped-stores/browser';

export const taskCompositionHandleStoreToken = scopedStoreToken<TaskCompositionHandle>(
  'workbench.task-composition-handle'
);
