import { useEffect, useSyncExternalStore } from "react";

import { useSettings } from "@renderer/state/settings";

/**
 * The theme is one preference (`system` / `light` / `dark`) resolved against
 * the OS, applied as a single `.dark` class on `<html>`.
 *
 * One class, not a `data-theme` attribute, because that is what Tailwind's
 * `@custom-variant dark (&:is(.dark *))` and every shadcn component compile
 * against — and it is what `apps/viewer` uses, so a viewer surface embedded
 * here (P4) flips with the app instead of against it.
 */
const query = "(prefers-color-scheme: dark)";

function subscribeToSystem(onChange: () => void) {
  const media = window.matchMedia(query);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

/** True when the OS is asking for dark. */
export function useSystemPrefersDark(): boolean {
  return useSyncExternalStore(
    subscribeToSystem,
    () => window.matchMedia(query).matches,
    () => false,
  );
}

/** The theme actually being rendered, after `system` is resolved. */
export function useResolvedTheme(): "light" | "dark" {
  const preference = useSettings((state) => state.settings?.theme ?? "system");
  const systemDark = useSystemPrefersDark();
  if (preference === "system") {
    return systemDark ? "dark" : "light";
  }
  return preference;
}

/** Keeps `<html>`'s class in step with the resolved theme. Mount once. */
export function useApplyTheme(): void {
  const resolved = useResolvedTheme();
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", resolved === "dark");
    // The native scrollbars, form controls and the window background Electron
    // paints behind the page all follow color-scheme, not our tokens.
    root.style.colorScheme = resolved;
  }, [resolved]);
}
