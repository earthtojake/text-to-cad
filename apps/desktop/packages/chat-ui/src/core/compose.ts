/**
 * Layout combinators — slim version.
 *
 * After Phase 3, only `stack` remains in use (by block-stack.ts and
 * BlockStackView). The bubble/pad/collapsible/scrollWindow/slot combinators
 * and SLOT_NAMES have been removed with the legacy ComponentDef machinery.
 */

import type { Measured } from './define';

// ── Layout payload types ───────────────────────────────────────────────────────

export type PlacedChild = { id: string; top: number; child: Measured };

export type StackLayout = {
  kind: 'stack';
  placed: PlacedChild[];
};

// ── stack ─────────────────────────────────────────────────────────────────────

/**
 * Vertically stack an ordered list of children with a symmetric top/bottom
 * padding and a per-slot gap function.
 *
 * The `gap` parameter may be:
 *   - a constant number applied between every pair of adjacent children
 *   - a function `(idx) => number` called with the current child index (≥ 1)
 *     so callers can vary the gap based on position (e.g. proseGap vs blockGap)
 *
 * Returns a `StackLayout` whose `placed` entries carry the absolute `top`
 * offset of each child within the stack's content area (padY already included).
 */
export function stack(
  children: { id: string; measured: Measured }[],
  opts: { padY?: number; gap?: number | ((idx: number) => number) } = {}
): Measured<StackLayout> {
  const padY = opts.padY ?? 0;
  let cursor = padY;
  let maxWidth = 0;
  const placed: PlacedChild[] = [];

  for (let i = 0; i < children.length; i++) {
    const { id, measured } = children[i];
    if (i > 0) {
      const gap = typeof opts.gap === 'function' ? opts.gap(i) : (opts.gap ?? 0);
      cursor += gap;
    }
    placed.push({ id, top: cursor, child: measured });
    cursor += measured.height;
    maxWidth = Math.max(maxWidth, measured.width);
  }

  cursor += padY;

  return {
    height: cursor,
    width: maxWidth,
    layout: { kind: 'stack', placed },
  };
}
