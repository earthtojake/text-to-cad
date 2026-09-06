import type { AutomationRunMeta, Task, TaskLifecycleStatus } from '@core/primitives/tasks/api';
import type { AutomationRunRow, TaskRow } from '@core/services/app-db/node/schema';
import type { PullRequest } from '@core/services/pull-requests/api';

export function mapAutomationRunRowToMeta(row: AutomationRunRow): AutomationRunMeta {
  return {
    automationName: row.automationName,
    status: row.status,
    scheduledAt: row.scheduledAt,
    startedAt: row.startedAt,
    finishedAt: row.finishedAt,
  };
}

export function mapTaskRowToTask(
  row: TaskRow,
  prs: PullRequest[] = [],
  conversations: Record<string, number> = {},
  automationRunMeta?: AutomationRunMeta
): Task {
  return {
    id: row.id,
    projectId: row.projectId,
    name: row.name,
    status: row.status as TaskLifecycleStatus,
    linkedIssue: row.linkedIssue ?? undefined,
    archivedAt: row.archivedAt ?? undefined,
    lastInteractedAt: row.lastInteractedAt ?? undefined,
    createdAt: row.createdAt,
    prs,
    conversations,
    updatedAt: row.updatedAt,
    statusChangedAt: row.statusChangedAt,
    isPinned: row.isPinned === 1,
    workspaceId: row.workspaceId ?? undefined,
    type: (row.type as 'task' | 'automation-run') ?? 'task',
    automationRunId: row.automationRunId ?? undefined,
    automationRunMeta,
  };
}
