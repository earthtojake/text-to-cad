/** Portable identity: a file by its absolute path; delivery addresses (HTTP/blob URLs) do not identify files. */
export type ResourceRef =
  | { kind: 'workspace-file'; path: string; revision?: string }
  | { kind: 'url'; url: string; revision?: string };
/** Zero-based UTF-16 coordinates; text ranges have an exclusive end. */
export interface TextPosition { line: number; character: number }
export type ReferenceTarget =
  | { kind: 'whole-resource' }
  | { kind: 'text-range'; start: TextPosition; end: TextPosition }
  | { kind: 'cad-selector'; selectors: readonly string[] };
export interface PromptReference { resource: ResourceRef; target: ReferenceTarget; label?: string;
  /** A sentence saying what the selection is about (a board's check), written before its references. */
  summary?: string }
export type PromptPart =
  | { id: string; kind: 'text'; text: string }
  | { id: string; kind: 'reference'; reference: PromptReference }
  /** `label` says what it is in a word or two ("Sketch"), for a message that names it by path. */
  | { id: string; kind: 'attachment'; name: string; mimeType: string; content: Blob | Promise<Blob>; about?: readonly string[]; label?: string };
export interface PromptContext { schemaVersion: 1; operationId: string; parts: readonly PromptPart[] }
export interface PromptDestinationState {
  kind: 'composer' | 'clipboard' | 'unavailable';
  available: boolean;
  reason?: string;
  capabilities?: {
    attachments: 'none' | 'png' | 'images-and-text';
    maxParts: number;
    maxAttachmentBytes: number;
    maxTotalAttachmentBytes?: number;
    mixedTextAndImage: 'atomic' | 'representations' | 'unsupported';
  };
}
export type PromptDeliveryResult =
  | { status: 'added' | 'copied' | 'sent'; partIds: string[] }
  | { status: 'partial'; partIds: string[]; message: string }
  | { status: 'deferred' | 'cancelled' | 'failed'; message?: string };
/**
 * Called synchronously from the gesture: bind the target before awaiting attachments.
 * `deliver` hands the context to the destination the snapshot names: a composer's context for
 * the next message (`added`), or the clipboard (`copied`). `send`, where the host has a chat to
 * post to, posts the context as the person's message now (`sent`); absent, nothing can send.
 */
export interface PromptContextPort {
  getSnapshot(): PromptDestinationState;
  subscribe(listener: () => void): () => void;
  deliver(context: PromptContext): Promise<PromptDeliveryResult>;
  send?(context: PromptContext): Promise<PromptDeliveryResult>;
}
export interface PromptMessageOptions {
  /** Where an attachment was saved, for one that travels as a file; nothing for one sent beside the text. */
  attachmentPath?: (part: Extract<PromptPart, { kind: 'attachment' }>) => string | null | undefined;
}
