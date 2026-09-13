/**
 * Theme registry — the canonical list of available themes.
 *
 * Lightweight metadata only: no ResolvedTheme objects, no palette generation,
 * no colorjs.io. Safe to import from renderer, Storybook, and CSS-in-JS files
 * without pulling in the full theme creation pipeline.
 */

export type ThemeManifestEntry = {
  id: string;
  label: string;
  polarity: 'light' | 'dark';
  selector: string;
};

export const THEME_MANIFEST: readonly ThemeManifestEntry[] = [
  { id: 'light', label: 'Light', polarity: 'light', selector: '.emlight' },
  { id: 'dark', label: 'Dark', polarity: 'dark', selector: '.emdark' },
  {
    id: 'solarized-light',
    label: 'Solarized Light',
    polarity: 'light',
    selector: '.emsolarized-light',
  },
  {
    id: 'solarized-dark',
    label: 'Solarized Dark',
    polarity: 'dark',
    selector: '.emsolarized-dark',
  },
] as const;

export type ThemeId = (typeof THEME_MANIFEST)[number]['id'];
