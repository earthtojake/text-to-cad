/**
 * Where the keyboard goes when the person opens or picks an explorer tab.
 *
 * A tab's body mounts on many occasions the person did not ask for — a
 * session switch, Back, a theme change, the sidebar folding — and a body that
 * took focus on every mount (the terminal did) pulled the keyboard out of
 * whatever the person was in. So a body takes focus only when asked: the
 * person's own open or pick (a shortcut, the `+` menu, a click on its tab)
 * names the tab here, and a body that can take focus claims it once it can
 * (a terminal, when its shell is attached). A body that claims nothing — a
 * review, a browser, a file — leaves focus on its strip tab: one Tab from the
 * rest of the pane, never the page, where no key reaches anything.
 */

/**
 * The one body the strip controls. `ExplorerPane` renders it and `TabStrip`
 * names it; it is declared here so the three share it without a cycle.
 */
export const EXPLORER_TABPANEL_ID = "explorer-tabpanel";

/** The tab the person asked for, until its body claims it or another request replaces it. */
let wanted: string | null = null;
/** Bodies that will claim focus when they can, each with how to focus it once it is mounted and ready. */
const claimants = new Map<string, () => void>();
/** Claimants that have come up to their claim once: mounted and ready, and not going to ask again. */
const claimed = new Set<string>();

/**
 * The person opened or picked `tabId`: its body takes focus, or its strip tab does.
 *
 * Two frames: one for the strip's render, one for the body's effects. A body
 * that is still getting ready to claim (a terminal whose shell is starting) is
 * left to claim when it is ready, and so is one whose code is still loading.
 * `prefer` names an element in the body to land on when it is there by then
 * (the tree's row, for a file opened from a tree), ahead of the strip tab.
 */
export function focusTabBody(tabId: string, prefer?: string): void {
  wanted = tabId;
  const later = (landing: boolean) => window.requestAnimationFrame(() => window.requestAnimationFrame(() => settle(landing)));
  const settle = (landing: boolean) => {
    if (wanted !== tabId) return;
    const panel = document.getElementById(EXPLORER_TABPANEL_ID);
    if (panel?.contains(document.activeElement)) {
      wanted = null;
      return;
    }
    if (claimants.has(tabId)) {
      // Still getting ready: it claims when it can. Ready already (the tab was picked while it
      // was the active one): nothing will run its claim again, so it is focused here — left
      // pending, the next rebuild of its widget (a theme change) would take the keyboard unasked.
      if (!claimed.has(tabId)) return;
      wanted = null;
      claimants.get(tabId)?.();
      return;
    }
    // A lazy body whose chunk is still loading (`data-focus-pending`, the
    // pane's fallback) is a claimant that has not mounted yet: wait for it,
    // then give what lands the same two frames a body that was there gets.
    if (panel?.querySelector("[data-focus-pending]")) {
      later(true);
      return;
    }
    if (landing) {
      later(false);
      return;
    }
    wanted = null;
    const preferred = prefer ? document.getElementById(EXPLORER_TABPANEL_ID)?.querySelector<HTMLElement>(prefer) : null;
    if (preferred) {
      preferred.focus();
      return;
    }
    document.querySelector<HTMLElement>(`[data-tab-strip] [data-tab="${CSS.escape(tabId)}"]`)?.focus();
  };
  later(false);
}

/**
 * A body that will take focus once it can: registered while it is mounted, so
 * the strip tab does not take focus it is about to claim. The return releases
 * it — an unmounted body claims nothing, and a request it never claimed must
 * not be claimed by the next mount of the same tab (a session switch back).
 */
export function holdFocusClaim(tabId: string, focus: () => void = () => {}): () => void {
  claimants.set(tabId, focus);
  return () => {
    claimants.delete(tabId);
    claimed.delete(tabId);
    if (wanted === tabId) wanted = null;
  };
}

/** True once, for the body of the tab the person asked for. */
export function claimFocus(tabId: string): boolean {
  claimed.add(tabId);
  if (wanted !== tabId) return false;
  wanted = null;
  return true;
}
