/**
 * The four appearance settings that are not React state: they are properties of
 * `<html>`, because everything below it — including a viewer surface P4 mounts
 * inside the app — reads them as tokens rather than as props.
 *
 * The theme itself lives in `use-theme.ts`; this is what rides on top of it.
 */
import { useEffect } from "react";

import { useResolvedTheme } from "@renderer/hooks/use-theme";
import { useSettings } from "@renderer/state/settings";
import type { AccentColor, CodeFont, UiFontSize } from "@shared/types";

/**
 * The accent, as an override of two stock tokens.
 *
 * shadcn's neutral `--primary` is a near-black in light and a near-white in
 * dark, so an accent cannot be one colour for both: each entry gives the light
 * and the dark value, and `--ring` follows `--primary` so focus rings stay in
 * the same family. `neutral` writes nothing at all, which is what keeps the
 * default app identical to the token set `apps/viewer` ships (plan §7).
 */
export const ACCENTS: Record<
  Exclude<AccentColor, "neutral">,
  { light: string; dark: string; swatch: string }
> = {
  blue: { light: "oklch(0.55 0.20 258)", dark: "oklch(0.65 0.17 258)", swatch: "oklch(0.6 0.19 258)" },
  violet: { light: "oklch(0.55 0.23 300)", dark: "oklch(0.66 0.19 300)", swatch: "oklch(0.6 0.21 300)" },
  green: { light: "oklch(0.53 0.14 152)", dark: "oklch(0.66 0.15 152)", swatch: "oklch(0.6 0.15 152)" },
  orange: { light: "oklch(0.62 0.18 48)", dark: "oklch(0.72 0.16 48)", swatch: "oklch(0.67 0.17 48)" },
  rose: { light: "oklch(0.57 0.22 15)", dark: "oklch(0.68 0.19 15)", swatch: "oklch(0.62 0.21 15)" },
};

/** Root font size per step. Every `rem` in the UI is a multiple of it. */
const FONT_SIZES: Record<UiFontSize, string> = {
  small: "14px",
  default: "16px",
  large: "18px",
};

/** What Monaco, the terminal and code blocks ask for. */
const CODE_FONTS: Record<CodeFont, string> = {
  system: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
  "jetbrains-mono":
    '"JetBrains Mono", ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
};

/** True when the family is installed on this machine. */
export function fontAvailable(family: string): boolean {
  try {
    return document.fonts.check(`12px "${family}"`);
  } catch {
    return false;
  }
}

/**
 * Applies the accent, the UI scale, the code font, reduced motion and the
 * translucent sidebar to `<html>`. Mount once, beside `useApplyTheme`.
 */
export function useApplyAppearance(): void {
  const settings = useSettings((state) => state.settings);
  const accent = settings?.accentColor ?? "neutral";
  const fontSize = settings?.uiFontSize ?? "default";
  const codeFont = settings?.codeFont ?? "system";
  const reduceMotion = settings?.reduceMotion ?? false;
  const translucent = settings?.translucentSidebar ?? false;
  // Not `settings.theme`: an accent has to re-resolve when the OS flips under
  // a `system` preference, and that never changes the setting.
  const resolved = useResolvedTheme();

  useEffect(() => {
    const root = document.documentElement;
    if (accent === "neutral") {
      root.style.removeProperty("--primary");
      root.style.removeProperty("--primary-foreground");
      root.style.removeProperty("--ring");
      root.removeAttribute("data-accent");
      return;
    }
    root.setAttribute("data-accent", accent);
    const colour = resolved === "dark" ? ACCENTS[accent].dark : ACCENTS[accent].light;
    root.style.setProperty("--primary", colour);
    root.style.setProperty("--primary-foreground", "oklch(0.985 0 0)");
    root.style.setProperty("--ring", colour);
  }, [accent, resolved]);

  useEffect(() => {
    document.documentElement.style.fontSize = FONT_SIZES[fontSize];
  }, [fontSize]);

  useEffect(() => {
    document.documentElement.style.setProperty("--font-mono", CODE_FONTS[codeFont]);
  }, [codeFont]);

  useEffect(() => {
    document.documentElement.classList.toggle("reduce-motion", reduceMotion);
  }, [reduceMotion]);

  useEffect(() => {
    document.documentElement.classList.toggle("translucent-sidebar", translucent);
  }, [translucent]);
}
