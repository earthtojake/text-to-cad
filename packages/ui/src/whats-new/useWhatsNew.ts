import { useCallback, useEffect, useRef, useState } from "react";
import { whatsNewEntry } from "./notes.js";

/** What a CAD app's server keeps of What's new (`/api/v1/settings`' `whats_new`). */
export interface WhatsNewSettings {
  /** The releases, by their minor (`0.11`), whose notes the person has seen. */
  seen: string[];
  /** The release the engine runs, by its minor. */
  release: string | null;
}

/** The host's call to its server: `whatsNew()` reads, `whatsNew(seen)` adds releases seen (null: a server that keeps none). */
export type WhatsNewCall = (seen?: readonly string[]) => Promise<WhatsNewSettings | null>;

/**
 * What's new, from the host's server: the release whose notes this view shows (`entry`, null for
 * none: a new person, a release with no notes or notes seen) and `dismiss`, which closes it at once
 * and keeps it seen for every view of the person's -- a write that fails changes nothing on screen.
 * Read once, and read again whenever the person comes back to the page, so notes dismissed in
 * another view close here too; only the latest read's reply is kept.
 */
export function useWhatsNew(whatsNew: WhatsNewCall) {
  const [settings, setSettings] = useState<WhatsNewSettings | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const turn = useRef(0);
  const read = useCallback(() => {
    const mine = ++turn.current;
    void whatsNew().then(next => { if (mine === turn.current) setSettings(next); }, () => {});
  }, [whatsNew]);
  useEffect(() => { read(); }, [read]);
  useEffect(() => {
    window.addEventListener("focus", read);
    return () => window.removeEventListener("focus", read);
  }, [read]);
  const found = settings ? whatsNewEntry(settings.release, settings.seen) : null;
  const entry = found && found !== dismissed ? found : null;
  const dismiss = useCallback(() => {
    if (!entry) return;
    setDismissed(entry);
    turn.current += 1;  // a read already sent answers from before the dismissal
    void whatsNew([...(settings?.seen ?? []), entry]).catch(() => {});
  }, [entry, settings, whatsNew]);
  return { entry, dismiss };
}
