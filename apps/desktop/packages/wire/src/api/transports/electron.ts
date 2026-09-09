import type { Unsubscribe } from '@emdash/shared';
import type { Controller } from '../controller';
import { createWireSessionHub } from '../sessions';
import { portTransport, type PortLike } from './port';

export type MessagePortMainLike = PortLike & {
  start?(): void;
  close?(): void;
};

export type WebContentsLike = {
  id: number;
  postMessage(channel: string, message: unknown, transfer?: unknown[]): void;
};

export type IpcMainInvokeEventLike = {
  sender: WebContentsLike;
};

export type IpcMainLike = {
  handle(channel: string, listener: (event: IpcMainInvokeEventLike) => unknown): void;
  removeHandler?(channel: string): void;
};

export type IpcRendererLike = {
  invoke(channel: string): Promise<unknown> | unknown;
  once(channel: string, listener: (event: { ports?: unknown[] }, value: unknown) => void): void;
  off?(channel: string, listener: (event: { ports?: unknown[] }, value: unknown) => void): void;
};

export type WindowLike = {
  postMessage(message: unknown, targetOrigin: string, transfer?: unknown[]): void;
  addEventListener(
    event: string,
    listener: (event: { data?: unknown; ports?: unknown[] }) => void
  ): void;
  removeEventListener?(
    event: string,
    listener: (event: { data?: unknown; ports?: unknown[] }) => void
  ): void;
};

export type MessageChannelFactory = () => {
  port1: MessagePortMainLike;
  port2: unknown;
};

export type ExposeWireOptions = {
  channel?: string;
  beforeOpen?: (event: IpcMainInvokeEventLike) => void | Promise<void>;
};

type WindowPortRecord = {
  port: MessagePortMainLike;
  disposeMapCleanup: Unsubscribe;
};

export function exposeWireToWindows(
  deps: { ipcMain: IpcMainLike; createMessageChannel: MessageChannelFactory },
  controller: Controller,
  options: ExposeWireOptions = {}
): () => Promise<void> {
  const channel = options.channel ?? 'wire';
  const connectChannel = `${channel}:connect`;
  const portChannel = `${channel}:port`;
  const hub = createWireSessionHub(controller);
  const ports = new Map<number, WindowPortRecord>();

  deps.ipcMain.handle(connectChannel, async (event) => {
    await options.beforeOpen?.(event);
    const { port1, port2 } = deps.createMessageChannel();
    const existing = ports.get(event.sender.id);
    existing?.port.close?.();
    existing?.disposeMapCleanup();
    ports.delete(event.sender.id);

    const transport = portTransport(port1);
    const disposeMapCleanup = transport.onDisconnect(() => {
      const current = ports.get(event.sender.id);
      if (current?.port !== port1) return;
      current.disposeMapCleanup();
      ports.delete(event.sender.id);
    });
    ports.set(event.sender.id, { port: port1, disposeMapCleanup });
    hub.open(event.sender.id, transport);
    port1.start?.();
    event.sender.postMessage(portChannel, null, [port2]);
    return undefined;
  });

  return async () => {
    deps.ipcMain.removeHandler?.(connectChannel);
    for (const record of ports.values()) record.disposeMapCleanup();
    ports.clear();
    await hub.dispose();
  };
}

export async function requestWirePort(
  deps: { ipcRenderer: IpcRendererLike; window: WindowLike },
  options: ExposeWireOptions = {}
): Promise<void> {
  const channel = options.channel ?? 'wire';
  const portChannel = `${channel}:port`;
  const connectChannel = `${channel}:connect`;
  await new Promise<void>((resolve, reject) => {
    const listener = (event: { ports?: unknown[] }, value: unknown): void => {
      try {
        const port = event.ports?.[0] ?? value;
        deps.window.postMessage({ kind: portChannel }, '*', [port]);
        resolve();
      } catch (error) {
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    };
    deps.ipcRenderer.once(portChannel, listener);
    Promise.resolve(deps.ipcRenderer.invoke(connectChannel)).catch((error: unknown) => {
      deps.ipcRenderer.off?.(portChannel, listener);
      reject(error instanceof Error ? error : new Error(String(error)));
    });
  });
}

export function awaitWirePort(
  windowLike: WindowLike,
  options: ExposeWireOptions = {}
): Promise<unknown> {
  const channel = options.channel ?? 'wire';
  const portChannel = `${channel}:port`;
  return new Promise((resolve) => {
    const listener = (event: { data?: unknown; ports?: unknown[] }): void => {
      if (!isWirePortMessage(event.data, portChannel)) return;
      windowLike.removeEventListener?.('message', listener);
      resolve(event.ports?.[0]);
    };
    windowLike.addEventListener('message', listener);
  });
}

function isWirePortMessage(value: unknown, channel: string): value is { kind: string } {
  return (
    typeof value === 'object' && value !== null && (value as { kind?: unknown }).kind === channel
  );
}
