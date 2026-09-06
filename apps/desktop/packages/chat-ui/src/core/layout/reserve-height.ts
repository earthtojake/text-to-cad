/**
 * reserveHeight — canonical chrome-aware height formula for block-level content.
 *
 * Every block that contributes padding or border to its outer height must use
 * this helper so the engine and the CSS stay in sync.  Prefer this over
 * hand-rolling `2*padY + 2*border + content` in individual layout functions,
 * because:
 *
 *   - It makes chrome terms explicit and self-documenting.
 *   - `borderLines` handles border-collapse correctly: a table with N rows draws
 *     N+1 horizontal grid lines, not 2.  Flat bordered boxes use the default (2).
 *
 * @param content   Intrinsic content height in px (e.g. lineCount * lineHeight,
 *                  or rowCount * TABLE_ROW_H).
 * @param padY      Vertical padding per side in px (default 0).
 * @param border    Border width in px (default 0).
 * @param borderLines Number of horizontal border lines drawn (default 2 — top
 *                  and bottom).  For a border-collapse table with N rows pass
 *                  N+1 (one line above each row plus the final bottom line).
 */
export function reserveHeight(opts: {
  content: number;
  padY?: number;
  border?: number;
  borderLines?: number;
}): number {
  const { content, padY = 0, border = 0, borderLines = 2 } = opts;
  return content + 2 * padY + borderLines * border;
}
