import {
  asAvailableProject,
  getProjectManagerStore,
  getProjectStore,
} from '@core/features/projects/api/browser/stores/project-selectors';
import type { TaskManagerStore } from '@core/features/tasks/api/browser/stores/task-manager';
import type { TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import { taskManagerStoreToken } from '@core/features/tasks/contributions/browser/project-store-tokens';
import {
  isProvisioned,
  isUnprovisioned,
  isUnregistered,
  registeredTaskData,
  type RegisteredTaskData,
} from '@core/primitives/task-state/browser/task-state';

/** Call only inside `observer` components (or other MobX reactions). */
export function getTaskManagerStore(projectId: string): TaskManagerStore | undefined {
  return asAvailableProject(getProjectStore(projectId))?.get(taskManagerStoreToken);
}

/** Call only inside `observer` components (or other MobX reactions). */
export function getTaskStore(projectId: string, taskId: string): TaskStore | undefined {
  return getTaskManagerStore(projectId)?.tasks.get(taskId);
}

/** Registered task payload (`Task`) when the row exists and is not unregistered; otherwise undefined. */
export function getRegisteredTaskData(
  projectId: string,
  taskId: string
): RegisteredTaskData | undefined {
  const store = getTaskStore(projectId, taskId);
  if (!store) return undefined;
  return registeredTaskData(store);
}

export type TaskHostActionAvailability = { kind: 'enabled' } | { kind: 'disabled' };

/** Host-backed Task verbs stay visible while degraded and share one accessible reason. */
export function taskHostActionAvailability(projectId: string): TaskHostActionAvailability {
  const context = asAvailableProject(getProjectStore(projectId));
  return context?.host.liveAction.kind === 'enabled' ? { kind: 'enabled' } : { kind: 'disabled' };
}

export type TaskViewKind =
  | 'missing'
  | 'project-hydrating'
  | 'project-error'
  | 'creating'
  | 'create-error'
  | 'provisioning'
  | 'provision-error'
  | 'teardown'
  | 'teardown-error'
  | 'idle'
  | 'ready';

/**
 * Derives the task view kind from the project + task store state.
 *
 * Pass `projectId` so that "project still opening" can be distinguished from
 * "task genuinely missing". Call only inside `observer` components.
 */
export function taskViewKind(store: TaskStore | undefined, projectId: string): TaskViewKind {
  const projectStore = getProjectManagerStore().projects.get(projectId);

  if (!projectStore) return 'missing';

  if (projectStore.state === 'unregistered') return 'missing';
  if (!projectStore.context || projectStore.context.kind === 'hydrating') {
    return 'project-hydrating';
  }
  if (projectStore.context.kind === 'failed') return 'project-error';

  if (!store) return 'missing';

  if (isUnregistered(store)) {
    if (store.phase === 'creating') return 'creating';
    return 'create-error';
  }
  if (isUnprovisioned(store)) {
    if (store.phase === 'provision') {
      return 'provisioning';
    }
    if (store.phase === 'provision-error') return 'provision-error';
    if (store.phase === 'teardown') return 'teardown';
    if (store.phase === 'teardown-error') return 'teardown-error';
    return 'idle';
  }
  return 'ready';
}

/** Returns the narrowed provisioned task store if the task is provisioned, otherwise undefined. */
export function asProvisioned(
  store: TaskStore | undefined
): (TaskStore & { state: 'provisioned'; workspaceId: string }) | undefined {
  return store && isProvisioned(store) ? store : undefined;
}

/** Returns the display name from any task store variant. */
export function taskDisplayName(store: TaskStore | undefined): string | undefined {
  if (!store) return undefined;
  return store.data.name;
}

/** Returns the error message for error states. */
export function taskErrorMessage(store: TaskStore | undefined): string | undefined {
  if (!store) return undefined;
  if (isUnregistered(store) && store.phase === 'create-error') {
    return store.errorMessage ?? 'Failed to create task';
  }
  if (isUnprovisioned(store)) {
    if (store.phase === 'provision-error') {
      return store.errorMessage ?? 'Failed to set up workspace';
    }
    if (store.phase === 'teardown-error') {
      return store.errorMessage ?? 'Failed to tear down task';
    }
  }
  return undefined;
}
