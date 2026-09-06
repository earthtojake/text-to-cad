import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';

export function resolveTask(
  taskSessions: Pick<TaskSessionManager, 'getTask'>,
  _projectId: string,
  taskId: string
) {
  return taskSessions.getTask(taskId) ?? null;
}

export type TimeoutError<T extends string> = {
  type: 'timeout';
  scope: T;
  timeout: number;
  message?: string;
};

export function timeoutError<T extends string>(
  scope: T,
  timeout: number,
  message?: string
): TimeoutError<T> {
  return {
    type: 'timeout',
    scope,
    timeout,
    message,
  };
}

export type AbortError<T extends string> = {
  type: 'abort';
  scope: T;
  message?: string;
};

export function abortError<T extends string>(scope: T, message?: string): AbortError<T> {
  return {
    type: 'abort',
    scope,
    message,
  };
}
