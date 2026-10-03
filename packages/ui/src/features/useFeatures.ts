import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AppSetting, ViewerFeatures } from "../file-viewer/types.js";

/** Every feature as it starts: on, until the person turns it off. */
export const DEFAULT_FEATURES: Readonly<Required<ViewerFeatures>> = Object.freeze({ quickEdit: true });

/** Settings' Features section: a row for each feature a person can turn off, in order. */
const FEATURE_ROWS: readonly { id: keyof ViewerFeatures; label: string }[] = [{ id: "quickEdit", label: "Quick edit" }];

/** What a server said, kept to the features this page knows, on or off. */
function known(reply: unknown): Partial<ViewerFeatures> {
  const entries = reply && typeof reply === "object" ? Object.entries(reply) : [];
  return Object.fromEntries(entries.filter(([name, on]) => name in DEFAULT_FEATURES && typeof on === "boolean"));
}

/**
 * Settings' Features section, and the features it turns on and off, from the host's server, which
 * keeps them for every view the person has (`features()` reads them; `features(change)` changes some
 * and answers them all): read once, read again whenever the person comes back to the page (another
 * view, in another tab or app, may have changed them meanwhile), and changed by a click — shown at
 * once, and read back if the change did not arrive. Each read and change takes a number and only the
 * latest one's reply is kept, so a read sent just before a click never undoes it. Until the server
 * has answered, every feature is as it starts, and Settings has no Features section: a view that
 * cannot ask its server offers no choice it could not keep.
 */
export function useFeatures(features: (change?: Partial<ViewerFeatures>) => Promise<ViewerFeatures>) {
  const [state, setState] = useState<Required<ViewerFeatures> | null>(null);
  const turn = useRef(0);
  const read = useCallback(function read(change?: Partial<ViewerFeatures>) {
    const mine = ++turn.current;
    void features(change).then(
      next => { if (mine === turn.current) setState({ ...DEFAULT_FEATURES, ...known(next) }); },
      () => { if (change !== undefined && mine === turn.current) read(); });
  }, [features]);
  useEffect(() => { read(); }, [read]);
  useEffect(() => {
    const recheck = () => read();
    window.addEventListener("focus", recheck);
    return () => window.removeEventListener("focus", recheck);
  }, [read]);
  const change = useCallback((next: Partial<ViewerFeatures>) => {
    setState(previous => previous && { ...previous, ...next });
    read(next);
  }, [read]);
  const appSettings = useMemo<AppSetting[] | undefined>(() => state ? FEATURE_ROWS.map(({ id, label }) => ({
    id, section: "Features", label, checked: state[id], onCheckedChange: (checked: boolean) => change({ [id]: checked }),
  })) : undefined, [state, change]);
  return { features: state ?? DEFAULT_FEATURES, appSettings };
}
