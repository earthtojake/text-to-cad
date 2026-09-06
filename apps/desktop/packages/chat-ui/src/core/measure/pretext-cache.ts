/**
 * Thin helpers around pretext's `prepareRichInline`.
 *
 * The per-instance richInlineCache has moved to ChatCaches (core/caches.ts).
 * This module now exports:
 *   registerFontsReadyClear  — font-load hook; calls onCleared which should
 *                              invoke caches.clearTextMeasure() + remeasure.
 *   clearPretextInternalCaches — flush pretext's internal global caches (re-exported
 *                               for use from ChatCaches.clearTextMeasure).
 */

export { clearCache as clearPretextInternalCaches } from '@chenglou/pretext';

/**
 * Named font faces to pre-load.  These must exactly match the font-family names
 * used in metrics.ts so `document.fonts.load()` resolves them correctly.
 */
const FONT_LOAD_SPECS = [
  '400 14px "Inter Variable"',
  '600 14px "Inter Variable"',
  '400 13px "JetBrains Mono Variable"',
  '400 12px "JetBrains Mono Variable"',
];

/**
 * Eagerly load the bundled named fonts, then call `onCleared`
 * (which should invoke `caches.clearTextMeasure()` + `virtualizer.measure()`).
 *
 * Using `document.fonts.load(spec)` instead of `document.fonts.ready` ensures
 * we wait for the exact faces pretext needs, not just "all fonts document-wide".
 * Without this, pretext measures with the fallback metrics during first paint
 * and produces wrong line-break positions until the cache is cleared.
 *
 * Call this once when ChatTranscript mounts.
 */
export function registerFontsReadyClear(onCleared?: () => void): void {
  if (typeof document === 'undefined') return;
  void Promise.all(FONT_LOAD_SPECS.map((spec) => document.fonts.load(spec))).then(() => {
    onCleared?.();
  });
}
