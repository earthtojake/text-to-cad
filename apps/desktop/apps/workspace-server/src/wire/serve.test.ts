import { mkdtemp, writeFile } from 'node:fs/promises';
import { createConnection, type Socket } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PassThrough } from 'node:stream';
import { PROTOCOL_VERSION, workspaceWireContract } from '@emdash/core/workspace-server';
import { client as createClient, connect, streamTransport } from '@emdash/wire/rpc';
import { afterEach, describe, expect, it } from 'vitest';
import { createTestWorkspaceWireController } from '../testing/controller';
import { serveSocket, type SocketServeHandle } from './serve-socket';
import { serveStdio } from './serve-stdio';

const handles: SocketServeHandle[] = [];
const disposers: Array<() => void> = [];

afterEach(async () => {
  for (const dispose of disposers.splice(0)) dispose();
  for (const handle of handles.splice(0)) await handle.dispose();
});

describe('serveSocket', () => {
  it('serves the wire handshake over a Unix socket', async () => {
    const handle = await serveTestSocket();
    const connection = await connectToSocket(handle.socketPath);

    const result = await connection.client.initialize(initializeInput());

    expect(result).toMatchObject({
      success: true,
      data: { protocolVersion: PROTOCOL_VERSION },
    });
    connection.dispose();
  });

  it('serves multiple concurrent clients through one controller', async () => {
    const handle = await serveTestSocket();
    const first = await connectToSocket(handle.socketPath);
    const second = await connectToSocket(handle.socketPath);

    await expect(first.client.health(undefined)).resolves.toMatchObject({
      status: 'ok',
      protocolVersion: PROTOCOL_VERSION,
    });
    await expect(second.client.health(undefined)).resolves.toMatchObject({
      status: 'ok',
      protocolVersion: PROTOCOL_VERSION,
    });

    first.dispose();
    second.dispose();
  });

  it('replaces a stale socket file before listening', async () => {
    const socketPath = await tempSocketPath();
    await writeFile(socketPath, '');

    const handle = await serveSocket(createTestWorkspaceWireController(), { socketPath });
    handles.push(handle);
    const connection = await connectToSocket(handle.socketPath);

    await expect(connection.client.health(undefined)).resolves.toMatchObject({ status: 'ok' });
    connection.dispose();
  });

  it('unlinks the socket file on dispose', async () => {
    const handle = await serveTestSocket();
    const socketPath = handle.socketPath;

    await handle.dispose();
    handles.splice(handles.indexOf(handle), 1);

    await expect(connectToRawSocket(socketPath)).rejects.toThrow();
  });
});

describe('serveStdio', () => {
  it('serves the wire handshake over stdio streams', async () => {
    const clientToServer = new PassThrough();
    const serverToClient = new PassThrough();
    const disposeServer = serveStdio(createTestWorkspaceWireController(), {
      input: clientToServer,
      output: serverToClient,
    });
    disposers.push(disposeServer);

    const transport = streamTransport(serverToClient, clientToServer);
    disposers.push(() => transport.close?.());
    const wireClient = createClient(workspaceWireContract, connect(transport));

    const result = await wireClient.initialize(initializeInput());

    expect(result).toMatchObject({
      success: true,
      data: { protocolVersion: PROTOCOL_VERSION },
    });
  });
});

async function serveTestSocket(): Promise<SocketServeHandle> {
  const handle = await serveSocket(createTestWorkspaceWireController(), {
    socketPath: await tempSocketPath(),
  });
  handles.push(handle);
  return handle;
}

function initializeInput() {
  return {
    protocolVersion: PROTOCOL_VERSION,
    client: { id: 'test-client', appVersion: 'test' },
  };
}

async function tempSocketPath(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), 'emdash-workspace-wire-'));
  return join(dir, 'workspace.sock');
}

async function connectToSocket(socketPath: string) {
  const socket = await connectToRawSocket(socketPath);
  const transport = streamTransport(socket, socket);
  return {
    client: createClient(workspaceWireContract, connect(transport)),
    dispose() {
      transport.close?.();
      socket.destroy();
    },
  };
}

function connectToRawSocket(socketPath: string): Promise<Socket> {
  return new Promise((resolve, reject) => {
    const socket = createConnection(socketPath);
    const cleanup = (): void => {
      socket.off('connect', onConnect);
      socket.off('error', onError);
    };
    const onConnect = (): void => {
      cleanup();
      resolve(socket);
    };
    const onError = (error: Error): void => {
      cleanup();
      socket.destroy();
      reject(error);
    };
    socket.once('connect', onConnect);
    socket.once('error', onError);
  });
}
