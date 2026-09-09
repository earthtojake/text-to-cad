import type { SessionUpdate } from '@agentclientprotocol/sdk';
import type { Logger } from '@emdash/shared/logger';
import { describe, expect, it, vi } from 'vitest';
import type { AttachmentStore } from './attachment-store';
import {
  persistToolOutputAttachments,
  redactToolOutputImageData,
  TOOL_OUTPUT_MAX_IMAGE_BYTES,
} from './tool-output-attachments';

function imageUpdate(data: string, mimeType = 'image/png'): SessionUpdate {
  return {
    sessionUpdate: 'tool_call_update',
    toolCallId: 'image-1',
    title: 'Image generation',
    status: 'completed',
    content: [
      {
        type: 'content',
        content: { type: 'image', data, mimeType, uri: 'file:///tmp/generated-cat.png' },
      },
    ],
    rawOutput: { status: 'completed', result: data },
  } as SessionUpdate;
}

function makeLogger(): Logger {
  const logger: Logger = {
    level: 'debug',
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    child: () => logger,
  };
  return logger;
}

function makeStore(): AttachmentStore & { put: ReturnType<typeof vi.fn> } {
  return {
    put: vi.fn(async (input) => ({
      id: 'sha256-image',
      name: input.name ?? 'image.png',
      mimeType: input.mimeType,
    })),
    get: vi.fn(),
    delete: vi.fn(),
    deleteConversation: vi.fn(),
  };
}

describe('provider tool output attachments', () => {
  it('persists supported image bytes and returns only a durable reference', async () => {
    const store = makeStore();
    const logger = makeLogger();
    const encoded = Buffer.from([1, 2, 3]).toString('base64');

    const attachments = await persistToolOutputAttachments({
      conversationId: 'conv-1',
      update: imageUpdate(encoded),
      attachmentStore: store,
      logger,
    });

    expect(store.put).toHaveBeenCalledWith({
      conversationId: 'conv-1',
      data: new Uint8Array([1, 2, 3]),
      name: 'generated-cat.png',
      mimeType: 'image/png',
      deduplicate: true,
    });
    expect(attachments).toEqual([
      { id: 'sha256-image', name: 'generated-cat.png', mimeType: 'image/png' },
    ]);
    expect(JSON.stringify(attachments)).not.toContain(encoded);
  });

  it.each([
    ['malformed base64', imageUpdate('%%%not-base64%%%'), 'invalid_base64'],
    [
      'unsupported MIME type',
      imageUpdate(Buffer.from('svg').toString('base64'), 'image/svg+xml'),
      'unsupported_mime_type',
    ],
  ])('ignores %s safely', async (_label, update, reason) => {
    const store = makeStore();
    const logger = makeLogger();

    await expect(
      persistToolOutputAttachments({
        conversationId: 'conv-1',
        update,
        attachmentStore: store,
        logger,
      })
    ).resolves.toBeUndefined();

    expect(store.put).not.toHaveBeenCalled();
    expect(logger.warn).toHaveBeenCalledWith(
      'SessionManager: ignored provider image output',
      expect.objectContaining({ reason })
    );
  });

  it('rejects provider images larger than 25 MiB before decoding', async () => {
    const store = makeStore();
    const logger = makeLogger();
    const tooLarge = 'A'.repeat(Math.ceil(TOOL_OUTPUT_MAX_IMAGE_BYTES / 3) * 4 + 1025);

    await expect(
      persistToolOutputAttachments({
        conversationId: 'conv-1',
        update: imageUpdate(tooLarge),
        attachmentStore: store,
        logger,
      })
    ).resolves.toBeUndefined();

    expect(store.put).not.toHaveBeenCalled();
    expect(logger.warn).toHaveBeenCalledWith(
      'SessionManager: ignored provider image output',
      expect.objectContaining({ reason: 'image_too_large' })
    );
  });

  it('redacts image bytes from tool content, raw output, and metadata in raw logs', () => {
    const encoded = Buffer.from('generated image bytes '.repeat(8)).toString('base64');
    const dataUri = `data:image/png;base64,${encoded}`;
    const update = {
      ...imageUpdate(encoded),
      content: [
        {
          type: 'content',
          content: { type: 'image', data: encoded, mimeType: 'image/png', uri: dataUri },
        },
      ],
      rawOutput: JSON.stringify({ result: dataUri, note: 'keep this text' }),
      _meta: { mirroredResult: encoded, mirroredUri: dataUri },
    } as SessionUpdate;

    const redacted = redactToolOutputImageData(update);

    expect(JSON.stringify(redacted)).not.toContain(encoded);
    expect(JSON.stringify(redacted)).not.toContain('data:image');
    expect(redacted).toMatchObject({
      content: [
        {
          type: 'content',
          content: {
            type: 'image',
            data: '',
            uri: undefined,
            _meta: {
              'emdash/attachment': { redacted: true },
            },
          },
        },
      ],
      rawOutput: JSON.stringify({ result: '', note: 'keep this text' }),
      _meta: { mirroredResult: '', mirroredUri: '' },
    });
  });
});
