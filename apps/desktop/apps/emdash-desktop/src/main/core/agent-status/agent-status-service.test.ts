import { installAppDbTestInstance } from '@tooling/vitest/app-db-test-instance';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentStatusSignal } from '@core/primitives/agents/api';
import {
  AgentStatusService,
  setAgentStatusConversationEventPublisher,
} from './agent-status-service';

type TestConversationRow = {
  projectId: string;
  taskId: string;
  providerId: string | null;
  agentStatusSeen: number | null;
};

const mocks = vi.hoisted(() => ({
  blockUpdates: false,
  emit: vi.fn(),
  select: vi.fn(),
  selectRows: [] as Array<TestConversationRow | null>,
  update: vi.fn(),
  updateCalls: [] as Array<Record<string, unknown>>,
  updateRows: [] as Array<TestConversationRow | null>,
  updateResolvers: [] as Array<() => void>,
}));

mocks.select.mockImplementation(() => ({
  from: () => ({
    where: () => ({
      limit: async () => {
        const row = mocks.selectRows.shift();
        return row ? [row] : [];
      },
    }),
  }),
}));
mocks.update.mockImplementation(() => ({
  set: (values: Record<string, unknown>) => {
    mocks.updateCalls.push(values);
    return {
      where: () => ({
        returning: async () => {
          const row = mocks.updateRows.shift();
          if (mocks.blockUpdates) {
            await new Promise<void>((resolve) => mocks.updateResolvers.push(resolve));
          }
          return row ? [row] : [];
        },
      }),
    };
  },
}));
installAppDbTestInstance(() => ({ select: mocks.select, update: mocks.update }) as never);

vi.mock('@main/lib/logger', () => ({ log: { error: vi.fn() } }));

function row(overrides: Partial<TestConversationRow> = {}): TestConversationRow {
  return {
    projectId: 'project-1',
    taskId: 'task-1',
    providerId: 'codex',
    agentStatusSeen: 1,
    ...overrides,
  };
}

function signal(
  type: AgentStatusSignal['type'],
  overrides: Partial<AgentStatusSignal> = {}
): AgentStatusSignal {
  return {
    type,
    conversationId: 'conversation-1',
    timestamp: 1,
    payload: {},
    ...overrides,
  };
}

function resolveUpdate(index: number): void {
  const resolve = mocks.updateResolvers[index];
  if (!resolve) throw new Error(`Missing update resolver at index ${index}`);
  resolve();
}

describe('AgentStatusService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAgentStatusConversationEventPublisher((event) => mocks.emit(undefined, event));
    mocks.blockUpdates = false;
    mocks.selectRows.length = 0;
    mocks.updateCalls.length = 0;
    mocks.updateRows.length = 0;
    mocks.updateResolvers.length = 0;
  });

  it('serializes each conversation while allowing other conversations to progress', async () => {
    const service = new AgentStatusService();
    mocks.blockUpdates = true;
    mocks.updateRows.push(row(), row({ projectId: 'project-2', taskId: 'task-2' }), row());

    const first = service.applySignal(signal('start'));
    const second = service.applySignal(signal('stop', { timestamp: 2 }));
    const interleaved = service.applySignal(
      signal('error', { conversationId: 'conversation-2', timestamp: 3 })
    );

    await vi.waitFor(() => expect(mocks.updateCalls).toHaveLength(2));
    expect(mocks.updateCalls.map((call) => call.agentStatus)).toEqual(['working', 'error']);

    resolveUpdate(1);
    await interleaved;
    expect(mocks.updateCalls).toHaveLength(2);

    resolveUpdate(0);
    await vi.waitFor(() => expect(mocks.updateCalls).toHaveLength(3));
    expect(mocks.updateCalls[2]?.agentStatus).toBe('completed');
    resolveUpdate(2);

    await Promise.all([first, second]);
  });

  it('drops a signal when its conversation no longer exists', async () => {
    const service = new AgentStatusService();
    mocks.updateRows.push(null);

    await service.applySignal(signal('start'));

    expect(mocks.update).toHaveBeenCalledTimes(1);
    expect(mocks.emit).not.toHaveBeenCalled();
  });

  it('enriches delivered signals and falls back to the stored provider', async () => {
    const service = new AgentStatusService();
    const handler = vi.fn();
    service.on('agent:event', handler);
    mocks.updateRows.push(row({ providerId: 'claude' }));

    await service.applySignal(signal('start'));

    expect(handler).toHaveBeenCalledWith(
      expect.objectContaining({
        conversationId: 'conversation-1',
        projectId: 'project-1',
        taskId: 'task-1',
        providerId: 'claude',
      })
    );
  });

  it('delivers hooks only after the status write completes', async () => {
    const service = new AgentStatusService();
    const handler = vi.fn();
    service.on('agent:event', handler);
    mocks.blockUpdates = true;
    mocks.updateRows.push(row());

    const pending = service.applySignal(signal('start'));
    await vi.waitFor(() => expect(mocks.updateCalls).toHaveLength(1));

    expect(handler).not.toHaveBeenCalled();

    resolveUpdate(0);
    await pending;
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it('caches snapshots without delivering hooks and preserves the seen flag', async () => {
    const service = new AgentStatusService();
    const handler = vi.fn();
    service.on('agent:event', handler);
    mocks.updateRows.push(row({ agentStatusSeen: 1 }));

    await service.cacheSignal(signal('stop'));

    expect(handler).not.toHaveBeenCalled();
    expect(mocks.updateCalls).toEqual([{ agentStatus: 'completed' }]);
    expect(mocks.emit).toHaveBeenCalledWith(
      undefined,
      expect.objectContaining({ status: 'completed', seen: true })
    );
  });

  it('waits for queued writes before disposing', async () => {
    const service = new AgentStatusService();
    mocks.blockUpdates = true;
    mocks.updateRows.push(row());

    const pending = service.applySignal(signal('start'));
    await vi.waitFor(() => expect(mocks.updateCalls).toHaveLength(1));

    let disposed = false;
    const disposal = Promise.resolve(service.dispose()).then(() => {
      disposed = true;
    });
    await Promise.resolve();
    expect(disposed).toBe(false);

    resolveUpdate(0);
    await Promise.all([pending, disposal]);
    expect(disposed).toBe(true);
  });
});
