import { useEffect, useSyncExternalStore } from "react";

import { useSettings } from "@renderer/state/settings";
import { ThemePreferenceSchema, type ThemePreference } from "@shared/types";

/**
 * The theme is one preference (`system` / `light` / `dark`) resolved against
 * the OS, applied as a single `.dark` class on `<html>`.
 *
 * One class, not a `data-theme` attribute, because that is what Tailwind's
 * `@custom-variant dark (&:is(.dark *))` and every shadcn component compile
 * against — and it is what `apps/viewer` uses, so a viewer surface embedded
 * here (P4) flips with the app instead of against it.
 *
 * In this app the APP writes it and nothing else does: the embedded surface is
 * handed the resolved answer as a prop (`CadRenderer`'s `colorScheme`) and is
 * forbidden from touching the document, so there is exactly one writer —
 * `applyResolvedTheme` below.
 */
const query = "(prefers-color-scheme: dark)";

/**
 * The last preference the app resolved, cached where the first line of the
 * renderer can read it.
 *
 * Settings live in main's sqlite and arrive over IPC, which is a frame or two
 * late — and a frame or two of the wrong colour scheme is the whole window
 * flashing white before it goes dark. `src/renderer/lib/platform.ts` has the
 * same problem for the traffic-light inset and the same answer: find it out
 * before the first paint. This is a CACHE, never the source of truth; the IPC
 * read that follows corrects it, and `useApplyTheme` writes it back.
 */
const THEME_CACHE_KEY = "hardcore.theme";

/** The cached preference, or `system` when there is none or it is junk. */
export function readCachedThemePreference(): ThemePreference {
  try {
    const parsed = ThemePreferenceSchema.safeParse(window.localStorage.getItem(THEME_CACHE_KEY));
    return parsed.success ? parsed.data : "system";
  } catch {
    // A renderer with storage blocked still has an OS preference to follow.
    return "system";
  }
}

function writeCachedThemePreference(preference: ThemePreference) {
  try {
    window.localStorage.setItem(THEME_CACHE_KEY, preference);
  } catch {
    /* see readCachedThemePreference */
  }
}

/** True when the OS is asking for dark, read once. */
function systemPrefersDark(): boolean {
  try {
    return window.matchMedia(query).matches;
  } catch {
    return false;
  }
}

/** A preference and the OS, resolved. `system` is the OS's answer, live. */
export function resolveThemePreference(preference: ThemePreference, prefersDark: boolean): "light" | "dark" {
  if (preference === "system") {
    return prefersDark ? "dark" : "light";
  }
  return preference;
}

/**
 * The app's one write of the document's colour scheme.
 *
 * The class is what Tailwind and shadcn compile against; `color-scheme` is
 * what the native scrollbars, the form controls and the window background
 * Electron paints behind the page follow, and neither of those reads a token.
 */
export function applyResolvedTheme(resolved: "light" | "dark"): void {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
}

/**
 * Call once, before render, beside `applyPlatformClass`.
 *
 * Without this the first paint of every renderer load — a launch, a reload,
 * a dev-server hot reload — is light whatever the person set, because the
 * class only arrives with React's first passive effect. The window is shown
 * on `ready-to-show`, which is after that paint, so the flash is on screen.
 */
export function applyCachedTheme(): void {
  applyResolvedTheme(resolveThemePreference(readCachedThemePreference(), systemPrefersDark()));
}

/** True when the OS is asking for dark, and again whenever that changes. */
function subscribeToSystem(onChange: () => void) {
  const media = window.matchMedia(query);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

export function useSystemPrefersDark(): boolean {
  return useSyncExternalStore(subscribeToSystem, systemPrefersDark, () => false);
}

/**
 * The preference as stored, or the cached one until the first IPC read lands.
 *
 * Not `"system"` for that gap: a person who chose Light would get a dark
 * window for the length of an IPC round trip, which is the flash this file
 * exists to remove — in the other direction.
 */
function useThemePreference(): ThemePreference {
  const stored = useSettings((state) => state.settings?.theme);
  return stored ?? readCachedThemePreference();
}

/** The theme actually being rendered, after `system` is resolved. */
export function useResolvedTheme(): "light" | "dark" {
  return resolveThemePreference(useThemePreference(), useSystemPrefersDark());
}

/** Keeps `<html>` and the cache in step with the resolved theme. Mount once. */
export function useApplyTheme(): void {
  const preference = useSettings((state) => state.settings?.theme);
  const resolved = useResolvedTheme();

  useEffect(() => {
    applyResolvedTheme(resolved);
  }, [resolved]);

  useEffect(() => {
    // Only what main actually stores: mirroring the fallback would write the
    // cache back over itself before the first read lands.
    if (preference) {
      writeCachedThemePreference(preference);
    }
  }, [preference]);
}
