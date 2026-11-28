/** Portable identity: a file by its absolute path, a model by its document id; delivery addresses (HTTP/blob URLs) do not identify files. */
export type ResourceRef =
  | { kind: 'workspace-file'; path: string; revision?: string }
  /** A document the engine holds by its id alone (a model's): `path` is the id, never a filesystem path. */
  | { kind: 'cad-model'; path: string; revision?: string }
  /** A document by its link (a shared model's page): whole, or what is picked in it, in either selector grammar. */
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
/** The workspace the agent reading a message works in and the person's home, `/`-separated: how a message names each file (`displayPath`). */
export interface PromptFolders { start?: string; home?: string }
/** `folders`, where the host knows them: a message names its files by them; the parts keep the absolute paths. */
export interface PromptContext { schemaVersion: 1; operationId: string; parts: readonly PromptPart[]; folders?: PromptFolders | PromiseLike<PromptFolders | null> }
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
  /** The folders the message names files by (`displayPath`); none, each by its absolute path. */
  folders?: PromptFolders | null;
}
/**
 * A view a Quick Edit's snapshot packet carries (`snapshotPacket`): a snapshot job's own words, by the label its ink
 * names it by ("view 1", "current view"), its picture's size (`width`, `height`) beside its camera.
 */
export interface SnapshotView {
  label: string;
  camera: { position: number[]; target: number[]; up: number[]; orthographicHalfHeight: number; zoom?: number } | string;
  width?: number;
  height?: number;
  display?: Record<string, unknown> & { hidden?: string[]; isolated?: string[] };
  kinematics?: Record<string, unknown>;
  jointValues?: Record<string, number>;
  animation?: { clip: string; time: number };
  selection?: { hide?: string[]; focus?: string[] };
}
/** The ink a snapshot packet carries: an annotation file's document (`@cad/core/common/annotation.js`). */
export interface SnapshotAnnotation { units?: string; parts?: Record<string, unknown>; marks: ReadonlyArray<Record<string, unknown>> }
/** One job of a snapshot packet: a view, its picture named by its label alone. */
export interface SnapshotJob {
  camera: SnapshotView['camera'];
  display?: SnapshotView['display'];
  kinematics?: SnapshotView['kinematics'];
  jointValues?: SnapshotView['jointValues'];
  animation?: SnapshotView['animation'];
  selection?: SnapshotView['selection'];
  /** A 3D view's framing; a drawing's view has none. */
  output?: { padding: 0; tightFrame: false };
  outputs: Array<{ label: string; width?: number; height?: number }>;
}
/** A Quick Edit's snapshot packet: what `cad snapshot --job` draws again, made in the page. */
export interface SnapshotPacket {
  /** The file's address, as the message's `File:` line names it. */
  input: string;
  jobs: SnapshotJob[];
  /** What a board's prompt names in it, which `--job` lights. */
  references?: string[];
  annotation?: { units?: string; parts?: Record<string, unknown>; marks: Array<Record<string, unknown>> };
  /** With ink: the parts the view it was last drawn in hid and isolated, by their selectors within the file. */
  hidden?: string[];
  isolated?: string[];
}
