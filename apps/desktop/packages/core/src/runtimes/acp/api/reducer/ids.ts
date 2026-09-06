/**
 * Deterministic, stable id synthesis for transcript items.
 *
 * Ids are synthesized once in the parser and never re-derived downstream.
 * The scheme preserves the existing renderer convention from acp-update-mapper.ts
 * so that a future migration can maintain render identity continuity.
 *
 * All functions are pure and total — no nullable returns. When a provider
 * messageId is absent the reducer's segmenter synthesizes a stable messageId
 * before item folding, ensuring every item always has a non-null id.
 */

/**
 * Stable turn id.
 * Format: `${conversationId}:turn:${turnIndex}`
 * `turnIndex` is 0-based and reflects the turn's position in the session.
 */
export function makeTurnId(conversationId: string, turnIndex: number): string {
  return `${conversationId}:turn:${turnIndex}`;
}

/**
 * Stable message item id.
 * Format: `${turnId}:message:${messageId}`
 *
 * Uses the provider messageId when available; otherwise uses the reducer's
 * synthesized segment id.
 */
export function makeMessageId(turnId: string, messageId: string, _role: string): string {
  return `${turnId}:message:${messageId}`;
}

/**
 * Stable thinking item id.
 * Format: `${turnId}:thinking:${messageId}`
 *
 * A kind-tag prefix ('thinking:') disambiguates from message items when
 * Claude reuses the same messageId across both update kinds.
 */
export function makeThinkingId(turnId: string, messageId: string): string {
  return `${turnId}:thinking:${messageId}`;
}

/**
 * Stable tool item id.
 * Format: `${turnId}:tool:${toolCallId}`
 */
export function makeToolId(turnId: string, toolCallId: string): string {
  return `${turnId}:tool:${toolCallId}`;
}

/**
 * Stable tool group item id.
 * Format: `${firstChildId}:group`
 */
export function makeToolGroupId(firstChildId: string): string {
  return `${firstChildId}:group`;
}

/**
 * Stable parent id for nested tool calls, scoped to the same turn.
 * Returns undefined when parentToolCallId is null (no parent).
 */
export function makeParentId(turnId: string, parentToolCallId: string | null): string | undefined {
  return parentToolCallId != null ? makeToolId(turnId, parentToolCallId) : undefined;
}

/**
 * Stable diff item id.
 * Format: `${toolId}:${path}`
 * One diff item per changed file within a single tool call.
 */
export function makeDiffId(toolId: string, path: string): string {
  return `${toolId}:${path}`;
}

/**
 * Stable plan item id — one plan per turn.
 * Format: `${turnId}:plan`
 */
export function makePlanId(turnId: string): string {
  return `${turnId}:plan`;
}
