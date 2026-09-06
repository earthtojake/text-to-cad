import {
  formatHostRef,
  hostRef,
  LOCAL_HOST_REF,
  type HostRef,
} from '@emdash/core/primitives/host/api';
import { tuiAgentsContract, type TuiAgentState } from '@emdash/core/runtimes/tui-agents/api';
import {
  createTuiAgentStatesLiveModel,
  createTuiSessionsLiveModel,
} from '@emdash/core/runtimes/tui-agents/node';
import { ok } from '@emdash/shared';
import { defineContract } from '@emdash/wire/rpc';
import { createTestWire } from '@emdash/wire/testing';
import type { WireWorkerState } from '@emdash/wire/worker';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TuiAgentStatusBridge } from './tui-agent-status-bridge';

const sessionsContract = defineContract({
  agentStates: tuiAgentsContract.agentStates,
  sessions: tuiAgentsContract.sessions,
});

const mocks = vi.hoisted(() => ({
  applySignal: vi.fn(async () => {}),
  cacheSignal: vi.fn(async () => {}),
  loadActiveIds: vi.fn(async (_host: HostRef) => [] as string[]),
  resetToIdle: vi.fn(async () => {}),
}));

vi.mock('./agent-status-service', () => ({
  agentStatusService: {
    applySignal: mocks.applySignal,
    cacheSignal: mocks.cacheSignal,
    resetToIdle: mocks.resetToIdle,
  },
}));
vi.mock('@main/lib/logger', () => ({ log: { warn: vi.fn() } }));

describe('TuiAgentStatusBridge', () => {
  beforeEach(() => {
    for (const mock of Object.values(mocks)) mock.mockClear();
  });

  it('attaches per host, caches bootstrap state, and drops detached host state', async () => {
    const remote = hostRef('remote', 'ssh-1');
    const localRuntime = createRuntime({ local: state('local', 'working') });
    const remoteRuntime = createRuntime({ remote: state('remote', 'awaiting-input') });
    const fixture = createBridge(
      new Map([
        [formatHostRef(LOCAL_HOST_REF), localRuntime],
        [formatHostRef(remote), remoteRuntime],
      ])
    );
    mocks.loadActiveIds.mockImplementation(async (host: HostRef) =>
      host.type === 'remote' ? ['remote', 'stale-remote'] : ['local', 'stale-local']
    );

    await fixture.bridge.attachHost(remote);

    expect(mocks.cacheSignal).toHaveBeenCalledWith(
      expect.objectContaining({ conversationId: 'remote', type: 'notification' })
    );
    expect(mocks.applySignal).not.toHaveBeenCalled();
    expect(mocks.resetToIdle).toHaveBeenCalledWith({ conversationId: 'stale-remote' });
    expect(mocks.resetToIdle).not.toHaveBeenCalledWith({ conversationId: 'stale-local' });

    fixture.bridge.detachHost(remote);
    remoteRuntime.agentStates.model.states.list.set({ remote: state('remote', 'completed') });
    await Promise.resolve();
    expect(mocks.applySignal).not.toHaveBeenCalled();
    await fixture.dispose();
  });

  it('resets local rows after a terminal worker failure without touching remote rows', async () => {
    const remote = hostRef('remote', 'ssh-1');
    const localRuntime = createRuntime({ local: state('local', 'working') });
    const remoteRuntime = createRuntime({ remote: state('remote', 'working') });
    const fixture = createBridge(
      new Map([
        [formatHostRef(LOCAL_HOST_REF), localRuntime],
        [formatHostRef(remote), remoteRuntime],
      ])
    );
    mocks.loadActiveIds.mockResolvedValue([]);
    await Promise.all([
      fixture.bridge.attachHost(LOCAL_HOST_REF),
      fixture.bridge.attachHost(remote),
    ]);
    mocks.loadActiveIds.mockImplementation(async (host: HostRef) =>
      host.type === 'local' ? ['local-active'] : ['remote-active']
    );
    mocks.resetToIdle.mockClear();
    const callsBeforeRecovery = fixture.client.mock.calls.length;

    fixture.emitWorkerState({ kind: 'failed', attempts: 1 });
    await vi.waitFor(() =>
      expect(mocks.resetToIdle).toHaveBeenCalledWith({ conversationId: 'local-active' })
    );
    expect(mocks.resetToIdle).not.toHaveBeenCalledWith({ conversationId: 'remote-active' });

    mocks.loadActiveIds.mockResolvedValue([]);
    fixture.emitWorkerState({ kind: 'ready', generation: 2, attempt: 0 });
    await vi.waitFor(() =>
      expect(fixture.client.mock.calls.length).toBeGreaterThan(callsBeforeRecovery)
    );
    expect(fixture.client).toHaveBeenLastCalledWith(LOCAL_HOST_REF);
    await fixture.dispose();
  });
});

function createBridge(runtimes: Map<string, ReturnType<typeof createRuntime>>) {
  let workerStateListener: ((state: WireWorkerState) => void) | undefined;
  const client = vi.fn(async (host: HostRef) => {
    const runtime = runtimes.get(formatHostRef(host));
    if (!runtime) throw new Error(`Missing runtime for ${formatHostRef(host)}`);
    return ok({ tuiAgents: runtime.wire.client });
  });
  const bridge = new TuiAgentStatusBridge();
  bridge.initialize({
    runtimes: { client } as never,
    onLocalWorkerStateChanged(listener) {
      workerStateListener = listener;
      return () => {
        workerStateListener = undefined;
      };
    },
    loadActiveConversationIds: mocks.loadActiveIds,
  });
  return {
    bridge,
    client,
    emitWorkerState: (state: WireWorkerState) => workerStateListener?.(state),
    async dispose() {
      bridge.dispose();
      await Promise.all([...runtimes.values()].map((runtime) => runtime.wire.dispose()));
    },
  };
}

function createRuntime(states: Record<string, TuiAgentState>) {
  const agentStates = createTuiAgentStatesLiveModel();
  const sessions = createTuiSessionsLiveModel();
  agentStates.model.states.list.set(states);
  const wire = createTestWire(sessionsContract, { agentStates, sessions });
  return { agentStates, sessions, wire };
}

function state(conversationId: string, status: TuiAgentState['status']): TuiAgentState {
  return {
    conversationId,
    providerId: 'codex',
    status,
    notificationType: status === 'awaiting-input' ? 'permission_prompt' : undefined,
    updatedAt: 1,
  };
}
