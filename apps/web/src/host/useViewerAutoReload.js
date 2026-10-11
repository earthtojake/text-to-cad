import { useEffect, useRef } from "react";
import {
  AUTO_RELOAD_PHASE,
  nextAutoReloadState,
  VIEWER_INSTALL_POLL_MS,
  VIEWER_RELOADING_POLL_MS,
  VIEWER_WATCH_INTERVAL_MS
} from "./viewerAutoReload.js";

const DEVELOPMENT_CADENCE = Object.freeze({ watchMs: VIEWER_WATCH_INTERVAL_MS, reloadingMs: VIEWER_RELOADING_POLL_MS });
const INSTALLED_CADENCE = Object.freeze({ watchMs: VIEWER_INSTALL_POLL_MS, reloadingMs: VIEWER_INSTALL_POLL_MS });

/**
 * Reload the page once its server is no longer the one it loaded from.
 *
 * Asks whenever the server says who it is (`serverInfo.identityToken`): at a
 * development backend's cadence when it restarts itself (`autoReload`, a source
 * checkout), at an installed one's otherwise, and at once when the person comes
 * back to the window. The decision lives in `viewerAutoReload.js`; this is the
 * timer, the fetch and the reload.
 *
 * @param {{autoReload?: boolean, identityToken?: string}|null} serverInfo
 * @param {{ fetchServerInfo: () => Promise<{ ok: boolean, identityToken?: string }> }} options  `fetchServerInfo`
 *   asks the backend who it is now; a closed port mid-restart answers `{ ok: false }`, not a throw.
 */
export function useViewerAutoReload(serverInfo, {
  fetchServerInfo,
  reload = defaultReload,
  now = () => Date.now(),
  schedule = (run, delayMs) => setTimeout(run, delayMs),
  cancel = (handle) => clearTimeout(handle)
}) {
  const optionsRef = useRef(null);
  optionsRef.current = { fetchServerInfo, reload, now, schedule, cancel };
  const development = Boolean(serverInfo?.autoReload);
  const baseline = String(serverInfo?.identityToken || "");

  useEffect(() => {
    if (!baseline) {
      return undefined;
    }
    const cadence = development ? DEVELOPMENT_CADENCE : INSTALLED_CADENCE;
    let active = true;
    let asking = false;
    let timer = null;
    let state = { phase: AUTO_RELOAD_PHASE.WATCHING, since: optionsRef.current.now() };

    const ask = async () => {
      if (timer !== null) {
        optionsRef.current.cancel(timer);
        timer = null;
      }
      if (asking) {
        return;
      }
      asking = true;
      const poll = await optionsRef.current.fetchServerInfo();
      asking = false;
      if (!active) {
        return;
      }
      const next = nextAutoReloadState(state, poll, { baseline, now: optionsRef.current.now(), ...cadence });
      state = { phase: next.phase, since: next.since };
      if (next.reload) {
        active = false;
        optionsRef.current.reload();
        return;
      }
      timer = optionsRef.current.schedule(ask, next.delayMs);
    };
    // Back in the window: ask now, not at the next tick a hidden tab's timers put off.
    const askNow = () => { void ask(); };

    timer = optionsRef.current.schedule(ask, 0);
    window.addEventListener("focus", askNow);
    return () => {
      active = false;
      window.removeEventListener("focus", askNow);
      if (timer !== null) {
        optionsRef.current.cancel(timer);
      }
    };
  }, [development, baseline]);
}

function defaultReload() {
  if (typeof window !== "undefined") {
    window.location.reload();
  }
}
