import type { SessionSummary } from '@emdash/core/runtimes/acp/api';
import { describe, expect, it } from 'vitest';
import { deriveAcpSessionTitleAction } from './session-title-action';

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

describe('deriveAcpSessionTitleAction', () => {
  it('projects a newly observed title', () => {
    expect(deriveAcpSessionTitleAction(undefined, summary({ title: 'Implement auth' }))).toEqual({
      conversationId: 'conv-1',
      title: 'Implement auth',
    });
  });

  it('ignores unchanged titles', () => {
    expect(
      deriveAcpSessionTitleAction(
        summary({ title: 'Implement auth' }),
        summary({ title: 'Implement auth' })
      )
    ).toBeNull();
  });

  it('projects changed titles', () => {
    expect(
      deriveAcpSessionTitleAction(
        summary({ title: 'Initial title' }),
        summary({ title: 'Better title' })
      )
    ).toEqual({
      conversationId: 'conv-1',
      title: 'Better title',
    });
  });

  it('ignores missing titles', () => {
    expect(
      deriveAcpSessionTitleAction(summary({ title: 'Initial title' }), summary({ title: null }))
    ).toBeNull();
  });
});
