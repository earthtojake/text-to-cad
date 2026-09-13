import { createConnection, type Socket } from 'node:net';
import type { WireTransport } from '@emdash/wire/rpc';
import type { LocalWorkspaceServerTarget } from '../../../api/targets';
import { ownedStreamTransport } from './owned-stream-transport';

export type OpenLocalWorkspaceServerTransportOptions = {
  connectTimeoutMs?: number;
};

const DEFAULT_CONNECT_TIMEOUT_MS = 5_000;

export async function openLocalWorkspaceServerTransport(
  target: LocalWorkspaceServerTarget,
  options: OpenLocalWorkspaceServerTransportOptions = {}
): Promise<WireTransport> {
  const socket = await connectLocalSocket(
    target.socketPath,
    options.connectTimeoutMs ?? DEFAULT_CONNECT_TIMEOUT_MS
  );
  return ownedStreamTransport(socket);
}

function connectLocalSocket(socketPath: string, timeoutMs: number): Promise<Socket> {
  return new Promise((resolve, reject) => {
    const socket = createConnection(socketPath);
    let settled = false;
    const timeout = setTimeout(() => {
      finish(new Error(`Timed out connecting to workspace server socket: ${socketPath}`));
    }, timeoutMs);
    timeout.unref?.();

    const cleanup = (): void => {
      clearTimeout(timeout);
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
        return;
      }
      resolve(socket);
    };
    const onConnect = (): void => finish();
    const onError = (error: Error): void => finish(error);

    socket.once('connect', onConnect);
    socket.once('error', onError);
  });
}
