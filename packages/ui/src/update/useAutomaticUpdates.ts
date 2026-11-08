import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AppSetting } from "../file-viewer/types.js";
import { translator } from "../i18n/core.js";

/** Whether the engine updates by itself (`cad_server/auto_updates.py`), and why. */
export interface AutomaticUpdates {
  automatic: boolean;
  /** `default` (on until the person chooses), `choice`, or `environment` (`CAD_UPDATE_CHECK=0`, CI: no click changes it). */
  reason?: "default" | "choice" | "environment";
}

/**
 * The app menu's Automatic updates, from the host's server (`automaticUpdates()` reads,
 * `automaticUpdates(on)` answers): read once, read again whenever the person comes back to the page
 * (another view or `cad update auto` may have changed it meanwhile), and changed by a click. The
 * same setting in every CAD app. Only the latest read or answer's reply is kept, so a read sent just
 * before a click can never undo it, and an answer that did not arrive is read back. One the
 * environment decided shows as fixed. Its label is in `locale`, as the host hands it.
 */
export function useAutomaticUpdates(automaticUpdates: (automatic?: boolean) => Promise<AutomaticUpdates>, locale?: string) {
  const t = translator(locale);
  const [state, setState] = useState<AutomaticUpdates | null>(null);
  const turn = useRef(0);
  const read = useCallback(function read(automatic?: boolean) {
    const mine = ++turn.current;
    void automaticUpdates(automatic).then(
      next => { if (mine === turn.current) setState(next); },
      () => { if (automatic !== undefined && mine === turn.current) read(); });
  }, [automaticUpdates]);
  useEffect(() => { read(); }, [read]);
  useEffect(() => {
    const recheck = () => read();
    window.addEventListener("focus", recheck);
    return () => window.removeEventListener("focus", recheck);
  }, [read]);
  const answer = useCallback((automatic: boolean) => {
    setState(previous => previous && { ...previous, automatic });
    read(automatic);
  }, [read]);
  const appSettings = useMemo<AppSetting[] | undefined>(() => state ? [{
    id: "automatic-updates", checked: state.automatic, onCheckedChange: (checked: boolean) => answer(checked),
    info: t("update.automaticInfo"),
    ...(state.reason === "environment"
      ? { label: t("update.automaticEnvironment"), disabled: true }
      : { label: t("update.automatic") }),
  }] : undefined, [state, answer, t]);
  return { automaticUpdates: state, appSettings };
}
