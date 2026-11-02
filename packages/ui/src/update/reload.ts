/**
 * A page's reload into a new release, deferred while the page has something unsaved: what a person is
 * typing (a field with focus that holds text -- Quick Edit's prompt, a value being edited) would be lost
 * to a reload, so the page waits until they leave it. Nothing else on a CAD page is unsaved: its views
 * and settings are the tab's (`tab-store`), and survive a reload.
 */

/** Whether the page has something a reload would lose: a focused field that holds text. */
export function pageHasUnsaved(doc: Document = document): boolean {
  const active = doc.activeElement as (HTMLElement & { value?: unknown }) | null;
  if (!active || active === doc.body) return false;
  if (active.isContentEditable) return Boolean(active.textContent?.trim());
  const tag = active.tagName;
  if (tag === "TEXTAREA" || (tag === "INPUT" && !["button", "checkbox", "radio", "range", "submit", "reset", "color", "file"]
    .includes(String((active as HTMLInputElement).type)))) {
    return typeof active.value === "string" && active.value.trim().length > 0;
  }
  return false;
}

/** How often a deferred reload looks again. */
export const RELOAD_RETRY_MS = 1000;

type Timers = Pick<Window, "addEventListener" | "removeEventListener" | "setTimeout" | "clearTimeout">;

/**
 * Reload now (`reload`, the host's: a page reloads itself, a card's shell loads the engine's app), or
 * once the page has nothing unsaved (`pageHasUnsaved`): looked at again as focus leaves a field, and
 * each `RELOAD_RETRY_MS`. Returns a function that cancels it.
 */
export function reloadWhenClean(reload: () => void,
  { unsaved = () => pageHasUnsaved(), target = window }: { unsaved?: () => boolean; target?: Timers } = {}): () => void {
  let done = false;
  let timer: number | null = null;
  const schedule = (delayMs: number) => {
    if (timer !== null) target.clearTimeout(timer);
    timer = target.setTimeout(look, delayMs);
  };
  // As focus leaves a field: looked at once it has gone wherever it goes.
  const left = () => schedule(0);
  const stop = () => {
    done = true;
    target.removeEventListener("focusout", left, true);
    if (timer !== null) target.clearTimeout(timer);
  };
  function look() {
    timer = null;
    if (done) return;
    if (unsaved()) {
      schedule(RELOAD_RETRY_MS);
      return;
    }
    stop();
    reload();
  }
  target.addEventListener("focusout", left, true);
  look();
  return stop;
}
