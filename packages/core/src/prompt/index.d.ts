import type { PromptContext, PromptPart, PromptReference, PromptTextOptions, PromptContextPort, PromptDeliveryResult } from './types.js';
export type * from './types.js';
export declare function validatePromptReference(reference: unknown): PromptReference;
export declare function validatePromptContext(context: unknown): PromptContext;
export declare function createPromptContext(parts: readonly PromptPart[], operationId?: string): PromptContext;
export declare function referencePart(reference: PromptReference, id?: string): Extract<PromptPart, { kind: 'reference' }>;
export declare function textPart(text: string, id?: string): Extract<PromptPart, { kind: 'text' }>;
export declare function annotationPart(references: readonly PromptReference[], text: string, id?: string): Extract<PromptPart, { kind: 'annotation' }>;
export declare function formatPromptAnnotation(part: { references: readonly PromptReference[]; text: string }, options?: PromptTextOptions & { labels?: boolean }): string;
export declare function formatPromptReference(reference: PromptReference, options?: PromptTextOptions): string;
export declare function formatPromptContextText(context: PromptContext, options?: PromptTextOptions): string;
export declare const unavailablePromptContext: PromptContextPort;
/** One delivery per operation id, a bound on deliveries in flight, and a bounded memory of completed ones. */
export interface PromptDeliveryLedger {
  deliver(operationId: string, start: () => Promise<PromptDeliveryResult> | PromptDeliveryResult): Promise<PromptDeliveryResult>;
}
export declare function createPromptDeliveryLedger(options?: { maxPending?: number; maxRemembered?: number; busyMessage?: string }): PromptDeliveryLedger;
