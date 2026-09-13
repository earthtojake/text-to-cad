import { getTaskStore } from '@core/features/tasks/api/browser/task-state/task-selectors';
import { taskCompositionHandleStoreToken } from '@core/features/workbench/contributions/browser/task-store-tokens';
import { workspaceRegistry } from '@core/features/workspaces/api/browser/stores/workspace-registry';

export function getTaskComposition(projectId: string, taskId: string) {
  return getTaskStore(projectId, taskId)?.get(taskCompositionHandleStoreToken).current ?? undefined;
}

export function getTaskWorkspace(projectId: string, taskId: string) {
  const workspaceId = getTaskStore(projectId, taskId)?.workspaceId;
  return workspaceId ? workspaceRegistry.get(workspaceId) : undefined;
}
