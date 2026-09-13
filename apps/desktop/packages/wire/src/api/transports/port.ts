import type { Unsubscribe } from '@emdash/shared';
import { isWireMessage, type WireTransport } from '../protocol';

export type PortLike = {
  postMessage(message: unknown): void;
  on(event: string, cb: (...args: unknown[]) => void): void;
  off?(event: string, cb: (...args: unknown[]) => void): void;
  removeListener?(event: string, cb: (...args: unknown[]) => void): void;
  close?(): void;
};

export function portTransport(port: PortLike): WireTransport {
  const disconnectListeners = new Set<() => void>();
  const messageListeners = new Set<(...args: unknown[]) => void>();
  const notifyDisconnect = (): void => {
    for (const listener of disconnectListeners) listener();
  };

  port.on('close', notifyDisconnect);
  port.on('exit', notifyDisconnect);
  port.on('error', notifyDisconnect);

  return {
    post: (message) => port.postMessage(message),
    onMessage(cb): Unsubscribe {
      const listener = (...args: unknown[]) => {
        const event = args[0];
        if (!isPortMessageEvent(event)) return;
        if (isWireMessage(event.data)) cb(event.data);
      };
      messageListeners.add(listener);
      port.on('message', listener);
      return () => {
        messageListeners.delete(listener);
        removePortListener(port, 'message', listener);
      };
    },
    onDisconnect(cb): Unsubscribe {
      disconnectListeners.add(cb);
      return () => disconnectListeners.delete(cb);
    },
    close() {
      for (const listener of messageListeners) removePortListener(port, 'message', listener);
      messageListeners.clear();
      removePortListener(port, 'close', notifyDisconnect);
      removePortListener(port, 'exit', notifyDisconnect);
      removePortListener(port, 'error', notifyDisconnect);
      disconnectListeners.clear();
      port.close?.();
    },
  };
}

function removePortListener(
  port: PortLike,
  event: 'message' | 'close' | 'exit' | 'error',
  cb: (...args: unknown[]) => void
): void {
  port.off?.(event, cb);
  port.removeListener?.(event, cb);
}

function isPortMessageEvent(value: unknown): value is { data: unknown } {
  return typeof value === 'object' && value !== null && 'data' in value;
}
