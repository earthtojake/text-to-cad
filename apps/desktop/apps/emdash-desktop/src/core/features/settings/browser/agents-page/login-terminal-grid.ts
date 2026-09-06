import {
  computeGridDimensions,
  type TerminalDimensions,
} from '@core/features/terminals/api/browser/pty/pty-dimensions';

/**
 * Upper bounds on the sign-in terminal grid. Any regression that lets the host
 * grow with the terminal content (a resize feedback loop) degrades to a
 * bounded grid instead of freezing the renderer.
 */
export const MAX_LOGIN_COLS = 500;
export const MAX_LOGIN_ROWS = 200;

export interface LoginHostSize {
  readonly width: number;
  readonly height: number;
}

/**
 * Plan the next sign-in terminal grid from the host's pixel size and the
 * mounted terminal's real cell metrics.
 *
 * Returns null when the host size has not changed since the last applied
 * resize — the structural guard that keeps a terminal.resize → content growth
 * → ResizeObserver tick cycle from feeding back into the grid.
 */
export function planLoginGrid({
  hostSize,
  cellWidth,
  cellHeight,
  paddingPx,
  lastAppliedHostSize,
}: {
  hostSize: LoginHostSize;
  cellWidth: number;
  cellHeight: number;
  paddingPx: number;
  lastAppliedHostSize: LoginHostSize | null;
}): TerminalDimensions | null {
  if (
    lastAppliedHostSize !== null &&
    lastAppliedHostSize.width === hostSize.width &&
    lastAppliedHostSize.height === hostSize.height
  ) {
    return null;
  }
  const dims = computeGridDimensions({
    widthPx: hostSize.width,
    heightPx: hostSize.height,
    cellWidth,
    cellHeight,
    paddingPx,
  });
  if (!dims) return null;
  return {
    cols: Math.min(dims.cols, MAX_LOGIN_COLS),
    rows: Math.min(dims.rows, MAX_LOGIN_ROWS),
  };
}
