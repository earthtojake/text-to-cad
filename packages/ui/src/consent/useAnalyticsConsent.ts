import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AppSetting } from "../file-viewer/types.js";

/** What a CAD app's server says about the usage stats cadgen sends (its telemetry). */
export interface AnalyticsConsent {
  sharing: boolean;
  /** Why: `environment` (DO_NOT_TRACK or CADGEN_TELEMETRY decided, and no click changes it), `choice`,
   * `default` (on by default: the person was told), `untold` (nothing sent yet), `unavailable`. */
  reason?: "environment" | "choice" | "default" | "untold" | "unavailable";
  /** The privacy policy. */
  policy: string;
}

/**
 * The app menu's Share anonymous usage data toggle, from the host's server (`consent()` reads, `consent(share)`
 * answers): read once, read again whenever the person comes back to the page (another view, the agent or
 * the CLI may have changed it meanwhile), and changed by a click. Nothing asks: cadgen's telemetry is on
 * by default once a `cadgen` command has said so. Each read and answer takes a number and only the latest
 * one's reply is kept, so a read sent just before a click (the click's own focus) can never undo it. An
 * answer that did not arrive is read back rather than shown as kept. A choice the environment made shows
 * as fixed.
 */
export function useAnalyticsConsent(consent: (share?: boolean) => Promise<AnalyticsConsent>) {
  const [state, setState] = useState<AnalyticsConsent | null>(null);
  const turn = useRef(0);
  const read = useCallback(function read(share?: boolean) {
    const mine = ++turn.current;
    void consent(share).then(
      next => { if (mine === turn.current) setState(next); },
      () => { if (share !== undefined && mine === turn.current) read(); });
  }, [consent]);
  useEffect(() => { read(); }, [read]);
  useEffect(() => {
    const recheck = () => read();
    window.addEventListener("focus", recheck);
    return () => window.removeEventListener("focus", recheck);
  }, [read]);
  const answer = useCallback((share: boolean) => {
    setState(previous => previous && { ...previous, sharing: share });
    read(share);
  }, [read]);
  const appSettings = useMemo<AppSetting[] | undefined>(() => state ? [{
    id: "analytics", checked: state.sharing, onCheckedChange: (checked: boolean) => answer(checked),
    ...(state.reason === "environment"
      ? { label: "Share anonymous usage data (set by your environment)", disabled: true }
      : { label: "Share anonymous usage data" }),
  }] : undefined, [state, answer]);
  return { consent: state, appSettings };
}
