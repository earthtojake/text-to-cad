import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { connect, defineContract, liveModel, liveState, procedure } from '..';
import { client } from '../../rpc/client';
import { createController } from '../../rpc/controller';
import { domPortTransport } from './dom-port';
import { awaitWirePort, exposeWireToWindows, requestWirePort } from './electron';

const api = defineContract({
  ping: procedure({ input: z.object({ value: z.string() }), output: z.string() }),
  state: liveModel({
    key: z.void().optional(),
    states: { state: liveState({ data: z.object({ ready: z.boolean() }) }) },
  }),
});

class FakeMessagePort {
  private peer: FakeMessagePort | undefined;
  private mainListeners = new Map<string, Set<(...args: unknown[]) => void>>();
  private domListeners = new Map<string, Set<(event: { data?: unknown }) => void>>();
  started = false;
  closed = false;
  closeCalls = 0;

  pair(peer: FakeMessagePort): void {
    this.peer = peer;
  }

  postMessage(message: unknown): void {
    if (!this.peer || this.closed) return;
    queueMicrotask(() => this.peer?.emitMessage(message));
  }

  start(): void {
    this.started = true;
  }

  close(): void {
    this.closeCalls += 1;
    if (this.closed) return;
    this.closed = true;
    this.emitClose();
    this.peer?.markClosedByPeer();
  }

  on(event: string, cb: (...args: unknown[]) => void): void {
    getOrCreate(this.mainListeners, event).add(cb);
  }

  off(event: string, cb: (...args: unknown[]) => void): void {
    this.mainListeners.get(event)?.delete(cb);
  }

  addEventListener(event: string, cb: (event: { data?: unknown }) => void): void {
    getOrCreate(this.domListeners, event).add(cb);
  }

  removeEventListener(event: string, cb: (event: { data?: unknown }) => void): void {
    this.domListeners.get(event)?.delete(cb);
  }

  private emitMessage(data: unknown): void {
    for (const cb of this.mainListeners.get('message') ?? []) cb({ data });
    for (const cb of this.domListeners.get('message') ?? []) cb({ data });
  }

  private emitClose(): void {
    for (const cb of this.mainListeners.get('close') ?? []) cb();
    for (const cb of this.domListeners.get('close') ?? []) cb({});
  }

  private markClosedByPeer(): void {
    if (this.closed) return;
    this.closed = true;
    this.emitClose();
  }
}

class FakeIpcMain {
  handlers = new Map<string, (event: { sender: FakeWebContents }) => unknown>();

  handle(channel: string, listener: (event: { sender: FakeWebContents }) => unknown): void {
    this.handlers.set(channel, listener);
  }

  removeHandler(channel: string): void {
    this.handlers.delete(channel);
  }
}

class FakeIpcRenderer {
  listeners = new Map<string, (event: { ports?: unknown[] }, value: unknown) => void>();

  constructor(
    private readonly ipcMain: FakeIpcMain,
    private readonly sender: FakeWebContents
  ) {}

  invoke(channel: string): unknown {
    return this.ipcMain.handlers.get(channel)?.({ sender: this.sender });
  }

  once(channel: string, listener: (event: { ports?: unknown[] }, value: unknown) => void): void {
    this.listeners.set(channel, listener);
  }

  off(channel: string): void {
    this.listeners.delete(channel);
  }

  emit(channel: string, event: { ports?: unknown[] }, value: unknown): void {
    const listener = this.listeners.get(channel);
    if (!listener) return;
    this.listeners.delete(channel);
    listener(event, value);
  }
}

class FakeWebContents {
  readonly id = 1;
  renderer: FakeIpcRenderer | undefined;

  postMessage(channel: string, message: unknown, transfer?: unknown[]): void {
    this.renderer?.emit(channel, { ports: transfer }, message);
  }
}

class FakeWindow {
  private listeners = new Map<
    string,
    Set<(event: { data?: unknown; ports?: unknown[] }) => void>
  >();

  postMessage(message: unknown, _targetOrigin: string, transfer?: unknown[]): void {
    for (const cb of this.listeners.get('message') ?? []) cb({ data: message, ports: transfer });
  }

  addEventListener(
    event: string,
    listener: (event: { data?: unknown; ports?: unknown[] }) => void
  ): void {
    getOrCreate(this.listeners, event).add(listener);
  }

  removeEventListener(
    event: string,
    listener: (event: { data?: unknown; ports?: unknown[] }) => void
  ): void {
    this.listeners.get(event)?.delete(listener);
  }
}

describe('Electron wire helpers', () => {
  it('connects a renderer port to a controller and replaces sessions on reload', async () => {
    const ipcMain = new FakeIpcMain();
    const sender = new FakeWebContents();
    const ipcRenderer = new FakeIpcRenderer(ipcMain, sender);
    sender.renderer = ipcRenderer;
    const windowLike = new FakeWindow();
    const mainPorts: FakeMessagePort[] = [];
    const controller = createController(api, {
      ping: ({ value }) => `pong:${value}`,
      state: fakeStateProvider(),
    });

    const dispose = exposeWireToWindows(
      {
        ipcMain,
        createMessageChannel: () => {
          const port1 = new FakeMessagePort();
          const port2 = new FakeMessagePort();
          mainPorts.push(port1);
          port1.pair(port2);
          port2.pair(port1);
          return { port1, port2 };
        },
      },
      controller
    );

    const firstPort = await requestAndAwaitPort(ipcRenderer, windowLike);
    const firstClient = client(api, connect(domPortTransport(firstPort)));
    await expect(firstClient.ping({ value: 'one' })).resolves.toBe('pong:one');

    const secondPort = await requestAndAwaitPort(ipcRenderer, windowLike);
    expect(firstPort.closed).toBe(true);
    const secondClient = client(api, connect(domPortTransport(secondPort)));
    await expect(secondClient.ping({ value: 'two' })).resolves.toBe('pong:two');

    dispose();
    expect(ipcMain.handlers.has('wire:connect')).toBe(false);
    expect(secondPort.closed).toBe(true);
    expect(mainPorts[1]?.closeCalls).toBe(1);
  });

  it('removes naturally closed ports from the session map', async () => {
    const ipcMain = new FakeIpcMain();
    const sender = new FakeWebContents();
    const ipcRenderer = new FakeIpcRenderer(ipcMain, sender);
    sender.renderer = ipcRenderer;
    const windowLike = new FakeWindow();
    const mainPorts: FakeMessagePort[] = [];
    const controller = createController(api, {
      ping: ({ value }) => `pong:${value}`,
      state: fakeStateProvider(),
    });

    const dispose = exposeWireToWindows(
      {
        ipcMain,
        createMessageChannel: () => {
          const port1 = new FakeMessagePort();
          const port2 = new FakeMessagePort();
          mainPorts.push(port1);
          port1.pair(port2);
          port2.pair(port1);
          return { port1, port2 };
        },
      },
      controller
    );

    const firstPort = await requestAndAwaitPort(ipcRenderer, windowLike);
    firstPort.close();
    expect(mainPorts[0]?.closed).toBe(true);
    expect(mainPorts[0]?.closeCalls).toBe(1);

    await requestAndAwaitPort(ipcRenderer, windowLike);
    expect(mainPorts[0]?.closeCalls).toBe(1);

    dispose();
  });

  it('awaits beforeOpen before creating a renderer port', async () => {
    const ipcMain = new FakeIpcMain();
    const sender = new FakeWebContents();
    const ipcRenderer = new FakeIpcRenderer(ipcMain, sender);
    sender.renderer = ipcRenderer;
    const windowLike = new FakeWindow();
    const mainPorts: FakeMessagePort[] = [];
    const beforeOpen = createDeferred<void>();
    const controller = createController(api, {
      ping: ({ value }) => `pong:${value}`,
      state: fakeStateProvider(),
    });

    const dispose = exposeWireToWindows(
      {
        ipcMain,
        createMessageChannel: () => {
          const port1 = new FakeMessagePort();
          const port2 = new FakeMessagePort();
          mainPorts.push(port1);
          port1.pair(port2);
          port2.pair(port1);
          return { port1, port2 };
        },
      },
      controller,
      { beforeOpen: () => beforeOpen.promise }
    );

    const portPromise = requestAndAwaitPort(ipcRenderer, windowLike);
    await flush();
    expect(mainPorts).toHaveLength(0);

    beforeOpen.resolve();
    const port = await portPromise;
    expect(port).toBeInstanceOf(FakeMessagePort);
    expect(mainPorts).toHaveLength(1);

    dispose();
  });
});

async function requestAndAwaitPort(
  ipcRenderer: FakeIpcRenderer,
  windowLike: FakeWindow
): Promise<FakeMessagePort> {
  const portPromise = awaitWirePort(windowLike) as Promise<FakeMessagePort>;
  await requestWirePort({ ipcRenderer, window: windowLike });
  return await portPromise;
}

function getOrCreate<K, V>(map: Map<K, Set<V>>, key: K): Set<V> {
  const existing = map.get(key);
  if (existing) return existing;
  const created = new Set<V>();
  map.set(key, created);
  return created;
}

function fakeStateProvider() {
  return {
    kind: 'liveModelProvider' as const,
    contract: api.state,
    resolveState: () => ({
      snapshot: () => ({ generation: 1, sequence: 0, timestamp: 0, data: { ready: true } }),
      subscribe: () => () => {},
    }),
    runMutation: async () => {
      throw new Error('No mutations');
    },
  };
}

function createDeferred<T>(): {
  promise: Promise<T>;
  resolve(value: T): void;
} {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}
