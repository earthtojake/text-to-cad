import type { PromptContext, PromptFolders, PromptPart, PromptReference, PromptMessageOptions, PromptContextPort, PromptDeliveryResult, ResourceRef,
  SnapshotAnnotation, SnapshotPacket, SnapshotView } from './types.js';
export type * from './types.js';
export declare function validatePromptReference(reference: unknown): PromptReference;
export declare function validatePromptContext(context: unknown): PromptContext;
export declare function createPromptContext(parts: readonly PromptPart[], operationId?: string, options?: { folders?: PromptContext['folders'] }): PromptContext;
export declare function displayPath(path: string, folders?: PromptFolders | null): string;
/** A document's address as a message names it: a file as `displayPath` names it, a model by its id, a link as it is. */
export declare function promptAddress(resource: ResourceRef, folders?: PromptFolders | null): string;
export declare function referencePart(reference: PromptReference, id?: string): Extract<PromptPart, { kind: 'reference' }>;
export declare function textPart(text: string, id?: string): Extract<PromptPart, { kind: 'text' }>;
export declare function promptReferenceIds(reference: PromptReference): string[];
export declare function formatPromptReference(reference: PromptReference, folders?: PromptFolders | null): string;
export declare function parsePromptReference(text: string): PromptReference | null;
export declare function formatPromptContextText(context: PromptContext): string;
export declare function formatPromptMessage(context: PromptContext, options?: PromptMessageOptions): string;
export declare function resolvePromptMessage(context: PromptContext): Promise<string>;
export declare function resolveAttachmentPaths(context: PromptContext): Promise<Map<string, string>>;
export declare const unavailablePromptContext: PromptContextPort;
/** One delivery per operation id, a bound on deliveries in flight, and a bounded memory of completed ones. */
export interface PromptDeliveryLedger {
  deliver(operationId: string, start: () => Promise<PromptDeliveryResult> | PromptDeliveryResult): Promise<PromptDeliveryResult>;
}
export declare function createPromptDeliveryLedger(options?: { maxPending?: number; maxRemembered?: number; busyMessage?: string }): PromptDeliveryLedger;
/**
 * A Quick Edit's snapshot packet, made in the page from the views a prompt carries, its ink and a board's references,
 * shortened; `input` is the file's address as the message names it, `type` its document type (`cad snapshot`).
 * Null without a view.
 */
export declare function snapshotPacket(options: { input: string; type: string; views: readonly SnapshotView[];
  annotation?: SnapshotAnnotation | null; references?: readonly string[] | null }): SnapshotPacket | null;
/** A packet as a message carries it: compact JSON with no character a single-quoted shell argument ends at. */
export declare function snapshotPacketText(packet: SnapshotPacket): string;
