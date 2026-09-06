# File Endpoints

`downloadFile()` and `uploadFile()` stream bytes through a dedicated blob channel
instead of embedding `Uint8Array` payloads in procedure inputs or results. The call
payload carries only typed input, metadata, and a channel id; byte chunks flow after
that over credit-based frames.

## Contracts

```ts
const api = defineContract({
  readAttachment: downloadFile({
    input: z.object({ id: z.string() }),
    error: z.object({ type: z.string() }),
  }),
  uploadAttachment: uploadFile({
    input: z.object({ conversationId: z.string() }),
    accept: ['image/png', 'image/jpeg'],
    maxSize: 25 * 1024 * 1024,
    result: attachmentRefSchema,
    error: z.object({ type: z.string() }),
  }),
});
```

File metadata uses `{ name, mimeType, size?, lastModified? }`. Download endpoints
may extend the metadata schema with endpoint-specific fields.

## Server Implementations

```ts
const controller = createController(api, {
  readAttachment: async ({ id }) => {
    const stored = await store.get(id);
    if (!stored) return err({ type: 'missing' });
    return ok({
      meta: {
        name: stored.ref.name,
        mimeType: stored.ref.mimeType,
        size: stored.data.byteLength,
      },
      source: stored.stream(),
    });
  },
  uploadAttachment: async (input, file) => {
    const bytes = await file.bytes();
    return ok(await store.put({ data: bytes, mimeType: file.mimeType, name: file.name }));
  },
});
```

The source can be an `AsyncIterable<Uint8Array>` or a readable stream-like value.
`WireFile` on upload exposes `stream()`, `bytes()`, `file()`, and `cancel()`.

## Client Usage

```ts
const downloaded = await client.readAttachment({ id });
if (downloaded.success) {
  for await (const chunk of downloaded.data.chunks()) {
    // incremental processing
  }
}

const uploaded = await client.uploadAttachment({ conversationId }, file);
```

Download handles are single-consumption: choose `chunks()`, `bytes()`, or `file()`.
`bytes()` verifies `meta.size` when present.

## Protocol Invariants

- Bytes are sent as `blob-chunk` frames and never inside `call`/`result` values.
- Producers send only after the consumer grants credit with `blob-pull`.
- Consumers keep a bounded local chunk mailbox aligned with the maximum granted
  credit. Overflow is treated as a protocol failure; blob chunks are never
  dropped.
- `blob-end` is the only successful EOF signal; disconnect before it is an error.
- `blob-close` cancels a channel and disposes the producer source.
- Frames for unknown channels are ignored so close/chunk races are harmless.
- Chunks are re-sliced to standalone buffers before posting to avoid cloning a much
  larger backing `ArrayBuffer`.

Structured-clone transports carry `Uint8Array` chunks natively. `streamTransport`
uses length-prefixed binary framing so workspace-server stdio/socket/SSH paths send
raw bytes with no base64 expansion.
