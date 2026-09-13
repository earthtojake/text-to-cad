import { createHash } from 'node:crypto';
import { mkdir, readFile, rename, rm, stat, unlink, writeFile } from 'node:fs/promises';
import { basename, join } from 'node:path';
import type { AttachmentMimeType, AttachmentRef } from '#runtimes/acp/api';
import type {
  AttachmentStore,
  StoredAttachment,
} from '#runtimes/acp/node/runtime/attachment-store';

type AttachmentRecord = {
  ref: AttachmentRef;
  createdAt: number;
  source:
    | {
        kind: 'reference';
        originalPath: string;
        size: number;
        mtimeMs: number;
      }
    | {
        kind: 'copy';
        storedPath: string;
      };
};

/**
 * Per-conversation layout (spec §3.6): `<root>/conversations/<conversationId>/` holds that
 * conversation's `index.json` and copied bytes under `objects/`, so conversation deletion is
 * one recursive directory removal. Pre-v8 flat-keyed attachments (`<root>/index.json`,
 * `<root>/objects/`) are orphaned and left inert — no migration by design.
 */
export class LocalAttachmentStore implements AttachmentStore {
  private readonly conversationsDir: string;
  private readonly conversations = new Map<string, ConversationAttachmentStore>();
  private readonly deletedConversations = new Set<string>();
  private readonly conversationDeletions = new Map<string, Promise<void>>();

  constructor(rootDir: string) {
    this.conversationsDir = join(rootDir, 'conversations');
  }

  async put(input: {
    conversationId: string;
    data?: Uint8Array;
    name?: string;
    mimeType: AttachmentMimeType;
    originalPath?: string;
    deduplicate?: boolean;
  }): Promise<AttachmentRef> {
    if (this.deletedConversations.has(input.conversationId)) {
      throw new Error(`Attachment storage was deleted for conversation '${input.conversationId}'`);
    }
    return this.forConversation(input.conversationId).put(input);
  }

  async get(conversationId: string, attachmentId: string): Promise<StoredAttachment | null> {
    if (this.deletedConversations.has(conversationId)) return null;
    return this.forConversation(conversationId).get(attachmentId);
  }

  async delete(conversationId: string, attachmentId: string): Promise<void> {
    if (this.deletedConversations.has(conversationId)) return;
    return this.forConversation(conversationId).delete(attachmentId);
  }

  async deleteConversation(conversationId: string): Promise<void> {
    assertSafePathSegment(conversationId);
    const pendingDeletion = this.conversationDeletions.get(conversationId);
    if (pendingDeletion) {
      await pendingDeletion;
      return;
    }
    if (this.deletedConversations.has(conversationId)) return;
    this.deletedConversations.add(conversationId);
    const deletion = (async () => {
      const store = this.conversations.get(conversationId);
      if (store) {
        await store.deleteAll();
        this.conversations.delete(conversationId);
        return;
      }
      await rm(join(this.conversationsDir, conversationId), { recursive: true, force: true });
    })();
    this.conversationDeletions.set(conversationId, deletion);
    try {
      await deletion;
    } finally {
      this.conversationDeletions.delete(conversationId);
    }
  }

  private forConversation(conversationId: string): ConversationAttachmentStore {
    assertSafePathSegment(conversationId);
    let store = this.conversations.get(conversationId);
    if (!store) {
      store = new ConversationAttachmentStore(join(this.conversationsDir, conversationId));
      this.conversations.set(conversationId, store);
    }
    return store;
  }
}

/** Conversation ids are wire input used as a path segment; refuse anything path-like. */
function assertSafePathSegment(conversationId: string): void {
  if (
    conversationId.length === 0 ||
    conversationId === '.' ||
    conversationId === '..' ||
    conversationId.includes('/') ||
    conversationId.includes('\\') ||
    conversationId.includes('\0')
  ) {
    throw new Error(`Invalid conversation id for attachment storage: '${conversationId}'`);
  }
}

class ConversationAttachmentStore {
  private readonly indexPath: string;
  private readonly objectsDir: string;
  private readonly records = new Map<string, AttachmentRecord>();
  private loadPromise: Promise<void> | null = null;
  private mutationQueue = Promise.resolve();
  private persistQueue = Promise.resolve();
  private deleted = false;

  constructor(private readonly rootDir: string) {
    this.indexPath = join(rootDir, 'index.json');
    this.objectsDir = join(rootDir, 'objects');
  }

  async put(input: {
    data?: Uint8Array;
    name?: string;
    mimeType: AttachmentMimeType;
    originalPath?: string;
    deduplicate?: boolean;
  }): Promise<AttachmentRef> {
    if (this.deleted) throw new Error('Conversation attachment storage has been deleted');
    return this.enqueueMutation(() => this.putInternal(input));
  }

  private async putInternal(input: {
    data?: Uint8Array;
    name?: string;
    mimeType: AttachmentMimeType;
    originalPath?: string;
    deduplicate?: boolean;
  }): Promise<AttachmentRef> {
    await this.ensureLoaded();
    const id =
      input.deduplicate && input.data
        ? `sha256-${createHash('sha256')
            .update(input.mimeType)
            .update('\0')
            .update(input.data)
            .digest('hex')}`
        : crypto.randomUUID();
    const existing = this.records.get(id);
    if (existing) {
      if (!input.deduplicate || !input.data) return existing.ref;
      if (await this.copiedObjectMatches(existing, input.data)) return existing.ref;

      const repairedRef: AttachmentRef = {
        ...existing.ref,
        mimeType: input.mimeType,
      };
      const storedPath = join(this.objectsDir, id);
      await this.writeCopiedObject(storedPath, input.data);
      this.records.set(id, {
        ref: repairedRef,
        createdAt: existing.createdAt,
        source: { kind: 'copy', storedPath },
      });
      await this.persist();
      return repairedRef;
    }

    const ref: AttachmentRef = {
      id,
      name: input.name ?? (input.originalPath ? basename(input.originalPath) : 'attachment'),
      mimeType: input.mimeType,
    };

    if (input.originalPath) {
      const fileStat = await stat(input.originalPath);
      this.records.set(id, {
        ref,
        createdAt: Date.now(),
        source: {
          kind: 'reference',
          originalPath: input.originalPath,
          size: fileStat.size,
          mtimeMs: fileStat.mtimeMs,
        },
      });
      await this.persist();
      return ref;
    }

    const data = input.data;
    if (!data) {
      throw new Error('Attachment data is required when originalPath is not provided');
    }
    const storedPath = join(this.objectsDir, id);
    await this.writeCopiedObject(storedPath, data);
    this.records.set(id, {
      ref,
      createdAt: Date.now(),
      source: { kind: 'copy', storedPath },
    });
    await this.persist();
    return ref;
  }

  async get(id: string): Promise<StoredAttachment | null> {
    if (this.deleted) return null;
    await this.ensureLoaded();
    const record = this.records.get(id);
    if (!record) return null;
    try {
      const path =
        record.source.kind === 'reference' ? record.source.originalPath : record.source.storedPath;
      return {
        ref: record.ref,
        data: new Uint8Array(await readFile(path)),
      };
    } catch {
      return null;
    }
  }

  async delete(id: string): Promise<void> {
    if (this.deleted) return;
    return this.enqueueMutation(() => this.deleteInternal(id));
  }

  async deleteAll(): Promise<void> {
    if (this.deleted) return;
    this.deleted = true;
    return this.enqueueMutation(async () => {
      this.records.clear();
      await rm(this.rootDir, { recursive: true, force: true });
    });
  }

  private async deleteInternal(id: string): Promise<void> {
    await this.ensureLoaded();
    const record = this.records.get(id);
    if (!record) return;
    this.records.delete(id);
    if (record.source.kind === 'copy') {
      await unlink(record.source.storedPath).catch(() => undefined);
    }
    await this.persist();
  }

  private enqueueMutation<T>(operation: () => Promise<T>): Promise<T> {
    const result = this.mutationQueue.then(operation, operation);
    this.mutationQueue = result.then(
      () => undefined,
      () => undefined
    );
    return result;
  }

  private async copiedObjectMatches(record: AttachmentRecord, expected: Uint8Array): Promise<boolean> {
    if (record.source.kind !== 'copy') return false;
    try {
      const actual = await readFile(record.source.storedPath);
      return actual.equals(Buffer.from(expected.buffer, expected.byteOffset, expected.byteLength));
    } catch {
      return false;
    }
  }

  private async writeCopiedObject(storedPath: string, data: Uint8Array): Promise<void> {
    await mkdir(this.objectsDir, { recursive: true });
    const tmpPath = `${storedPath}.${process.pid}.${crypto.randomUUID()}.tmp`;
    try {
      await writeFile(tmpPath, data);
      await rename(tmpPath, storedPath);
    } finally {
      await unlink(tmpPath).catch(() => undefined);
    }
  }

  private async ensureLoaded(): Promise<void> {
    this.loadPromise ??= this.load();
    await this.loadPromise;
  }

  private async load(): Promise<void> {
    let contents: string;
    try {
      contents = await readFile(this.indexPath, 'utf8');
    } catch {
      return;
    }

    const parsed: unknown = JSON.parse(contents);
    if (!Array.isArray(parsed)) return;
    for (const value of parsed) {
      if (isAttachmentRecord(value)) {
        this.records.set(value.ref.id, value);
      }
    }
  }

  private persist(): Promise<void> {
    this.persistQueue = this.persistQueue.then(async () => {
      await mkdir(this.rootDir, { recursive: true });
      const tmpPath = `${this.indexPath}.${process.pid}.${Date.now()}.tmp`;
      await writeFile(tmpPath, JSON.stringify([...this.records.values()], null, 2));
      await rename(tmpPath, this.indexPath);
    });
    return this.persistQueue;
  }
}

function isAttachmentRecord(value: unknown): value is AttachmentRecord {
  if (!value || typeof value !== 'object') return false;
  const record = value as AttachmentRecord;
  if (!record.ref || typeof record.ref.id !== 'string') return false;
  if (typeof record.ref.name !== 'string' || typeof record.ref.mimeType !== 'string') return false;
  if (!record.source || typeof record.source !== 'object') return false;
  if (record.source.kind === 'reference') {
    return (
      typeof record.source.originalPath === 'string' &&
      typeof record.source.size === 'number' &&
      typeof record.source.mtimeMs === 'number'
    );
  }
  return record.source.kind === 'copy' && typeof record.source.storedPath === 'string';
}
