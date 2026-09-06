import {
  formatHostRef,
  hostRef,
  LOCAL_HOST_REF,
  type HostRef,
} from '@emdash/core/primitives/host/api';
import { acpApiContract, type SessionSummary } from '@emdash/core/runtimes/acp/api';
import { createAcpSessionsLiveHost } from '@emdash/core/runtimes/acp/node';
import { ok } from '@emdash/shared';
import { defineContract } from '@emdash/wire/rpc';
import { createTestWire } from '@emdash/wire/testing';
import type { WireWorkerState } from '@emdash/wire/worker';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AcpAgentStatusBridge } from './agent-status-bridge';

const sessionsContract = defineContract({ sessions: acpApiContract.sessions });

const mocks = vi.hoisted(() => ({
  applySignal: vi.fn(async () => {}),
  cacheSignal: vi.fn(async () => {}),
  loadActiveIds: vi.fn(async (_host: HostRef) => [] as string[]),
  resetToIdle: vi.fn(async () => {}),
}));

vi.mock('@main/core/agent-status/agent-status-service', () => ({
  agentStatusService: {
    applySignal: mocks.applySignal,
    cacheSignal: mocks.cacheSignal,
    resetToIdle: mocks.resetToIdle,
  },
}));
vi.mock('@main/lib/logger', () => ({ log: { warn: vi.fn() } }));

describe('AcpAgentStatusBridge', () => {
  beforeEach(() => {
    for (const mock of Object.values(mocks)) mock.mockClear();
  });

  it('attaches per host, caches bootstrap state, and sweeps only that host', async () => {
    const remote = hostRef('remote', 'ssh-1');
    const localRuntime = createRuntime({ local: summary('local', 'working') });
    const remoteRuntime = createRuntime({ remote: summary('remote', 'working') });
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
      expect.objectContaining({ conversationId: 'remote', type: 'start' })
    );
    expect(mocks.applySignal).not.toHaveBeenCalled();
    expect(mocks.resetToIdle).toHaveBeenCalledWith({ conversationId: 'stale-remote' });
    expect(mocks.resetToIdle).not.toHaveBeenCalledWith({ conversationId: 'stale-local' });

    await fixture.bridge.attachHost(LOCAL_HOST_REF);
    expect(mocks.cacheSignal).toHaveBeenCalledWith(
      expect.objectContaining({ conversationId: 'local', type: 'start' })
    );
    expect(mocks.resetToIdle).toHaveBeenCalledWith({ conversationId: 'stale-local' });

    fixture.bridge.detachHost(remote);
    mocks.applySignal.mockClear();
    remoteRuntime.host.model.states.list.set({ remote: summary('remote', 'ready') });
    await Promise.resolve();
    expect(mocks.applySignal).not.toHaveBeenCalled();
    await fixture.dispose();
  });

  it('resets only local rows on terminal worker failure and reattaches on recovery', async () => {
    const remote = hostRef('remote', 'ssh-1');
    const localRuntime = createRuntime({ local: summary('local', 'working') });
    const remoteRuntime = createRuntime({ remote: summary('remote', 'working') });
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
    mocks.loadActiveIds.mockClear();
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
    return ok({ acp: runtime.wire.client });
  });
  const bridge = new AcpAgentStatusBridge();
  bridge.initialize(() => () => {}, {
    runtimes: { client } as never,
    onLocalWorkerStateChanged(listener) {
      workerStateListener = listener;
      return () => {
        workerStateListener = undefined;
      };
    },
    loadActiveConversationIds: mocks.loadActiveIds,
    renameConversation: vi.fn(async () => {}),
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

function createRuntime(summaries: Record<string, SessionSummary>) {
  const host = createAcpSessionsLiveHost();
  host.model.states.list.set(summaries);
  const wire = createTestWire(sessionsContract, { sessions: host });
  return { host, wire };
}

function summary(conversationId: string, lifecycle: SessionSummary['lifecycle']): SessionSummary {
  return {
    conversationId,
    providerId: 'codex',
    lifecycle,
    isGenerating: lifecycle === 'working',
    lastStopReason: lifecycle === 'ready' ? 'end_turn' : null,
    lastTurnErrored: false,
    pendingPermissionCount: 0,
    backgroundAgentCount: 0,
    queuedPromptCount: 0,
    title: null,
    updatedAt: 1,
  };
}
