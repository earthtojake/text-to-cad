import { useEffect, useMemo, useState } from "react";
import { readChromeBackgroundToken, resolveChromeBackdropColor } from "./chromeBackdrop.js";

/**
 * The chrome's own background colour, live.
 *
 * The frame around the scene follows it (chromeBackdrop.js), so it has
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
