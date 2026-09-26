import { createStoredCadPreferences } from '@hardcore/ui/renderers/workspace';

/** The browser host keeps viewer preferences in localStorage, and hears other tabs change them. */
export function createWebCadPreferences() {
  const source = createStoredCadPreferences(localStorage);
  return {
    ...source,
    connect() {
      const sync = (event: StorageEvent) => source.storageChanged(event.key);
      window.addEventListener('storage', sync);
      return () => window.removeEventListener('storage', sync);
    },
  };
}
