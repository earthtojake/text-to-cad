import { EventEmitter } from 'node:events';
import { describe, expect, it } from 'vitest';
import type { WireMessage } from '../protocol';
import { streamTransport } from './stream';

class FakeReadable extends EventEmitter {
  push(chunk: string | Uint8Array): void {
    this.emit('data', chunk);
  }

  close(): void {
    this.emit('close');
  }
}

class FakeWritable {
  readonly chunks: Array<string | Uint8Array> = [];

  write(chunk: string | Uint8Array): void {
    this.chunks.push(chunk);
  }
}

describe('streamTransport', () => {
  it('parses length-prefixed messages split across chunks and coalesced in one chunk', () => {
    const senderInput = new FakeReadable();
    const senderOutput = new FakeWritable();
    const sender = streamTransport(senderInput, senderOutput);
    sender.post({ kind: 'cancel', id: 'call-1' });
    sender.post({ kind: 'detach', topic: 'topic' });

    const input = new FakeReadable();
    const output = new FakeWritable();
    const receiver = streamTransport(input, output);
    const messages: WireMessage[] = [];
    receiver.onMessage((message) => messages.push(message));
    const combined = concatChunks(senderOutput.chunks);
    input.push(combined.subarray(0, 3));
    input.push(combined.subarray(3, 11));
    input.push(combined.subarray(11));

    expect(messages).toEqual([
      { kind: 'cancel', id: 'call-1' },
      { kind: 'detach', topic: 'topic' },
    ]);
  });

  it('writes binary frames and emits disconnects', () => {
    const input = new FakeReadable();
    const output = new FakeWritable();
    const transport = streamTransport(input, output);
    let disconnected = false;
    transport.onDisconnect(() => {
      disconnected = true;
    });

    transport.post({ kind: 'detach', topic: 'topic' });
    input.close();

    expect(output.chunks).toHaveLength(1);
    expect(output.chunks[0]).toBeInstanceOf(Uint8Array);
    expect(disconnected).toBe(true);
  });

  it('round-trips blob chunks with raw bytes', () => {
    const senderInput = new FakeReadable();
    const senderOutput = new FakeWritable();
    const sender = streamTransport(senderInput, senderOutput);
    const payload = new Uint8Array([0, 10, 255, 42]);

    sender.post({ kind: 'blob-chunk', channel: 'blob', seq: 7, data: payload });

    const input = new FakeReadable();
    const output = new FakeWritable();
    const receiver = streamTransport(input, output);
    const messages: WireMessage[] = [];
    receiver.onMessage((message) => messages.push(message));
    const frame = concatChunks(senderOutput.chunks);
    expect(frame.includes(255)).toBe(true);

    input.push(frame);

    expect(messages).toEqual([{ kind: 'blob-chunk', channel: 'blob', seq: 7, data: payload }]);
  });

  it('disconnects on corrupt frames', () => {
    const input = new FakeReadable();
    const output = new FakeWritable();
    const transport = streamTransport(input, output);
    let disconnected = false;
    transport.onDisconnect(() => {
      disconnected = true;
    });

    input.push(new Uint8Array([0xff, 0, 0, 0, 0]));

    expect(disconnected).toBe(true);
  });
});

function concatChunks(chunks: Array<string | Uint8Array>): Uint8Array {
  const encoded = chunks.map((chunk) =>
    typeof chunk === 'string' ? new TextEncoder().encode(chunk) : chunk
  );
  const total = encoded.reduce((sum, chunk) => sum + chunk.byteLength, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of encoded) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out;
}
