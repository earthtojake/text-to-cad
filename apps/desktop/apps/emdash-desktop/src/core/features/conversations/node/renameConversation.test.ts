import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { HostConversationMutationDeps } from './host-mutation';
import { renameConversation } from './renameConversation';

const emitWire = vi.hoisted(() => vi.fn());
const emitEvent = vi.hoisted(() => vi.fn());

vi.mock('./event-host', () => ({
  conversationWireEvents: { emit: emitWire },
}));
vi.mock('@core/features/conversations/api/node/conversation-events', () => ({
  conversationEvents: { _emit: emitEvent },
}));
vi.mock('@core/services/app-db/node/pokes', () => ({
  appDbPokes: { conversations: { poke: vi.fn() } },
}));

type FakeRow = {
  projectId: string | null;
  taskId: string | null;
  location: 'local' | 'remote';
  sshConnectionId: string | null;
};

/** Rename as a host-gated foreground wire mutation (spec §4.3). */
describe('renameConversation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renames through the host verb and caches the acknowledged title', async () => {
    const { deps, host, cacheWrites } = fakeDeps({
      projectId: 'project-1',
      taskId: 'task-1',
      location: 'local',
      sshConnectionId: null,
    });
    host.rename.mockResolvedValueOnce({
      success: true,
      data: { conversationId: 'conversation-1', title: 'Trimmed by host', updatedAt: Date.now() },
    } as never);

    await renameConversation(deps, 'conversation-1', '  New title  ');

    expect(host.rename).toHaveBeenCalledWith({
      conversationId: 'conversation-1',
      title: 'New title',
    });
    // The cache holds the host-acknowledged value, not the requested one.
    expect(cacheWrites[0]?.title).toBe('Trimmed by host');
    expect(emitWire).toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ changes: { title: 'Trimmed by host' } })
    );
  });

  it('refuses the rename when the remote host is unreachable', async () => {
    const { deps, host } = fakeDeps({
      projectId: 'project-1',
      taskId: 'task-1',
      location: 'remote',
      sshConnectionId: 'conn-1',
    });
    deps.hostIsReachable = vi.fn(() => false);

    await expect(renameConversation(deps, 'conversation-1', 'New title')).rejects.toThrow(
      'The workspace host is offline'
    );
    expect(host.rename).not.toHaveBeenCalled();
  });

  it('surfaces host rejection without a cache write', async () => {
    const { deps, host, cacheWrites } = fakeDeps({
      projectId: 'project-1',
      taskId: 'task-1',
      location: 'local',
      sshConnectionId: null,
    });
    host.rename.mockResolvedValueOnce({
      success: false,
      error: { type: 'conversation-not-found', conversationId: 'conversation-1', message: 'gone' },
    } as never);

    await expect(renameConversation(deps, 'conversation-1', 'New title')).rejects.toThrow(
      'Rename was rejected by the host'
    );
    expect(cacheWrites).toHaveLength(0);
    expect(emitWire).not.toHaveBeenCalled();
  });
});

function fakeDeps(row: FakeRow) {
  const cacheWrites: Array<Record<string, unknown>> = [];
  const host = {
    rename: vi.fn(async (input: { conversationId: string; title: string }) => ({
      success: true as const,
      data: { ...input, updatedAt: Date.now() },
    })),
  };
  const database = {
    select: () => ({
      from: () => ({
        where: () => ({
          limit: async () => [{ id: 'conversation-1', ...row }],
        }),
      }),
    }),
    update: () => ({
      set: (values: Record<string, unknown>) => ({
        where: () => ({
          run: () => {
            cacheWrites.push(values);
            return { changes: 1 };
          },
        }),
      }),
    }),
  };
  const deps: HostConversationMutationDeps = {
    db: database as never,
    runtimes: {
      client: vi.fn(async () => ({
        success: true as const,
        data: { conversations: host },
      })),
    } as never,
    hostIsReachable: vi.fn(() => true),
  };
  return { deps, host, cacheWrites };
}
