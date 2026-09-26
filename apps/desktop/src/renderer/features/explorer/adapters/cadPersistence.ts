import { createStoredCadPreferences } from "@hardcore/ui/renderers/workspace";
import type { CadPreferenceSource } from "@hardcore/ui/renderers/workspace";

let sharedPreferences: CadPreferenceSource | undefined;
/**
 * CAD viewer preferences are shared by every root in this desktop window. Storage events carry
 * updates from another Hardcore window; this store has the window's lifetime, not a root's.
 */
export function desktopCadPreferences(): CadPreferenceSource {
  if (!sharedPreferences) {
    const source = createStoredCadPreferences(localStorage);
    window.addEventListener("storage", event => source.storageChanged(event.key));
    sharedPreferences = source;
  }
  return sharedPreferences;
}
