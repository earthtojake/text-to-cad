import { useEffect, useState } from "react";

/**
 * The OS light/dark preference, live.
 *
 * This is the app's colour scheme when nothing else decides it — the chrome's
 * light/dark, never the scene's. The CAD theme paints the scene and only the
 * scene: a dark studio inside a light window is a legal picture, so nothing
 * here reads a theme.
 *
 * `false` on a page with no `matchMedia` (a test environment, a very old
 * engine), which is `prefers-color-scheme: light` — the same fallback
 * `resolveColorSchemeMode` takes.
 */
export function useSystemPrefersDark() {
  const [prefersDark, setPrefersDark] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return undefined;
    }
    let query;
    try {
      query = window.matchMedia("(prefers-color-scheme: dark)");
    } catch {
      return undefined;
    }
    const sync = () => setPrefersDark(query.matches === true);
    sync();
    query.addEventListener?.("change", sync);
    return () => query.removeEventListener?.("change", sync);
  }, []);
  return prefersDark;
}
