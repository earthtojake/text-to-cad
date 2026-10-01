import { useExplorer } from "@renderer/state/explorer";
import { useSessions } from "@renderer/state/sessions";

/** How long to wait for the explorer to bind to the session just selected. */
const BIND_TIMEOUT_MS = 5_000;

/**
 * Open the Review tab, scoped to `This session`, in *that session's*
 * explorer — the sidebar's `+9 −1` suffix.
 *
 * The explorer belongs to the selected session (docs/session-workspaces.md),
 * so the caller selects the session first and this waits for the bridge to
 * bind the strip to it before touching anything. A review tab already in the
 * strip is brought forward rather than doubled. If the strip never becomes
 * this session's (an archived row, a bind that failed) nothing is opened:
 * a tab in another session's explorer would be worse than none.
 *
 * At most one wait is pending, app-wide, and any change of the selected
 * session cancels it: click A's badge, then row B, then A again inside the
 * timeout, and A's review must not open unasked. The caller selects the
 * session *before* calling, so the selection this sees is already the
 * target's. Nothing else cancels a wait, so nothing is returned: a badge
 * whose row unmounts mid-wait (archived, filtered out) leaves a wait that
 * still ends on the next click, a selection change, the bind or the timeout.
 */
export function openSessionReview(sessionId: string): void {
  const ready = () => {
    const state = useExplorer.getState();
    return state.sessionId === sessionId && state.ready;
  };
  const open = () => {
    const state = useExplorer.getState();
    const existing = state.tabs.find((tab) => tab.kind === "review");
    if (existing) {
      if (existing.kind === "review" && existing.scope !== "session") {
        state.update(existing.id, { scope: "session" });
      }
      state.setActive(existing.id);
      state.show();
      return;
    }
    state.open("review", { scope: "session" });
  };

  cancelPendingReview();
  if (ready()) {
    open();
    return;
  }
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    unsubscribeExplorer();
    unsubscribeSelection();
    clearTimeout(timer);
    if (pending === finish) pending = null;
  };
  const unsubscribeExplorer = useExplorer.subscribe(() => {
    if (!done && ready()) {
      finish();
      open();
    }
  });
  const selected = useSessions.getState().activeId;
  const unsubscribeSelection = useSessions.subscribe((state) => {
    if (state.activeId !== selected) finish();
  });
  const timer = setTimeout(finish, BIND_TIMEOUT_MS);
  pending = finish;
}

let pending: (() => void) | null = null;

/** Drop the one pending wait, if any. */
export function cancelPendingReview(): void {
  pending?.();
}
