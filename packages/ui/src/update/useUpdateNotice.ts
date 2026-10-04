import { useCallback, useEffect, useRef, useState } from "react";

/** What a CAD app's server says when a newer text-to-cad is out (`cadgen/updates.py`). */
export interface UpdateNotice {
  /** The release offered. */
  latest: string;
  /** The release this install runs. */
  version: string;
  /** `text-to-cad 0.9.0 is available (you have 0.8.1)` */
  text: string;
  /** What to ask the person's agent, worded like the install message: `Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad`. */
  prompt: string;
  /** The full install instructions (`https://www.texttocad.dev/install`), should the agent not manage. */
  instructions: string;
}

/** The host's call to its server: read (`dismiss` omitted), or keep the person's answer for a release. */
export type UpdateCall = (dismiss?: string) => Promise<{ notice: UpdateNotice | null }>;

/**
 * The update card's state, from the host's server: read once, and again whenever the person comes
 * back to the page (another view may have answered meanwhile). The person's answer -- they sent or
 * copied the prompt, or closed the card -- is kept by the server (`answer`), so that release is not
 * offered again, in any view or either app; the next one is. A page that answered never shows the
 * card again, whatever a read still on its way says. A view that cannot ask its server shows nothing.
 */
export function useUpdateNotice(call: UpdateCall) {
  const [notice, setNotice] = useState<UpdateNotice | null>(null);
  const [closed, setClosed] = useState(false);
  const answered = useRef(false);
  const read = useCallback(() => {
    void call().then(reply => { if (!answered.current) setNotice(reply.notice ?? null); }, () => {});
  }, [call]);
  useEffect(() => { read(); }, [read]);
  useEffect(() => {
    window.addEventListener("focus", read);
    return () => window.removeEventListener("focus", read);
  }, [read]);
  const answer = useCallback(() => {
    if (!notice || answered.current) return;
    answered.current = true;
    void call(notice.latest).catch(() => {});
  }, [call, notice]);
  const close = useCallback(() => {
    answer();
    setClosed(true);
  }, [answer]);
  return { notice: closed ? null : notice, answer, close };
}
