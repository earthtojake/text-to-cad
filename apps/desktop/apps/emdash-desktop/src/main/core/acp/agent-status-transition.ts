import type { SessionSummary } from '@emdash/core/runtimes/acp/api';
import type { AgentStatusSignal } from '@core/primitives/agents/api';

export type AcpAgentStatusAction =
  | { kind: 'event'; event: AgentStatusSignal }
  | { kind: 'reset'; conversationId: string };

function isBusy(summary: SessionSummary | undefined): boolean {
  return summary?.isGenerating ?? false;
}

function eventBase(summary: SessionSummary): Omit<AgentStatusSignal, 'type' | 'payload'> {
  return {
    source: 'input',
    providerId: summary.providerId,
    conversationId: summary.conversationId,
    timestamp: Date.now(),
  };
}

function eventAction(
  summary: SessionSummary,
  type: 'start' | 'stop' | 'error'
): AcpAgentStatusAction {
  return { kind: 'event', event: { ...eventBase(summary), type, payload: {} } };
}

function permissionAction(summary: SessionSummary): AcpAgentStatusAction {
  return {
    kind: 'event',
    event: {
      ...eventBase(summary),
      type: 'notification',
      payload: { notificationType: 'permission_prompt' },
    },
  };
}

function resetAction(conversationId: string): AcpAgentStatusAction {
  return { kind: 'reset', conversationId };
}

function settledAction(summary: SessionSummary): AcpAgentStatusAction | null {
  if (summary.lastTurnErrored) return eventAction(summary, 'error');
  if (summary.lastStopReason === 'cancelled') return resetAction(summary.conversationId);
  if (summary.lastStopReason !== null) return eventAction(summary, 'stop');
  return null;
}

export function projectAcpStatusSnapshot(summary: SessionSummary): AcpAgentStatusAction | null {
  if (summary.pendingPermissionCount > 0) return permissionAction(summary);
  if (isBusy(summary)) return eventAction(summary, 'start');
  return settledAction(summary);
}

export function deriveAcpAgentStatusActions(
  previous: SessionSummary | undefined,
  next: SessionSummary | undefined
): AcpAgentStatusAction[] {
  if (!next) {
    if (!previous) return [];
    return [resetAction(previous.conversationId)];
  }

  if (!previous) return [];

  if (next.lifecycle === 'closed') {
    return [resetAction(next.conversationId)];
  }

  const actions: AcpAgentStatusAction[] = [];
  const wasBusy = isBusy(previous);
  const nowBusy = isBusy(next);
  const previousPendingPermissionCount = previous?.pendingPermissionCount ?? 0;
  const permissionAppeared =
    previousPendingPermissionCount === 0 && next.pendingPermissionCount > 0;

  if (!wasBusy && nowBusy && !permissionAppeared) {
    actions.push(eventAction(next, 'start'));
  }

  if (permissionAppeared) {
    actions.push(permissionAction(next));
  }

  if (wasBusy && !nowBusy && next.pendingPermissionCount === 0) {
    actions.push(settledAction(next) ?? resetAction(next.conversationId));
  }

  return actions;
}
