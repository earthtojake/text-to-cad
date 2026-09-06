import type { TaskService } from '@core/features/tasks/api/node/task-service';
import type { CreateTaskParams, DeleteTaskOptions } from '@core/primitives/tasks/api';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';
import { generateTaskName } from './name-generation/generateTaskName';

export function createTaskOperations(dependencies: {
  service: TaskService;
  telemetry: TelemetryService;
}) {
  const { service: taskService } = dependencies;
  return {
    async createTask(params: CreateTaskParams) {
      return taskService.createTask(params);
    },
    async getTasks(projectId?: string) {
      return taskService.getTasks(projectId);
    },
    async getDeletePreflight(_projectId: string, taskIds: string[]) {
      return taskService.getDeletePreflight(taskIds);
    },
    async deleteTask(projectId: string, taskId: string, options?: DeleteTaskOptions) {
      return taskService.deleteTask(projectId, taskId, options);
    },
    async deleteTasks(projectId: string, taskIds: string[], options?: DeleteTaskOptions) {
      return taskService.deleteTasks(projectId, taskIds, options);
    },
    async teardownTask(projectId: string, taskId: string) {
      return taskService.teardown(projectId, taskId, 'terminate');
    },
    generateTaskName,
  };
}
