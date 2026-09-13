import { createMailbox, MailboxClosedError } from '@emdash/shared/concurrency';
import { systemClock, type Clock, type TimerHandle } from '@emdash/shared/scheduling';
import { WireError, type WireFileMeta, type WireTransport } from './protocol';

export const BLOB_CHUNK_SIZE = 64 * 1024;
export const BLOB_WINDOW = 16;
export const BLOB_TOP_UP = 8;
export const BLOB_MAX_CREDIT = 64;
export const BLOB_IDLE_TIMEOUT_MS = 30_000;

export type ReadableStreamLike = {
  getReader(): {
    read(): Promise<{ done: boolean; value?: Uint8Array }>;
    releaseLock?(): void;
    cancel?(reason?: unknown): Promise<void> | void;
  };
};

export type BlobSource = AsyncIterable<Uint8Array> | ReadableStreamLike;

const downloadFileOpenSymbol: unique symbol = Symbol('wire.downloadFileOpen');

export type DownloadFileOpen = {
  readonly [downloadFileOpenSymbol]: true;
  readonly meta: WireFileMeta;
  readonly source: BlobSource;
};

export function markDownloadFileOpen(meta: WireFileMeta, source: BlobSource): DownloadFileOpen {
  return { [downloadFileOpenSymbol]: true, meta, source };
}

export function isDownloadFileOpenResult(
  value: unknown
): value is { success: true; data: DownloadFileOpen } {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { success?: unknown }).success === true &&
    typeof (value as { data?: unknown }).data === 'object' &&
    (value as { data?: { [downloadFileOpenSymbol]?: unknown } }).data?.[downloadFileOpenSymbol] ===
      true
  );
}

export type FileLike = WireFileMeta & {
  stream(): BlobSource;
  arrayBuffer?(): Promise<ArrayBuffer>;
};

export type UploadFileValue =
  | WireFile
  | FileLike
  | {
      name: string;
      mimeType: string;
      size?: number;
      lastModified?: number;
      source: BlobSource;
    };

export type WireFile = WireFileMeta & {
  stream(): AsyncIterable<Uint8Array>;
  bytes(): Promise<Uint8Array>;
  file(): Promise<FileLike>;
  cancel(): void;
};

export type BlobDownloadHandle<Meta extends WireFileMeta = WireFileMeta> = {
  readonly meta: Meta;
  chunks(): AsyncIterable<Uint8Array>;
  bytes(): Promise<Uint8Array>;
  file(): Promise<FileLike>;
  cancel(): void;
};

export type BlobProducer = {
  grant(credit: number): void;
  close(): void;
};

export type BlobConsumer = {
  readonly channel: string;
  push(seq: number, data: Uint8Array): void;
  end(): void;
  fail(error: Error): void;
  stream(): AsyncIterable<Uint8Array>;
  bytes(): Promise<Uint8Array>;
  cancel(): void;
};

type NormalizedIterator = AsyncIterator<Uint8Array> & {
  return?(value?: unknown): Promise<IteratorResult<Uint8Array>> | IteratorResult<Uint8Array>;
};

export function createBlobProducer(options: {
  channel: string;
  source: BlobSource;
  post: WireTransport['post'];
  onClose?: () => void;
  idleTimeoutMs?: number;
  clock?: Clock;
}): BlobProducer {
  const clock = options.clock ?? systemClock;
  const iterator = normalizeSource(options.source);
  let closed = false;
  let credit = 0;
  let seq = 0;
  let pumping = false;
  let carry: Uint8Array | undefined;
  const idleTimer: TimerHandle | undefined =
    options.idleTimeoutMs === 0
      ? undefined
      : clock.schedule(options.idleTimeoutMs ?? BLOB_IDLE_TIMEOUT_MS, () => close(), {
          unref: true,
        });

  function safePost(message: Parameters<WireTransport['post']>[0]): void {
    try {
      options.post(message);
    } catch {
      close();
    }
  }

  async function pump(): Promise<void> {
    if (pumping || closed) return;
    pumping = true;
    clearIdle();
    try {
      while (!closed && credit > 0) {
        const next = await nextChunk(iterator, carry);
        carry = next.carry;
        if (!next.chunk) {
          safePost({ kind: 'blob-end', channel: options.channel });
          closeWithoutReturn();
          return;
        }
        credit -= 1;
        safePost({ kind: 'blob-chunk', channel: options.channel, seq: seq++, data: next.chunk });
      }
    } catch (error) {
      safePost({
        kind: 'blob-error',
        channel: options.channel,
        error:
          error instanceof WireError
            ? { code: error.code, message: error.message }
            : {
                code: 'HANDLER_ERROR',
                message: error instanceof Error ? error.message : String(error),
              },
      });
      closeWithoutReturn();
    } finally {
      pumping = false;
    }
  }

  function grant(addedCredit: number): void {
    if (closed || !Number.isFinite(addedCredit) || addedCredit <= 0) return;
    credit = Math.min(BLOB_MAX_CREDIT, credit + Math.floor(addedCredit));
    void pump();
  }

  function clearIdle(): void {
    idleTimer?.dispose();
  }

  function closeWithoutReturn(): void {
    if (closed) return;
    closed = true;
    clearIdle();
    options.onClose?.();
  }

  function close(): void {
    if (closed) return;
    closed = true;
    clearIdle();
    void iterator.return?.();
    options.onClose?.();
  }

  return { grant, close };
}

export function createBlobConsumer(options: {
  channel: string;
  post: WireTransport['post'];
  maxSize?: number;
  onMaxSizeExceeded?: () => void;
}): BlobConsumer {
  const chunks = createMailbox<Uint8Array>({ capacity: BLOB_MAX_CREDIT, overflow: 'reject' });
  let expectedSeq = 0;
  let receivedBytes = 0;
  let cancelled = false;
  let started = false;
  let consumedSincePull = 0;

  function safePost(message: Parameters<WireTransport['post']>[0]): void {
    try {
      options.post(message);
    } catch {
      fail(new WireError('DISCONNECTED', 'Wire transport disconnected'));
    }
  }

  function requestInitialCredit(): void {
    if (started) return;
    started = true;
    safePost({ kind: 'blob-pull', channel: options.channel, credit: BLOB_WINDOW });
  }

  function topUp(): void {
    consumedSincePull += 1;
    if (consumedSincePull < BLOB_TOP_UP) return;
    consumedSincePull = 0;
    safePost({ kind: 'blob-pull', channel: options.channel, credit: BLOB_TOP_UP });
  }

  function push(seq: number, data: Uint8Array): void {
    if (cancelled || chunks.state !== 'open') return;
    if (seq !== expectedSeq) {
      fail(
        new WireError(
          'HANDLER_ERROR',
          `Blob channel '${options.channel}' received out-of-order chunk`
        )
      );
      return;
    }
    expectedSeq += 1;
    receivedBytes += data.byteLength;
    if (options.maxSize !== undefined && receivedBytes > options.maxSize) {
      options.onMaxSizeExceeded?.();
      fail(new WireError('HANDLER_ERROR', 'Blob exceeded maximum size'));
      return;
    }
    const result = chunks.tryOffer(copyBytes(data));
    if (result.kind !== 'accepted') {
      fail(new WireError('HANDLER_ERROR', `Blob channel '${options.channel}' exceeded credit`));
    }
  }

  function end(): void {
    if (cancelled || chunks.state !== 'open') return;
    chunks.close();
  }

  function fail(nextError: Error): void {
    if (cancelled || chunks.state !== 'open') return;
    chunks.fail(nextError);
  }

  function cancel(): void {
    if (cancelled) return;
    cancelled = true;
    chunks.dispose();
    safePost({ kind: 'blob-close', channel: options.channel });
  }

  async function* stream(): AsyncIterable<Uint8Array> {
    requestInitialCredit();
    try {
      for (;;) {
        let chunk: Uint8Array;
        try {
          chunk = await chunks.take();
        } catch (error) {
          if (cancelled) throw new WireError('CANCELLED', 'Blob stream cancelled');
          if (error instanceof MailboxClosedError) return;
          throw error;
        }
        topUp();
        yield chunk;
      }
    } finally {
      if (chunks.state === 'open' && !cancelled) cancel();
    }
  }

  async function bytes(): Promise<Uint8Array> {
    const chunks: Uint8Array[] = [];
    let total = 0;
    for await (const chunk of stream()) {
      chunks.push(chunk);
      total += chunk.byteLength;
    }
    return concatBytes(chunks, total);
  }

  return { channel: options.channel, push, end, fail, stream, bytes, cancel };
}

export function createSingleUseDownloadHandle<Meta extends WireFileMeta>(
  meta: Meta,
  consumer: BlobConsumer
): BlobDownloadHandle<Meta> {
  let consumed = false;

  function claim(): void {
    if (consumed) throw new WireError('HANDLER_ERROR', 'Blob handle can only be consumed once');
    consumed = true;
  }

  async function bytes(): Promise<Uint8Array> {
    claim();
    const data = await consumer.bytes();
    verifySize(meta, data.byteLength);
    return data;
  }

  return {
    meta,
    chunks() {
      claim();
      return consumer.stream();
    },
    bytes,
    async file() {
      const data = await bytes();
      return makeFileLike(meta, data);
    },
    cancel: () => consumer.cancel(),
  };
}

export function createWireFile(
  meta: WireFileMeta,
  consumer: BlobConsumer,
  options: { verifySize?: boolean } = {}
): WireFile {
  let consumed = false;

  function claim(): void {
    if (consumed) throw new WireError('HANDLER_ERROR', 'WireFile can only be consumed once');
    consumed = true;
  }

  async function bytes(): Promise<Uint8Array> {
    claim();
    const data = await consumer.bytes();
    if (options.verifySize !== false) verifySize(meta, data.byteLength);
    return data;
  }

  return {
    ...meta,
    stream() {
      claim();
      return consumer.stream();
    },
    bytes,
    async file() {
      const data = await bytes();
      return makeFileLike(meta, data);
    },
    cancel: () => consumer.cancel(),
  };
}

export function normalizeUploadFile(input: UploadFileValue): {
  meta: WireFileMeta;
  source: BlobSource;
} {
  if (isWireFile(input)) return { meta: fileMeta(input), source: input.stream() };
  if (hasSource(input)) {
    const { source, ...meta } = input;
    return { meta: fileMeta(meta), source };
  }
  const maybeFile = input as FileLike;
  return {
    meta: {
      name: maybeFile.name,
      mimeType:
        maybeFile.mimeType ?? (maybeFile as { type?: string }).type ?? 'application/octet-stream',
      size: maybeFile.size,
      lastModified: maybeFile.lastModified,
    },
    source: maybeFile.stream(),
  };
}

function hasSource(value: UploadFileValue): value is {
  name: string;
  mimeType: string;
  size?: number;
  lastModified?: number;
  source: BlobSource;
} {
  return typeof value === 'object' && value !== null && 'source' in value;
}

export function concatBytes(chunks: Uint8Array[], total?: number): Uint8Array {
  const size = total ?? chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0);
  const out = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return out;
}

export function copyBytes(chunk: Uint8Array): Uint8Array {
  return new Uint8Array(chunk).slice();
}

export async function* blobSourceFromBytes(data: Uint8Array): AsyncIterable<Uint8Array> {
  yield copyBytes(data);
}

function isWireFile(value: unknown): value is WireFile {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { stream?: unknown }).stream === 'function' &&
    typeof (value as { bytes?: unknown }).bytes === 'function' &&
    typeof (value as { cancel?: unknown }).cancel === 'function'
  );
}

function fileMeta(value: WireFileMeta): WireFileMeta {
  // The meta travels inside the `call` message envelope, so it must stay
  // structured-clone-safe: drop functions (e.g. WireFile methods) while
  // preserving extra custom meta keys.
  const extras: Record<string, unknown> = {};
  for (const [key, entry] of Object.entries(value)) {
    if (typeof entry === 'function') continue;
    extras[key] = entry;
  }
  return {
    ...extras,
    name: value.name,
    mimeType: value.mimeType,
    size: value.size,
    lastModified: value.lastModified,
  };
}

async function nextChunk(
  iterator: NormalizedIterator,
  carry: Uint8Array | undefined
): Promise<{ chunk?: Uint8Array; carry?: Uint8Array }> {
  if (carry && carry.byteLength > 0) return splitChunk(carry);
  for (;;) {
    const next = await iterator.next();
    if (next.done) return {};
    if (!next.value || next.value.byteLength === 0) continue;
    return splitChunk(next.value);
  }
}

function splitChunk(chunk: Uint8Array): { chunk: Uint8Array; carry?: Uint8Array } {
  if (chunk.byteLength <= BLOB_CHUNK_SIZE) return { chunk: copyBytes(chunk) };
  return {
    chunk: copyBytes(chunk.subarray(0, BLOB_CHUNK_SIZE)),
    carry: chunk.subarray(BLOB_CHUNK_SIZE),
  };
}

function normalizeSource(source: BlobSource): NormalizedIterator {
  if (isAsyncIterable(source)) return source[Symbol.asyncIterator]();
  const reader = source.getReader();
  return {
    next: () => reader.read() as Promise<IteratorResult<Uint8Array>>,
    async return() {
      await reader.cancel?.();
      reader.releaseLock?.();
      return { done: true, value: undefined as never };
    },
  };
}

function isAsyncIterable(value: BlobSource): value is AsyncIterable<Uint8Array> {
  return Symbol.asyncIterator in value;
}

function verifySize(meta: WireFileMeta, actualSize: number): void {
  if (meta.size === undefined || meta.size === actualSize) return;
  throw new WireError(
    'HANDLER_ERROR',
    `Blob size mismatch: expected ${meta.size} bytes, received ${actualSize} bytes`
  );
}

function makeFileLike(meta: WireFileMeta, data: Uint8Array): FileLike {
  const blobCtor = (
    globalThis as unknown as {
      Blob?: new (parts: Uint8Array[], opts?: { type?: string }) => unknown;
    }
  ).Blob;
  const fileCtor = (
    globalThis as unknown as {
      File?: new (
        parts: Uint8Array[],
        name: string,
        opts?: { type?: string; lastModified?: number }
      ) => FileLike;
    }
  ).File;
  if (fileCtor) {
    return new fileCtor([data], meta.name, {
      type: meta.mimeType,
      lastModified: meta.lastModified,
    });
  }
  if (blobCtor) {
    const blob = new blobCtor([data], { type: meta.mimeType }) as {
      size: number;
      arrayBuffer?: () => Promise<ArrayBuffer>;
      stream?: () => BlobSource;
    };
    return {
      ...meta,
      size: meta.size ?? blob.size,
      arrayBuffer: blob.arrayBuffer?.bind(blob),
      stream: blob.stream ? () => blob.stream?.() as BlobSource : () => blobSourceFromBytes(data),
    };
  }
  return {
    ...meta,
    size: meta.size ?? data.byteLength,
    arrayBuffer: async () => data.slice().buffer as ArrayBuffer,
    stream: () => blobSourceFromBytes(data),
  };
}
