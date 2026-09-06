import { describe, expect, it } from 'vitest';
import { defaultRoutingPolicy, type NotificationRoutingSettings } from './routing';
import type { AppNotification } from './schemas';

const baseNotification: AppNotification = {
  id: 'n-1',
  kind: 'agent-attention',
  groupKey: 'conversation:1',
  title: 'Agent',
  body: 'Waiting for input',
  target: { kind: 'task', projectId: 'project-1', taskId: 'task-1', conversationId: 'conv-1' },
  source: {
    kind: 'conversation',
    projectId: 'project-1',
    taskId: 'task-1',
    conversationId: 'conv-1',
  },
  sound: 'needs_attention',
  count: 1,
  createdAt: 1,
  readAt: null,
};

const settings: NotificationRoutingSettings = {
  enabled: true,
  sound: true,
  osNotifications: true,
  soundFocusMode: 'always',
};

describe('defaultRoutingPolicy', () => {
  it('routes system notifications only when the app is unfocused', () => {
    expect(defaultRoutingPolicy(baseNotification, { appFocused: false, settings })).toEqual({
      system: true,
      sound: true,
    });
    expect(defaultRoutingPolicy(baseNotification, { appFocused: true, settings })).toEqual({
      system: false,
      sound: true,
    });
  });

  it('honors disabled settings and focused-only sound mode', () => {
    expect(
      defaultRoutingPolicy(baseNotification, {
        appFocused: true,
        settings: { ...settings, soundFocusMode: 'unfocused' },
      })
    ).toEqual({ system: false, sound: false });

    expect(
      defaultRoutingPolicy(baseNotification, {
        appFocused: false,
        settings: { ...settings, enabled: false },
      })
    ).toEqual({ system: false, sound: false });
  });

  it('keeps non-urgent update notifications feed-only', () => {
    expect(
      defaultRoutingPolicy(
        {
          ...baseNotification,
          kind: 'update-available',
          sound: null,
          target: { kind: 'update', version: '1.2.3' },
          source: { kind: 'app' },
        },
        { appFocused: false, settings }
      )
    ).toEqual({ system: false, sound: false });

    expect(
      defaultRoutingPolicy(
        {
          ...baseNotification,
          kind: 'update-error',
          sound: null,
          target: { kind: 'update' },
          source: { kind: 'app' },
        },
        { appFocused: false, settings }
      )
    ).toEqual({ system: false, sound: false });
  });
});
