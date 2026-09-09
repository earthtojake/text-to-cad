import { describe, expect, it, vi } from 'vitest';
import type { ConversationConfig } from '@core/primitives/conversations/api';
import type { HostConversationMutationDeps } from './host-mutation';
import { setConversationModeId } from './set-mode-id';

type FakeRow = {
  config: ConversationConfig | null;
  projectId: string;
  taskId: string;
  location: 'local' | 'remote';
  sshConnectionId: string | null;
};

describe('setConversationModeId', () => {
  it('rejects an empty mode id', async () => {
    const { deps } = fakeDeps(acpRow());

    const result = await setConversationModeId(deps, 'conversation-1', '  ');

    expect(result).toEqual({ success: false, error: { type: 'empty-mode-id' } });
  });

  it('returns conversation-not-found when the row is missing', async () => {
    const { deps } = fakeDeps(undefined);

    const result = await setConversationModeId(deps, 'conversation-1', 'agent');

    expect(result).toMatchObject({ success: false, error: { type: 'conversation-not-found' } });
  });

  it('rejects non-ACP conversations', async () => {
    const { deps } = fakeDeps({
      config: { version: '1', type: 'pty' },
      projectId: 'project-1',
      taskId: 'task-1',
      location: 'local',
      sshConnectionId: null,
    });

    const result = await setConversationModeId(deps, 'conversation-1', 'agent');

    expect(result).toMatchObject({ success: false, error: { type: 'not-acp-conversation' } });
  });

  it('writes the mode id through the host updateConfig verb and caches the acknowledged config', async () => {
    const row = acpRow({ model: 'claude-sonnet-5' });
    const { deps, hostCalls, cacheWrites } = fakeDeps(row);

    const result = await setConversationModeId(deps, 'conversation-1', 'agent-full-access');

    expect(result).toEqual({
      success: true,
      data: { projectId: 'project-1', taskId: 'task-1' },
    });
    expect(hostCalls).toHaveLength(1);
    expect(hostCalls[0]).toEqual({
      conversationId: 'conversation-1',
      config: {
        version: '1',
        type: 'acp',
        model: 'claude-sonnet-5',
        modeId: 'agent-full-access',
      },
    });
    // The cache write holds the host-acknowledged config, not the optimistic value.
    expect(cacheWrites).toHaveLength(1);
    expect(cacheWrites[0]?.config).toEqual(hostCalls[0]?.config);
  });

  it('skips the write when the mode id is unchanged', async () => {
    const row = acpRow({ modeId: 'agent' });
    const { deps, hostCalls } = fakeDeps(row);

    const result = await setConversationModeId(deps, 'conversation-1', 'agent');

    expect(result).toEqual({
      success: true,
      data: { projectId: 'project-1', taskId: 'task-1' },
    });
    expect(hostCalls).toHaveLength(0);
  });

  it('refuses the edit when the remote host is unreachable', async () => {
    const { deps, hostCalls } = fakeDeps({
      ...acpRow(),
      location: 'remote',
      sshConnectionId: 'conn-1',
    });
    deps.hostIsReachable = vi.fn(() => false);

    const result = await setConversationModeId(deps, 'conversation-1', 'agent');

    expect(result).toMatchObject({ success: false });
    expect(hostCalls).toHaveLength(0);
  });

  it('surfaces host rejection without a cache write', async () => {
    const { deps, cacheWrites, host } = fakeDeps(acpRow());
    host.updateConfig.mockResolvedValueOnce({
      success: false,
      error: { type: 'conversation-not-found', conversationId: 'conversation-1', message: 'gone' },
    } as never);

    const result = await setConversationModeId(deps, 'conversation-1', 'agent');

    expect(result).toMatchObject({ success: false, error: { type: 'host-rejected' } });
    expect(cacheWrites).toHaveLength(0);
  });
});

function acpRow(config: Partial<ConversationConfig> = {}): FakeRow {
  return {
    config: { version: '1', type: 'acp', ...config } as ConversationConfig,
    projectId: 'project-1',
    taskId: 'task-1',
    location: 'local',
    sshConnectionId: null,
  };
}

function fakeDeps(row: FakeRow | undefined) {
  const hostCalls: Array<{ conversationId: string; config: Record<string, unknown> }> = [];
  const cacheWrites: Array<Record<string, unknown>> = [];
  const host = {
    updateConfig: vi.fn(
      async (input: { conversationId: string; config: Record<string, unknown> }) => {
        hostCalls.push(input);
        return {
          success: true as const,
          data: { ...input, updatedAt: Date.now() },
        };
      }
    ),
  };
  const database = {
    select: () => ({
      from: () => ({
        where: () => ({
          limit: async () => (row ? [row] : []),
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
  return { deps, hostCalls, cacheWrites, host };
}
