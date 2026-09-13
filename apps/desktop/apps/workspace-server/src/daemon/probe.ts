import { createConnection, type Socket } from 'node:net';
import { workspaceWireContract } from '@emdash/core/workspace-server';
import { err, ok, type Result } from '@emdash/shared';
import { runWithTimeout } from '@emdash/shared/scheduling';
import { client as createClient, connect, streamTransport } from '@emdash/wire/rpc';

export type DaemonHealth = Awaited<
  ReturnType<ReturnType<typeof createClient<typeof workspaceWireContract>>['health']>
>;

export type DaemonProbeError = {
  type: 'not-running' | 'unhealthy';
  message: string;
};

export async function probeDaemon(
  socketPath: string,
  options: { timeoutMs?: number } = {}
): Promise<Result<DaemonHealth, DaemonProbeError>> {
  const timeoutMs = options.timeoutMs ?? 1_000;
  let socket: Socket | undefined;
  try {
    socket = await connectToSocket(socketPath, timeoutMs);
    const transport = streamTransport(socket, socket);
    const wireClient = createClient(workspaceWireContract, connect(transport));
    const health = await runWithTimeout((signal) => wireClient.health(undefined, { signal }), {
      timeoutMs,
    });
    transport.close?.();
    socket.destroy();
    return ok(health);
  } catch (error) {
    socket?.destroy();
    return err({
      type: isConnectionError(error) ? 'not-running' : 'unhealthy',
      message: error instanceof Error ? error.message : String(error),
    });
  }
}

function connectToSocket(socketPath: string, timeoutMs: number): Promise<Socket> {
  return new Promise((resolve, reject) => {
    const socket = createConnection(socketPath);
    let settled = false;
    const timer = setTimeout(() => {
      finish(new Error(`Timed out connecting to workspace daemon socket: ${socketPath}`));
    }, timeoutMs);

    const cleanup = (): void => {
      clearTimeout(timer);
      socket.off('connect', onConnect);
      socket.off('error', onError);
    };
    const finish = (error?: Error): void => {
      if (settled) return;
      settled = true;
      cleanup();
      if (error) {
        socket.destroy();
        reject(error);
      } else {
        resolve(socket);
      }
    };
    const onConnect = (): void => finish();
    const onError = (error: Error): void => finish(error);

    socket.once('connect', onConnect);
    socket.once('error', onError);
  });
}

function isConnectionError(error: unknown): boolean {
  return (
    error instanceof Error &&
    'code' in error &&
    ['ENOENT', 'ECONNREFUSED', 'ECONNRESET', 'ETIMEDOUT'].includes(
      String((error as NodeJS.ErrnoException).code)
    )
  );
}
