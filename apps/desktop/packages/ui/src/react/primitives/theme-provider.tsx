/**
 * ThemeProvider — self-contained theme manager for @emdash/ui.
 *
 * CONTRACT
 * --------
 * import = CSS loaded: just importing this module pulls in the full CSS
 * stack as side-effects (palette vars, semantic aliases, VE globals, fonts,
 * typography, overflow-fade). No separate CSS import is required.
 *
 * mount  = theme applied: mounting the component applies the active theme's
 * selector class. All @emdash/ui primitives work immediately within the tree.
 *
 * THEME APPLICATION TARGET
 * ------------------------
 * By default (target="documentElement") the theme class is applied to
 * <html>, so portal-rendered UI (dropdowns, popovers, dialogs from
 * @base-ui/react) inherits the correct tokens without manual wiring.
 *
 * Use target="wrapper" when you want the theme scoped to a wrapper element
 * only (e.g. Storybook surface decorators, embedded widgets).
 *
 * USAGE
 * -----
 *   // Uncontrolled — ThemeProvider manages its own state:
 *   <ThemeProvider defaultTheme="dark"><App /></ThemeProvider>
 *
 *   // Controlled — an external owner drives the theme (e.g. Storybook globals):
 *   <ThemeProvider theme={colorMode}><Story /></ThemeProvider>
 *
 *   // Access theme inside the tree:
 *   const { themeId, setTheme, toggle } = useTheme();
 *
 * SSR NOTE
 * --------
 * documentElement mode is guarded with typeof document checks and is safe
 * to render on the server (no class will be applied server-side).
 *
 * SINGLE-PROVIDER ASSUMPTION
 * --------------------------
 * Only one ThemeProvider with target="documentElement" should be mounted at
 * a time — nested providers would compete for the <html> class.
 */

// ── CSS side-effects ─────────────────────────────────────────────────────────
// Importing this module loads the full @emdash/ui CSS stack.
// In Vite/Storybook (dev): the source import graph is followed directly.
// In a published dist: all CSS is extracted into dist/style.css (referenced
// in package.json#sideEffects) — apps import @emdash/ui/style.css once.
//
// VE barrel: layers order, non-color token contract, surfaces, reset/base
// element defaults, sx() sprinkles atoms, animation keyframes, SVG helpers.
import '@styles/global.css';
// Generated palette ramps + per-theme semantic aliases (wrapped in @layer tokens).
import '@emdash/theme/theme.css';
import '@emdash/theme/semantic.css';
// JetBrains Mono variable font + structural keyframes (accordion, panel-blur).
import '@styles/theme.base.css';
// Semantic typography role classes (.text-role-body, .text-role-h1, etc.).
import '@styles/typography.css';
// Scroll-aware overflow-fade utility (.scroll-fade / .scroll-fade__viewport).
import '@styles/effects/overflow-fade.css';
// ── Component ────────────────────────────────────────────────────────────────
import { DENSITY_MANIFEST } from '@emdash/theme/densities';
import type { DensityId } from '@emdash/theme/densities';
import { THEME_MANIFEST } from '@emdash/theme/manifest';
import type { ThemeId } from '@emdash/theme/manifest';
import { cx } from '@styles/utilities/cx';
import React, {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
} from 'react';

// Re-export for consumers that want to enumerate themes.
export type { ThemeId };
export type { DensityId };
export { DENSITY_MANIFEST, THEME_MANIFEST };

export interface ThemeContextValue {
  /** Active theme id (e.g. "light" | "dark"). */
  themeId: ThemeId;
  /** Active density id (e.g. "comfortable" | "compact"). */
  densityId: DensityId;
  /** Change to a specific theme id. */
  setTheme: (id: ThemeId) => void;
  /** Change to a specific density id. */
  setDensity: (id: DensityId) => void;
  /** Toggle between available themes in manifest order. */
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

/**
 * Returns the active theme context. Must be called inside a ThemeProvider.
 */
export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used inside a ThemeProvider');
  }
  return ctx;
}

/**
 * Non-throwing variant of {@link useTheme} for components that accept a prop
 * fallback when rendered outside a ThemeProvider (e.g. Toaster). Returns null
 * when no provider is mounted.
 */
export function useThemeOptional(): ThemeContextValue | null {
  return useContext(ThemeContext);
}

/**
 * Returns the CSS selector class for the active theme (e.g. `"emlight"` or
 * `"emdark"`), or an empty string when called outside a ThemeProvider.
 *
 * Designed for portal elements that need to inherit the theme when they render
 * outside the ThemeProvider's wrapper element. Apply the returned class to the
 * outermost element of the portal so theme-scoped CSS tokens resolve correctly.
 *
 * In documentElement mode (the default) the theme class is already on <html>,
 * so all portals inherit it automatically — this hook returns an empty string
 * and has no effect in that case.
 */
export function usePortalThemeClass(): string {
  const ctx = useContext(ThemeContext);
  if (!ctx) return '';
  const themeEntry = THEME_MANIFEST.find((e) => e.id === ctx.themeId) ?? THEME_MANIFEST[0]!;
  const densityEntry = DENSITY_MANIFEST.find((e) => e.id === ctx.densityId) ?? DENSITY_MANIFEST[0]!;
  return cx(themeEntry.selector.replace(/^\./, ''), densityEntry.selector.replace(/^\./, ''));
}

export interface ThemeProviderProps {
  /**
   * Controlled theme id. When provided, the component is fully controlled —
   * the class always reflects this value and internal state is kept in sync.
   * Use this when an external owner (e.g. Storybook globals) drives the theme.
   */
  theme?: ThemeId;
  /**
   * Controlled density id. When provided, spacing/radius density is controlled
   * by the parent independently from the color theme.
   */
  density?: DensityId;
  /**
   * Uncontrolled initial theme id. Only used on the first render.
   * Defaults to the first entry in the manifest ("light").
   */
  defaultTheme?: ThemeId;
  /**
   * Uncontrolled initial density id. Defaults to the first density manifest
   * entry ("comfortable").
   */
  defaultDensity?: DensityId;
  /**
   * Where to apply the active theme class.
   *
   * "documentElement" (default) — applies the class to <html> so portal-rendered
   * elements (dropdowns, dialogs, popovers from @base-ui/react) are themed
   * automatically. Children are rendered as-is; className/style props are
   * forwarded to the optional wrapper element rendered when either is present.
   *
   * "wrapper" — applies the class to the wrapper element (controlled by `as`).
   * Portals that render outside the wrapper must use usePortalThemeClass().
   *
   * "none" — context-only mode. No theme class is written to the DOM at all.
   * Use when the host application's own provider is the sole DOM class writer
   * and you only need ThemeContext to be available inside the tree (e.g. when
   * embedding @emdash/ui components inside an app that manages themes itself).
   */
  target?: 'documentElement' | 'wrapper' | 'none';
  /** Element type for the wrapper (only used when target="wrapper" or className/style are supplied). Defaults to 'div'. */
  as?: React.ElementType;
  className?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}

const ALL_THEME_CLASSES = THEME_MANIFEST.map((e) => e.selector.replace(/^\./, ''));
const ALL_DENSITY_CLASSES = DENSITY_MANIFEST.map((e) => e.selector.replace(/^\./, ''));

/**
 * ThemeProvider — renders the theme class and provides ThemeContext.
 *
 * See module-level doc for target, CSS, and SSR notes.
 */
export function ThemeProvider({
  theme: controlledTheme,
  density: controlledDensity,
  defaultTheme,
  defaultDensity,
  target = 'documentElement',
  as: As = 'div',
  className,
  style,
  children,
}: ThemeProviderProps) {
  const initial: ThemeId =
    controlledTheme ?? defaultTheme ?? (THEME_MANIFEST[0]?.id as ThemeId) ?? 'light';
  const [themeId, setThemeId] = useState<ThemeId>(initial);
  const initialDensity: DensityId =
    controlledDensity ?? defaultDensity ?? (DENSITY_MANIFEST[0]?.id as DensityId) ?? 'comfortable';
  const [densityId, setDensityId] = useState<DensityId>(initialDensity);

  // Sync internal state whenever the controlled prop changes.
  const prevControlled = React.useRef(controlledTheme);
  if (controlledTheme !== undefined && controlledTheme !== prevControlled.current) {
    prevControlled.current = controlledTheme;
    setThemeId(controlledTheme);
  }
  const prevControlledDensity = React.useRef(controlledDensity);
  if (controlledDensity !== undefined && controlledDensity !== prevControlledDensity.current) {
    prevControlledDensity.current = controlledDensity;
    setDensityId(controlledDensity);
  }

  const resolvedThemeId = controlledTheme ?? themeId;
  const resolvedDensityId = controlledDensity ?? densityId;

  const setTheme = useCallback((id: ThemeId) => {
    setThemeId(id);
  }, []);

  const setDensity = useCallback((id: DensityId) => {
    setDensityId(id);
  }, []);

  const toggle = useCallback(() => {
    setThemeId((current) => {
      const ids = THEME_MANIFEST.map((e) => e.id as ThemeId);
      const idx = ids.indexOf(current);
      return ids[(idx + 1) % ids.length] ?? ids[0]!;
    });
  }, []);

  const entry = THEME_MANIFEST.find((e) => e.id === resolvedThemeId) ?? THEME_MANIFEST[0]!;
  const themeClass = entry.selector.replace(/^\./, '');
  const densityEntry =
    DENSITY_MANIFEST.find((e) => e.id === resolvedDensityId) ?? DENSITY_MANIFEST[0]!;
  const densityClass = densityEntry.selector.replace(/^\./, '');

  // Apply theme class to <html> in documentElement mode.
  useLayoutEffect(() => {
    if (target !== 'documentElement') return;
    if (typeof document === 'undefined') return;
    const root = document.documentElement;
    root.classList.remove(...ALL_THEME_CLASSES, ...ALL_DENSITY_CLASSES);
    root.classList.add(themeClass, densityClass);
    return () => {
      root.classList.remove(...ALL_THEME_CLASSES, ...ALL_DENSITY_CLASSES);
    };
  }, [target, themeClass, densityClass]);

  const ctx = useMemo<ThemeContextValue>(
    () => ({
      themeId: resolvedThemeId,
      densityId: resolvedDensityId,
      setTheme,
      setDensity,
      toggle,
    }),
    [resolvedThemeId, resolvedDensityId, setTheme, setDensity, toggle]
  );

  // In "none" mode: supply context without touching the DOM.
  if (target === 'none') {
    return <ThemeContext.Provider value={ctx}>{children}</ThemeContext.Provider>;
  }

  if (target === 'documentElement') {
    // No wrapper needed for theming. Render a wrapper only if className/style
    // were passed (e.g. for layout in Storybook).
    if (className !== undefined || style !== undefined) {
      return (
        <ThemeContext.Provider value={ctx}>
          <As className={className} style={style}>
            {children}
          </As>
        </ThemeContext.Provider>
      );
    }
    return <ThemeContext.Provider value={ctx}>{children}</ThemeContext.Provider>;
  }

  // wrapper mode: apply the theme class to the wrapper element.
  return (
    <ThemeContext.Provider value={ctx}>
      <As className={cx(themeClass, densityClass, className)} style={style}>
        {children}
      </As>
    </ThemeContext.Provider>
  );
}
