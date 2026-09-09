import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { SessionUpdate } from '@agentclientprotocol/sdk';
import { isOk } from '@emdash/shared';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { makeAcpHarness, makeStartInput } from '#runtimes/acp/node/acp-test-support';
import { LocalAttachmentStore } from '#runtimes/acp/node/node/local-attachment-store';
import type { AttachmentStore } from './attachment-store';
import { AcpRuntime } from './runtime';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

async function makeRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'emdash-tool-output-'));
  roots.push(root);
  return root;
}

function imageUpdate(data: string): SessionUpdate {
  const dataUri = `data:image/png;base64,${data}`;
  return {
    sessionUpdate: 'tool_call_update',
    toolCallId: 'image-1',
    title: 'Image generation',
    kind: 'other',
    status: 'completed',
    content: [
      {
        type: 'content',
        content: { type: 'image', data, mimeType: 'image/png', uri: dataUri },
      },
    ],
    rawOutput: JSON.stringify({ result: dataUri, note: 'generation complete' }),
    _meta: { mirroredImage: data, mirroredUri: dataUri },
  } as SessionUpdate;
}

describe('ACP tool output image ingress', () => {
  it('stores image output once and keeps only deduplicated references in transcript and raw log', async () => {
    const root = await makeRoot();
    const attachmentStore = new LocalAttachmentStore(join(root, 'attachments'));
    const h = makeAcpHarness({ attachmentStore });
    const rt = new AcpRuntime(h.deps);
    const started = await rt.startSession(makeStartInput({ conversationId: 'conv-image' }));
    expect(isOk(started)).toBe(true);
    const encoded = Buffer.from([1, 2, 3]).toString('base64');

    await h.client().sessionUpdate({ sessionId: 'session-1', update: imageUpdate(encoded) });
    await h.client().sessionUpdate({ sessionId: 'session-1', update: imageUpdate(encoded) });

    const history = rt.getChatHistory('conv-image');
    expect(JSON.stringify(history)).not.toContain(encoded);
    expect(JSON.stringify(history)).not.toContain('data:image');
    expect(history.active?.items).toHaveLength(1);
    expect(history.active?.items[0]).toMatchObject({
      kind: 'unknown-tool-call',
      attachments: [
        {
          id: expect.stringMatching(/^sha256-[a-f0-9]{64}$/),
          name: 'generated-image-1.png',
          mimeType: 'image/png',
        },
      ],
    });
    const item = history.active?.items[0];
    if (!item || !('attachments' in item) || !item.attachments?.[0]) {
      throw new Error('expected tool attachment');
    }
    await expect(rt.downloadAttachment('conv-image', item.attachments[0].id)).resolves.toEqual({
      success: true,
      data: { ref: item.attachments[0], data: new Uint8Array([1, 2, 3]) },
    });

    const raw = rt.exportRawAcpLog('conv-image');
    expect(isOk(raw)).toBe(true);
    if (isOk(raw)) {
      expect(raw.data).not.toContain(encoded);
      expect(raw.data).not.toContain('data:image');
      expect(raw.data).toContain('emdash/attachment');
      expect(raw.data).toContain('generation complete');
    }
  });

  it('awaits durable image storage before applying later updates from the same session', async () => {
    const root = await makeRoot();
    const localStore = new LocalAttachmentStore(join(root, 'attachments'));
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const attachmentStore: AttachmentStore = {
      put: vi.fn(async (input) => {
        await gate;
        return localStore.put(input);
      }),
      get: (conversationId, attachmentId) => localStore.get(conversationId, attachmentId),
      delete: (conversationId, attachmentId) => localStore.delete(conversationId, attachmentId),
      deleteConversation: (conversationId) => localStore.deleteConversation(conversationId),
    };
    const h = makeAcpHarness({ attachmentStore });
    const rt = new AcpRuntime(h.deps);
    await rt.startSession(makeStartInput({ conversationId: 'conv-order' }));
    const encoded = Buffer.from([4, 5, 6]).toString('base64');

    const image = h
      .client()
      .sessionUpdate({ sessionId: 'session-1', update: imageUpdate(encoded) });
    const message = h.client().sessionUpdate({
      sessionId: 'session-1',
      update: {
        sessionUpdate: 'agent_message_chunk',
        content: { type: 'text', text: 'Finished generating.' },
      },
    });
    await Promise.resolve();
    await Promise.resolve();
    expect(rt.getChatHistory('conv-order').active).toBeNull();

    release();
    await Promise.all([image, message]);

    expect(rt.getChatHistory('conv-order').active?.items.map((item) => item.kind)).toEqual([
      'unknown-tool-call',
      'message',
    ]);
  });

  it('reuses the same attachment id when a provider replays image output', async () => {
    const root = await makeRoot();
    const attachmentStore = new LocalAttachmentStore(join(root, 'attachments'));
    const h = makeAcpHarness({ attachmentStore });
    const rt = new AcpRuntime(h.deps);
    const encoded = Buffer.from([7, 8, 9]).toString('base64');
    h.agent.loadSession = vi.fn(async () => {
      await h.client().sessionUpdate({
        sessionId: 'session-old',
        update: imageUpdate(encoded),
      });
      await h.client().sessionUpdate({
        sessionId: 'session-old',
        update: imageUpdate(encoded),
      });
      return {};
    });

    const resumed = await rt.resumeSession({
      ...makeStartInput({ conversationId: 'conv-replay-image' }),
      sessionId: 'session-old',
    });

    expect(isOk(resumed)).toBe(true);
    if (!isOk(resumed)) return;
    expect(resumed.data.turns[0].items[0]).toMatchObject({
      attachments: [
        {
          id: expect.stringMatching(/^sha256-[a-f0-9]{64}$/),
          mimeType: 'image/png',
        },
      ],
    });
  });
});
