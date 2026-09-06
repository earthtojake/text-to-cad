import type { Unsubscribe } from '@emdash/shared';
import { isWireMessage, type WireMessage, type WireTransport } from '../api/protocol';
import type { WorkerParentPort, WorkerProcess } from './types';

const WIRE_WORKER_FRAME_KIND = 'wire-worker-frame';
const WIRE_COMPONENT_BOOTSTRAP_KIND = 'wire-component-bootstrap';

export const RUNTIME_CHANNEL = 'runtime';

export type WireWorkerFrame = {
  kind: typeof WIRE_WORKER_FRAME_KIND;
  channel: string;
  payload: unknown;
};

export type WireComponentBootstrapRequest = {
  kind: typeof WIRE_COMPONENT_BOOTSTRAP_KIND;
  event: 'request';
  componentId: string;
};

export type WireComponentBootstrapResponse = {
  kind: typeof WIRE_COMPONENT_BOOTSTRAP_KIND;
  event: 'ready';
  componentId: string;
  config: unknown;
  dependencies: Record<string, WireComponentBootstrapDependency>;
};

export type WireComponentBootstrapDependency = { kind: 'contract'; channel: string };

export function isWireWorkerFrame(message: unknown): message is WireWorkerFrame {
  return (
    typeof message === 'object' &&
    message !== null &&
    (message as { kind?: unknown }).kind === WIRE_WORKER_FRAME_KIND &&
    typeof (message as { channel?: unknown }).channel === 'string'
  );
}

export function isWireComponentBootstrapRequest(
  message: unknown
): message is WireComponentBootstrapRequest {
  return (
    typeof message === 'object' &&
    message !== null &&
    (message as { kind?: unknown }).kind === WIRE_COMPONENT_BOOTSTRAP_KIND &&
    (message as { event?: unknown }).event === 'request' &&
    typeof (message as { componentId?: unknown }).componentId === 'string'
  );
}

export function isWireComponentBootstrapResponse(
  message: unknown
): message is WireComponentBootstrapResponse {
  return (
    typeof message === 'object' &&
    message !== null &&
    (message as { kind?: unknown }).kind === WIRE_COMPONENT_BOOTSTRAP_KIND &&
    (message as { event?: unknown }).event === 'ready' &&
    typeof (message as { componentId?: unknown }).componentId === 'string'
  );
}

export function workerProcessChannelTransport(
  process: WorkerProcess,
  channel: string
): WireTransport {
  return {
    post(message) {
      process.send({ kind: WIRE_WORKER_FRAME_KIND, channel, payload: message });
    },
    onMessage(cb): Unsubscribe {
      return process.onMessage((message) => {
        if (!isWireWorkerFrame(message) || message.channel !== channel) return;
        if (isWireMessage(message.payload)) cb(message.payload);
      });
    },
    onDisconnect(cb): Unsubscribe {
      return process.onExit(() => cb());
    },
  };
}

export function parentPortChannelTransport(port: WorkerParentPort, channel: string): WireTransport {
  return {
    post(message) {
      port.send({ kind: WIRE_WORKER_FRAME_KIND, channel, payload: message });
    },
    onMessage(cb): Unsubscribe {
      return port.onMessage((message) => {
        if (!isWireWorkerFrame(message) || message.channel !== channel) return;
        if (isWireMessage(message.payload)) cb(message.payload as WireMessage);
      });
    },
    onDisconnect(cb): Unsubscribe {
      return port.onDisconnect(cb);
    },
  };
}
