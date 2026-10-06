/** The appearance a person can choose, and what each resolves to against the OS. */
export type ColorSchemePreference = 'system' | 'light' | 'dark';
export type ColorSchemeMode = 'light' | 'dark';

export const COLOR_SCHEMES: { id: ColorSchemePreference; label: string }[] = [
  { id: 'system', label: 'System' }, { id: 'light', label: 'Light' }, { id: 'dark', label: 'Dark' },
];

export function resolveColorSchemeMode(preference: string | undefined, { prefersDark }: { prefersDark: boolean }): ColorSchemeMode {
  if (preference === 'light' || preference === 'dark') return preference;
  return prefersDark ? 'dark' : 'light';
}

/** The page's root in `mode`: the `dark` class the design tokens key on, and the browser's own controls. */
export function applyColorSchemeToDocument(mode: ColorSchemeMode, root: HTMLElement): void {
  root.classList.toggle('dark', mode === 'dark');
  root.style.colorScheme = mode;
}
