/**
 * createClipboard — Solid primitive for copy-to-clipboard interactions.
 *
 * Returns { copied, copy } where:
 *   copied — a reactive accessor; true for `resetMs` ms after a successful copy.
 *   copy   — async function that writes text to the clipboard and sets copied.
 *
 * The reset timer is cleaned up on component disposal via onCleanup.
 *
 * @example
 * const { copied, copy } = createClipboard();
 * <button onClick={() => copy(text)}>
 *   {copied() ? 'Copied!' : 'Copy'}
 * </button>
 */

import { createSignal, onCleanup } from 'solid-js';

export type ClipboardState = {
  copied: () => boolean;
  copy: (text: string) => void;
};

export function createClipboard(resetMs = 1500): ClipboardState {
  const [copied, setCopied] = createSignal(false);
  let resetTimer: ReturnType<typeof setTimeout> | undefined;

  const copy = (text: string): void => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      if (resetTimer !== undefined) clearTimeout(resetTimer);
      resetTimer = setTimeout(() => {
        setCopied(false);
        resetTimer = undefined;
      }, resetMs);
    });
  };

  onCleanup(() => {
    if (resetTimer !== undefined) clearTimeout(resetTimer);
  });

  return { copied, copy };
}
