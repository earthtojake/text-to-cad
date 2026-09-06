/**
 * Snapshot types and equality helpers for the write-phase-owned geometry pass.
 *
 * Extracted from ChatRoot.tsx so unit tests can import these pure helpers
 * without pulling in any DOM-dependent modules.
 */

/**
 * Everything about the current pinned-header overlay that the write phase
 * needs to commit into the DOM and signal to JSX.
 */
export type PinSnapshot = {
  /** Stable item id of the active (scrolled-past) user message. */
  itemId: string;
  /** Index of the active user message unit in the virtualizer. */
  activeUserIdx: number;
  /** CSS translateY offset for the pinned overlay (≤ 0). */
  overlayTop: number;
};

/**
 * Full geometry snapshot produced by derive() on each scheduler frame.
 * commit() diffs this against lastLayout and applies only the changed fields.
 */
export type LayoutSnapshot = {
  start: number;
  end: number;
  canvasHeight: number;
  pin: PinSnapshot | null;
};

/**
 * Array equality for visible-row index arrays.
 * Returns true iff the arrays have the same length and identical elements.
 */
export function sameRange(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

/**
 * Structural equality for PinSnapshot (or null).
 * Compares all three fields so commit() skips the DOM write on stable frames.
 */
export function samePin(a: PinSnapshot | null, b: PinSnapshot | null): boolean {
  if (a === null && b === null) return true;
  if (a === null || b === null) return false;
  return (
    a.itemId === b.itemId && a.activeUserIdx === b.activeUserIdx && a.overlayTop === b.overlayTop
  );
}
