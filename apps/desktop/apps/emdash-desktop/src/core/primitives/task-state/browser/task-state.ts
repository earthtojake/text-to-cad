import type { Task, TaskLifecycleStatus } from '@core/primitives/tasks/api';

/** Browser task-list state; renderer-derived PR association lives in its feature store. */
export type RegisteredTaskData = Omit<Task, 'prs'>;

export type UnregisteredTaskPhase = 'creating' | 'create-error';

export type UnprovisionedTaskPhase =
  | 'provision'
  | 'provision-error'
  | 'teardown'
  | 'teardown-error'
  | 'idle';

export type UnregisteredTaskData = {
  id: string;
  name: string;
  status: TaskLifecycleStatus;
  lastInteractedAt: string;
  createdAt: string;
  statusChangedAt: string;
  isPinned: boolean;
  type: 'task' | 'automation-run';
  automationRunId?: string;
};

export interface TaskState {
  readonly state: 'unregistered' | 'unprovisioned' | 'provisioned';
  readonly data: UnregisteredTaskData | RegisteredTaskData;
  readonly phase: UnregisteredTaskPhase | UnprovisionedTaskPhase | null;
  readonly errorMessage: string | undefined;
  readonly workspaceId: string | null;
  readonly workspacePath: string | null;
  readonly workspaceSshConnectionId: string | undefined;
}

export type UnregisteredTaskState = TaskState & {
  state: 'unregistered';
  data: UnregisteredTaskData;
  phase: UnregisteredTaskPhase;
};

export type UnprovisionedTaskState = TaskState & {
  state: 'unprovisioned';
  data: RegisteredTaskData;
  phase: UnprovisionedTaskPhase;
};

export type ProvisionedTaskState = TaskState & {
  state: 'provisioned';
  data: RegisteredTaskData;
  workspaceId: string;
};

export function isUnregistered<T extends TaskState>(task: T): task is T & UnregisteredTaskState {
  return task.state === 'unregistered';
}

export function isRegistered(
  task: TaskState
): task is UnprovisionedTaskState | ProvisionedTaskState {
  return task.state === 'unprovisioned' || task.state === 'provisioned';
}

export function isUnprovisioned<T extends TaskState>(task: T): task is T & UnprovisionedTaskState {
  return task.state === 'unprovisioned';
}

export function isProvisioned<T extends TaskState>(task: T): task is T & ProvisionedTaskState {
  return task.state === 'provisioned';
}

export function registeredTaskData(task: TaskState): RegisteredTaskData | undefined {
  return isRegistered(task) ? task.data : undefined;
}

export function unregisteredTaskData(task: TaskState): UnregisteredTaskData | undefined {
  return isUnregistered(task) ? task.data : undefined;
}
