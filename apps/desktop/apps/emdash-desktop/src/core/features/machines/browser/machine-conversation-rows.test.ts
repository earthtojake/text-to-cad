import { describe, expect, it } from 'vitest';
import type { HostConversationRow } from '@core/primitives/conversations/api';
import { joinMachineConversationRows } from './machine-conversation-rows';

function row(overrides: Partial<HostConversationRow> & { id: string }): HostConversationRow {
  return {
    title: `Conversation ${overrides.id}`,
    provider: 'claude',
    type: 'acp',
    projectId: null,
    taskId: null,
    projectName: null,
    taskName: null,
    workspacePath: '/work/repo',
    lastSessionActivityAt: null,
    observedStatus: 'present',
    lastObservedAt: '2026-01-01T00:00:00.000Z',
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
    pendingRemoval: false,
    ...overrides,
  };
}

describe('joinMachineConversationRows', () => {
  it('derives linked vs orphan from the client task link', () => {
    const items = joinMachineConversationRows({
      conversations: [
        row({ id: 'linked', taskId: 'task-1', projectId: 'project-1' }),
        row({ id: 'orphan' }),
      ],
    });
    expect(items.find((item) => item.conversation.id === 'linked')?.linked).toBe(true);
    expect(items.find((item) => item.conversation.id === 'orphan')?.linked).toBe(false);
  });

  it('marks missing and removal-pending states from the row observation', () => {
    const items = joinMachineConversationRows({
      conversations: [
        row({ id: 'missing', observedStatus: 'missing' }),
        row({ id: 'pending', pendingRemoval: true }),
      ],
    });
    expect(items.find((item) => item.conversation.id === 'missing')?.missing).toBe(true);
    expect(items.find((item) => item.conversation.id === 'pending')?.pendingRemoval).toBe(true);
  });

  it('asserts dangling paths only when a workspace observation is available', () => {
    const conversations = [
      row({ id: 'present-path', workspacePath: '/work/repo' }),
      row({ id: 'dangling-path', workspacePath: '/work/removed' }),
      row({ id: 'no-path', workspacePath: null }),
    ];

    const withoutObservation = joinMachineConversationRows({ conversations });
    expect(withoutObservation.every((item) => !item.dangling)).toBe(true);

    const withObservation = joinMachineConversationRows({
      conversations,
      knownWorkspacePaths: new Set(['/work/repo']),
    });
    expect(withObservation.find((item) => item.conversation.id === 'present-path')?.dangling).toBe(
      false
    );
    expect(withObservation.find((item) => item.conversation.id === 'dangling-path')?.dangling).toBe(
      true
    );
    expect(withObservation.find((item) => item.conversation.id === 'no-path')?.dangling).toBe(
      false
    );
  });

  it('sorts by last session activity, falling back to updatedAt', () => {
    const items = joinMachineConversationRows({
      conversations: [
        row({ id: 'stale', updatedAt: '2026-01-01T00:00:00.000Z' }),
        row({ id: 'recent-activity', lastSessionActivityAt: '2026-03-01T00:00:00.000Z' }),
        row({ id: 'recently-updated', updatedAt: '2026-02-01T00:00:00.000Z' }),
      ],
    });
    expect(items.map((item) => item.conversation.id)).toEqual([
      'recent-activity',
      'recently-updated',
      'stale',
    ]);
  });
});
