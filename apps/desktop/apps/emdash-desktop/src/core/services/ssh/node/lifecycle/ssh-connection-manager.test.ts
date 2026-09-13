import { once } from 'node:events';
import { createServer, type Server, type Socket } from 'node:net';
import { PassThrough } from 'node:stream';
import type { Client } from 'ssh2';
import { describe, expect, it, vi } from 'vitest';

describe('SshConnectionManager', () => {
  it('cleans up a proxied transport when dropped during handshake', async () => {
    const { SshConnectionManager } = await import('./ssh-connection-manager');
    const manager = new SshConnectionManager();
    const sockets: Socket[] = [];
    const server: Server = createServer((socket) => {
      sockets.push(socket);
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const address = server.address();
    if (!address || typeof address === 'string') throw new Error('Expected TCP server address');
    let cleanupCount = 0;

    const connectPromise = manager.createConnection(
      'pending',
      async () => ({
        config: {
          host: '127.0.0.1',
          port: address.port,
          username: 'alice',
        },
        cleanup: () => {
          cleanupCount += 1;
        },
        debugLogs: [],
      }),
      { ephemeral: true }
    );
    connectPromise.catch(() => {});
    await new Promise((resolve) => setImmediate(resolve));

    expect(manager.getConnectionState('pending')).toBe('connecting');
    await manager.dropConnection('pending');
    for (const socket of sockets) socket.destroy();
    server.close();

    expect(cleanupCount).toBe(1);
    expect(manager.getConnectionState('pending')).toBe('disconnected');
    await expect(connectPromise).rejects.toThrow();
  });

  it('coalesces concurrent creates before resolving proxy transports', async () => {
    const { SshConnectionManager } = await import('./ssh-connection-manager');
    const cleanupCalls: string[] = [];
    let releaseResolver!: () => void;
    const resolverGate = new Promise<void>((resolve) => {
      releaseResolver = resolve;
    });
    const resolve = vi.fn(async () => {
      await resolverGate;
      return {
        config: { sock: new PassThrough(), username: 'alice' },
        cleanup: () => cleanupCalls.push('cleanup'),
        debugLogs: [],
      };
    });
    const manager = new SshConnectionManager({
      createClient: () =>
        new (class extends PassThrough {
          connect() {}
        })() as unknown as Client,
    });

    const firstConnect = manager.createConnection('ssh-1', resolve);
    const secondConnect = manager.createConnection('ssh-1', resolve);
    firstConnect.catch(() => {});
    secondConnect.catch(() => {});
    await new Promise((resolveImmediate) => setImmediate(resolveImmediate));

    expect(resolve).toHaveBeenCalledTimes(1);

    releaseResolver();
    await new Promise((resolveImmediate) => setImmediate(resolveImmediate));
    await manager.dropConnection('ssh-1');

    await expect(firstConnect).rejects.toThrow();
    await expect(secondConnect).rejects.toThrow();
    expect(cleanupCalls).toEqual(['cleanup']);
  });

  it('does not let a stale resolver create a client after drop and recreate', async () => {
    const { SshConnectionManager } = await import('./ssh-connection-manager');
    const cleanupCalls: string[] = [];
    const createClientCalls: string[] = [];
    let releaseFirstResolver!: () => void;
    let releaseSecondResolver!: () => void;
    const firstResolverGate = new Promise<void>((resolve) => {
      releaseFirstResolver = resolve;
    });
    const secondResolverGate = new Promise<void>((resolve) => {
      releaseSecondResolver = resolve;
    });
    const firstResolve = async () => {
      await firstResolverGate;
      return {
        config: { sock: new PassThrough(), username: 'alice-1' },
        cleanup: () => cleanupCalls.push('cleanup-1'),
        debugLogs: [],
      };
    };
    const secondResolve = async () => {
      await secondResolverGate;
      return {
        config: { sock: new PassThrough(), username: 'alice-2' },
        cleanup: () => cleanupCalls.push('cleanup-2'),
        debugLogs: [],
      };
    };
    const manager = new SshConnectionManager({
      createClient: () => {
        createClientCalls.push('client');
        return new (class extends PassThrough {
          connect() {}
        })() as unknown as Client;
      },
    });

    const firstConnect = manager.createConnection('ssh-1', firstResolve);
    firstConnect.catch(() => {});
    await new Promise((resolve) => setImmediate(resolve));
    await manager.dropConnection('ssh-1');

    const secondConnect = manager.createConnection('ssh-1', secondResolve);
    secondConnect.catch(() => {});

    releaseFirstResolver();
    await expect(firstConnect).rejects.toThrow('was disconnected before connecting');
    expect(createClientCalls).toEqual([]);
    expect(cleanupCalls).toEqual(['cleanup-1']);

    releaseSecondResolver();
    await new Promise((resolve) => setImmediate(resolve));
    expect(createClientCalls).toEqual(['client']);
    await manager.dropConnection('ssh-1');
    await expect(secondConnect).rejects.toThrow();
    expect(cleanupCalls).toEqual(['cleanup-1', 'cleanup-2']);
  });

  it('cleans up transport state when client.connect throws synchronously', async () => {
    const { SshConnectionManager } = await import('./ssh-connection-manager');
    const cleanupCalls: string[] = [];
    const manager = new SshConnectionManager({
      createClient: () =>
        new (class extends PassThrough {
          connect() {
            throw new Error('sync connect failure');
          }
        })() as unknown as Client,
    });

    await expect(
      manager.createConnection('sync-failure', async () => ({
        config: { sock: new PassThrough(), username: 'alice' },
        cleanup: () => cleanupCalls.push('cleanup'),
        debugLogs: [],
      }))
    ).rejects.toThrow('sync connect failure');

    expect(cleanupCalls).toEqual(['cleanup']);
    expect(manager.getConnectionState('sync-failure')).toBe('disconnected');
  });

  it('destroys a client when graceful drop times out', async () => {
    vi.useFakeTimers();
    try {
      const { SshConnectionManager } = await import('./ssh-connection-manager');
      class StuckCloseClient extends PassThrough {
        destroyCalls = 0;
        connect() {
          queueMicrotask(() => this.emit('ready'));
        }
        end() {
          return this;
        }
        destroy(error?: Error) {
          this.destroyCalls += 1;
          return super.destroy(error);
        }
      }
      const client = new StuckCloseClient();
      const manager = new SshConnectionManager({
        createClient: () => client as unknown as Client,
      });

      const proxy = await manager.createConnection('stuck-close', async () => ({
        config: { sock: new PassThrough(), username: 'alice' },
        cleanup: () => {},
        debugLogs: [],
      }));
      expect(proxy.isConnected).toBe(true);

      const dropPromise = manager.dropConnection('stuck-close');
      await vi.advanceTimersByTimeAsync(5_000);
      await dropPromise;

      expect(client.destroyCalls).toBe(1);
      expect(manager.getConnectionState('stuck-close')).toBe('disconnected');
    } finally {
      vi.useRealTimers();
    }
  });

  it('destroys a pending client when dropped before ready', async () => {
    const { SshConnectionManager } = await import('./ssh-connection-manager');
    class StuckHandshakeClient extends PassThrough {
      destroyCalls = 0;
      connect() {}
      destroy() {
        this.destroyCalls += 1;
        this.emit('close');
        return this;
      }
    }
    const client = new StuckHandshakeClient();
    const cleanupCalls: string[] = [];
    const manager = new SshConnectionManager({
      createClient: () => client as unknown as Client,
    });

    const connectPromise = manager.createConnection('pending-drop', async () => ({
      config: { sock: new PassThrough(), username: 'alice' },
      cleanup: () => cleanupCalls.push('cleanup'),
      debugLogs: [],
    }));
    connectPromise.catch(() => {});
    await new Promise((resolve) => setImmediate(resolve));

    await manager.dropConnection('pending-drop');

    expect(client.destroyCalls).toBe(1);
    expect(cleanupCalls).toEqual(['cleanup']);
    expect(manager.getConnectionState('pending-drop')).toBe('disconnected');
    await expect(connectPromise).rejects.toThrow('SSH connection closed before ready');
  });

  it('disconnectAll drops pending connections before they create clients', async () => {
    const { SshConnectionManager } = await import('./ssh-connection-manager');
    const cleanupCalls: string[] = [];
    const createClientCalls: string[] = [];
    let releaseResolver!: () => void;
    const resolverGate = new Promise<void>((resolve) => {
      releaseResolver = resolve;
    });
    const manager = new SshConnectionManager({
      createClient: () => {
        createClientCalls.push('client');
        return new PassThrough() as unknown as Client;
      },
    });
    const resolve = async () => {
      await resolverGate;
      return {
        config: { sock: new PassThrough(), username: 'alice' },
        cleanup: () => cleanupCalls.push('cleanup'),
        debugLogs: [],
      };
    };

    const connectPromise = manager.createConnection('ssh-1', resolve);
    connectPromise.catch(() => {});
    await new Promise((resolveImmediate) => setImmediate(resolveImmediate));

    expect(manager.getAllConnectionStates()).toEqual({ 'ssh-1': 'connecting' });
    await manager.disconnectAll();
    releaseResolver();

    await expect(connectPromise).rejects.toThrow('was disconnected before connecting');
    expect(cleanupCalls).toEqual(['cleanup']);
    expect(createClientCalls).toEqual([]);
  });

  it('re-resolves fresh config and cleanup while preserving the proxy on reconnect', async () => {
    vi.useFakeTimers();
    try {
      const { SshConnectionManager } = await import('./ssh-connection-manager');
      class FakeReadyClient extends PassThrough {
        connectedUsername: string | undefined;
        connect(config: { username?: string }) {
          this.connectedUsername = config.username;
          queueMicrotask(() => this.emit('ready'));
        }
        end() {
          this.emit('close');
          return this;
        }
      }
      const clients: FakeReadyClient[] = [];
      const cleanupCalls: string[] = [];
      const events: string[] = [];
      let resolveCalls = 0;
      const resolve = async () => {
        resolveCalls += 1;
        const call = resolveCalls;
        return {
          config: { sock: new PassThrough(), username: `alice-${call}` },
          cleanup: () => cleanupCalls.push(`cleanup-${call}`),
          debugLogs: [],
        };
      };
      const manager = new SshConnectionManager({
        createClient: () => {
          const client = new FakeReadyClient();
          clients.push(client);
          return client as unknown as Client;
        },
      });
      manager.on('connection-event', (event) => events.push(event.type));

      const proxy = await manager.createConnection('ssh-1', resolve);
      expect(proxy.isConnected).toBe(true);
      expect(clients[0]!.connectedUsername).toBe('alice-1');

      clients[0]!.emit('error', new Error('transport failed'));
      clients[0]!.emit('close');

      expect(events.filter((event) => event === 'disconnected')).toHaveLength(1);
      expect(events).toContain('reconnecting');
      expect(manager.getConnectionState('ssh-1')).toBe('reconnecting');

      await vi.advanceTimersByTimeAsync(1_000);

      expect(resolveCalls).toBe(2);
      expect(cleanupCalls).toEqual(['cleanup-1']);
      expect(manager.getProxy('ssh-1')).toBe(proxy);
      expect(proxy.isConnected).toBe(true);
      expect(proxy.client).toBe(clients[1]);
      expect(clients[1]!.connectedUsername).toBe('alice-2');

      await manager.dropConnection('ssh-1');
      expect(cleanupCalls).toEqual(['cleanup-1', 'cleanup-2']);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not re-enter reconnecting after dropping an in-flight reconnect', async () => {
    vi.useFakeTimers();
    try {
      const { SshConnectionManager } = await import('./ssh-connection-manager');
      class FakeReadyClient extends PassThrough {
        connect() {
          queueMicrotask(() => this.emit('ready'));
        }
        end() {
          this.emit('close');
          return this;
        }
      }
      const client = new FakeReadyClient();
      const events: string[] = [];
      let resolveCalls = 0;
      let releaseReconnect!: () => void;
      const reconnectGate = new Promise<void>((resolve) => {
        releaseReconnect = resolve;
      });
      const resolve = async () => {
        resolveCalls += 1;
        if (resolveCalls > 1) {
          await reconnectGate;
          throw new Error('reconnect failed after drop');
        }
        return {
          config: { sock: new PassThrough(), username: 'alice' },
          cleanup: () => {},
          debugLogs: [],
        };
      };
      const manager = new SshConnectionManager({
        createClient: () => client as unknown as Client,
      });
      manager.on('connection-event', (event) => events.push(event.type));

      await manager.createConnection('ssh-1', resolve);
      client.emit('error', new Error('transport failed'));
      client.emit('close');
      await vi.advanceTimersByTimeAsync(1_000);

      await manager.dropConnection('ssh-1');
      const reconnectingBeforeRelease = events.filter((event) => event === 'reconnecting').length;
      releaseReconnect();
      await vi.advanceTimersByTimeAsync(0);

      expect(events.filter((event) => event === 'reconnecting')).toHaveLength(
        reconnectingBeforeRelease
      );
      expect(manager.getConnectionState('ssh-1')).toBe('disconnected');
    } finally {
      vi.useRealTimers();
    }
  });

  it('rejects a stale in-flight handshake that becomes ready after drop and recreate', async () => {
    const { SshConnectionManager } = await import('./ssh-connection-manager');
    class ManualReadyClient extends PassThrough {
      connect() {}
      destroy() {
        return this;
      }
      end() {
        this.emit('close');
        return this;
      }
    }
    const clients: ManualReadyClient[] = [];
    const manager = new SshConnectionManager({
      createClient: () => {
        const client = new ManualReadyClient();
        clients.push(client);
        return client as unknown as Client;
      },
    });
    const resolve = async () => ({
      config: { sock: new PassThrough(), username: 'alice' },
      cleanup: () => {},
      debugLogs: [],
    });

    const firstConnect = manager.createConnection('ssh-1', resolve);
    firstConnect.catch(() => {});
    await new Promise((resolveImmediate) => setImmediate(resolveImmediate));
    await manager.dropConnection('ssh-1');

    const secondConnect = manager.createConnection('ssh-1', resolve);
    secondConnect.catch(() => {});
    await new Promise((resolveImmediate) => setImmediate(resolveImmediate));

    clients[0]!.emit('ready');
    await expect(firstConnect).rejects.toThrow('SSH connection closed before ready');

    clients[1]!.emit('ready');
    const secondProxy = await secondConnect;
    expect(secondProxy.isConnected).toBe(true);
    expect(secondProxy.client).toBe(clients[1]);
    await manager.dropConnection('ssh-1');
  });

  it('classifies handshake authentication and timeout errors', async () => {
    const { SshAuthError, SshConnectionManager, SshTimeoutError } =
      await import('./ssh-connection-manager');
    class ErrorClient extends PassThrough {
      constructor(private readonly error: Error) {
        super();
      }
      connect() {
        queueMicrotask(() => this.emit('error', this.error));
      }
    }
    const resolve = async () => ({
      config: { sock: new PassThrough(), username: 'alice' },
      cleanup: () => {},
      debugLogs: [],
    });

    await expect(
      new SshConnectionManager({
        createClient: () => new ErrorClient(new Error('permission denied')) as unknown as Client,
      }).createConnection('auth-failure', resolve)
    ).rejects.toBeInstanceOf(SshAuthError);

    await expect(
      new SshConnectionManager({
        createClient: () => new ErrorClient(new Error('ready timeout')) as unknown as Client,
      }).createConnection('timeout-failure', resolve)
    ).rejects.toBeInstanceOf(SshTimeoutError);
  });

  it('stops reconnecting immediately after an auth failure during reconnect', async () => {
    vi.useFakeTimers();
    try {
      const { SshAuthError, SshConnectionManager } = await import('./ssh-connection-manager');
      class FakeReadyClient extends PassThrough {
        connect() {
          queueMicrotask(() => this.emit('ready'));
        }
        end() {
          this.emit('close');
          return this;
        }
      }
      const client = new FakeReadyClient();
      const events: string[] = [];
      let resolveCalls = 0;
      const resolve = async () => {
        resolveCalls += 1;
        if (resolveCalls > 1) throw new SshAuthError('auth failed');
        return {
          config: { sock: new PassThrough(), username: 'alice' },
          cleanup: () => {},
          debugLogs: [],
        };
      };
      const manager = new SshConnectionManager({
        createClient: () => client as unknown as Client,
      });
      manager.on('connection-event', (event) => events.push(event.type));

      await manager.createConnection('ssh-1', resolve);
      client.emit('error', new Error('transport failed'));
      client.emit('close');
      await vi.advanceTimersByTimeAsync(1_000);

      expect(events).toContain('reconnect-failed');
      expect(manager.getConnectionState('ssh-1')).toBe('disconnected');
    } finally {
      vi.useRealTimers();
    }
  });

  it('suppresses ephemeral events, snapshots, and automatic reconnects', async () => {
    vi.useFakeTimers();
    try {
      const { SshConnectionManager } = await import('./ssh-connection-manager');
      class FakeReadyClient extends PassThrough {
        connect() {
          queueMicrotask(() => this.emit('ready'));
        }
        end() {
          this.emit('close');
          return this;
        }
      }
      const clients: FakeReadyClient[] = [];
      const internalEvents: string[] = [];
      const publishEvent = vi.fn();
      const resolve = vi.fn(async () => ({
        config: { sock: new PassThrough(), username: 'alice' },
        cleanup: () => {},
        debugLogs: [],
      }));
      const manager = new SshConnectionManager({
        createClient: () => {
          const client = new FakeReadyClient();
          clients.push(client);
          return client as unknown as Client;
        },
        publishEvent,
      });
      manager.on('connection-event', (event) => internalEvents.push(event.type));

      const proxy = await manager.createConnection('temporary-check', resolve, {
        ephemeral: true,
      });

      expect(proxy.isConnected).toBe(true);
      expect(manager.getProxy('temporary-check')).toBe(proxy);
      expect(manager.isConnected('temporary-check')).toBe(true);
      expect(manager.getConnectionState('temporary-check')).toBe('connected');
      expect(manager.getConnectionIds()).toEqual([]);
      expect(manager.getAllConnectionStates()).toEqual({});
      expect(manager.getAllHealthStates()).toEqual({});
      expect(internalEvents).toEqual([]);
      expect(publishEvent).not.toHaveBeenCalled();

      clients[0]!.emit('error', new Error('transport failed'));
      clients[0]!.emit('close');
      await vi.advanceTimersByTimeAsync(30_000);

      expect(resolve).toHaveBeenCalledTimes(1);
      expect(clients).toHaveLength(1);
      expect(manager.getConnectionState('temporary-check')).toBe('disconnected');
      expect(internalEvents).toEqual([]);
      expect(publishEvent).not.toHaveBeenCalled();

      await manager.dropConnection('temporary-check');
    } finally {
      vi.useRealTimers();
    }
  });
});
