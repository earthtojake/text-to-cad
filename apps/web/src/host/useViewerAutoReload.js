import { useEffect, useRef } from "react";
import { AUTO_RELOAD_PHASE, nextAutoReloadState } from "./viewerAutoReload.js";

/**
 * Watch a development backend that restarts itself, and reload when it does.
 *
 * Inert unless `serverInfo.autoReload` is true, which only a cadgen running
 * from a source checkout reports. The decision lives in
 * `viewerAutoReload.js`; this is the timer, the fetch and the reload.
 *
 * @param {{autoReload?: boolean, identityToken?: string}|null} serverInfo
 */
export function useViewerAutoReload(serverInfo, {
  fetchServerInfo = defaultFetchServerInfo,
  reload = defaultReload,
  now = () => Date.now(),
  schedule = (run, delayMs) => setTimeout(run, delayMs),
  cancel = (handle) => clearTimeout(handle)
} = {}) {
  const optionsRef = useRef(null);
  optionsRef.current = { fetchServerInfo, reload, now, schedule, cancel };
  const enabled = Boolean(serverInfo?.autoReload);
  const baseline = String(serverInfo?.identityToken || "");

  useEffect(() => {
    if (!enabled || !baseline) {
      return undefined;
    }
    let active = true;
    let timer = null;
    let state = { phase: AUTO_RELOAD_PHASE.WATCHING, since: optionsRef.current.now() };

    const tick = async () => {
      const poll = await optionsRef.current.fetchServerInfo();
      if (!active) {
        return;
      }
      const moment = optionsRef.current.now();
      const next = nextAutoReloadState(state, poll, { baseline, now: moment });
      state = { phase: next.phase, since: next.since };
      if (next.reload) {
        active = false;
        optionsRef.current.reload();
        return;
      }
      timer = optionsRef.current.schedule(tick, next.delayMs);
    };

    timer = optionsRef.current.schedule(tick, 0);
    return () => {
      active = false;
      if (timer !== null) {
        optionsRef.current.cancel(timer);
      }
    };
  }, [enabled, baseline]);
}

async function defaultFetchServerInfo() {
  try {
    const response = await fetch("/__cad/server", { cache: "no-store" });
    if (!response.ok) {
      return { ok: false };
    }
    const payload = await response.json();
    return { ok: true, identityToken: String(payload?.identityToken || "") };
  } catch {
    // A closed port mid-exec. The caller reads this as "restarting", not as a
    // failure, and asks again shortly.
    return { ok: false };
  }
}

function defaultReload() {
  if (typeof window !== "undefined") {
    window.location.reload();
  }
}
