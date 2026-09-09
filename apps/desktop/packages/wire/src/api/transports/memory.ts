import type { Unsubscribe } from '@emdash/shared';
import type { WireMessage, WireTransport } from '../protocol';

type MemoryEndpoint = WireTransport & {
  disconnect(): void;
  close(): void;
};

export type MemoryTransportPair = {
  left: MemoryEndpoint;
  right: MemoryEndpoint;
  disconnect(): void;
};

export function memoryTransportPair(): MemoryTransportPair {
  const leftMessages = new Set<(message: WireMessage) => void>();
  const rightMessages = new Set<(message: WireMessage) => void>();
  const leftDisconnects = new Set<() => void>();
  const rightDisconnects = new Set<() => void>();
  let connected = true;

  const left = createEndpoint(leftMessages, rightMessages, leftDisconnects, () => connected);
  const right = createEndpoint(rightMessages, leftMessages, rightDisconnects, () => connected);

  const disconnect = (): void => {
    if (!connected) return;
    connected = false;
    for (const listener of leftDisconnects) listener();
    for (const listener of rightDisconnects) listener();
  };

  return {
    left: { ...left, disconnect, close: disconnect },
    right: { ...right, disconnect, close: disconnect },
    disconnect,
  };
}

function createEndpoint(
  incoming: Set<(message: WireMessage) => void>,
  outgoing: Set<(message: WireMessage) => void>,
  disconnects: Set<() => void>,
  isConnected: () => boolean
): WireTransport {
  return {
    post(message) {
      if (!isConnected()) throw new Error('Memory transport disconnected');
      queueMicrotask(() => {
        if (!isConnected()) return;
        for (const listener of outgoing) listener(message);
      });
    },
    onMessage(cb): Unsubscribe {
      incoming.add(cb);
      return () => incoming.delete(cb);
    },
    onDisconnect(cb): Unsubscribe {
      disconnects.add(cb);
      return () => disconnects.delete(cb);
    },
  };
}
