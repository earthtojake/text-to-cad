import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ConversationRow } from '@core/services/app-db/node/schema';
import { launchTuiConversation } from './launch-tui-conversation';

const resolveTask = vi.hoisted(() => vi.fn());
const emit = vi.hoisted(() => vi.fn());
const capture = vi.hoisted(() => vi.fn());

vi.mock('@core/features/conversations/api/node', () => ({
  conversationWireEvents: { emit },
}));

describe('launchTuiConversation', () => {
  beforeEach(() => {
    resolveTask.mockReset();
    emit.mockReset();
    capture.mockReset();
  });

  it('starts first-spawn conversations without a client session id write', async () => {
    const row = conversationRow({ providerSessionId: null });
    const database = fakeDatabase(row);
    const ensureSession = vi.fn(() => Promise.resolve({ outcome: 'started' as const }));
    resolveTask.mockReturnValue({
      conversations: {
        ensureSession,
        stopSession: vi.fn(),
      },
    });

    const result = await launchTuiConversation({
      projectId: 'project-1',
      taskId: 'task-1',
      conversationId: 'conversation-1',
      database: database as never,
      telemetry: { capture },
      taskSessions: { getTask: resolveTask },
    });

    expect(ensureSession).toHaveBeenCalledWith(
      expect.objectContaining({
        mode: 'start',
        initialPrompt: 'hello',
      })
    );
    // The resume handle is host truth: the runtime reports it into the index and
    // convergence caches it — no client write, no client-emitted sessionId event.
    expect(row.providerSessionId).toBe(null);
    expect(emit).not.toHaveBeenCalled();
    expect(result.outcome).toBe('started');
  });

  it('resumes when the observation cache holds a provider session id', async () => {
    const row = conversationRow({ providerSessionId: 'native-session' });
    const database = fakeDatabase(row);
    const ensureSession = vi.fn(() => Promise.resolve({ outcome: 'started' as const }));
    resolveTask.mockReturnValue({
      conversations: {
        ensureSession,
        stopSession: vi.fn(),
      },
    });

    const result = await launchTuiConversation({
      projectId: 'project-1',
      taskId: 'task-1',
      conversationId: 'conversation-1',
      database: database as never,
      telemetry: { capture },
      taskSessions: { getTask: resolveTask },
    });

    expect(ensureSession).toHaveBeenCalledWith(
      expect.objectContaining({ mode: 'resume', initialPrompt: undefined })
    );
    expect(result.conversation.sessionId).toBe('native-session');
    expect(emit).not.toHaveBeenCalled();
  });
});

function fakeDatabase(row: ConversationRow) {
  return {
    select: () => ({
      from: () => ({
        where: () => ({
          limit: async () => [row],
        }),
      }),
    }),
  };
}

function conversationRow(overrides: Partial<ConversationRow>): ConversationRow {
  return {
    id: 'conversation-1',
    projectId: 'project-1',
    taskId: 'task-1',
    title: 'Conversation',
    provider: 'claude',
    providerSessionId: null,
    config: {
      version: '1',
      type: 'pty',
      initialPrompt: 'hello',
    },
    isInitialConversation: false,
    type: 'pty',
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
    lastSessionActivityAt: null,
    agentStatus: null,
    agentStatusSeen: 1,
    ...overrides,
  } as ConversationRow;
}
