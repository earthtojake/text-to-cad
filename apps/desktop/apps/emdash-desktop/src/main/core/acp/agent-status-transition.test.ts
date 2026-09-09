import type { SessionSummary } from '@emdash/core/runtimes/acp/api';
import { describe, expect, it } from 'vitest';
import { deriveAcpAgentStatusActions, projectAcpStatusSnapshot } from './agent-status-transition';

function summary(overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    conversationId: 'conv-1',
    providerId: 'claude',
    lifecycle: 'ready',
    isGenerating: false,
    lastStopReason: null,
    lastTurnErrored: false,
    pendingPermissionCount: 0,
    backgroundAgentCount: 0,
    queuedPromptCount: 0,
    title: null,
    updatedAt: 1,
    ...overrides,
  };
}

describe('projectAcpStatusSnapshot', () => {
  it('projects busy work and pending permissions', () => {
    expect(projectAcpStatusSnapshot(summary({ queuedPromptCount: 1 }))).toBeNull();
    expect(
      projectAcpStatusSnapshot(summary({ isGenerating: true, pendingPermissionCount: 1 }))
    ).toMatchObject({
      kind: 'event',
      event: { type: 'notification', payload: { notificationType: 'permission_prompt' } },
    });
  });

  it('reconstructs completed and errored terminal statuses', () => {
    expect(projectAcpStatusSnapshot(summary({ lastStopReason: 'end_turn' }))).toMatchObject({
      kind: 'event',
      event: { type: 'stop' },
    });
    expect(projectAcpStatusSnapshot(summary({ lastTurnErrored: true }))).toMatchObject({
      kind: 'event',
      event: { type: 'error' },
    });
  });

  it('resets cancelled snapshots without overwriting fresh persisted state', () => {
    expect(projectAcpStatusSnapshot(summary({ lastStopReason: 'cancelled' }))).toEqual({
      kind: 'reset',
      conversationId: 'conv-1',
    });
    expect(projectAcpStatusSnapshot(summary())).toBeNull();
  });
});

describe('deriveAcpAgentStatusActions', () => {
  it('does not project a newly observed summary on the live path', () => {
    expect(deriveAcpAgentStatusActions(undefined, summary({ lifecycle: 'starting' }))).toEqual([]);
    expect(
      deriveAcpAgentStatusActions(
        undefined,
        summary({ lifecycle: 'starting', queuedPromptCount: 1 })
      )
    ).toEqual([]);
  });

  it('emits start when generation begins', () => {
    const actions = deriveAcpAgentStatusActions(
      summary(),
      summary({ lifecycle: 'working', isGenerating: true })
    );

    expect(actions).toHaveLength(1);
    expect(actions[0]).toMatchObject({ kind: 'event', event: { type: 'start' } });
  });

  it('does not report an idle queue as active work', () => {
    expect(deriveAcpAgentStatusActions(summary(), summary({ queuedPromptCount: 1 }))).toEqual([]);
  });

  it('emits an attention notification when a permission prompt appears', () => {
    const actions = deriveAcpAgentStatusActions(
      summary({ lifecycle: 'working', isGenerating: true }),
      summary({ lifecycle: 'working', isGenerating: true, pendingPermissionCount: 1 })
    );

    expect(actions).toHaveLength(1);
    expect(actions[0]).toMatchObject({
      kind: 'event',
      event: {
        type: 'notification',
        payload: { notificationType: 'permission_prompt' },
      },
    });
  });

  it('does not also emit start when a permission prompt is the first busy state', () => {
    const actions = deriveAcpAgentStatusActions(
      summary(),
      summary({ lifecycle: 'working', isGenerating: true, pendingPermissionCount: 1 })
    );

    expect(actions).toHaveLength(1);
    expect(actions[0]).toMatchObject({ kind: 'event', event: { type: 'notification' } });
  });

  it('emits stop when busy work ends normally', () => {
    const actions = deriveAcpAgentStatusActions(
      summary({ lifecycle: 'working', isGenerating: true }),
      summary({ lifecycle: 'ready', lastStopReason: 'end_turn' })
    );

    expect(actions).toHaveLength(1);
    expect(actions[0]).toMatchObject({ kind: 'event', event: { type: 'stop' } });
  });

  it('emits error when busy work ends with an error', () => {
    const actions = deriveAcpAgentStatusActions(
      summary({ lifecycle: 'working', isGenerating: true }),
      summary({ lifecycle: 'ready', lastTurnErrored: true })
    );

    expect(actions).toHaveLength(1);
    expect(actions[0]).toMatchObject({ kind: 'event', event: { type: 'error' } });
  });

  it('resets to idle when busy work is cancelled', () => {
    const actions = deriveAcpAgentStatusActions(
      summary({ lifecycle: 'cancelling', isGenerating: true }),
      summary({
        lifecycle: 'ready',
        lastStopReason: 'cancelled',
      })
    );

    expect(actions).toEqual([
      {
        kind: 'reset',
        conversationId: 'conv-1',
      },
    ]);
  });

  it('resets to idle when a session is removed or closed', () => {
    expect(deriveAcpAgentStatusActions(summary(), undefined)).toEqual([
      {
        kind: 'reset',
        conversationId: 'conv-1',
      },
    ]);
    expect(deriveAcpAgentStatusActions(summary(), summary({ lifecycle: 'closed' }))).toEqual([
      {
        kind: 'reset',
        conversationId: 'conv-1',
      },
    ]);
  });
});
