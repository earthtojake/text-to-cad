import { useEffect, useMemo, useState } from "react";
import { readChromeBackgroundToken, resolveChromeBackdropColor } from "../workbench/chromeBackdrop.js";

// Read after the document's class/style mutation: a parent can change the
// app's mode after child effects have already run. Only System uses this color.
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
