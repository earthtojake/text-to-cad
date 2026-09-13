/**
 * Pre-mount grid seeding: convert a pane's pixel dimensions into cols/rows
 * using the same standalone cell measurement the per-pane resize controller
 * (usePtyPaneResize) seeds itself with. Lets callers size a PTY spawn before
 * any terminal has mounted, so the first broadcast after calibration is a
 * no-op (or a minimal correction) instead of a jump from the 80×24 default.
 */

import {
  TERMINAL_LETTER_SPACING,
  TERMINAL_LINE_HEIGHT,
  TERMINAL_PADDING_PX,
} from '@core/features/terminals/api/browser/pty/pty';
import {
  computeGridDimensions,
  measureTerminalCell,
  type TerminalDimensions,
} from '@core/features/terminals/api/browser/pty/pty-dimensions';
import { buildTerminalFontFamily } from '@core/features/terminals/api/browser/pty/terminal-font';
import { TERMINAL_FONT_SIZE_DEFAULT } from '@core/primitives/terminals/api';

/**
 * Compute the cols/rows a PTY spawned into a pane of the given pixel size
 * should start with. Mirrors the resize controller's pre-calibration seed
 * (default font, uniform TERMINAL_PADDING_PX inset). Returns null when cell
 * metrics are unavailable (e.g. no canvas in tests).
 */
export function computeSeededGridDimensions(
  widthPx: number,
  heightPx: number
): TerminalDimensions | null {
  const cell = measureTerminalCell(
    buildTerminalFontFamily(),
    TERMINAL_FONT_SIZE_DEFAULT,
    TERMINAL_LINE_HEIGHT,
    TERMINAL_LETTER_SPACING
  );
  if (!cell) return null;
  return computeGridDimensions({
    widthPx,
    heightPx,
    cellWidth: cell.width,
    cellHeight: cell.height,
    paddingPx: TERMINAL_PADDING_PX,
  });
}
