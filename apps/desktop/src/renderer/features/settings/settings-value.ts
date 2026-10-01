/**
 * Reading and writing settings from a page, with the "not loaded yet" case
 * answered once instead of on every row.
 *
 * `useSettings().settings` is null until the first IPC read lands. A page that
 * spread `?? false` over forty rows would be a page where the default of a
 * given row is whatever its author typed at the call site, and the schema's
 * default — the one main actually stores — would be a second opinion.
 */
import { useEffect, useState } from "react";

import { useSettings } from "@renderer/state/settings";
import { defaultSettings, type Settings } from "@shared/types";

/** The schema's defaults, parsed once. */
const FALLBACK = defaultSettings();

/** The current settings, or the schema's defaults for the frame before they load. */
export function useSettingsValue(): Settings {
  return useSettings((state) => state.settings) ?? FALLBACK;
}

/** The write path. Optimistic in the store; main's reply is the correction, and a refused write reverts and toasts. */
export function useSettingsPatch(): (patch: Partial<Settings>) => void {
  const patch = useSettings((state) => state.patch);
  return (next) => void patch(next);
}

type SettingsFallbacks = { refused: Record<string, string>; gone: Record<string, { path: string; reason: "missing" | "file" }> };
const NO_FALLBACKS: SettingsFallbacks = { refused: {}, gone: {} };

/**
 * What main read as a default instead of the stored value, or found gone
 * (`settings.fallbacks`: `refused`, and `gone` for a remembered folder), by field: asked again whenever settings change, so a
 * note goes once the field is set.
 */
export function useSettingsFallbacks(): SettingsFallbacks {
  const settings = useSettingsValue();
  const [fallbacks, setFallbacks] = useState<SettingsFallbacks>(NO_FALLBACKS);
  useEffect(() => {
    let current = true;
    void window.textToCad.settings
      .fallbacks()
      .then((next) => {
        if (current) setFallbacks(next);
      })
      .catch(() => {});
    return () => {
      current = false;
    };
  }, [settings]);
  return fallbacks;
}
