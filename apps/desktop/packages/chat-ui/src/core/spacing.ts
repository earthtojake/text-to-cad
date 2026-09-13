/**
 * spacing.ts — shared margin-collapse primitives for the chat-ui render engine.
 *
 * Both the unit layer (transcript rows) and the block layer (markdown blocks)
 * use the same collapse rule: each def declares top/bottom margins and each
 * seam between siblings resolves to max(prevBottom, curTop).
 */

// ── Margin ────────────────────────────────────────────────────────────────────

/**
 * Vertical margins declared by a UnitDef or BlockDef.
 *
 * `top`    — space requested above this item when it follows a sibling.
 * `bottom` — space requested below this item before the next sibling.
 *
 * At each seam the engine takes max(prev.bottom, cur.top) and assigns the
 * result to the lower item's `gapBefore` (or stack gap). The upper item
 * contributes zero trailing space so the gap is owned by exactly one side.
 */
export type Margin = { top: number; bottom: number };

// ── collapse ──────────────────────────────────────────────────────────────────

/**
 * Resolve the gap at a seam between two siblings using margin-collapse.
 *
 * Returns max(prevBottom, curTop), matching the CSS block-formatting-context
 * collapse rule and ensuring each seam is owned by exactly one value.
 */
export const collapse = (prevBottom: number, curTop: number): number =>
  Math.max(prevBottom, curTop);

// ── resolveSeamGap ────────────────────────────────────────────────────────────

/**
 * Resolve the gap (px) at the seam between two adjacent render units.
 *
 * `marginOf` is a pure lookup — pass `(k) => unitDefs[k]?.margin` so this
 * helper stays free of concrete registry imports and the module remains cycle-free.
 *
 * All unit defs declare margin, so `marginOf` is expected to always return a
 * value for registered kinds.
 */
export function resolveSeamGap(
  prevKind: string,
  curKind: string,
  marginOf: (kind: string) => Margin | undefined
): number {
  const prevBottom = marginOf(prevKind)?.bottom ?? 0;
  const curTop = marginOf(curKind)?.top ?? 0;
  return collapse(prevBottom, curTop);
}
