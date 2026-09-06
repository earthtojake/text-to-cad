import { err, ok } from '@emdash/shared';
import { waitFor } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import type { createController } from '../rpc/controller';
import { createTestWire } from '../testing';
import {
  BLOB_CHUNK_SIZE,
  blobSourceFromBytes,
  normalizeUploadFile,
  type BlobSource,
  type UploadFileValue,
} from './blob-channel';
import { defineContract, downloadFile, uploadFile } from './define';

const textEncoder = new TextEncoder();
const textDecoder = new TextDecoder();
const errorSchema = z.object({ type: z.string() });

const contract = defineContract({
  download: downloadFile({
    input: z.object({ id: z.string() }),
    error: errorSchema,
  }),
  upload: uploadFile({
    input: z.object({ id: z.string() }),
    result: z.object({ id: z.string(), bytes: z.number(), text: z.string() }),
    error: errorSchema,
  }),
});

describe('blob file endpoints', () => {
  it('downloads multi-chunk files byte-exactly with metadata', async () => {
    const data = sequenceBytes(BLOB_CHUNK_SIZE * 2 + 17);
    const { api } = setup({
      download: ({ id }) =>
        id === 'missing'
          ? err({ type: 'missing' })
          : ok({
              meta: { name: `${id}.bin`, mimeType: 'application/octet-stream', size: data.length },
              source: chunks(data, 31_000),
            }),
      upload: async ({ id }, file) =>
        ok({ id, bytes: (await file.bytes()).byteLength, text: 'unused' }),
    });

    const result = await api.download({ id: 'known' });

    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(result.data.meta).toMatchObject({ name: 'known.bin', size: data.length });
    expect(await result.data.bytes()).toEqual(data);
  });

  it('returns domain errors without opening a blob channel', async () => {
    const { api } = setup({
      download: () => err({ type: 'missing' }),
      upload: async ({ id }, file) =>
        ok({ id, bytes: (await file.bytes()).byteLength, text: 'unused' }),
    });

    await expect(api.download({ id: 'missing' })).resolves.toEqual(err({ type: 'missing' }));
  });

  it('uploads async iterable file sources without buffering the call input', async () => {
    const payload = textEncoder.encode('hello from upload');
    const { api } = setup({
      download: () =>
        ok({
          meta: { name: 'unused', mimeType: 'application/octet-stream', size: 0 },
          source: chunks(new Uint8Array()),
        }),
      upload: async ({ id }, file) => {
        const bytes = await file.bytes();
        return ok({ id, bytes: bytes.byteLength, text: textDecoder.decode(bytes) });
      },
    });

    await expect(
      api.upload(
        { id: 'up' },
        {
          name: 'upload.txt',
          mimeType: 'text/plain',
          size: payload.byteLength,
          source: chunks(payload, 3),
        }
      )
    ).resolves.toEqual(ok({ id: 'up', bytes: payload.byteLength, text: 'hello from upload' }));
  });

  it('exposes copied byte sources as blob sources', async () => {
    const data = new Uint8Array([1, 2, 3]);
    const source = blobSourceFromBytes(data) satisfies BlobSource;
    const iterator = source[Symbol.asyncIterator]();

    const first = await iterator.next();
    expect(first).toMatchObject({ done: false, value: new Uint8Array([1, 2, 3]) });
    if (!first.done) first.value[0] = 9;

    expect(data).toEqual(new Uint8Array([1, 2, 3]));
    await expect(iterator.next()).resolves.toMatchObject({ done: true });
  });

  it('fails bytes() when declared download size does not match received bytes', async () => {
    const { api } = setup({
      download: () =>
        ok({
          meta: { name: 'bad.bin', mimeType: 'application/octet-stream', size: 999 },
          source: chunks(new Uint8Array([1, 2, 3])),
        }),
      upload: async ({ id }, file) =>
        ok({ id, bytes: (await file.bytes()).byteLength, text: 'unused' }),
    });

    const result = await api.download({ id: 'bad' });

    expect(result.success).toBe(true);
    if (!result.success) return;
    await expect(result.data.bytes()).rejects.toMatchObject({ code: 'HANDLER_ERROR' });
  });

  it('cancels download sources when the handle is cancelled', async () => {
    let disposed = false;
    const { api } = setup({
      download: () =>
        ok({
          meta: { name: 'slow.bin', mimeType: 'application/octet-stream' },
          source: {
            [Symbol.asyncIterator]() {
              return {
                async next() {
                  return { done: false, value: new Uint8Array([1]) };
                },
                async return() {
                  disposed = true;
                  return { done: true, value: undefined as never };
                },
              };
            },
          },
        }),
      upload: async ({ id }, file) =>
        ok({ id, bytes: (await file.bytes()).byteLength, text: 'unused' }),
    });

    const result = await api.download({ id: 'slow' });
    expect(result.success).toBe(true);
    if (!result.success) return;

    const iterator = result.data.chunks()[Symbol.asyncIterator]();
    await expect(iterator.next()).resolves.toMatchObject({ done: false });
    result.data.cancel();

    await waitFor(() => disposed);
  });

  it('keeps upload meta structured-clone-safe (no source or functions leaked)', () => {
    const sourceMeta = normalizeUploadFile({
      name: 'upload.txt',
      mimeType: 'text/plain',
      size: 3,
      customKey: 'kept',
      source: chunks(new Uint8Array([1, 2, 3])),
    } as UploadFileValue).meta;
    expect('source' in sourceMeta).toBe(false);
    expect(sourceMeta).toMatchObject({ name: 'upload.txt', mimeType: 'text/plain', size: 3 });
    expect(sourceMeta.customKey).toBe('kept');

    const wireFileMeta = normalizeUploadFile({
      name: 'wire.bin',
      mimeType: 'application/octet-stream',
      size: 1,
      stream: () => chunks(new Uint8Array([1])),
      bytes: async () => new Uint8Array([1]),
      file: async () => ({ name: 'wire.bin', mimeType: 'application/octet-stream' }) as never,
      cancel: () => undefined,
    }).meta;
    expect(Object.values(wireFileMeta).some((value) => typeof value === 'function')).toBe(false);
    expect(wireFileMeta).toMatchObject({ name: 'wire.bin', size: 1 });
  });

  it('rejects double consumption of a download handle', async () => {
    const { api } = setup({
      download: () =>
        ok({
          meta: { name: 'once.bin', mimeType: 'application/octet-stream', size: 1 },
          source: chunks(new Uint8Array([1])),
        }),
      upload: async ({ id }, file) =>
        ok({ id, bytes: (await file.bytes()).byteLength, text: 'unused' }),
    });

    const result = await api.download({ id: 'once' });
    expect(result.success).toBe(true);
    if (!result.success) return;

    await result.data.bytes();
    expect(() => result.data.chunks()).toThrow();
  });
});

function setup(
  impl: Pick<Parameters<typeof createController<typeof contract>>[1], 'download' | 'upload'>
) {
  const wire = createTestWire(contract, impl, { validate: 'full' });
  return { api: wire.client, pair: wire.pair };
}

async function* chunks(data: Uint8Array, size = BLOB_CHUNK_SIZE): AsyncIterable<Uint8Array> {
  for (let offset = 0; offset < data.byteLength; offset += size) {
    yield data.subarray(offset, Math.min(data.byteLength, offset + size));
  }
}

function sequenceBytes(size: number): Uint8Array {
  const data = new Uint8Array(size);
  for (let i = 0; i < data.byteLength; i += 1) data[i] = i % 251;
  return data;
}
