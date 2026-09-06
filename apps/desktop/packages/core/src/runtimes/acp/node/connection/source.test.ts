import type { Client } from '@agentclientprotocol/sdk';
import { err, isErr, isOk } from '@emdash/shared';
import { acquireResourceAsResult } from '@emdash/shared/concurrency';
import { noopLogger } from '@emdash/shared/logger';
import { describe, expect, it, vi } from 'vitest';
import {
  FakeAcpAgent,
  FakeAcpProcessHost,
  testPluginHost,
} from '#runtimes/acp/node/acp-test-support';
import type { AgentPluginHost, IAcpBehavior } from '#services/agent-plugins/api/plugins';
import { createAcpConnectionSource, isAcpConnectionError, makeAcpConnectionKey } from './source';

function makeBehavior(agent: FakeAcpAgent): IAcpBehavior {
  return {
    buildSpawn: vi.fn().mockReturnValue({ command: '/fake/agent', args: [], env: {} }),
    connect: agent.behavior.connect,
  };
}

function connectionKey(cwd = '/tmp/workspace') {
  return {
    providerId: 'claude',
    cwd,
  };
}

function waitForTeardown(): Promise<void> {
  return new Promise((resolve) => setImmediate(resolve));
}

function sourceDeps(
  host: FakeAcpProcessHost,
  onClosed = vi.fn(),
  agent = new FakeAcpAgent(),
  agentHost = testPluginHost({ acpBehavior: makeBehavior(agent) })
) {
  return {
    host,
    agentHost,
    logger: noopLogger,
    buildClient: vi.fn(() => ({}) as Client),
    onClosed,
  };
}

describe('createAcpConnectionSource', () => {
  it('dedupes acquisitions by provider and cwd and refcounts release', async () => {
    const agent = new FakeAcpAgent();
    const host = new FakeAcpProcessHost();
    const source = createAcpConnectionSource(sourceDeps(host, vi.fn(), agent));
    const key = connectionKey();

    const first = await acquireResourceAsResult(source, key, isAcpConnectionError);
    const second = await acquireResourceAsResult(source, key, isAcpConnectionError);

    expect(isOk(first)).toBe(true);
    expect(isOk(second)).toBe(true);
    if (!isOk(first) || !isOk(second)) return;
    expect(host.allHandles).toHaveLength(1);

    await first.data.release();
    expect(host.lastHandle.kill).not.toHaveBeenCalled();
    expect(source.peek(key)).not.toBeUndefined();

    await second.data.release();
    expect(host.lastHandle.kill).toHaveBeenCalledWith('SIGTERM');
    await waitForTeardown();
    expect(source.peek(key)).toBeUndefined();
  });

  it('provisions separate working directories independently', async () => {
    const agent = new FakeAcpAgent();
    const host = new FakeAcpProcessHost();
    const source = createAcpConnectionSource(sourceDeps(host, vi.fn(), agent));

    await acquireResourceAsResult(source, connectionKey('/tmp/workspace-1'), isAcpConnectionError);
    await acquireResourceAsResult(source, connectionKey('/tmp/workspace-2'), isAcpConnectionError);

    expect(host.allHandles).toHaveLength(2);
  });

  it('forwards provider environment settings to spawn resolution', async () => {
    const host = new FakeAcpProcessHost();
    const deps = sourceDeps(host);
    const buildAcpSpawn = vi.spyOn(deps.agentHost, 'buildAcpSpawn');
    const source = createAcpConnectionSource(deps);
    const env = { PROVIDER_API_URL: 'https://provider.example.test' };

    await acquireResourceAsResult(source, { ...connectionKey(), env }, isAcpConnectionError);

    expect(buildAcpSpawn).toHaveBeenCalledWith('claude', {
      cwd: '/tmp/workspace',
      env,
    });
  });

  it('forwards process close and invalidates closed entries', async () => {
    const agent = new FakeAcpAgent();
    const host = new FakeAcpProcessHost();
    const onClosed = vi.fn();
    const source = createAcpConnectionSource(sourceDeps(host, onClosed, agent));
    const key = connectionKey();
    const routeKey = makeAcpConnectionKey('claude', '/tmp/workspace');

    await acquireResourceAsResult(source, key, isAcpConnectionError);
    host.lastHandle.emitExit(7);

    await vi.waitFor(() => expect(onClosed).toHaveBeenCalledWith(routeKey, 7));
    await source.invalidate(key);
    await waitForTeardown();
    expect(source.peek(key)).toBeUndefined();
  });

  it('disposes all active pooled processes', async () => {
    const agent = new FakeAcpAgent();
    const host = new FakeAcpProcessHost();
    const source = createAcpConnectionSource(sourceDeps(host, vi.fn(), agent));
    const key = connectionKey();

    const acquired = await acquireResourceAsResult(source, key, isAcpConnectionError);
    expect(isOk(acquired)).toBe(true);
    await source.dispose();

    expect(host.lastHandle.kill).toHaveBeenCalledWith('SIGTERM');
    expect(source.peek(key)).toBeUndefined();
  });

  it('returns spawn_failed when spawn resolution fails', async () => {
    const agent = new FakeAcpAgent();
    const host = new FakeAcpProcessHost();
    const agentHost = {
      resolveAcp: vi.fn(() => ({ behavior: makeBehavior(agent) })),
      buildAcpSpawn: vi
        .fn()
        .mockResolvedValue(
          err({ type: 'cli-not-found', providerId: 'claude', message: 'missing cli' })
        ),
    } as unknown as AgentPluginHost;
    const source = createAcpConnectionSource(sourceDeps(host, vi.fn(), agent, agentHost));
    const key = connectionKey();

    const result = await acquireResourceAsResult(source, key, isAcpConnectionError);

    expect(isErr(result)).toBe(true);
    if (!isErr(result)) return;
    expect(result.error.type).toBe('spawn_failed');
    expect(result.error.cause?.message).toBe('missing cli');
    expect(host.allHandles).toHaveLength(0);
  });

  it('returns initialize_failed without notifying close when initialize fails', async () => {
    const agent = new FakeAcpAgent();
    agent.initialize = vi.fn().mockRejectedValue(new Error('init failed'));
    const host = new FakeAcpProcessHost();
    const onClosed = vi.fn();
    const source = createAcpConnectionSource(sourceDeps(host, onClosed, agent));
    const key = connectionKey();

    const result = await acquireResourceAsResult(source, key, isAcpConnectionError);

    expect(isErr(result)).toBe(true);
    if (!isErr(result)) return;
    expect(result.error.type).toBe('initialize_failed');
    expect(host.lastHandle.kill).toHaveBeenCalledWith('SIGTERM');
    expect(source.peek(key)).toBeUndefined();
    expect(onClosed).not.toHaveBeenCalled();
  });

  it('shares a single failed in-flight initialization across concurrent acquires', async () => {
    const agent = new FakeAcpAgent();
    agent.initialize = vi.fn().mockRejectedValue(new Error('init failed'));
    const host = new FakeAcpProcessHost();
    const onClosed = vi.fn();
    const source = createAcpConnectionSource(sourceDeps(host, onClosed, agent));
    const key = connectionKey();

    const [first, second] = await Promise.all([
      acquireResourceAsResult(source, key, isAcpConnectionError),
      acquireResourceAsResult(source, key, isAcpConnectionError),
    ]);

    expect(isErr(first)).toBe(true);
    expect(isErr(second)).toBe(true);
    expect(host.allHandles).toHaveLength(1);
    expect(host.lastHandle.kill).toHaveBeenCalledWith('SIGTERM');
    expect(source.peek(key)).toBeUndefined();
    expect(onClosed).not.toHaveBeenCalled();
  });
});
