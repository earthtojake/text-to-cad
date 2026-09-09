import type { Unsubscribe } from '@emdash/shared';
import { isWireMessage, type WireMessage, type WireTransport } from '../protocol';

type ReadableLike = {
  on(event: 'data', cb: (chunk: Uint8Array | string) => void): unknown;
  on(event: 'close' | 'end' | 'error', cb: () => void): unknown;
};

type WritableLike = {
  write(chunk: string | Uint8Array): unknown;
};

type Bytes = Uint8Array<ArrayBufferLike>;

const FRAME_JSON = 0x00;
const FRAME_BINARY = 0x01;
const HEADER_BYTES = 5;
const BODY_LENGTH_BYTES = 4;
const MAX_FRAME_BYTES = 16 * 1024 * 1024;

export function streamTransport(input: ReadableLike, output: WritableLike): WireTransport {
  const messageListeners = new Set<(message: WireMessage) => void>();
  const disconnectListeners = new Set<() => void>();
  let buffer: Bytes = new Uint8Array(0);
  let disconnected = false;

  const notifyDisconnect = (): void => {
    if (disconnected) return;
    disconnected = true;
    for (const listener of disconnectListeners) listener();
  };

  input.on('data', (chunk) => {
    if (disconnected) return;
    buffer = concat(buffer, normalizeChunk(chunk));
    try {
      buffer = emitParsedFrames(buffer, messageListeners, notifyDisconnect);
    } catch {
      notifyDisconnect();
    }
  });
  input.on('close', notifyDisconnect);
  input.on('end', notifyDisconnect);
  input.on('error', notifyDisconnect);

  return {
    post(message) {
      if (disconnected) throw new Error('Stream transport disconnected');
      output.write(encodeFrame(message));
    },
    onMessage(cb): Unsubscribe {
      messageListeners.add(cb);
      return () => messageListeners.delete(cb);
    },
    onDisconnect(cb): Unsubscribe {
      disconnectListeners.add(cb);
      return () => disconnectListeners.delete(cb);
    },
    close() {
      notifyDisconnect();
      messageListeners.clear();
      disconnectListeners.clear();
      buffer = new Uint8Array(0);
    },
  };
}

function encodeFrame(message: WireMessage): Uint8Array {
  if (message.kind === 'blob-chunk') {
    const header = encodeJson({
      kind: message.kind,
      channel: message.channel,
      seq: message.seq,
    });
    const body = message.data;
    const frame = new Uint8Array(
      HEADER_BYTES + header.byteLength + BODY_LENGTH_BYTES + body.byteLength
    );
    frame[0] = FRAME_BINARY;
    writeU32(frame, 1, header.byteLength);
    frame.set(header, HEADER_BYTES);
    writeU32(frame, HEADER_BYTES + header.byteLength, body.byteLength);
    frame.set(body, HEADER_BYTES + header.byteLength + BODY_LENGTH_BYTES);
    return frame;
  }

  const header = encodeJson(message);
  const frame = new Uint8Array(HEADER_BYTES + header.byteLength);
  frame[0] = FRAME_JSON;
  writeU32(frame, 1, header.byteLength);
  frame.set(header, HEADER_BYTES);
  return frame;
}

function emitParsedFrames(
  input: Bytes,
  listeners: Set<(message: WireMessage) => void>,
  disconnect: () => void
): Bytes {
  let offset = 0;
  while (input.byteLength - offset >= HEADER_BYTES) {
    const kind = input[offset];
    const headerLength = readU32(input, offset + 1);
    if (headerLength > MAX_FRAME_BYTES) {
      disconnect();
      return new Uint8Array(0);
    }
    const headerStart = offset + HEADER_BYTES;
    const headerEnd = headerStart + headerLength;
    if (input.byteLength < headerEnd) break;

    if (kind === FRAME_JSON) {
      emitParsedMessage(input.subarray(headerStart, headerEnd), undefined, listeners);
      offset = headerEnd;
      continue;
    }

    if (kind !== FRAME_BINARY) {
      disconnect();
      return new Uint8Array(0);
    }

    if (input.byteLength - headerEnd < BODY_LENGTH_BYTES) break;
    const bodyLength = readU32(input, headerEnd);
    if (bodyLength > MAX_FRAME_BYTES) {
      disconnect();
      return new Uint8Array(0);
    }
    const bodyStart = headerEnd + BODY_LENGTH_BYTES;
    const bodyEnd = bodyStart + bodyLength;
    if (input.byteLength < bodyEnd) break;
    emitParsedMessage(
      input.subarray(headerStart, headerEnd),
      input.subarray(bodyStart, bodyEnd),
      listeners
    );
    offset = bodyEnd;
  }
  return input.subarray(offset);
}

function emitParsedMessage(
  headerBytes: Uint8Array,
  body: Bytes | undefined,
  listeners: Set<(message: WireMessage) => void>
): void {
  const parsed: unknown = JSON.parse(decodeText(headerBytes));
  const message = body
    ? { ...(parsed as Record<string, unknown>), data: new Uint8Array(body) }
    : parsed;
  if (!isWireMessage(message)) return;
  for (const listener of listeners) listener(message);
}

function encodeJson(value: unknown): Uint8Array {
  return encodeText(JSON.stringify(value));
}

function concat(left: Bytes, right: Bytes): Bytes {
  if (left.byteLength === 0) return new Uint8Array(right);
  const out = new Uint8Array(left.byteLength + right.byteLength);
  out.set(left, 0);
  out.set(right, left.byteLength);
  return out;
}

function normalizeChunk(chunk: Uint8Array | string): Bytes {
  return typeof chunk === 'string' ? new Uint8Array(encodeText(chunk)) : new Uint8Array(chunk);
}

function encodeText(value: string): Uint8Array {
  return new globalThis.TextEncoder().encode(value);
}

function decodeText(value: Uint8Array): string {
  return new globalThis.TextDecoder().decode(value);
}

function writeU32(target: Uint8Array, offset: number, value: number): void {
  target[offset] = (value >>> 24) & 0xff;
  target[offset + 1] = (value >>> 16) & 0xff;
  target[offset + 2] = (value >>> 8) & 0xff;
  target[offset + 3] = value & 0xff;
}

function readU32(source: Uint8Array, offset: number): number {
  return (
    source[offset]! * 0x1000000 +
    ((source[offset + 1]! << 16) | (source[offset + 2]! << 8) | source[offset + 3]!)
  );
}
