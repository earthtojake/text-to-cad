import { useEffect, useMemo, useState } from "react";
import { resolveThemeSettingsForColorMode, SYSTEM_THEME_ID } from "@hardcore/core/lib/themeSettings.js";
import { readChromeBackgroundToken, resolveChromeBackdropColor } from "./chromeBackdrop.js";

/**
 * The chrome's own background colour, live.
 *
 * The "System" CAD theme paints the scene on it (chromeBackdrop.js), so it has
 * to survive the app switching light and dark — and the app that owns the
 * `--background` token is not this surface. A host toggles `.dark` on the
 * document in an effect of its own, and effects run child-first, so reading
 * the token in an effect here would read the class as it was BEFORE the
 * switch. Hence the observer: whatever moves the token — a host's class, this
 * surface's own colour-scheme write, a stylesheet swapped at runtime — is a
 * mutation on `<html>`, and the read happens after it.
 *
 * `prefersDark` is a dependency as well, so the first paint of a scheme change
 * already has the right colour when the token and the class move together.
 */
export function useChromeBackdropColor(prefersDark) {
  const [token, setToken] = useState(readChromeBackgroundToken);
  useEffect(() => {
    if (typeof document === "undefined" || typeof MutationObserver === "undefined") {
      return undefined;
    }
    const read = () => setToken(readChromeBackgroundToken());
    read();
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributeFilter: ["class", "style"] });
    return () => observer.disconnect();
  }, [prefersDark]);
  return useMemo(() => resolveChromeBackdropColor({ token, prefersDark }), [prefersDark, token]);
}


/** Resolve the scene theme consistently for populated and empty CAD stages. */
export function resolveCadThemeSettings(themeSettings, themeId, { prefersDark, chromeBackdropColor }) {
  // A system color mode follows the app's resolved appearance.
  const resolved = resolveThemeSettingsForColorMode(themeSettings, { prefersDark });
  if (themeId !== SYSTEM_THEME_ID) return resolved;
  // Only the System preset follows the host's background token. Other presets
  // and custom themes keep their own scene backdrop.
  return {
    ...resolved,
    background: { ...(resolved.background || {}), type: "solid", solidColor: chromeBackdropColor }
  };
}
