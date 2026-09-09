import { waitFor } from '@emdash/shared/testing';
import { describe, expect, it, vi } from 'vitest';
import {
  BLOB_CHUNK_SIZE,
  BLOB_MAX_CREDIT,
  BLOB_TOP_UP,
  BLOB_WINDOW,
  createBlobConsumer,
  createBlobProducer,
} from './blob-channel';
import type { WireMessage, WireTransport } from './protocol';

describe('createBlobConsumer', () => {
  it('requests initial credit and tops up after consumed chunks', async () => {
    const posts: WireMessage[] = [];
    const consumer = createBlobConsumer({ channel: 'c', post: (message) => posts.push(message) });
    const iterator = consumer.stream()[Symbol.asyncIterator]();
    const first = iterator.next();

    expect(posts).toEqual([{ kind: 'blob-pull', channel: 'c', credit: BLOB_WINDOW }]);

    for (let seq = 0; seq < BLOB_TOP_UP; seq += 1) {
      consumer.push(seq, new Uint8Array([seq]));
      const next = seq === 0 ? await first : await iterator.next();
      expect(next).toEqual({ done: false, value: new Uint8Array([seq]) });
    }

    expect(posts).toEqual([
      { kind: 'blob-pull', channel: 'c', credit: BLOB_WINDOW },
      { kind: 'blob-pull', channel: 'c', credit: BLOB_TOP_UP },
    ]);

    consumer.end();
    await expect(iterator.next()).resolves.toEqual({ done: true, value: undefined });
  });

  it('fails on out-of-order chunks', async () => {
    const consumer = createBlobConsumer({ channel: 'c', post: () => {} });
    consumer.push(1, new Uint8Array([1]));

    await expect(consumer.bytes()).rejects.toMatchObject({ code: 'HANDLER_ERROR' });
  });

  it('fails when the defensive buffer bound is exceeded', async () => {
    const consumer = createBlobConsumer({ channel: 'c', post: () => {} });
    for (let seq = 0; seq <= BLOB_MAX_CREDIT; seq += 1) {
      consumer.push(seq, new Uint8Array([seq]));
    }

    await expect(consumer.bytes()).rejects.toMatchObject({ code: 'HANDLER_ERROR' });
  });

  it('fails and notifies when max size is exceeded', async () => {
    const onMaxSizeExceeded = vi.fn();
    const consumer = createBlobConsumer({
      channel: 'c',
      post: () => {},
      maxSize: 1,
      onMaxSizeExceeded,
    });
    consumer.push(0, new Uint8Array([1, 2]));

    await expect(consumer.bytes()).rejects.toMatchObject({ code: 'HANDLER_ERROR' });
    expect(onMaxSizeExceeded).toHaveBeenCalledTimes(1);
  });

  it('throws cancelled for a pending stream when cancelled', async () => {
    const posts: WireMessage[] = [];
    const consumer = createBlobConsumer({ channel: 'c', post: (message) => posts.push(message) });
    const next = consumer.stream()[Symbol.asyncIterator]().next();

    consumer.cancel();

    await expect(next).rejects.toMatchObject({ code: 'CANCELLED' });
    expect(posts).toContainEqual({ kind: 'blob-close', channel: 'c' });
  });

  it('cancels abandoned streams', async () => {
    const posts: WireMessage[] = [];
    const consumer = createBlobConsumer({ channel: 'c', post: (message) => posts.push(message) });
    const iterator = consumer.stream()[Symbol.asyncIterator]();
    consumer.push(0, new Uint8Array([1]));

    await expect(iterator.next()).resolves.toEqual({ done: false, value: new Uint8Array([1]) });
    await iterator.return?.();

    expect(posts).toContainEqual({ kind: 'blob-close', channel: 'c' });
  });

  it('fails as disconnected when posting credit throws', async () => {
    const consumer = createBlobConsumer({
      channel: 'c',
      post: () => {
        throw new Error('offline');
      },
    });

    await expect(consumer.bytes()).rejects.toMatchObject({ code: 'DISCONNECTED' });
  });
});

describe('createBlobProducer', () => {
  it('caps granted credit', async () => {
    const posts: WireMessage[] = [];
    const producer = createBlobProducer({
      channel: 'c',
      source: sourceChunks(BLOB_MAX_CREDIT + 2),
      post: (message) => posts.push(message),
      idleTimeoutMs: 0,
    });

    producer.grant(1_000);

    await waitFor(() => blobChunks(posts).length === BLOB_MAX_CREDIT);
    expect(blobChunks(posts)).toHaveLength(BLOB_MAX_CREDIT);
    producer.close();
  });

  it('splits chunks larger than the blob frame size', async () => {
    const posts: WireMessage[] = [];
    const data = new Uint8Array(BLOB_CHUNK_SIZE + 1);
    const producer = createBlobProducer({
      channel: 'c',
      source: (async function* () {
        yield data;
      })(),
      post: (message) => posts.push(message),
      idleTimeoutMs: 0,
    });

    producer.grant(2);

    await waitFor(() => blobChunks(posts).length === 2);
    expect(blobChunks(posts).map((message) => message.data.byteLength)).toEqual([
      BLOB_CHUNK_SIZE,
      1,
    ]);
  });

  it('returns the source when posting a chunk throws', async () => {
    const returned = vi.fn();
    const producer = createBlobProducer({
      channel: 'c',
      source: {
        [Symbol.asyncIterator]() {
          return {
            async next() {
              return { done: false, value: new Uint8Array([1]) };
            },
            async return() {
              returned();
              return { done: true, value: undefined as never };
            },
          };
        },
      },
      post: throwingPost,
      idleTimeoutMs: 0,
    });

    producer.grant(1);

    await waitFor(() => returned.mock.calls.length === 1);
  });
});

function blobChunks(messages: WireMessage[]): Array<Extract<WireMessage, { kind: 'blob-chunk' }>> {
  return messages.filter(
    (message): message is Extract<WireMessage, { kind: 'blob-chunk' }> =>
      message.kind === 'blob-chunk'
  );
}

async function* sourceChunks(count: number): AsyncIterable<Uint8Array> {
  for (let index = 0; index < count; index += 1) {
    yield new Uint8Array([index]);
  }
}

function throwingPost(_message: Parameters<WireTransport['post']>[0]): void {
  throw new Error('offline');
}
