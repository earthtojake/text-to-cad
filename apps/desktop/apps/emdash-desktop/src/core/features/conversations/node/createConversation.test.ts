import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createConversation } from './createConversation';

vi.mock('@core/features/conversations/api/node', () => ({
  conversationWireEvents: { emit: vi.fn() },
}));
vi.mock('@core/features/conversations/api/node/conversation-events', () => ({
  conversationEvents: { _emit: vi.fn() },
}));
vi.mock('@core/services/app-db/node/pokes', () => ({
  appDbPokes: { conversations: { poke: vi.fn() } },
}));
vi.mock('./launch-tui-conversation', () => ({
  launchTuiConversation: vi.fn(async () => ({
    conversation: { id: 'conv-1' },
    outcome: 'started',
  })),
}));

const conversationRow = {
  id: 'conv-1',
  projectId: 'project-1',
  taskId: 'task-1',
  title: 'Chat',
  provider: 'claude-code',
  type: 'acp',
  config: { version: '1', type: 'acp' },
  isInitialConversation: false,
  agentStatus: null,
  agentStatusSeen: 1,
  createdAt: '2026-01-01 00:00:00',
  updatedAt: '2026-01-01 00:00:00',
  providerSessionId: null,
  cwd: '/work/repo',
  workspacePath: '/work/repo',
  idRegime: 'provider-minted',
  lastSessionActivityAt: '2026-01-01T00:00:00.000Z',
  observedStatus: null,
  lastObservedAt: null,
  origin: 'registered',
  location: 'local',
  sshConnectionId: null,
  untrackedAt: null,
};

function fakeDatabase(options: { failInsert?: boolean; existingCadContextKey?: string } = {}) {
  const inserted: unknown[] = [];
  return {
    inserted,
    select: vi.fn(() => ({
      from: () => ({
        where: () => ({
          limit: async () => [{ id: 'other-conv', workspaceId: 'workspace-1' }],
          // Registry purge's tracked-rows check: untrack always ran first, so none remain.
          all: () =>
            options.existingCadContextKey
              ? [
                  {
                    id: 'existing-cad-conversation',
                    config: {
                      version: '1',
                      type: 'acp',
                      contextKey: options.existingCadContextKey,
                    },
                  },
                ]
              : [],
        }),
      }),
    })),
    insert: vi.fn(() => ({
      values: (values: unknown) => ({
        onConflictDoUpdate: () => ({
          returning: () => ({
            get: () => {
              if (options.failInsert) throw new Error('constraint violation');
              inserted.push(values);
              return { ...conversationRow, ...(values as object) };
            },
          }),
        }),
      }),
    })),
    delete: vi.fn(() => ({
      where: () => ({ execute: async () => {}, run: () => ({ changes: 1 }) }),
    })),
    update: vi.fn(() => ({
      set: () => ({ where: () => ({ run: () => ({ changes: 1 }) }) }),
    })),
  };
}

const hostConversations = {
  create: vi.fn(async (input: { id: string }) => ({ success: true as const, data: input })),
  delete: vi.fn(async () => ({ success: true as const, data: undefined })),
};
const runtimes = {
  client: vi.fn(async () => ({
    success: true as const,
    data: { conversations: hostConversations },
  })),
} as never;

function dependencies(overrides: Partial<Parameters<typeof createConversation>[1]> = {}) {
  return {
    db: fakeDatabase() as never,
    telemetry: { capture: vi.fn() },
    taskSessions: { getTask: vi.fn() },
    withCompensation: (async ({ action, compensate }) => {
      try {
        return await action();
      } catch (error) {
        await compensate();
        throw error;
      }
    }) as Parameters<typeof createConversation>[1]['withCompensation'],
    runtimes,
    hostIsReachable: vi.fn(() => true),
    workspaceIdentity: {
      resolve: vi.fn(async () => ({ host: LOCAL_HOST_REF, path: '/work/repo' })),
    },
    ...overrides,
  };
}

const baseParams = {
  projectId: 'project-1',
  taskId: 'task-1',
  provider: 'claude-code',
  title: 'Chat',
  type: 'acp' as const,
  id: 'conv-1',
};

/** Host-first additional-conversation creation (spec §6.2-6.3). */
describe('createConversation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('registers the host record before the client row, with the workspace path frozen', async () => {
    const deps = dependencies();
    const conversation = await createConversation(
      {
        ...baseParams,
        contextKey: 'cad-model:examples/plate',
        initialQueue: [{ text: 'hello' }],
      },
      deps
    );

    expect(conversation.id).toBe('conv-1');
    expect(hostConversations.create).toHaveBeenCalledTimes(1);
    const hostInput = hostConversations.create.mock.calls[0][0] as Record<string, unknown>;
    expect(hostInput).toMatchObject({
      conversationId: 'conv-1',
      cwd: '/work/repo',
      workspacePath: '/work/repo',
      idRegime: 'provider-minted',
      config: expect.objectContaining({
        contextKey: 'cad-model:examples/plate',
        initialQueue: [{ text: 'hello' }],
      }),
    });
    const db = deps.db as unknown as ReturnType<typeof fakeDatabase>;
    expect(hostConversations.create.mock.invocationCallOrder[0]).toBeLessThan(
      db.insert.mock.invocationCallOrder[0]
    );
    expect(db.inserted[0]).toMatchObject({ cwd: '/work/repo', workspacePath: '/work/repo' });
  });

  it('allows several conversations to share one CAD model context', async () => {
    const deps = dependencies({
      db: fakeDatabase({ existingCadContextKey: 'cad-model:examples/plate' }) as never,
    });

    await expect(
      createConversation(
        {
          ...baseParams,
          contextKey: 'cad-model:examples/plate',
          initialQueue: [{ text: 'hello' }],
        },
        deps
      )
    ).resolves.toMatchObject({ id: 'conv-1', contextKey: 'cad-model:examples/plate' });
    expect(hostConversations.create).toHaveBeenCalledTimes(1);
    expect((deps.db as unknown as ReturnType<typeof fakeDatabase>).insert).toHaveBeenCalledTimes(1);
  });

  it('refuses creation against an unreachable remote host before touching the host or DB', async () => {
    const deps = dependencies({
      hostIsReachable: vi.fn(() => false),
      workspaceIdentity: {
        resolve: vi.fn(async () => ({ host: hostRef('remote', 'conn-1'), path: '/work/repo' })),
      },
    });

    await expect(createConversation(baseParams, deps)).rejects.toThrow(
      'The workspace host is offline'
    );
    expect(hostConversations.create).not.toHaveBeenCalled();
    expect((deps.db as unknown as ReturnType<typeof fakeDatabase>).insert).not.toHaveBeenCalled();
  });

  it('compensates with a direct host delete when the client insert fails', async () => {
    const deps = dependencies({ db: fakeDatabase({ failInsert: true }) as never });

    await expect(createConversation(baseParams, deps)).rejects.toThrow('constraint violation');
    expect(hostConversations.create).toHaveBeenCalledTimes(1);
    expect(hostConversations.delete).toHaveBeenCalledWith({ conversationId: 'conv-1' });
  });

  it('fails without a client insert when host registration fails', async () => {
    hostConversations.create.mockResolvedValueOnce({
      success: false,
      error: { type: 'immutable-field-mismatch', message: 'id reuse' },
    } as never);
    const deps = dependencies();

    await expect(createConversation(baseParams, deps)).rejects.toThrow('id reuse');
    expect((deps.db as unknown as ReturnType<typeof fakeDatabase>).insert).not.toHaveBeenCalled();
    expect(hostConversations.delete).not.toHaveBeenCalled();
  });

  it('rolls back both the client row and the host record when the PTY launch fails', async () => {
    const { launchTuiConversation } = await import('./launch-tui-conversation');
    vi.mocked(launchTuiConversation).mockRejectedValueOnce(new Error('spawn failed'));
    const deps = dependencies();

    await expect(createConversation({ ...baseParams, type: 'pty' as const }, deps)).rejects.toThrow(
      'spawn failed'
    );
    expect((deps.db as unknown as ReturnType<typeof fakeDatabase>).delete).toHaveBeenCalled();
    expect(hostConversations.delete).toHaveBeenCalledWith({ conversationId: 'conv-1' });
  });
});
