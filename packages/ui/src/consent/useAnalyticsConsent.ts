import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AppSetting } from "../file-viewer/types.js";

/** What a CAD app's server says about anonymous usage analytics. */
export interface AnalyticsConsent {
  /** Show the card: nothing is chosen yet, and an answer could be kept. cadgen no longer asks: its
   * analytics are on by default once a `cadgen` command has said so. */
  ask: boolean;
  sharing: boolean;
  /** Why: `environment` (DO_NOT_TRACK or CADGEN_ANALYTICS decided, and no click changes it), `choice`,
   * `default` (on by default: the person was told), `untold` (nothing sent yet), `unavailable`. */
  reason?: "environment" | "choice" | "default" | "untold" | "unavailable";
  /** The privacy policy the card links. */
  policy: string;
}

/**
 * Where an answer came from: the card, which answers only an open question (one still up in
 * another view must not undo an answer just given there), or the app menu's toggle, which changes it
 * whenever. The host passes it on to its server.
 */
export type AnswerFrom = "card" | "settings";

/**
 * The analytics card's and the app menu toggle's state, from the host's server (`consent()` reads,
 * `consent(share, from)` answers): read once, read again whenever the person comes back to the
 * page (another view, the agent or the CLI may have changed it meanwhile), and answered by a click.
 * Each read and answer takes a number and only the latest one's reply is kept, so a read sent just
 * before a click (the click's own focus) can never bring the card back. An answer that did not
 * arrive is read back rather than shown as kept, and a page that answered never asks again. A view
 * that cannot ask its server asks nothing. A choice the environment made shows in the app menu as fixed.
 */
export function useAnalyticsConsent(consent: (share?: boolean, from?: AnswerFrom) => Promise<AnalyticsConsent>) {
  const [state, setState] = useState<AnalyticsConsent | null>(null);
  const turn = useRef(0);
  const answered = useRef(false);
  const read = useCallback(function read(share?: boolean, from?: AnswerFrom) {
    const mine = ++turn.current;
    void consent(share, from).then(
      next => { if (mine === turn.current) setState(next); },
      () => { if (share !== undefined && mine === turn.current) read(); });
  }, [consent]);
  useEffect(() => { read(); }, [read]);
  useEffect(() => {
    const recheck = () => read();
    window.addEventListener("focus", recheck);
    return () => window.removeEventListener("focus", recheck);
  }, [read]);
  const answer = useCallback((share: boolean, from: AnswerFrom = "card") => {
    answered.current = true;
    setState(previous => previous && { ...previous, ask: false, sharing: share });
    read(share, from);
  }, [read]);
  // The same choice, changed later: the app menu's toggle.
  const appSettings = useMemo<AppSetting[] | undefined>(() => state ? [{
    id: "analytics", checked: state.sharing, onCheckedChange: (checked: boolean) => answer(checked, "settings"),
    ...(state.reason === "environment"
      ? { label: "Share anonymous usage data (set by your environment)", disabled: true }
      : { label: "Share anonymous usage data" }),
  }] : undefined, [state, answer]);
  return { consent: state && answered.current ? { ...state, ask: false } : state, answer, appSettings };
}
