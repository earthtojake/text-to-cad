import { getGitCheckoutStore } from '@core/features/source-control/api/browser/stores/source-control-selectors';
import type { TaskPrAssociationStore } from '@core/features/source-control/api/browser/stores/task-pr-association-store';
import { taskPrAssociationStoreToken } from '@core/features/source-control/contributions/browser/task-stores';
import type { TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import { getTaskStore } from '@core/features/tasks/api/browser/task-state/task-selectors';
import type { GitCheckoutStore } from '../../../browser/stores/git-checkout-store';

/** Call only inside `observer` components (or other MobX reactions). */
export function getTaskGitCheckoutStore(
  projectId: string,
  taskId: string
): GitCheckoutStore | undefined {
  const workspaceId = getTaskStore(projectId, taskId)?.workspaceId;
  return workspaceId ? getGitCheckoutStore(workspaceId) : undefined;
}

/** Task-lifetime PR association state, available for active and inactive tasks. */
export function getTaskPrAssociationStore(task: TaskStore): TaskPrAssociationStore {
  return task.get(taskPrAssociationStoreToken);
}
