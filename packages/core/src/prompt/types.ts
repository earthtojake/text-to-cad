/** Portable identity: delivery addresses (HTTP/blob URLs) do not identify workspace files. */
export type ResourceRef =
  | { kind: 'workspace-file'; workspaceId: string; path: string; revision?: string }
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
  | { id: string; kind: 'attachment'; name: string; mimeType: string; content: Blob | Promise<Blob>; about?: readonly string[] }
  /** A note the person pinned to geometry: what it is about, and what they want done there. */
  | { id: string; kind: 'annotation'; references: readonly PromptReference[]; text: string };
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
  | { status: 'added' | 'copied'; partIds: string[] }
  | { status: 'partial'; partIds: string[]; message: string }
  | { status: 'deferred' | 'cancelled' | 'failed'; message?: string };
/** Called synchronously from the gesture: bind the target before awaiting attachments. */
export interface PromptContextPort {
  getSnapshot(): PromptDestinationState;
  subscribe(listener: () => void): () => void;
  deliver(context: PromptContext): Promise<PromptDeliveryResult>;
}
export interface PromptTextOptions { resolvePath?: (resource: ResourceRef) => string }
