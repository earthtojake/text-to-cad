/** Portable identity: a file by its absolute path, a model by its document id; delivery addresses (HTTP/blob URLs) do not identify files. */
export type ResourceRef =
  | { kind: 'workspace-file'; path: string; revision?: string }
  /** A document the engine holds by its id alone (a model's): `path` is the id, never a filesystem path. */
  | { kind: 'cad-model'; path: string; revision?: string }
  | { kind: 'url'; url: string; revision?: string };
/** Zero-based UTF-16 coordinates; text ranges have an exclusive end. */
export interface TextPosition { line: number; character: number }
export type ReferenceTarget =
  | { kind: 'whole-resource' }
  | { kind: 'text-range'; start: TextPosition; end: TextPosition }
  | { kind: 'cad-selector'; selectors: readonly string[] };
export interface PromptReference { resource: ResourceRef; target: ReferenceTarget; label?: string }
export type PromptPart =
  | { id: string; kind: 'text'; text: string }
  | { id: string; kind: 'reference'; reference: PromptReference }
  /** `label` says what it is in a word or two ("Annotation"), for a message that names it by path; `path`, where it is already saved. */
  | { id: string; kind: 'attachment'; name: string; mimeType: string; content: Blob | PromiseLike<Blob>; about?: readonly string[]; label?: string; path?: string | PromiseLike<string>; inlineText?: string | PromiseLike<string | null> };
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
  /** Complete inline representation, used instead of the attachment path when present. */
  attachmentText?: (part: Extract<PromptPart, { kind: 'attachment' }>) => string | null | undefined;
  /** Where an attachment was saved, for one that travels as a file; nothing for one sent beside the text. */
  attachmentPath?: (part: Extract<PromptPart, { kind: 'attachment' }>) => string | null | undefined;
}
