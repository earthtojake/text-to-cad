import { useEffect, useRef } from "react";

/**
 * The search's key: ⌘K on a Mac, Ctrl+K elsewhere (the host's `environment.platform`, as every other key the viewer
 * names). Pure, so `node --test` reads it.
 */

/** The key as a menu or a hint writes it. */
export const searchShortcut = platform => (platform === "darwin" ? "⌘K" : "Ctrl+K");

/** Whether a key press is the search's: K with ⌘ on a Mac, with Ctrl elsewhere, and nothing else held. */
export function isSearchKey(event, platform) {
  if (event.key?.toLowerCase() !== "k" || event.altKey || event.shiftKey) return false;
  return platform === "darwin" ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
}

/** Whether a dialog other than the search is up (What's new, the home's Delete, a phone's panel sheet): the key waits for it. */
const anotherDialog = document => Boolean(document.querySelector('[role="dialog"]:not([data-document-search]), [role="alertdialog"]'));

/**
 * ⌘K (Ctrl+K) from anywhere on the page, a text field too, while `enabled` (never in Preview): `onSearch`. Held, it
 * does not repeat; it waits while another dialog is up, and leaves a press another handler took (`defaultPrevented`).
 * The page's own (a browser's Ctrl+K, its search bar) is the viewer's while it is.
 *
 * @param {(() => void) | null | undefined} onSearch
 * @param {{ platform?: string, enabled: boolean }} options
 */
export function useSearchKey(onSearch, { platform, enabled }) {
  const latest = useRef(onSearch);
  latest.current = onSearch;
  const on = Boolean(onSearch) && enabled;
  useEffect(() => {
    if (!on) return undefined;
    const press = event => {
      if (event.defaultPrevented || event.repeat || !isSearchKey(event, platform)) return;
      const page = event.target?.ownerDocument ?? document;
      if (anotherDialog(page) || page.querySelector("[data-document-search]")) return;
      event.preventDefault();
      latest.current?.();
    };
    window.addEventListener("keydown", press);
    return () => window.removeEventListener("keydown", press);
  }, [on, platform]);
}
