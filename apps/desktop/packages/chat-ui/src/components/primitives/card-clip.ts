/**
 * card-clip — Shared helpers for bordered cards that need to track the animated
 * clip edge during a UnitRow expand/collapse tween.
 *
 * Problem: UnitRow wraps the row content with `overflow: hidden` at the
 * interpolated height during animation. A bordered card whose own root height
 * is set to the full logical height will have its bottom border and rounded
 * corners hidden by the clip (they sit below the animated edge). Fix: resolve
 * the card-root height to `ctx.clipHeight?.() ?? fullHeight` so the bordered
 * shell tracks the moving clipped edge.
 *
 * Usage:
 *   const cardH = clipTrackedHeight(props.ctx, () => props.height);
 *   // In JSX: style={assignInlineVars(myVars, { height: cardH() })}
 *
 *   // Switch overflow-y while the tween is in flight to avoid a scrollbar:
 *   style={{ 'overflow-y': isCardAnimating(props.ctx) ? 'hidden' : 'auto' }}
 */

import type { RenderCtx } from '@core/define';
import type { Accessor } from 'solid-js';

/**
 * Returns a reactive accessor that resolves to `ctx.clipHeight()` while a
 * UnitRow tween is in flight, or `fullHeight()` at rest. Wire this to the
 * bordered root element height so the bottom border tracks the animated edge.
 */
export function clipTrackedHeight(ctx: RenderCtx, fullHeight: Accessor<number>): Accessor<number> {
  return () => ctx.clipHeight?.() ?? fullHeight();
}

/**
 * Returns true while UnitRow is clipping this card's height during a tween.
 * Call inside a reactive context (JSX attribute, style object, createMemo, etc.)
 * so changes to `ctx.clipHeight` are tracked automatically.
 */
export function isCardAnimating(ctx: RenderCtx): boolean {
  return ctx.clipHeight?.() != null;
}
