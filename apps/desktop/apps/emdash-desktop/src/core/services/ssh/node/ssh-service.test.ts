import { generateKeyPairSync } from 'node:crypto';
import { EventEmitter, once } from 'node:events';
import { Server, type Client, type ConnectConfig } from 'ssh2';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ConnectionState, SshConfig } from '@core/primitives/ssh/api';
import type { AppDb } from '@core/services/app-db/node/db';
import type { SshConnectionRow } from '@core/services/app-db/node/schema';
import type { SshConnectResult } from './connect/resolve-ssh-connect-config';
import { SshConnectionManager } from './lifecycle/ssh-connection-manager';
import { SshService, type SshServiceDeps } from './ssh-service';

const { privateKey: hostKey } = generateKeyPairSync('rsa', {
  modulusLength: 2048,
  privateKeyEncoding: { type: 'pkcs1', format: 'pem' },
  publicKeyEncoding: { type: 'pkcs1', format: 'pem' },
});

const baseConfig: SshConfig & { password?: string } = {
  id: '',
  name: 'Test connection',
  host: 'wrong.example.com',
  port: 2222,
  username: 'nobody',
  authType: 'password',
  password: 'secret',
};

function createService(options: {
  manager: SshConnectionManager;
  resolve: () => Promise<SshConnectResult>;
  createId?: () => string;
  now?: () => number;
  capture?: SshServiceDeps['telemetry']['capture'];
}): SshService {
  return new SshService({
    db: {} as AppDb,
    manager: options.manager,
    runtime: { remove: vi.fn() },
    resolveConnectConfig: options.resolve,
    parseSshConfigFile: vi.fn(),
    resolveSshConfig: vi.fn(),
    telemetry: {
      capture: options.capture ?? vi.fn<SshServiceDeps['telemetry']['capture']>(),
    },
    log: { warn: vi.fn() },
    createId: options.createId ?? (() => 'temporary-check'),
    now: options.now,
  });
}

async function startServer() {
  const server = new Server({ hostKeys: [hostKey] });
  server.on('connection', (client) => {
    client.on('authentication', (context) => {
      if (
        context.method === 'password' &&
        context.username === 'alice' &&
        context.password === 'secret'
      ) {
        context.accept();
        return;
      }
      context.reject();
    });
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const address = server.address();
  if (!address || typeof address === 'string') throw new Error('Expected TCP server address');
  return { server, port: address.port };
}

describe('SshService connection intent', () => {
  it('records explicit connect intent before connecting persisted config', async () => {
    const fixture = createIntentFixture({ shouldConnect: null, now: 1_700_000_000_000 });

    await expect(fixture.service.connect('ssh-1')).resolves.toBe('connected');

    expect(fixture.updateSets).toEqual([
      {
        shouldConnect: 1,
        updatedAt: '2023-11-14T22:13:20.000Z',
      },
    ]);
    expect(fixture.manager.createConnection).toHaveBeenCalledWith('ssh-1', expect.any(Function));
    expect(fixture.resolveConnectConfig).toHaveBeenCalledWith({
      kind: 'persisted',
      row: fixture.row,
    });
  });

  it('records explicit disconnect intent before dropping active connections', async () => {
    const fixture = createIntentFixture({
      shouldConnect: 1,
      state: 'connected',
      now: 1_700_000_000_000,
    });

    await fixture.service.disconnect('ssh-1');

    expect(fixture.updateSets).toEqual([
      {
        shouldConnect: 0,
        updatedAt: '2023-11-14T22:13:20.000Z',
      },
    ]);
    expect(fixture.manager.dropConnection).toHaveBeenCalledWith('ssh-1');
  });

  it('refuses implicit connects for deliberately disconnected machines', async () => {
    const fixture = createIntentFixture({ shouldConnect: 0 });

    await expect(fixture.service.ensureConnected('ssh-1')).resolves.toBe('disconnected');

    expect(fixture.updateSets).toEqual([]);
    expect(fixture.manager.createConnection).not.toHaveBeenCalled();
    expect(fixture.resolveConnectConfig).not.toHaveBeenCalled();
  });

  it('allows implicit connects when intent is unset without changing intent', async () => {
    const fixture = createIntentFixture({ shouldConnect: null });

    await expect(fixture.service.ensureConnected('ssh-1')).resolves.toBe('connected');

    expect(fixture.updateSets).toEqual([]);
    expect(fixture.manager.createConnection).toHaveBeenCalledWith('ssh-1', expect.any(Function));
    expect(fixture.resolveConnectConfig).toHaveBeenCalledWith({
      kind: 'persisted',
      row: fixture.row,
    });
  });
});

function createIntentFixture(options: {
  shouldConnect: number | null;
  state?: ConnectionState;
  now?: number;
}) {
  const row = {
    id: 'ssh-1',
    name: 'Corp',
    host: 'corp.example.com',
    port: 22,
    username: 'alice',
    authType: 'agent',
    privateKeyPath: null,
    useAgent: 1,
    metadata: {},
    shouldConnect: options.shouldConnect,
    createdAt: '2026-01-01T00:00:00.000Z',
    updatedAt: '2026-01-01T00:00:00.000Z',
  } as unknown as SshConnectionRow;
  const updateSets: unknown[] = [];
  const db = {
    select: vi.fn(() => ({
      from: vi.fn(() => ({
        where: vi.fn(() => ({
          limit: vi.fn(async () => [row]),
        })),
      })),
    })),
    update: vi.fn(() => ({
      set: vi.fn((value: unknown) => {
        updateSets.push(value);
        return { where: vi.fn(async () => {}) };
      }),
    })),
  } as unknown as AppDb;
  const manager = {
    createConnection: vi.fn(
      async (_connectionId: string, resolve: () => Promise<SshConnectResult>) => {
        await resolve();
      }
    ),
    dropConnection: vi.fn(async () => {}),
    getConnectionState: vi.fn(() => options.state ?? 'connected'),
  } as unknown as SshConnectionManager;
  const resolveConnectConfig = vi.fn(
    async (): Promise<SshConnectResult> => ({
      config: {
        host: 'corp.example.com',
        username: 'alice',
      },
      cleanup: () => {},
      debugLogs: [],
    })
  );
  const service = new SshService({
    db,
    manager,
    runtime: { remove: vi.fn() },
    resolveConnectConfig,
    parseSshConfigFile: vi.fn(),
    resolveSshConfig: vi.fn(),
    telemetry: { capture: vi.fn() },
    log: { warn: vi.fn() },
    now: () => options.now ?? 0,
  });

  return {
    service,
    manager,
    row,
    updateSets,
    resolveConnectConfig,
  };
}

describe('SshService.testConnection', () => {
  const servers: Server[] = [];

  afterEach(() => {
    for (const server of servers.splice(0)) {
      server.close();
    }
  });

  it('uses the unified resolver and drops its ephemeral connection', async () => {
    const { server, port } = await startServer();
    servers.push(server);
    const cleanups: string[] = [];
    const manager = new SshConnectionManager();
    const dropConnection = vi.spyOn(manager, 'dropConnection');
    const capture = vi.fn<SshServiceDeps['telemetry']['capture']>();
    const service = createService({
      manager,
      capture,
      now: vi.fn().mockReturnValueOnce(100).mockReturnValueOnce(145),
      resolve: async () => ({
        config: {
          host: '127.0.0.1',
          port,
          username: 'alice',
          password: 'secret',
          readyTimeout: 5_000,
        },
        cleanup: () => cleanups.push('cleanup'),
        debugLogs: ['resolved via alias'],
      }),
    });

    await expect(service.testConnection(baseConfig)).resolves.toMatchObject({
      success: true,
      latency: 45,
      debugLogs: expect.arrayContaining(['resolved via alias']),
    });
    expect(cleanups).toEqual(['cleanup']);
    expect(dropConnection).toHaveBeenCalledWith('temporary-check');
    expect(capture).toHaveBeenCalledWith('ssh_connection_attempted', { success: true });
    expect(manager.getAllConnectionStates()).toEqual({});
  });

  it('defaults readyTimeout to 10 seconds and captures ssh2 debug output', async () => {
    let receivedConfig: ConnectConfig | undefined;
    class DebugClient extends EventEmitter {
      connect(config: ConnectConfig) {
        receivedConfig = config;
        config.debug?.('ssh2 debug output');
        queueMicrotask(() => this.emit('ready'));
      }
      end() {
        queueMicrotask(() => this.emit('close'));
        return this;
      }
    }
    const manager = new SshConnectionManager({
      createClient: () => new DebugClient() as unknown as Client,
    });
    const service = createService({
      manager,
      resolve: async () => ({
        config: { host: '127.0.0.1', port: 22, username: 'alice' },
        cleanup: () => {},
        debugLogs: ['resolved'],
      }),
    });

    await expect(service.testConnection(baseConfig)).resolves.toMatchObject({
      success: true,
      debugLogs: ['resolved', 'ssh2 debug output'],
    });
    expect(receivedConfig?.readyTimeout).toBe(10_000);
  });

  it('maps resolver and client failures and still cleans up', async () => {
    const resolverCapture = vi.fn<SshServiceDeps['telemetry']['capture']>();
    const resolverManager = new SshConnectionManager();
    const resolverDrop = vi.spyOn(resolverManager, 'dropConnection');
    const resolverService = createService({
      manager: resolverManager,
      capture: resolverCapture,
      resolve: async () => {
        throw new Error('resolve failed');
      },
    });

    await expect(resolverService.testConnection(baseConfig)).resolves.toEqual({
      success: false,
      error: 'resolve failed',
      debugLogs: [],
    });
    expect(resolverDrop).toHaveBeenCalledWith('temporary-check');
    expect(resolverCapture).toHaveBeenCalledWith('ssh_connection_attempted', { success: false });

    const cleanups: string[] = [];
    class ErrorClient extends EventEmitter {
      connect() {
        queueMicrotask(() => this.emit('error', new Error('auth failed')));
      }
    }
    const errorManager = new SshConnectionManager({
      createClient: () => new ErrorClient() as unknown as Client,
    });
    const errorService = createService({
      manager: errorManager,
      resolve: async () => ({
        config: { host: '127.0.0.1', port: 22, username: 'alice' },
        cleanup: () => cleanups.push('cleanup'),
        debugLogs: ['resolved'],
      }),
    });

    await expect(errorService.testConnection(baseConfig)).resolves.toEqual({
      success: false,
      error: 'auth failed',
      debugLogs: ['resolved'],
    });
    expect(cleanups).toEqual(['cleanup']);
  });

  it('maps close-before-ready and synchronous connect failures', async () => {
    class ClosingClient extends EventEmitter {
      connect() {
        queueMicrotask(() => this.emit('close'));
      }
    }
    const closingService = createService({
      manager: new SshConnectionManager({
        createClient: () => new ClosingClient() as unknown as Client,
      }),
      resolve: async () => ({
        config: { host: '127.0.0.1', port: 22, username: 'alice' },
        cleanup: () => {},
        debugLogs: ['resolved'],
      }),
    });

    await expect(closingService.testConnection(baseConfig)).resolves.toMatchObject({
      success: false,
      error: 'SSH connection closed before ready',
      debugLogs: ['resolved'],
    });

    const cleanups: string[] = [];
    class ThrowingClient extends EventEmitter {
      connect() {
        throw new Error('connect exploded');
      }
    }
    const throwingService = createService({
      manager: new SshConnectionManager({
        createClient: () => new ThrowingClient() as unknown as Client,
      }),
      resolve: async () => ({
        config: { host: '127.0.0.1', port: 22, username: 'alice' },
        cleanup: () => cleanups.push('cleanup'),
        debugLogs: [],
      }),
    });

    await expect(throwingService.testConnection(baseConfig)).resolves.toMatchObject({
      success: false,
      error: 'connect exploded',
    });
    expect(cleanups).toEqual(['cleanup']);
  });
});
