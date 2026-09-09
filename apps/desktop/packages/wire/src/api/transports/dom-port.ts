import type { Unsubscribe } from '@emdash/shared';
import { isWireMessage, type WireTransport } from '../protocol';

export type DomPortLike = {
  postMessage(message: unknown): void;
  start?(): void;
  close?(): void;
  addEventListener(event: string, cb: (event: { data?: unknown }) => void): void;
  removeEventListener?(event: string, cb: (event: { data?: unknown }) => void): void;
};

export function domPortTransport(port: DomPortLike): WireTransport {
  const disconnectListeners = new Set<() => void>();
  const messageListeners = new Set<(event: { data?: unknown }) => void>();
  const notifyDisconnect = (): void => {
    for (const listener of disconnectListeners) listener();
  };

  port.addEventListener('close', notifyDisconnect);
  port.start?.();

  return {
    post: (message) => port.postMessage(message),
    onMessage(cb): Unsubscribe {
      const listener = (event: { data?: unknown }) => {
        if (isWireMessage(event.data)) cb(event.data);
      };
      messageListeners.add(listener);
      port.addEventListener('message', listener);
      return () => {
        messageListeners.delete(listener);
        port.removeEventListener?.('message', listener);
      };
    },
    onDisconnect(cb): Unsubscribe {
      disconnectListeners.add(cb);
      return () => disconnectListeners.delete(cb);
    },
    close() {
      for (const listener of messageListeners) port.removeEventListener?.('message', listener);
      messageListeners.clear();
      port.removeEventListener?.('close', notifyDisconnect);
      disconnectListeners.clear();
      port.close?.();
    },
  };
}
