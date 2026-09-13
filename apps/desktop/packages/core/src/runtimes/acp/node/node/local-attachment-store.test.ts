import { access, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { LocalAttachmentStore } from './local-attachment-store';

const CONV = 'conv-1';

const roots: string[] = [];

afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

async function makeRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), 'emdash-attachments-'));
  roots.push(root);
  return root;
}

function conversationDir(root: string, conversationId = CONV): string {
  return join(root, 'store', 'conversations', conversationId);
}

describe('LocalAttachmentStore', () => {
  it('stores references without copying original bytes', async () => {
    const root = await makeRoot();
    const sourcePath = join(root, 'source.png');
    await writeFile(sourcePath, new Uint8Array([1, 2, 3]));

    const store = new LocalAttachmentStore(join(root, 'store'));
    const ref = await store.put({
      conversationId: CONV,
      originalPath: sourcePath,
      mimeType: 'image/png',
      name: 'source.png',
    });
    const stored = await store.get(CONV, ref.id);

    expect(stored).toEqual({
      ref,
      data: new Uint8Array([1, 2, 3]),
    });
    await expect(access(join(conversationDir(root), 'objects', ref.id))).rejects.toThrow();
  });

  it('copies uploaded bytes into the conversation directory when no original path is provided', async () => {
    const root = await makeRoot();
    const store = new LocalAttachmentStore(join(root, 'store'));

    const ref = await store.put({
      conversationId: CONV,
      data: new Uint8Array([4, 5, 6]),
      mimeType: 'image/webp',
      name: 'copy.webp',
    });

    await expect(readFile(join(conversationDir(root), 'objects', ref.id))).resolves.toEqual(
      Buffer.from([4, 5, 6])
    );
    await expect(store.get(CONV, ref.id)).resolves.toEqual({
      ref,
      data: new Uint8Array([4, 5, 6]),
    });
  });

  it('deduplicates copied tool output by MIME-aware content digest across writes and restarts', async () => {
    const root = await makeRoot();
    const storeDir = join(root, 'store');
    const store = new LocalAttachmentStore(storeDir);
    const bytes = new Uint8Array([4, 5, 6]);

    const [first, repeated] = await Promise.all([
      store.put({
        conversationId: CONV,
        data: bytes,
        mimeType: 'image/png',
        name: 'first.png',
        deduplicate: true,
      }),
      store.put({
        conversationId: CONV,
        data: bytes,
        mimeType: 'image/png',
        name: 'replayed.png',
        deduplicate: true,
      }),
    ]);
    const afterRestart = await new LocalAttachmentStore(storeDir).put({
      conversationId: CONV,
      data: bytes,
      mimeType: 'image/png',
      name: 'after-restart.png',
      deduplicate: true,
    });
    const differentMime = await store.put({
      conversationId: CONV,
      data: bytes,
      mimeType: 'image/webp',
      name: 'same-bytes.webp',
      deduplicate: true,
    });

    expect(first.id).toMatch(/^sha256-[a-f0-9]{64}$/);
    expect(repeated).toEqual(first);
    expect(afterRestart).toEqual(first);
    expect(differentMime.id).not.toBe(first.id);
    await expect(readFile(join(conversationDir(root), 'objects', first.id))).resolves.toEqual(
      Buffer.from(bytes)
    );
  });

  it.each(['missing', 'corrupt'] as const)(
    'repairs a %s deduplicated object from replayed bytes after restart',
    async (damage) => {
      const root = await makeRoot();
      const storeDir = join(root, 'store');
      const bytes = new Uint8Array([4, 5, 6]);
      const first = await new LocalAttachmentStore(storeDir).put({
        conversationId: CONV,
        data: bytes,
        mimeType: 'image/png',
        name: 'first.png',
        deduplicate: true,
      });
      const objectPath = join(conversationDir(root), 'objects', first.id);
      if (damage === 'missing') {
        await rm(objectPath);
      } else {
        await writeFile(objectPath, new Uint8Array([9, 9, 9]));
      }

      const restartedStore = new LocalAttachmentStore(storeDir);
      const replayed = await restartedStore.put({
        conversationId: CONV,
        data: bytes,
        mimeType: 'image/png',
        name: 'replayed.png',
        deduplicate: true,
      });

      expect(replayed).toEqual(first);
      await expect(readFile(objectPath)).resolves.toEqual(Buffer.from(bytes));
      await expect(restartedStore.get(CONV, first.id)).resolves.toEqual({
        ref: first,
        data: bytes,
      });
    }
  );

  it('scopes attachments to their conversation', async () => {
    const root = await makeRoot();
    const store = new LocalAttachmentStore(join(root, 'store'));

    const ref = await store.put({
      conversationId: CONV,
      data: new Uint8Array([1]),
      mimeType: 'image/png',
      name: 'scoped.png',
    });

    await expect(store.get('conv-other', ref.id)).resolves.toBeNull();
    await expect(store.get(CONV, ref.id)).resolves.not.toBeNull();
  });

  it('persists the index across store instances', async () => {
    const root = await makeRoot();
    const sourcePath = join(root, 'source.jpg');
    await writeFile(sourcePath, new Uint8Array([7, 8, 9]));
    const storeDir = join(root, 'store');

    const ref = await new LocalAttachmentStore(storeDir).put({
      conversationId: CONV,
      originalPath: sourcePath,
      mimeType: 'image/jpeg',
      name: 'source.jpg',
    });

    await expect(new LocalAttachmentStore(storeDir).get(CONV, ref.id)).resolves.toEqual({
      ref,
      data: new Uint8Array([7, 8, 9]),
    });
  });

  it('returns null when a referenced file disappears', async () => {
    const root = await makeRoot();
    const sourcePath = join(root, 'source.gif');
    await writeFile(sourcePath, new Uint8Array([1]));
    const store = new LocalAttachmentStore(join(root, 'store'));
    const ref = await store.put({
      conversationId: CONV,
      originalPath: sourcePath,
      mimeType: 'image/gif',
      name: 'source.gif',
    });

    await rm(sourcePath);

    await expect(store.get(CONV, ref.id)).resolves.toBeNull();
  });

  it('does not delete original files for reference records', async () => {
    const root = await makeRoot();
    const sourcePath = join(root, 'source.png');
    await writeFile(sourcePath, new Uint8Array([1, 2, 3]));
    const store = new LocalAttachmentStore(join(root, 'store'));
    const ref = await store.put({
      conversationId: CONV,
      originalPath: sourcePath,
      mimeType: 'image/png',
      name: 'source.png',
    });

    await store.delete(CONV, ref.id);

    await expect(readFile(sourcePath)).resolves.toEqual(Buffer.from([1, 2, 3]));
    await expect(store.get(CONV, ref.id)).resolves.toBeNull();
  });

  it('deletes copied bytes for copy records', async () => {
    const root = await makeRoot();
    const store = new LocalAttachmentStore(join(root, 'store'));
    const ref = await store.put({
      conversationId: CONV,
      data: new Uint8Array([1, 2, 3]),
      mimeType: 'image/png',
      name: 'copy.png',
    });

    await store.delete(CONV, ref.id);

    await expect(access(join(conversationDir(root), 'objects', ref.id))).rejects.toThrow();
    await expect(store.get(CONV, ref.id)).resolves.toBeNull();
  });

  it('removes the whole conversation directory on conversation deletion', async () => {
    const root = await makeRoot();
    const store = new LocalAttachmentStore(join(root, 'store'));
    const ref = await store.put({
      conversationId: CONV,
      data: new Uint8Array([1, 2, 3]),
      mimeType: 'image/png',
      name: 'copy.png',
    });
    const otherRef = await store.put({
      conversationId: 'conv-other',
      data: new Uint8Array([9]),
      mimeType: 'image/png',
      name: 'other.png',
    });

    await store.deleteConversation(CONV);

    await expect(access(conversationDir(root))).rejects.toThrow();
    await expect(store.get(CONV, ref.id)).resolves.toBeNull();
    // Other conversations are untouched.
    await expect(store.get('conv-other', otherRef.id)).resolves.not.toBeNull();
    // Idempotent for absent conversations.
    await expect(store.deleteConversation(CONV)).resolves.toBeUndefined();
    await expect(store.deleteConversation('never-existed')).resolves.toBeUndefined();
  });

  it('waits for in-flight writes before deletion and cannot resurrect the conversation directory', async () => {
    const root = await makeRoot();
    const store = new LocalAttachmentStore(join(root, 'store'));
    type ConversationStoreTestAccess = {
      writeCopiedObject(storedPath: string, data: Uint8Array): Promise<void>;
    };
    type LocalStoreTestAccess = {
      forConversation(conversationId: string): ConversationStoreTestAccess;
    };
    const conversationStore = (store as unknown as LocalStoreTestAccess).forConversation(CONV);
    const originalWrite = conversationStore.writeCopiedObject.bind(conversationStore);
    let releaseWrite!: () => void;
    const writeReleased = new Promise<void>((resolve) => {
      releaseWrite = resolve;
    });
    let markWriteStarted!: () => void;
    const writeStarted = new Promise<void>((resolve) => {
      markWriteStarted = resolve;
    });
    conversationStore.writeCopiedObject = async (storedPath, data) => {
      markWriteStarted();
      await writeReleased;
      await originalWrite(storedPath, data);
    };

    const pendingPut = store.put({
      conversationId: CONV,
      data: new Uint8Array([1, 2, 3]),
      mimeType: 'image/png',
      name: 'in-flight.png',
      deduplicate: true,
    });
    await writeStarted;
    const firstDeletion = store.deleteConversation(CONV);
    let repeatedDeletionFinished = false;
    const repeatedDeletion = store.deleteConversation(CONV).then(() => {
      repeatedDeletionFinished = true;
    });
    await Promise.resolve();
    expect(repeatedDeletionFinished).toBe(false);

    releaseWrite();
    const [ref] = await Promise.all([pendingPut, firstDeletion, repeatedDeletion]);

    await expect(access(conversationDir(root))).rejects.toThrow();
    await expect(store.get(CONV, ref.id)).resolves.toBeNull();
    await expect(
      store.put({
        conversationId: CONV,
        data: new Uint8Array([4, 5, 6]),
        mimeType: 'image/png',
        name: 'too-late.png',
        deduplicate: true,
      })
    ).rejects.toThrow(/deleted/);
    await expect(access(conversationDir(root))).rejects.toThrow();
  });

  it('rejects path-like conversation ids', async () => {
    const root = await makeRoot();
    const store = new LocalAttachmentStore(join(root, 'store'));

    await expect(store.get('../escape', 'attachment-1')).rejects.toThrow(/Invalid conversation id/);
    await expect(store.deleteConversation('a/b')).rejects.toThrow(/Invalid conversation id/);
  });
});
