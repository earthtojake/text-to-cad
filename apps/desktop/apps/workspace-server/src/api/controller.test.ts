import { mkdtemp, rm } from 'node:fs/promises';
import net from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PassThrough } from 'node:stream';
import { parseAbsolute } from '@emdash/core/primitives/path/api';
import type { TerminalShellResolver } from '@emdash/core/primitives/terminal-shell/api';
import type { AcpApiContract } from '@emdash/core/runtimes/acp/api';
import { filesContract } from '@emdash/core/runtimes/files/api';
import { createFilesController, FilesRuntime } from '@emdash/core/runtimes/files/node';
import { gitContract } from '@emdash/core/runtimes/git/api';
import { createGitController, GitRuntime } from '@emdash/core/runtimes/git/node';
import { terminalsContract } from '@emdash/core/runtimes/terminals/api';
import { createTerminalsController, TerminalsRuntime } from '@emdash/core/runtimes/terminals/node';
import type { IWatchService } from '@emdash/core/services/fs-watch/api';
import type { PtySpawner } from '@emdash/core/services/pty/api';
import { PROTOCOL_VERSION, workspaceWireContract } from '@emdash/core/workspace-server';
import { ok } from '@emdash/shared';
import { client as createClient, connect, serve, streamTransport } from '@emdash/wire/rpc';
import type { ContractClient } from '@emdash/wire/rpc';
import { createTestWire } from '@emdash/wire/testing';
import { describe, expect, it, vi } from 'vitest';
import { createTestWorkspaceWireController } from '../testing/controller';

describe('createWorkspaceWireController', () => {
  it('forwards ACP procedures to the mounted runtime client', async () => {
    const acp = createFakeAcpClient();
    const clientToServer = new PassThrough();
    const serverToClient = new PassThrough();
    const controller = createTestWorkspaceWireController({ acp });
    const disposeServer = serve(streamTransport(clientToServer, serverToClient), controller);
    const transport = streamTransport(serverToClient, clientToServer);
    const wireClient = createClient(workspaceWireContract, connect(transport));

    try {
      const result = await wireClient.acp.start({
        conversationId: 'conversation-1',
        providerId: 'codex',
        cwd: '/tmp/project',
        sessionId: null,
        model: null,
      });

      expect(result).toEqual(ok({ sessionId: 'acp-session-1' }));
      expect(acp.start).toHaveBeenCalledWith(
        expect.objectContaining({ conversationId: 'conversation-1' }),
        expect.any(Object)
      );
    } finally {
      disposeServer();
      transport.close?.();
    }
  });
});

function createFakeAcpClient(): ContractClient<AcpApiContract> {
  const liveSource = {
    snapshot: async () => ({ version: 0, data: null }),
    attach: async () => () => {},
    asLiveSource: () => null,
  };
  const liveModel = (def: unknown) => ({
    kind: 'liveModelClientHandle' as const,
    def,
    state: () => liveSource,
    mutate: async () => ok(undefined),
  });
  const liveLog = (def: unknown) => ({
    kind: 'liveLogClientHandle' as const,
    def,
    handle: () => liveSource,
  });

  return {
    start: vi.fn(async () => ok({ sessionId: 'acp-session-1' })),
    resume: vi.fn(),
    kill: vi.fn(),
    sendPrompt: vi.fn(),
    editQueuedPrompt: vi.fn(),
    deleteQueuedPrompt: vi.fn(),
    changeQueuePromptOrder: vi.fn(),
    cancelTurn: vi.fn(),
    setModelOption: vi.fn(),
    setModeOption: vi.fn(),
    resolvePermission: vi.fn(),
    setPromptDraft: vi.fn(),
    exportAcpTranscript: vi.fn(),
    exportRawAcpLog: vi.fn(),
    uploadAttachment: vi.fn(),
    downloadAttachment: vi.fn(),
    deleteAttachment: vi.fn(),
    deleteAttachments: vi.fn(),
    getHistory: vi.fn(),
    sessions: liveModel(workspaceWireContract.acp.sessions),
    session: liveModel(workspaceWireContract.acp.session),
    terminalOutput: liveLog(workspaceWireContract.acp.terminalOutput),
  } as unknown as ContractClient<AcpApiContract>;
}

describe('runtime domain forwarding', () => {
  it('forwards shell availability through the real terminals runtime controller', async () => {
    const availability = [
      {
        id: 'system' as const,
        label: 'bash',
        isSystemDefault: true,
        available: true,
      },
      {
        id: 'bash' as const,
        label: 'Bash',
        isSystemDefault: true,
        available: true,
      },
    ];
    const spawner: PtySpawner = {
      spawn: () => {
        throw new Error('PTY spawning is not expected in this test');
      },
    };
    const shellResolver: TerminalShellResolver = {
      resolveWithSystemFallback: async () => {
        throw new Error('Shell resolution is not expected in this test');
      },
      getAvailability: async () => availability,
    };
    const terminalsRuntime = new TerminalsRuntime({
      spawner,
      userEnv: async () => ({}),
      shellResolver,
    });
    const terminals = createTestWire(
      terminalsContract,
      createTerminalsController(terminalsRuntime)
    );
    const workspace = createTestWire(
      workspaceWireContract,
      createTestWorkspaceWireController({ terminals: terminals.client })
    );

    try {
      await expect(workspace.client.terminals.getShellAvailability(undefined)).resolves.toEqual(
        ok(availability)
      );
    } finally {
      await workspace.dispose();
      await terminals.dispose();
      terminalsRuntime.dispose();
    }
  });

  it('forwards Git and Files procedures, live models, and binary streams', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'emdash-workspace-server-domains-'));
    const root = parseAbsolute(directory);
    const textPath = parseAbsolute(join(directory, 'remote.txt'));
    const binaryPath = parseAbsolute(join(directory, 'remote.bin'));
    if (!root.success || !textPath.success || !binaryPath.success) {
      throw new Error('expected test paths to parse');
    }

    const watcher = createNoopWatcher();
    const filesRuntime = new FilesRuntime({ watcher });
    const gitRuntime = new GitRuntime({ watcher });
    const files = createTestWire(filesContract, createFilesController(filesRuntime));
    const git = createTestWire(gitContract, createGitController(gitRuntime));
    const workspace = createTestWire(
      workspaceWireContract,
      createTestWorkspaceWireController({ files: files.client, git: git.client })
    );

    try {
      const textBytes = Buffer.from('hello from the remote runtime');
      await expect(
        workspace.client.files.fs.upload(
          { path: textPath.data },
          {
            name: 'remote.txt',
            mimeType: 'text/plain',
            size: textBytes.byteLength,
            source: chunks(textBytes),
          }
        )
      ).resolves.toEqual(ok({ bytesWritten: textBytes.byteLength }));
      await expect(
        workspace.client.files.fs.readText({ path: textPath.data })
      ).resolves.toMatchObject({
        success: true,
        data: { content: 'hello from the remote runtime', truncated: false },
      });

      const binary = new Uint8Array([0, 1, 2, 255]);
      await expect(
        workspace.client.files.fs.upload(
          { path: binaryPath.data },
          {
            name: 'remote.bin',
            mimeType: 'application/octet-stream',
            size: binary.byteLength,
            source: chunks(binary),
          }
        )
      ).resolves.toEqual(ok({ bytesWritten: binary.byteLength }));
      const download = await workspace.client.files.fs.readBytes({
        path: binaryPath.data,
      });
      expect(download.success).toBe(true);
      if (!download.success) return;
      await expect(download.data.bytes()).resolves.toEqual(binary);

      await expect(
        workspace.client.git.ensureRepository({
          path: root.data,
          options: { initIfMissing: true },
        })
      ).resolves.toMatchObject({ success: true });
      await expect(
        workspace.client.git.repository.model.state({ repository: root.data }, 'refs').snapshot()
      ).resolves.toMatchObject({ data: { branches: [] } });
    } finally {
      await workspace.dispose();
      await git.dispose();
      await files.dispose();
      await Promise.all([gitRuntime.dispose(), filesRuntime.dispose(), watcher.dispose()]);
      await rm(directory, { recursive: true, force: true });
    }
  });
});

function createNoopWatcher(): IWatchService {
  return {
    watch: () => ({
      ready: async () => ok(undefined),
      release: async () => {},
    }),
    dispose: async () => {},
  };
}

async function* chunks(data: Uint8Array): AsyncIterable<Uint8Array> {
  yield data;
}

describe('createWorkspaceWireController', () => {
  it('health returns ok status and protocol version', async () => {
    const controller = createTestWorkspaceWireController(
      {},
      {
        appVersion: '1.2.3',
        daemonId: 'daemon-test',
        startedAt: Date.now(),
      }
    );

    const result = await controller.call('health', undefined);

    expect(result).toMatchObject({
      status: 'ok',
      version: '1.2.3',
      protocolVersion: PROTOCOL_VERSION,
    });
    expect((result as { uptimeMs: number }).uptimeMs).toBeGreaterThanOrEqual(0);
  });

  it('initializes compatible clients with the negotiated minor version', async () => {
    const controller = createTestWorkspaceWireController(
      {},
      {
        appVersion: '1.2.3',
        daemonId: 'daemon-test',
        startedAt: 100,
      }
    );
    const [major] = PROTOCOL_VERSION.split('.');

    const result = await controller.call('initialize', {
      protocolVersion: `${major}.0.0`,
      client: { id: 'client-test', appVersion: '1.2.3' },
    });

    expect(result).toEqual({
      success: true,
      data: {
        protocolVersion: PROTOCOL_VERSION,
        agreedVersion: `${major}.0.0`,
        agreedMinor: 0,
        server: {
          appVersion: '1.2.3',
          daemonId: 'daemon-test',
          startedAt: 100,
        },
      },
    });
  });

  it('returns upgrade-client when the client major is too old', async () => {
    const controller = createTestWorkspaceWireController();

    const result = await controller.call('initialize', {
      protocolVersion: '0.9.0',
      client: { id: 'client-test', appVersion: '1.2.3' },
    });

    expect(result).toMatchObject({
      success: false,
      error: {
        type: 'protocol-incompatible',
        action: 'upgrade-client',
        clientProtocolVersion: '0.9.0',
        serverProtocolVersion: PROTOCOL_VERSION,
      },
    });
  });

  it('returns upgrade-server when the client major is too new', async () => {
    const controller = createTestWorkspaceWireController();
    const [major] = PROTOCOL_VERSION.split('.');
    const futureVersion = `${Number(major) + 1}.0.0`;

    const result = await controller.call('initialize', {
      protocolVersion: futureVersion,
      client: { id: 'client-test', appVersion: '1.2.3' },
    });

    expect(result).toMatchObject({
      success: false,
      error: {
        type: 'protocol-incompatible',
        action: 'upgrade-server',
        clientProtocolVersion: futureVersion,
        serverProtocolVersion: PROTOCOL_VERSION,
      },
    });
  });

  it('inspects daemon-local preview ports', async () => {
    const server = net.createServer((socket) => socket.end());
    await listen(server, '127.0.0.1', 0);
    const address = server.address();
    if (typeof address !== 'object' || address === null) {
      throw new Error('expected TCP listener address');
    }

    const controller = createTestWorkspaceWireController();

    try {
      const result = await controller.call('portForwards.inspect', { port: address.port });

      expect(result).toEqual({
        success: true,
        data: {
          listening: true,
          families: ['ipv4'],
        },
      });
    } finally {
      await closeServer(server);
    }
  });

  it('reports closed preview ports as not listening', async () => {
    const server = net.createServer();
    await listen(server, '127.0.0.1', 0);
    const address = server.address();
    if (typeof address !== 'object' || address === null) {
      throw new Error('expected TCP listener address');
    }
    await closeServer(server);

    const controller = createTestWorkspaceWireController();
    const result = await controller.call('portForwards.inspect', { port: address.port });

    expect(result).toEqual({
      success: true,
      data: {
        listening: false,
        families: [],
      },
    });
  });
});

function listen(server: net.Server, host: string, port: number): Promise<void> {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen({ host, port }, () => {
      server.removeListener('error', reject);
      resolve();
    });
  });
}

function closeServer(server: net.Server): Promise<void> {
  return new Promise((resolve, reject) => {
    server.close((error) => (error ? reject(error) : resolve()));
  });
}
