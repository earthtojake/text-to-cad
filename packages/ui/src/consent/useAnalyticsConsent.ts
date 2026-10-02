import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AppSetting } from "../file-viewer/types.js";

/** What a CAD app's server says about anonymous usage analytics. */
export interface AnalyticsConsent {
  /** Show the card: nothing is chosen yet, and an answer could be kept. */
  ask: boolean;
  sharing: boolean;
  /** Why: `environment` (DO_NOT_TRACK or CADGEN_ANALYTICS decided, and no click changes it), `choice`, `unasked`, `unavailable`. */
  reason?: "environment" | "choice" | "unasked" | "unavailable";
  /** The privacy policy the card links. */
  policy: string;
}

/**
 * The analytics card's and the Settings toggle's state, from the host's server (`consent()` reads,
 * `consent(share)` answers): read once; read again, while it still asks, when the person comes back
 * to the page (another view may have been answered meanwhile); and answered by a click. Each read
 * and answer takes a number and only the latest one's reply is kept, so a read sent just before a
 * click (the click's own focus) can never bring the card back. A view that cannot ask its server
 * asks nothing. A choice the environment made shows in Settings as fixed.
 */
export function useAnalyticsConsent(consent: (share?: boolean) => Promise<AnalyticsConsent>) {
  const [state, setState] = useState<AnalyticsConsent | null>(null);
  const turn = useRef(0);
  const read = useCallback((share?: boolean) => {
    const mine = ++turn.current;
    void consent(share).then(next => { if (mine === turn.current) setState(next); }, () => {});
  }, [consent]);
  useEffect(() => { read(); }, [read]);
  const asking = Boolean(state?.ask);
  useEffect(() => {
    if (!asking) return;
    const recheck = () => read();
    window.addEventListener("focus", recheck);
    return () => window.removeEventListener("focus", recheck);
  }, [read, asking]);
  const answer = useCallback((share: boolean) => {
    setState(previous => previous && { ...previous, ask: false, sharing: share });
    read(share);
  }, [read]);
  // The same choice, changed later: Settings' Analytics section.
  const appSettings = useMemo<AppSetting[] | undefined>(() => state ? [{
    id: "analytics", section: "Analytics", checked: state.sharing, onCheckedChange: answer,
    ...(state.reason === "environment"
      ? { label: "Share anonymous usage data (set by your environment)", disabled: true }
      : { label: "Share anonymous usage data" }),
  }] : undefined, [state, answer]);
  return { consent: state, answer, appSettings };
}
