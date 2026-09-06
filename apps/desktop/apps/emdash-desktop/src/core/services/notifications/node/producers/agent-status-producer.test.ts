import { describe, expect, it } from 'vitest';
import type { AgentEvent } from '@core/primitives/agents/api';
import { agentNotificationInputFromEvent, notificationMapping } from './agent-status-mapping';

function event(overrides: Partial<AgentEvent> = {}): AgentEvent {
  return {
    type: 'notification',
    providerId: 'codex',
    projectId: 'project-1',
    taskId: 'task-1',
    conversationId: 'conv-1',
    timestamp: 123,
    payload: { notificationType: 'permission_prompt' },
    ...overrides,
  };
}

describe('agent status notification producer', () => {
  it('maps attention events to agent-attention notifications', () => {
    const input = agentNotificationInputFromEvent(event(), 'Codex', 'Fix tests');

    expect(input).toEqual({
      kind: 'agent-attention',
      groupKey: 'conversation:conv-1',
      dedupeKey: 'conv-1:notification:123',
      title: 'Codex - Fix tests',
      body: 'Your agent is waiting for input',
      sound: 'needs_attention',
      target: {
        kind: 'task',
        projectId: 'project-1',
        taskId: 'task-1',
        conversationId: 'conv-1',
      },
      source: {
        kind: 'conversation',
        projectId: 'project-1',
        taskId: 'task-1',
        conversationId: 'conv-1',
      },
    });
  });

  it('maps stop events to completion notifications', () => {
    const input = agentNotificationInputFromEvent(
      event({ type: 'stop', payload: {} }),
      'Claude',
      null
    );

    expect(input).toMatchObject({
      kind: 'agent-complete',
      title: 'Claude',
      body: 'Your agent has finished working',
      sound: 'task_complete',
      source: {
        kind: 'conversation',
        projectId: 'project-1',
        taskId: 'task-1',
        conversationId: 'conv-1',
      },
    });
  });

  it('ignores non-attention notification events', () => {
    expect(
      notificationMapping(event({ payload: { notificationType: 'auth_success' } }))
    ).toBeNull();
  });
});
