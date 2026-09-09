import type { TelemetryEnvelope } from '@core/primitives/telemetry/api/telemetry';

type TelemetryScope = Pick<TelemetryEnvelope, 'project_id' | 'task_id' | 'conversation_id'>;

const scope: TelemetryScope = {
  project_id: undefined,
  task_id: undefined,
  conversation_id: undefined,
};

export function setTelemetryTaskScope({
  projectId,
  taskId,
}: {
  projectId: string;
  taskId: string;
}): void {
  scope.project_id = projectId;
  scope.task_id = taskId;
  scope.conversation_id = undefined;
}

export function clearTelemetryTaskScope(): void {
  scope.project_id = undefined;
  scope.task_id = undefined;
  scope.conversation_id = undefined;
}

export function setTelemetryConversationScope(conversationId: string | null): void {
  scope.conversation_id = conversationId ?? undefined;
}

export function getTelemetryScope(): TelemetryScope {
  return { ...scope };
}
