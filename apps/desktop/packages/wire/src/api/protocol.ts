import { toSerializedError, type SerializedError, type Unsubscribe } from '@emdash/shared';
import type { LiveUpdate } from './channel';

export type WireErrorCode =
  | 'CANCELLED'
  | 'DISCONNECTED'
  | 'SERIALIZATION'
  | 'UNKNOWN_PROCEDURE'
  | 'UNKNOWN_TOPIC'
  | 'NOT_FOUND'
  | 'MISSING_HANDLER'
  | 'CONTRACT_MISMATCH'
  | 'ALREADY_EXISTS'
  | 'TIMEOUT'
  | 'HANDLER_ERROR';

export type WireCallMessage = {
  kind: 'call';
  id: string;
  path: string;
  input: unknown;
  upload?: {
    channel: string;
    meta: WireFileMeta;
  };
};

export type WireSnapshotMessage = {
  kind: 'snapshot';
  id: string;
  topic: string;
};

export type WireAttachMessage = {
  kind: 'attach';
  id: string;
  topic: string;
};

export type WireDetachMessage = {
  kind: 'detach';
  topic: string;
};

export type WireCancelMessage = {
  kind: 'cancel';
  id: string;
};

export type WireResultMessage =
  | {
      kind: 'result';
      id: string;
      ok: true;
      value: unknown;
    }
  | {
      kind: 'result';
      id: string;
      ok: false;
      code: WireErrorCode;
      message: string;
      cause?: SerializedError;
    };

export type WireUpdateMessage = {
  kind: 'update';
  topic: string;
  update: LiveUpdate;
};

export type WireTopicGapMessage = {
  kind: 'topic-gap';
  topic: string;
};

export type WireTopicErrorMessage = {
  kind: 'topic-error';
  topic: string;
  error: SerializedWireError;
  retrying: boolean;
};

export type WireFileMeta = {
  name: string;
  mimeType: string;
  size?: number;
  lastModified?: number;
  [key: string]: unknown;
};

export type WireBlobPullMessage = {
  kind: 'blob-pull';
  channel: string;
  credit: number;
};

export type WireBlobChunkMessage = {
  kind: 'blob-chunk';
  channel: string;
  seq: number;
  data: Uint8Array;
};

export type WireBlobEndMessage = {
  kind: 'blob-end';
  channel: string;
};

export type WireBlobErrorMessage = {
  kind: 'blob-error';
  channel: string;
  error: SerializedWireError;
};

export type WireBlobCloseMessage = {
  kind: 'blob-close';
  channel: string;
};

export type WireMessage =
  | WireCallMessage
  | WireSnapshotMessage
  | WireAttachMessage
  | WireDetachMessage
  | WireCancelMessage
  | WireResultMessage
  | WireUpdateMessage
  | WireTopicGapMessage
  | WireTopicErrorMessage
  | WireBlobPullMessage
  | WireBlobChunkMessage
  | WireBlobEndMessage
  | WireBlobErrorMessage
  | WireBlobCloseMessage;

export type WireTransport = {
  post(message: WireMessage): void;
  onMessage(cb: (message: WireMessage) => void): Unsubscribe;
  onDisconnect(cb: () => void): Unsubscribe;
  /**
   * Fires whenever the transport establishes connectivity, including the first
   * time. Presence of this hook marks the transport as reconnect-capable and
   * opts connections into holding calls issued while disconnected until the
   * next reconnect or their deadline; transports without it fail such calls
   * immediately.
   */
  onReconnect?(cb: () => void): Unsubscribe;
  /**
   * Fires once when the transport gives up permanently (reconnect abandoned or
   * the transport closed), carrying the cause. Connections reject all held and
   * future calls with a `WireError('DISCONNECTED')` wrapping it.
   */
  onTerminalFailure?(cb: (error: unknown) => void): Unsubscribe;
  close?(): void;
};

export class WireError extends Error {
  constructor(
    readonly code: WireErrorCode,
    message: string,
    options: { cause?: unknown } = {}
  ) {
    super(message, options);
    this.name = 'WireError';
  }
}

export type SerializedWireError = {
  code: WireErrorCode;
  message: string;
  cause?: SerializedError;
};

export function serializeWireError(error: unknown): SerializedWireError {
  if (error instanceof WireError) {
    return {
      code: error.code,
      message: error.message,
      cause: serializeCause(error.cause),
    };
  }
  if (error instanceof Error) {
    return { code: 'HANDLER_ERROR', message: error.message, cause: toSerializedError(error) };
  }
  return { code: 'HANDLER_ERROR', message: String(error), cause: toSerializedError(error) };
}

export function isWireError(error: unknown, code?: WireErrorCode): error is WireError {
  return error instanceof WireError && (code === undefined || error.code === code);
}

export function isWireMessage(value: unknown): value is WireMessage {
  if (typeof value !== 'object' || value === null) return false;
  const message = value as Record<string, unknown>;
  switch (message.kind) {
    case 'call':
      return typeof message.id === 'string' && typeof message.path === 'string';
    case 'snapshot':
    case 'attach':
      return typeof message.id === 'string' && typeof message.topic === 'string';
    case 'detach':
      return typeof message.topic === 'string';
    case 'cancel':
      return typeof message.id === 'string';
    case 'result':
      if (typeof message.id !== 'string') return false;
      if (message.ok === true) return true;
      return (
        message.ok === false &&
        typeof message.code === 'string' &&
        typeof message.message === 'string'
      );
    case 'update':
      return typeof message.topic === 'string' && typeof message.update === 'object';
    case 'topic-gap':
      return typeof message.topic === 'string';
    case 'topic-error':
      return (
        typeof message.topic === 'string' &&
        typeof message.error === 'object' &&
        typeof message.retrying === 'boolean'
      );
    case 'blob-pull':
      return typeof message.channel === 'string' && typeof message.credit === 'number';
    case 'blob-chunk':
      return (
        typeof message.channel === 'string' &&
        typeof message.seq === 'number' &&
        message.data instanceof Uint8Array
      );
    case 'blob-end':
    case 'blob-close':
      return typeof message.channel === 'string';
    case 'blob-error':
      return typeof message.channel === 'string' && typeof message.error === 'object';
    default:
      return false;
  }
}

function serializeCause(cause: unknown): SerializedError | undefined {
  if (cause === undefined) return undefined;
  if (isSerializedError(cause)) return cause;
  return toSerializedError(cause);
}

function isSerializedError(value: unknown): value is SerializedError {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { name?: unknown }).name === 'string' &&
    typeof (value as { message?: unknown }).message === 'string'
  );
}
