import { useCallback, useEffect, useState } from "react";

/** What a CAD app's server says when a newer text-to-cad is out (`cadgen/updates.py`). */
export interface UpdateNotice {
  /** The release offered. */
  latest: string;
  /** The release this install runs. */
  version: string;
  /** `A new version v0.9.0 of text-to-cad is available (currently on v0.8.1)` */
  text: string;
  /** What to ask the person's agent, worded like the install message: `Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad`. */
  prompt: string;
  /** The full install instructions (`https://www.texttocad.dev/install`), should the agent not manage. */
  instructions: string;
}

/** The host's call to its server: whether a newer text-to-cad is out. */
export type UpdateCall = () => Promise<{ notice: UpdateNotice | null }>;

/**
 * The update button's state, from the host's server: what the host already knew as the page started
 * (`initial`: a CAD app's launch carries it, the web page reads it with its server's description), so
 * the button draws with the page rather than after it; then read again, and again whenever the person
 * comes back to the page (the day's check may have found a release meanwhile). There is no answer to
 * keep: the button stays while this install is behind and goes once the update lands. A view that
 * cannot ask its server shows nothing.
 */
export function useUpdateNotice(call: UpdateCall, initial: UpdateNotice | null = null): UpdateNotice | null {
  const [notice, setNotice] = useState<UpdateNotice | null>(initial);
  const read = useCallback(() => {
    void call().then(reply => setNotice(reply.notice ?? null), () => {});
  }, [call]);
  useEffect(() => { read(); }, [read]);
  useEffect(() => {
    window.addEventListener("focus", read);
    return () => window.removeEventListener("focus", read);
  }, [read]);
  return notice;
}
