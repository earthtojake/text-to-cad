import { hostRef } from '@emdash/core/primitives/host/api';
import { ok } from '@emdash/shared';
import type { LiveSource } from '@emdash/wire/rpc';
import { encodeTopic } from '@emdash/wire/rpc';
import { describe, expect, it, vi } from 'vitest';
import { mcpContract } from '../api';
import { createMcpWireController } from './wire-controller';

const remoteHost = hostRef('remote', 'ssh-2');

describe('createMcpWireController', () => {
  it('forwards MCP procedures to the selected host', async () => {
    const saveMcpServer = vi.fn(async () => ok(undefined));
    const client = vi.fn(async () => ok({ agentConfig: { saveMcpServer } }));
    const controller = createMcpWireController({ runtimes: { client } as never });
    const server = {
      name: 'context7',
      transport: 'stdio' as const,
      command: 'npx',
      args: ['-y', '@upstash/context7-mcp'],
      env: {},
      providers: [],
    };

    await expect(controller.call('saveServer', { host: remoteHost, server })).resolves.toEqual(
      ok(undefined)
    );

    expect(client).toHaveBeenCalledWith(remoteHost);
    expect(saveMcpServer).toHaveBeenCalledWith({ server }, {});
  });

  it('resolves the host for the MCP live model', async () => {
    const source = liveSource([]);
    const state = vi.fn(() => ({ asLiveSource: () => source }));
    const controller = createMcpWireController({
      runtimes: {
        client: async () => ok({ agentConfig: { mcpServers: { state } } }),
      } as never,
    });
    const topic = encodeTopic(mcpContract.servers.states.list.id, { host: remoteHost });

    const lease = controller.acquireLive(topic);
    await expect(lease?.ready()).resolves.toBe(source);
    expect(state).toHaveBeenCalledWith(undefined, 'list');

    await lease?.release();
  });
});

function liveSource(data: unknown): LiveSource {
  return {
    snapshot: async () => ({ generation: 1, sequence: 0, timestamp: 0, data }),
    subscribe: () => () => {},
  };
}
