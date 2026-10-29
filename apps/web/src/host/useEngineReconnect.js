import { useEffect, useRef, useState } from "react";

/** The first wait before a page whose engine is gone asks again, and the longest it backs off to. */
export const RECONNECT_FIRST_MS = 1000;
export const RECONNECT_LONGEST_MS = 5000;

/**
 * A page whose engine is gone (`gone`) asks the same address again -- with its token, the cookie its
 * link left -- after a second, backing off to every five, until an engine answers it. The
 * installation's engine comes back on the same port with the same token (`cadgen/engine/daemon.py`,
 * `bind`), so a restart, a stop or a reboot costs an open tab nothing: once another engine
 * than the one the page loaded from (`pid`) answers, the page reloads itself into the same document
 * (its URL, `/<id>`), whatever the page's reads said meanwhile. The same engine answering was a
 * blip: nothing is reloaded. An engine that answers without knowing the token -- another
 * installation's, or one whose token was rotated -- is not back: the page keeps asking, and is never
 * reloaded for it (under the dev server's proxy a reload would be refused again, and again), so the
 * page's new link, opened beside it, heals it: its cookie is the tab's too.
 *
 * Returns what the last ask met while the engine is gone: `true` when an engine answered and refused
 * the page's token, `false` when nothing answered, `null` before the first ask.
 *
 * @param {boolean} gone
 * @param {{ pid: unknown, ask: () => Promise<{ pid?: unknown } | { refused: true } | null>, reload?: () => void,
 *   schedule?: (run: () => void, delayMs: number) => unknown, cancel?: (handle: unknown) => void }} options
 *   `ask` answers the engine's description (`/__cad/server`) when one answered this page, `{ refused:
 *   true }` when one answered and refused its token, else null.
 * @returns {boolean | null}
 */
export function useEngineReconnect(gone, {
  pid,
  ask,
  reload = defaultReload,
  schedule = (run, delayMs) => setTimeout(run, delayMs),
  cancel = (handle) => clearTimeout(handle)
}) {
  const optionsRef = useRef(null);
  optionsRef.current = { pid, ask, reload, schedule, cancel };
  const asking = useRef(null);
  const [refused, setRefused] = useState(null);

  useEffect(() => {
    if (!gone || asking.current) {
      return;
    }
    const loop = { active: true, timer: null };
    asking.current = loop;
    let delayMs = RECONNECT_FIRST_MS;
    const wait = () => {
      loop.timer = optionsRef.current.schedule(attempt, delayMs);
      delayMs = Math.min(delayMs * 2, RECONNECT_LONGEST_MS);
    };
    const attempt = async () => {
      loop.timer = null;
      const answer = await optionsRef.current.ask().catch(() => null);
      if (!loop.active) {
        return;
      }
      if (!answer || answer.refused) {
        setRefused(Boolean(answer?.refused));
        wait();
        return;
      }
      loop.active = false;
      asking.current = null;
      setRefused(null);
      if (answer.pid !== optionsRef.current.pid) {
        optionsRef.current.reload();
      }
    };
    wait();
  }, [gone]);

  // Asking outlives the notice (a read that answers clears it), never the page.
  useEffect(() => () => {
    const loop = asking.current;
    if (loop) {
      loop.active = false;
      if (loop.timer !== null) {
        optionsRef.current.cancel(loop.timer);
      }
      asking.current = null;
    }
  }, []);
  return refused;
}

function defaultReload() {
  if (typeof window !== "undefined") {
    window.location.reload();
  }
}
