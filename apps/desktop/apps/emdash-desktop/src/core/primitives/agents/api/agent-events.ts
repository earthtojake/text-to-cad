export type AgentEventType = 'notification' | 'stop' | 'error' | 'start';

export type AgentStatus = 'idle' | 'working' | 'awaiting-input' | 'error' | 'completed';

export type NotificationType =
  | 'permission_prompt'
  | 'idle_prompt'
  | 'auth_success'
  | 'elicitation_dialog';

const ATTENTION_NOTIFICATION_TYPES: ReadonlySet<NotificationType> = new Set([
  'permission_prompt',
  'idle_prompt',
  'elicitation_dialog',
]);

export function isAttentionNotification(
  notificationType: NotificationType | undefined
): notificationType is NotificationType {
  return notificationType !== undefined && ATTENTION_NOTIFICATION_TYPES.has(notificationType);
}

export interface AgentEvent {
  type: AgentEventType;
  source?: 'hook' | 'input';
  ptyId?: string;
  providerId?: string;
  projectId: string;
  taskId: string;
  conversationId: string;
  timestamp: number;
  payload: {
    notificationType?: NotificationType;
    title?: string;
    message?: string;
    lastAssistantMessage?: string;
  };
}

export type AgentStatusSignal = Omit<AgentEvent, 'projectId' | 'taskId'>;

export type SoundEvent = 'needs_attention' | 'task_complete';
