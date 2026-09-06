import type { Theme } from '@core/primitives/app-settings/api';

export function getNextTheme(
  current: Theme,
  fallbackEffectiveTheme: NonNullable<Theme>
): NonNullable<Theme> {
  const effectiveTheme = current ?? fallbackEffectiveTheme;
  return effectiveTheme === 'emlight' ? 'emdark' : 'emlight';
}
