/**
 * Declarative scroll intent type and ergonomic constructors.
 *
 * Kept in a standalone module (no DOM or parse-cache imports) so unit tests
 * running in the `node` Vitest project can import the helpers without
 * triggering `decode-named-character-reference` which requires a DOM.
 */

/**
 * Declarative scroll intent. Owned by ChatState.scroll and projected onto the
 * DOM's scrollTop by ChatRoot's projectAnchor() — the sole scrollTop writer.
 *
 * Intent is **event-sourced**: it changes only on discrete user gestures or
 * host calls, never derived from geometry. This prevents geometry (scrollTop,
 * reserve height) from feeding back into intent and causing scroll jumps.
 *
 * `tail`    — follow newest content; re-pin to the bottom edge whenever
 *             content grows (replaces the old `bottom` mode).
 * `anchor`  — keep the given item's `edge` ('top' | 'bottom') at the
 *             viewport position described by `offset` (px from scroll top).
 *             Used for user-parked positions, expand/collapse stability, and
 *             pin-to-top-on-send (edge:'top', offset:0 = replaces `pinTop`).
 */
export type ScrollMode =
  | { kind: 'tail' }
  | { kind: 'anchor'; itemId: string; edge: 'top' | 'bottom'; offset: number };

/** Construct a tail (follow-newest) scroll intent. */
export const tailMode = (): ScrollMode => ({ kind: 'tail' });

/**
 * Construct a top-edge anchor that holds `itemId` flush with the viewport top.
 * Replaces the old `pinTop` mode used when pinning the last user message.
 */
export const pinTopMode = (itemId: string): ScrollMode => ({
  kind: 'anchor',
  itemId,
  edge: 'top',
  offset: 0,
});
