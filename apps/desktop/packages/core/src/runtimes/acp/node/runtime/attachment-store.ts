import type { AttachmentMimeType, AttachmentRef } from '#runtimes/acp/api';

export interface StoredAttachment {
  ref: AttachmentRef;
  data: Uint8Array;
}

/**
 * Attachments are conversation-scoped (spec §3.6): every operation carries the owning
 * conversation id, and `deleteConversation` is the cleanup hook for conversation deletion.
 */
export interface AttachmentStore {
  put(input: {
    conversationId: string;
    data?: Uint8Array;
    name?: string;
    mimeType: AttachmentMimeType;
    originalPath?: string;
    /** Reuse a content-digest id for identical copied bytes (used for replayed tool output). */
    deduplicate?: boolean;
  }): Promise<AttachmentRef>;
  get(conversationId: string, attachmentId: string): Promise<StoredAttachment | null>;
  delete(conversationId: string, attachmentId: string): Promise<void>;
  /** Removes every attachment stored for the conversation; a no-op for absent conversations. */
  deleteConversation(conversationId: string): Promise<void>;
}
