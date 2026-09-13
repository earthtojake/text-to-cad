import type { TuiAgentState } from '@emdash/core/runtimes/tui-agents/api';
import type { AgentStatusSignal } from '@core/primitives/agents/api';

export function shouldApplyAgentStateTransition(
  previous: TuiAgentState | undefined,
  next: TuiAgentState
): boolean {
  if (!previous) return true;
  if (previous.status !== next.status) return true;
  if (previous.notificationType !== next.notificationType) return true;
  return false;
}

export function eventFromTuiAgentState(state: TuiAgentState): AgentStatusSignal | null {
  const base = {
    source: state.source,
    providerId: state.providerId,
    conversationId: state.conversationId,
    timestamp: state.updatedAt,
    payload: {
      notificationType: state.notificationType,
      title: state.title,
      message: state.message,
      lastAssistantMessage: state.lastAssistantMessage,
    },
  } satisfies Omit<AgentStatusSignal, 'type'>;

  if (state.status === 'working') return { ...base, type: 'start' };
  if (state.status === 'completed') return { ...base, type: 'stop' };
  if (state.status === 'error') return { ...base, type: 'error' };
  if (state.status === 'awaiting-input') return { ...base, type: 'notification' };
  return null;
}
