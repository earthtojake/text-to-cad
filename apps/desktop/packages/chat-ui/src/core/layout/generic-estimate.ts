/**
 * genericEstimate — engine-level fallback height heuristic.
 *
 * Used by ChatRoot when a ComponentDef does not implement `estimate`.
 * Suitable for simple kinds whose content is plain text and which have no
 * significant fixed chrome (footer, header, border, bubble padding).
 *
 * The formula is intentionally coarse: idle-time prefetch in ChatRoot
 * corrects near-viewport rows to exact heights before they enter the window,
 * and visible rows always re-measure via `def.measure` + `virt.setSize`.
 * Estimate accuracy only affects off-screen scrollbar proportion.
 *
 * Kinds that implement `estimate` explicitly:
 *   - `message`  — assistant footer + bubble padding + 8px are material.
 *   - `thinking` — collapsed vs expanded height differ greatly; expanded-aware.
 *   - `file-op`  — same expanded-vs-collapsed concern.
 *   - `diff`     — fixed header + capped line count via estimateDiff.
 */

import type { MeasureCtx } from '@core/define';
import type { ChatItem } from '@/model';

/**
 * Returns a coarse height estimate (content-only, px) for any ChatItem.
 * Caller wraps it with `rowReservedHeight(...)` (adds per-def padding and the
 * uniform inter-row gap), matching the pattern for all explicit estimates.
 */
export function genericEstimate(item: ChatItem, ctx: MeasureCtx): number {
  // Pull the first text-bearing field we can find on any item shape.
  const text =
    'text' in item && typeof item.text === 'string'
      ? item.text
      : 'command' in item && typeof item.command === 'string'
        ? item.command
        : 'name' in item && typeof item.name === 'string'
          ? item.name
          : '';
  const lines = Math.max(1, Math.ceil(text.length / 60));
  return lines * ctx.theme.fonts.body.lineHeight;
}
