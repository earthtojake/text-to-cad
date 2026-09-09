import type { TaskService } from '@core/features/tasks/api/node/task-service';
import type { TaskSessionManager } from '@core/features/tasks/api/node/task-session-manager';
import type { TelemetryService } from '@core/primitives/telemetry/api/telemetry';

let installed = false;

export function installTaskTelemetry(
  telemetry: TelemetryService,
  taskService: TaskService,
  taskSessionManager: TaskSessionManager
): void {
  if (installed) return;
  installed = true;

  taskService.on('task:created', (task, params) => {
    const { git } = params.workspaceConfig;
    const { linkedIssue, initialConversation } = params.taskConfig;
    const taskCreatedStrategy = (() => {
      if (git.kind === 'pr-branch') return 'pr';
      if (linkedIssue) return 'issue';
      if (git.kind === 'none') return 'blank';
      return 'branch';
    })();
    telemetry.capture('task_created', {
      strategy: taskCreatedStrategy,
      has_initial_prompt: Boolean(
        initialConversation?.initialPrompt?.trim() ||
        initialConversation?.initialQueue?.some((prompt) => prompt.text.trim())
      ),
      has_issue: linkedIssue?.provider ?? 'none',
      provider: initialConversation?.provider ?? null,
      project_id: task.projectId,
      task_id: task.id,
    });
    if (linkedIssue) {
      telemetry.capture('issue_linked_to_task', {
        provider: linkedIssue.provider,
        project_id: task.projectId,
        task_id: task.id,
      });
    }
  });

  taskSessionManager.hooks.on('task:provisioned', ({ projectId, taskId }) => {
    telemetry.capture('task_provisioned', { project_id: projectId, task_id: taskId });
  });

  taskService.on('task:provision-timing', ({ taskId, durationMs }) => {
    // Coarse resolution only; full-resolution stage timings stay in the local log.
    telemetry.capture('task_provision_timing', {
      task_id: taskId,
      duration_ms: Math.round(durationMs / 100) * 100,
    });
  });
}
