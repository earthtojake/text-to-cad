import {
  THEME_MANIFEST,
  ThemeProvider as UiThemeProvider,
  type ThemeId,
} from '@emdash/ui/react/primitives';
import {
  createContext,
  useEffect,
  useLayoutEffect,
  useSyncExternalStore,
  type ReactNode,
} from 'react';
import type { Theme } from '@core/primitives/app-settings/api';
import {
  THEME_CLASS_DARK,
  THEME_CLASS_LIGHT,
  THEME_CLASSES,
  THEME_STORAGE_KEY,
} from './theme-classes';
import { getNextTheme } from './theme-toggle-model';

export type EffectiveTheme = (typeof THEME_CLASSES)[number];

function getSystemTheme(): EffectiveTheme {
  if (typeof window === 'undefined') return THEME_CLASS_LIGHT;
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? THEME_CLASS_DARK
    : THEME_CLASS_LIGHT;
}

/**
 * Map the app's effective theme class to the @emdash/ui theme id, via the
 * manifest selectors so a rename fails loudly instead of drifting.
 */
function uiThemeId(effective: EffectiveTheme): ThemeId {
  const entry = THEME_MANIFEST.find((e) => e.selector === `.${effective}`);
  if (!entry) throw new Error(`No @emdash/theme entry for selector ".${effective}"`);
  return entry.id as ThemeId;
}

function subscribeToSystemTheme(onChange: () => void) {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  mq.addEventListener('change', onChange);
  return () => mq.removeEventListener('change', onChange);
}

function applyTheme(effective: EffectiveTheme) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.classList.remove(...THEME_CLASSES);
  root.classList.add(effective);
}

export interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  effectiveTheme: EffectiveTheme;
}

export const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export interface ThemeProviderProps {
  readonly children: ReactNode;
  readonly theme: Theme;
  readonly isLoading?: boolean;
  readonly onThemeChange: (theme: Theme) => void;
  readonly onThemeApplied?: (effectiveTheme: EffectiveTheme) => void;
}

export function ThemeProvider({
  children,
  theme,
  isLoading = false,
  onThemeChange,
  onThemeApplied,
}: ThemeProviderProps) {
  const systemTheme = useSyncExternalStore(subscribeToSystemTheme, getSystemTheme);
  const effectiveTheme: EffectiveTheme = theme ?? systemTheme;

  useLayoutEffect(() => {
    if (isLoading) return;
    applyTheme(effectiveTheme);
  }, [effectiveTheme, isLoading]);

  useEffect(() => {
    if (isLoading) return;
    try {
      localStorage.setItem(THEME_STORAGE_KEY, JSON.stringify(theme));
    } catch {
      // Local storage is only a startup paint cache; persisted settings remain authoritative.
    }
  }, [theme, isLoading]);

  const setTheme = (newTheme: Theme) => {
    onThemeChange(newTheme);
  };

  const toggleTheme = () => {
    const next = getNextTheme(theme, effectiveTheme);
    setTheme(next);
  };

  useEffect(() => {
    if (!isLoading) onThemeApplied?.(effectiveTheme);
  }, [effectiveTheme, isLoading, onThemeApplied]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme, effectiveTheme }}>
      {/* Context-only @emdash/ui provider: the app's applyTheme above stays the
          sole DOM class writer; this makes @emdash/ui's useTheme() (needed by
          theme-aware components like markdown/shiki) work app-wide. */}
      <UiThemeProvider target="none" theme={uiThemeId(effectiveTheme)}>
        {children}
      </UiThemeProvider>
    </ThemeContext.Provider>
  );
}
