/**
 * Where focus belongs in each pane, shared by the shell's F6 cycling and by whatever returns the
 * keyboard to the shell from a route of its own (Settings).
 */

/**
 * Where focus lands in a pane it has not been in yet: the sidebar's current
 * session, the composer, the explorer's strip tab — each pane's one stop
 * worth arriving at — else the pane's first control.
 */
export const PANE_HOMES: Record<"sidebar" | "session" | "explorer", string> = {
  sidebar: "[aria-current=page], [aria-current=true]",
  session: "[data-composer-input][contenteditable=true], [data-composer-input]:not([disabled])",
  explorer: '[role=tab][tabindex="0"]',
};

export const TABBABLE = 'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), [contenteditable=true], [tabindex]:not([tabindex="-1"])';

/**
 * Put focus where the session's work is: the composer, else the pane's first control. For a
 * route that just closed (Settings) whose button took its focus with it. The pane mounts in the
 * same commit, but the composer's editor does not (`immediatelyRender: false`), so it is absent
 * on the first try and arrives a frame later. Only the composer is tried first, so the header's
 * buttons are not focused, and announced, on the way to it; the pane's first control is the
 * fallback after that frame, for a session with no composer to land on.
 */
export function focusSessionHome(): void {
  const pane = () => document.getElementById("session");
  const composer = () => pane()?.querySelector<HTMLElement>(PANE_HOMES.session) ?? null;
  const first = composer();
  if (first) {
    first.focus();
    return;
  }
  window.requestAnimationFrame(() => (composer() ?? pane()?.querySelector<HTMLElement>(TABBABLE))?.focus());
}
