import { isErr, isOk } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { describe, expect, it, vi } from 'vitest';
import { FakeAcpAgent, FakeAcpProcessHost } from '#runtimes/acp/node/acp-test-support';
import type { AgentHostAcpSpawn, IAcpBehavior } from '#services/agent-plugins/api/plugins';
import { createAcpAgentConnection } from './acp-agent-connection';

function makeBehavior(agent: FakeAcpAgent): IAcpBehavior {
  return {
    buildSpawn: vi.fn().mockReturnValue({ command: '/fake/agent', args: ['--stdio'], env: {} }),
    connect: agent.behavior.connect,
  };
}

function makeCtx(agent?: FakeAcpAgent) {
  const fakeAgent = agent ?? new FakeAcpAgent();
  const host = new FakeAcpProcessHost();
  const behavior = makeBehavior(fakeAgent);
  const scope = createScope({ label: 'test-connection' });
  return { host, fakeAgent, behavior, scope };
}

function spawnSpec(overrides: Partial<AgentHostAcpSpawn> = {}): AgentHostAcpSpawn {
  return {
    command: '/fake/agent',
    args: ['--stdio'],
    env: {},
    cwd: '/tmp/workspace',
    ...overrides,
  };
}

const connArgs = (scope: Scope, onClosed = vi.fn()) => ({
  providerId: 'test-provider',
  spawn: spawnSpec(),
  scope,
  buildClient: vi.fn(),
  onClosed,
});

describe('createAcpAgentConnection()', () => {
  it('spawns the resolved spec, initializes, and returns a ready connection', async () => {
    const { host, behavior, scope } = makeCtx();
    const result = await createAcpAgentConnection({ host, behavior }, connArgs(scope));

    expect(isOk(result)).toBe(true);
    if (!isOk(result)) return;
    expect(host.allHandles).toHaveLength(1);
    expect(result.data.supportsLoadSession).toBe(true);
    expect(result.data.mcpCapabilities).toEqual({ http: false, sse: false });
  });

  it('returns err(spawn_failed) when spawn throws', async () => {
    const { host, behavior, scope } = makeCtx();
    host.spawn = vi.fn().mockRejectedValue(new Error('spawn-error'));
    const result = await createAcpAgentConnection({ host, behavior }, connArgs(scope));

    expect(isErr(result)).toBe(true);
    if (!isErr(result)) return;
    expect(result.error.type).toBe('spawn_failed');
    expect(result.error.cause?.message).toBe('spawn-error');
  });

  it('calls onClosed with the exit code when a ready process exits', async () => {
    const { host, behavior, scope } = makeCtx();
    const onClosed = vi.fn();
    await createAcpAgentConnection({ host, behavior }, connArgs(scope, onClosed));

    host.lastHandle.emitExit(7);

    await vi.waitFor(() => expect(onClosed).toHaveBeenCalledOnce());
    expect(onClosed).toHaveBeenCalledWith(7);
  });

  it('derives supportsLoadSession from agent capabilities', async () => {
    for (const loadSession of [true, false]) {
      const agent = new FakeAcpAgent();
      agent.initialize = vi.fn().mockResolvedValue({
        protocolVersion: 1,
        agentCapabilities: { loadSession },
      });
      const { host, behavior, scope } = makeCtx(agent);
      const result = await createAcpAgentConnection({ host, behavior }, connArgs(scope));

      expect(isOk(result)).toBe(true);
      if (!isOk(result)) return;
      expect(result.data.supportsLoadSession).toBe(loadSession);
    }
  });

  it('derives MCP capabilities from agent capabilities', async () => {
    const agent = new FakeAcpAgent();
    agent.initialize = vi.fn().mockResolvedValue({
      protocolVersion: 1,
      agentCapabilities: { mcpCapabilities: { http: true, sse: true } },
    });
    const { host, behavior, scope } = makeCtx(agent);

    const result = await createAcpAgentConnection({ host, behavior }, connArgs(scope));

    expect(isOk(result)).toBe(true);
    if (!isOk(result)) return;
    expect(result.data.mcpCapabilities).toEqual({ http: true, sse: true });
  });

  it('returns initialize_failed, kills the partial process, and does not call onClosed', async () => {
    const agent = new FakeAcpAgent();
    agent.initialize = vi.fn().mockRejectedValue(new Error('init-failed'));
    const { host, behavior, scope } = makeCtx(agent);
    const onClosed = vi.fn();
    const result = await createAcpAgentConnection({ host, behavior }, connArgs(scope, onClosed));

    expect(isErr(result)).toBe(true);
    if (!isErr(result)) return;
    expect(result.error.type).toBe('initialize_failed');
    expect(host.lastHandle.kill).toHaveBeenCalledWith('SIGTERM');
    expect(onClosed).not.toHaveBeenCalled();
  });

  it('returns initialize_failed when the process exits during initialize', async () => {
    const agent = new FakeAcpAgent();
    agent.initialize = vi.fn(() => new Promise(() => {}));
    const { host, behavior, scope } = makeCtx(agent);
    const onClosed = vi.fn();
    const pending = createAcpAgentConnection({ host, behavior }, connArgs(scope, onClosed));

    await vi.waitFor(() => expect(host.allHandles).toHaveLength(1));
    host.lastHandle.emitExit(9);
    const result = await pending;

    expect(isErr(result)).toBe(true);
    if (!isErr(result)) return;
    expect(result.error.type).toBe('initialize_failed');
    expect(onClosed).not.toHaveBeenCalled();
  });

  it('notifies ready close handlers at most once', async () => {
    const { host, behavior, scope } = makeCtx();
    const onClosed = vi.fn();
    await createAcpAgentConnection({ host, behavior }, connArgs(scope, onClosed));

    host.lastHandle.emitError(new Error('boom'));
    host.lastHandle.emitExit(1);

    await vi.waitFor(() => expect(onClosed).toHaveBeenCalledOnce());
    expect(onClosed).toHaveBeenCalledWith(null);
  });

  it('suppresses onClosed during intentional scope disposal', async () => {
    const { host, behavior, scope } = makeCtx();
    const onClosed = vi.fn();
    await createAcpAgentConnection({ host, behavior }, connArgs(scope, onClosed));

    await scope.dispose();
    host.lastHandle.emitExit(0);

    expect(host.lastHandle.kill).toHaveBeenCalledWith('SIGTERM');
    expect(onClosed).not.toHaveBeenCalled();
  });

  it('advertises terminal capability based on host.spawnTerminal presence', async () => {
    const withTerminal = new FakeAcpProcessHost();
    const withoutTerminal = new FakeAcpProcessHost();
    (withoutTerminal as { spawnTerminal?: unknown }).spawnTerminal = undefined;

    for (const [host, expected] of [
      [withTerminal, true],
      [withoutTerminal, false],
    ] as const) {
      const agent = new FakeAcpAgent();
      const behavior = makeBehavior(agent);
      await createAcpAgentConnection(
        { host, behavior },
        connArgs(createScope({ label: 'terminal-capability' }))
      );
      const initCall = agent.initialize.mock.calls[0]?.[0];
      expect(initCall?.clientCapabilities?.terminal).toBe(expected);
    }
  });

  it('normalize applies behavior.enrich when present', async () => {
    const agent = new FakeAcpAgent();
    const host = new FakeAcpProcessHost();
    const enrichSpy = vi.fn().mockImplementation((u) => ({ ...u, enriched: true }));
    const behavior: IAcpBehavior = {
      buildSpawn: vi.fn().mockReturnValue({ command: '/fake/agent', args: [], env: {} }),
      connect: agent.behavior.connect,
      enrich: enrichSpy,
    };
    const result = await createAcpAgentConnection(
      { host, behavior },
      connArgs(createScope({ label: 'normalize' }))
    );

    expect(isOk(result)).toBe(true);
    if (!isOk(result)) return;
    const raw = { sessionUpdate: 'message_delta', delta: { type: 'text', text: 'hi' } } as never;
    const out = result.data.normalize(raw);
    expect(enrichSpy).toHaveBeenCalledTimes(1);
    expect((out as { enriched?: boolean }).enriched).toBe(true);
  });
});
