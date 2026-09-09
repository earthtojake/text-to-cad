import { Readable, Writable } from 'node:stream';
import { ClientSideConnection, ndJsonStream } from '@agentclientprotocol/sdk';
import type {
  AcpAgentApi,
  AcpClientFactory,
  AcpProcessIo,
  AcpSpawnContext,
  AcpSpawnResult,
  IAcpBehavior,
} from '@emdash/core/services/agent-plugins/api/plugins';

type NativeAcpSpawnResult = Omit<AcpSpawnResult, 'command'> & {
  command?: string;
};

export function connectStdioAcp(io: AcpProcessIo, toClient: AcpClientFactory): AcpAgentApi {
  const stream = ndJsonStream(
    Writable.toWeb(io.stdin) as WritableStream<Uint8Array>,
    Readable.toWeb(io.stdout) as unknown as ReadableStream<Uint8Array>
  );
  return new ClientSideConnection((agent) => toClient(agent as never), stream);
}

export function createNativeAcpBehavior(
  buildSpawn: (ctx: AcpSpawnContext) => NativeAcpSpawnResult
): IAcpBehavior {
  return {
    buildSpawn: (ctx) => {
      const spawn = buildSpawn(ctx);
      return {
        command: spawn.command ?? ctx.cli,
        args: spawn.args,
        env: spawn.env,
      };
    },
    connect: connectStdioAcp,
  };
}
