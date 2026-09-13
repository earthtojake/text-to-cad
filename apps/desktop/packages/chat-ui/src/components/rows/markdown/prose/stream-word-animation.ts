const STREAM_WORD_STAGGER_MS = 14;
const STREAM_WORD_MAX_STAGGER_MS = 98;

/**
 * Paint-only reveal delay for a word appended after the previous render.
 * The cap keeps a large provider chunk readable without making the canonical
 * transcript feel artificially delayed.
 */
export function streamWordDelayMs(wordIndex: number, frontier: number): number {
  const appendedIndex = Math.max(0, wordIndex - frontier);
  return Math.min(appendedIndex * STREAM_WORD_STAGGER_MS, STREAM_WORD_MAX_STAGGER_MS);
}
