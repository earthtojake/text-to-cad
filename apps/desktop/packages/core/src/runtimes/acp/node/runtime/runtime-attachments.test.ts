import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { makeAcpHarness } from '#runtimes/acp/node/acp-test-support';
import { LocalAttachmentStore } from '#runtimes/acp/node/node/local-attachment-store';
import { AcpRuntime } from '#runtimes/acp/node/runtime/runtime';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

async function makeRuntime() {
  const root = await mkdtemp(join(tmpdir(), 'emdash-acp-attachments-'));
  roots.push(root);
  const h = makeAcpHarness({ attachmentStore: new LocalAttachmentStore(join(root, 'store')) });
  return new AcpRuntime(h.deps);
}

describe('AcpRuntime conversation-scoped attachments', () => {
  it('round-trips an attachment within its conversation scope', async () => {
    const rt = await makeRuntime();

    const uploaded = await rt.uploadAttachment({
      conversationId: 'conv-1',
      data: new Uint8Array([1, 2, 3]),
      mimeType: 'image/png',
      name: 'image.png',
    });
    if (!uploaded.success) throw new Error('upload failed');

    const downloaded = await rt.downloadAttachment('conv-1', uploaded.data.id);
    expect(downloaded).toEqual({
      success: true,
      data: { ref: uploaded.data, data: new Uint8Array([1, 2, 3]) },
    });

    // The same attachment id is invisible from another conversation.
    const crossConversation = await rt.downloadAttachment('conv-2', uploaded.data.id);
    expect(crossConversation.success).toBe(false);
  });

  it('deletes all of a conversation attachments on conversation deletion cleanup', async () => {
    const rt = await makeRuntime();

    const first = await rt.uploadAttachment({
      conversationId: 'conv-1',
      data: new Uint8Array([1]),
      mimeType: 'image/png',
      name: 'one.png',
    });
    const second = await rt.uploadAttachment({
      conversationId: 'conv-1',
      data: new Uint8Array([2]),
      mimeType: 'image/jpeg',
      name: 'two.jpg',
    });
    const other = await rt.uploadAttachment({
      conversationId: 'conv-2',
      data: new Uint8Array([3]),
      mimeType: 'image/gif',
      name: 'other.gif',
    });
    if (!first.success || !second.success || !other.success) throw new Error('upload failed');

    const cleaned = await rt.deleteConversationAttachments('conv-1');
    expect(cleaned).toEqual({ success: true, data: undefined });

    await expect(rt.downloadAttachment('conv-1', first.data.id)).resolves.toMatchObject({
      success: false,
    });
    await expect(rt.downloadAttachment('conv-1', second.data.id)).resolves.toMatchObject({
      success: false,
    });
    // Other conversations keep their attachments.
    await expect(rt.downloadAttachment('conv-2', other.data.id)).resolves.toMatchObject({
      success: true,
    });

    // Idempotent for already-cleaned conversations.
    await expect(rt.deleteConversationAttachments('conv-1')).resolves.toEqual({
      success: true,
      data: undefined,
    });
  });

  it('cleanup is a no-op success when no attachment store is configured', async () => {
    const h = makeAcpHarness();
    const rt = new AcpRuntime(h.deps);
    await expect(rt.deleteConversationAttachments('conv-1')).resolves.toEqual({
      success: true,
      data: undefined,
    });
  });
});
